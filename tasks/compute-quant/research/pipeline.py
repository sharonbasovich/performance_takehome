"""Orchestration: load → classify → normalize → curve → cost → valuation → outputs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .comparability import AS_OF_VALID, classify
from .crosscheck import (
    commitment_context,
    flexibility_premium,
    historical_variability,
    performance_cross_check,
    spot_context,
)
from .curve import CurveModel, build_curve_model
from .loader import LoadedInputs, load_inputs
from .normalize import (
    NormalizedQuote,
    apply_quantity_adjustment,
    estimate_quantity_factor,
    normalize_quote,
)
from .schema import Case, InputError
from .supply_cost import breakeven, sensitivity_grid
from .valuation import valuation_as_dict, value_reservation

OUTPUT_SCHEMA_VERSION = 1
CURVE_COLUMNS = (
    "tenor_months",
    "delivery_month",
    "delivery_start",
    "delivery_end",
    "hours",
    "unit",
    "status",
    "usd_per_gpu_hour_mid",
    "usd_per_gpu_hour_low",
    "usd_per_gpu_hour_high",
    "bid",
    "ask",
    "uncertainty_type",
    "evidence_ids",
    "scenario_base",
    "scenario_cheap_compute",
    "scenario_scarcity",
    "months_beyond_last_anchor",
    "notes",
)
PACKAGE_DIR = Path(__file__).resolve().parent


def load_config(path: Path | None) -> dict:
    """Load the model configuration JSON (default: ``research/config/default.json``)."""
    target = Path(path) if path else PACKAGE_DIR / "config" / "default.json"
    config = json.loads(target.read_text(encoding="utf-8"))
    if config.get("config_version") != 1:
        raise InputError(f"{target}: unsupported config_version {config.get('config_version')!r}")
    return config


def code_digest() -> str:
    """SHA-256 over the research package's source files (sorted by relative path)."""
    digest = hashlib.sha256()
    for path in sorted(PACKAGE_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json"} and "__pycache__" not in path.parts:
            digest.update(path.relative_to(PACKAGE_DIR).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def run_pipeline(
    case_path: Path,
    config: dict,
    *,
    exclude_quote_ids: tuple[str, ...] = (),
    as_of_override: str | None = None,
) -> dict[str, object]:
    """Run everything and return the JSON-ready results mapping."""
    loaded: LoadedInputs = load_inputs(case_path)
    case: Case = loaded.case
    if as_of_override:
        from dataclasses import replace

        from .months import parse_utc

        case = replace(case, as_of=parse_utc(as_of_override))
    quotes = [q for q in loaded.quotes if q.id not in set(exclude_quote_ids)]
    missing = sorted(set(exclude_quote_ids) - {q.id for q in loaded.quotes})
    if missing:
        raise InputError(f"--exclude-quote ids not present in the quotes file: {missing}")
    normalized: list[NormalizedQuote] = [
        normalize_quote(q, classify(q, case), case) for q in quotes
    ]
    factor, factor_note = estimate_quantity_factor(normalized, case)
    apply_quantity_adjustment(normalized, factor, case)
    model: CurveModel = build_curve_model(normalized, case, config)
    nodes = [model.node(t) for t in case.tenor_months]
    base_cost = breakeven(case.economics)
    valuation = value_reservation(model, case)
    sensitivities = _sensitivities(model, case, config["sensitivities"], valuation.identified)
    quote_table = []
    for item in normalized:
        q, c = item.quote, item.classification
        quote_table.append(
            {
                "id": q.id,
                "provider": q.provider,
                "kind": q.kind,
                "side": q.side,
                "observed_at": q.observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "valid_until": None
                if q.valid_until is None
                else q.valid_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "raw": {
                    "price": float(q.price),
                    "currency": q.currency,
                    "unit": q.unit,
                    "gpu_count": q.gpu_count,
                },
                "as_of_status": c.as_of_status,
                "tier": c.tier,
                "contract_class": c.contract_class,
                "delivery_months": [m.strftime("%Y-%m") for m in c.delivery_months],
                "tenor_months": list(c.tenor_months),
                "curve_eligible": item.usable and c.curve_eligible,
                "usd_per_gpu_hour": None
                if item.usd_per_gpu_hour is None
                else float(item.usd_per_gpu_hour),
                "single_gpu_equivalent_usd_per_gpu_hour": (
                    None
                    if item.single_gpu_equivalent is None
                    else float(item.single_gpu_equivalent)
                ),
                "excluded_reason": item.excluded_reason,
                "steps": [
                    {
                        "step": s.name,
                        "before": None if s.before is None else float(s.before),
                        "after": None if s.after is None else float(s.after),
                        "note": s.note,
                    }
                    for s in item.steps
                ],
                "reasons": list(c.reasons),
                "unknown_columns": dict(q.unknown_columns),
            }
        )
    exclusions = [
        {
            "id": row["id"],
            "reason": row["excluded_reason"]
            or "; ".join(x for x in row["reasons"] if not x.startswith("observed on/before")),
        }
        for row in quote_table
        if not row["curve_eligible"]
    ]
    results: dict[str, object] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "task": "compute-quant",
        "synthetic_inputs": case.synthetic,
        "disclaimer": (
            "All inputs are the repository's synthetic demo data; nothing here is a real market "
            "view, provider offer, or executable price."
        ),
        "as_of": case.as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reference_product": {
            "gpu": case.reference_product.gpu,
            "memory_gib": case.reference_product.memory_gib,
            "gpu_count": case.reference_product.gpu_count,
            "region": case.reference_product.region,
            "isolation": case.reference_product.isolation,
            "preemptible": case.reference_product.preemptible,
            "sla_pct": float(case.reference_product.sla_pct),
            "payment": case.reference_product.payment,
            "cancellation": case.reference_product.cancellation,
        },
        "inputs": {
            "files": [dict(f.__dict__, path=_display_path(f.path)) for f in loaded.files],
            "input_pack_digest": loaded.input_pack_digest,
            "input_pack_digest_definition": "sha256 over sorted "
            "'<role>:<sha256>\\n' lines (candidate-defined)",
            "quote_columns": list(loaded.quote_columns),
            "excluded_quote_ids_by_flag": list(exclude_quote_ids),
        },
        "quotes": quote_table,
        "exclusions": exclusions,
        "quantity_adjustment": {
            "factor": None if factor is None else float(factor),
            "note": factor_note,
        },
        "curve": {
            "unit": "USD per GPU-hour of reserved capacity, paid monthly in arrears",
            "tenor_definition": "delivery month starts this "
            "many calendar months after the as-of month start",
            "nodes": [n.as_dict() for n in nodes],
            "anchors": [
                {
                    "tenor_months": a.tenor,
                    "status": a.status,
                    "mid": round(a.mid, 6),
                    "low": round(a.low, 6),
                    "high": round(a.high, 6),
                    "bids": [o.quote_id for o in a.bids],
                    "asks": [o.quote_id for o in a.asks],
                    "uncertainty_type": a.uncertainty_type,
                    "notes": list(a.notes),
                }
                for a in model.anchors
            ],
            "reference_two_sided_spread": None
            if model.reference_spread is None
            else round(model.reference_spread, 6),
            "reversion": {
                "kappa_per_month": round(model.kappa, 6),
                "source": model.kappa_source,
                **model.kappa_detail,
            },
            "scenario_anchor_levels": {
                k: (None if v is None else round(v, 6))
                for k, v in model.scenario_anchor_levels.items()
            },
            "scenario_anchor_notes": dict(model.scenario_anchor_notes),
            "warnings": list(model.warnings),
            "monthly_base_mid": {
                str(t): (None if model.price(t)[0] is None else round(model.price(t)[0], 6))
                for t in range(0, max(case.tenor_months) + 1)
            },
        },
        "supply_cost": {
            "base": base_cost.as_dict(),
            "sensitivity_grid": sensitivities["supply_cost_breakeven_grid"],
        },
        "cross_checks": {
            "performance_translation": performance_cross_check(
                normalized, loaded.performance, case
            ),
            "usage_commitments": commitment_context(normalized, case),
            "spot": spot_context(normalized, case),
            "flexibility_premium": flexibility_premium(normalized, case),
            "historical_variability": historical_variability(normalized, case),
        },
        "reservation": {
            "id": case.reservation.id,
            "gpu_count": case.reservation.gpu_count,
            "delivery_start": case.reservation.delivery_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "delivery_end": case.reservation.delivery_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fixed_usd_per_gpu_hour": float(case.reservation.fixed_usd_per_gpu_hour),
            "payment": case.reservation.payment,
            "cancellation": case.reservation.cancellation,
            "sla_pct": float(case.reservation.sla_pct),
            "expected_buyer_used_fraction": (
                None
                if case.reservation.expected_buyer_used_fraction is None
                else float(case.reservation.expected_buyer_used_fraction)
            ),
        },
        "valuation": valuation_as_dict(valuation),
        "sensitivities": {
            k: v for k, v in sensitivities.items() if k != "supply_cost_breakeven_grid"
        },
        "config": config,
        "valid_quote_count": sum(1 for row in quote_table if row["as_of_status"] == AS_OF_VALID),
    }
    return _round_floats(results)


def _sensitivities(
    model: CurveModel, case: Case, sens: dict, identified: bool
) -> dict[str, object]:
    """Sensitivity tables; valuation-based ones are empty when the curve is unidentified."""
    out: dict[str, object] = {
        "supply_cost_breakeven_grid": sensitivity_grid(
            case.economics, sens["utilizations"], sens["financing_rates"]
        ),
        "reversion_multiplier": [
            {
                "multiplier": m,
                "kappa": model.kappa * m,
                "curve_mid_by_tenor": {
                    str(t): model.price(t, "base", model.kappa * m)[0] for t in case.tenor_months
                },
            }
            for m in sens["reversion_multipliers"]
        ],
        "discount_rate_bump": [],
        "default_probability": [],
        "horizon_vol_multiplier": [],
    }
    if not identified:
        return out
    base_rate = float(case.economics.buyer_discount_annual_rate)
    for row in out["reversion_multiplier"]:
        row["mark_adjusted_usd"] = value_reservation(model, case, kappa=row["kappa"]).mark_adjusted
    out["discount_rate_bump"] = [
        {
            "bump": b,
            "rate": base_rate + b,
            "mark_adjusted_usd": value_reservation(
                model, case, discount_rate=base_rate + b
            ).mark_adjusted,
        }
        for b in sens["discount_rate_bumps"]
    ]
    out["default_probability"] = [
        {
            "p_default": p,
            "mark_adjusted_usd": value_reservation(model, case, p_default=p).mark_adjusted,
        }
        for p in sens["default_probabilities"]
    ]
    out["horizon_vol_multiplier"] = [
        {
            "multiplier": m,
            "mark_interval_usd": {
                "low": value_reservation(model, case, vol_multiplier=m).mark_low,
                "high": value_reservation(model, case, vol_multiplier=m).mark_high,
            },
        }
        for m in sens["horizon_vol_multipliers"]
    ]
    return out


def _display_path(path: str) -> str:
    """Repository-relative POSIX path when the file is inside the repo, else as given."""
    repo_root = PACKAGE_DIR.parents[2]
    try:
        return Path(path).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _round_floats(obj):
    if isinstance(obj, float):
        return round(obj, 8)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v) for v in obj]
    return obj


def render_curve_csv(results: dict[str, object]) -> str:
    """Serialize the curve nodes as CSV text (LF line endings)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CURVE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for node in results["curve"]["nodes"]:
        writer.writerow(
            {
                "tenor_months": node["tenor_months"],
                "delivery_month": node["delivery_month"],
                "delivery_start": node["delivery_start"],
                "delivery_end": node["delivery_end"],
                "hours": node["hours"],
                "unit": "USD/GPU-hour reserved capacity, monthly arrears",
                "status": node["status"],
                "usd_per_gpu_hour_mid": _fmt(node["usd_per_gpu_hour_mid"]),
                "usd_per_gpu_hour_low": _fmt(node["usd_per_gpu_hour_low"]),
                "usd_per_gpu_hour_high": _fmt(node["usd_per_gpu_hour_high"]),
                "bid": _fmt(node["bid"]),
                "ask": _fmt(node["ask"]),
                "uncertainty_type": node["uncertainty_type"],
                "evidence_ids": ";".join(node["evidence_ids"]),
                "scenario_base": _fmt(node["scenarios"].get("base")),
                "scenario_cheap_compute": _fmt(node["scenarios"].get("cheap_compute")),
                "scenario_scarcity": _fmt(node["scenarios"].get("scarcity")),
                "months_beyond_last_anchor": ""
                if node["months_beyond_last_anchor"] is None
                else node["months_beyond_last_anchor"],
                "notes": " | ".join(node["notes"]),
            }
        )
    return buffer.getvalue()


def render_json(obj: dict[str, object]) -> str:
    return json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False, allow_nan=False) + "\n"


def build_manifest(
    results: dict[str, object], case_path: Path, config_path: Path | None, argv: list[str]
) -> dict[str, object]:
    """Machine-readable provenance for a run."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    when = datetime.fromtimestamp(int(epoch), tz=UTC) if epoch else datetime.now(tz=UTC)
    repo_root = PACKAGE_DIR.parents[2]
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "task": "compute-quant",
        "generated_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_source": "SOURCE_DATE_EPOCH" if epoch else "wall-clock",
        "code": {
            "package": "tasks/compute-quant/research",
            "version": __version__,
            "source_sha256": code_digest(),
            "git_commit": git_commit(repo_root),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "command": argv,
        "case": _display_path(str(case_path)),
        "config": (Path(config_path).as_posix() if config_path else "research/config/default.json"),
        "config_name": results["config"].get("name"),
        "inputs": results["inputs"],
        "as_of": results["as_of"],
        "parameters": results["config"],
        "network_access": "none",
        "outputs": ["curve.csv", "valuation.json", "run-manifest.json"],
    }


def write_outputs(
    results: dict[str, object], out_dir: Path, manifest: dict[str, object]
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "curve.csv": out_dir / "curve.csv",
        "valuation.json": out_dir / "valuation.json",
        "run-manifest.json": out_dir / "run-manifest.json",
    }
    paths["curve.csv"].write_text(render_curve_csv(results), encoding="utf-8", newline="\n")
    paths["valuation.json"].write_text(render_json(results), encoding="utf-8", newline="\n")
    paths["run-manifest.json"].write_text(render_json(manifest), encoding="utf-8", newline="\n")
    return paths


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)
