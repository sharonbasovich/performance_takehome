"""Build the validation artifacts from the generated fixtures (CPU mock, not GPU).

    cd tasks/benchmark-design && python validation/build_validation.py

Writes, under ``validation/``:
  reports/public/<fixture>.report.json|.md   evaluate.py output per public fixture
  reports/heldout/<opaque>.report.json       evaluate.py output per held-out fixture
  discrimination.json / discrimination.md     fault family -> expected -> observed -> detected?
  controls.json                               false-positive accounting on clean/noisy controls
  heldout_results.json                        key vs evaluator verdict (key read only here)
  comparison_*.json                           --compare semantics between two runs
  timing.json / timing.md                     measured wall time of fixture generation,
                                              evaluation and the unittest suite on this host
Everything here is produced by running the committed code; nothing is typed in by hand.
"""

import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TASK = Path(__file__).resolve().parent.parent
SUITE = TASK / "suite"
sys.path.insert(0, str(SUITE))

import evaluate as ev_mod  # noqa: E402
from bench.plan import load_plan  # noqa: E402

VALIDATION = TASK / "validation"
PUBLIC = SUITE / "fixtures" / "public"
HELDOUT = SUITE / "fixtures" / "heldout"
PLAN = SUITE / "fixtures" / "workload.mock.json"
KEY = "chat_short_open|rate=4rps"


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def observed_signals(report: dict[str, Any], clean: dict[str, Any] | None) -> list[str]:
    """Machine-derived description of what the evaluator actually flagged."""
    signals: list[str] = []
    if report["status"] != "valid":
        why = report.get("reasons") or report.get("inconclusive_reasons") or []
        signals.append(f"status={report['status']}: " + "; ".join(why))
    totals = report.get("population", {}).get("totals", {})
    for cat in ("failed", "unfinished", "evidence_invalid"):
        if totals.get(cat):
            signals.append(f"{cat}={totals[cat]}")
    reasons: dict[str, int] = {}
    for cell in report.get("cells", {}).values():
        for k, n in cell["rejection_reasons"].items():
            reasons[k] = reasons.get(k, 0) + n
    if reasons:
        signals.append("gates=" + ",".join(f"{k}:{n}" for k, n in sorted(reasons.items())))
    cell = report.get("cells", {}).get(KEY)
    if cell and clean and KEY in clean.get("cells", {}):
        ref = clean["cells"][KEY]
        ttft = cell["ttft_s"]["p50"]["point"]
        ttft_ref = ref["ttft_s"]["p50"]["point"]
        if ttft is not None and ttft_ref is not None and ttft > ttft_ref * 1.5:
            signals.append(f"ttft_p50={ttft:.3f}s vs clean {ttft_ref:.3f}s")
        fi = cell["fluidity"]["strict"]["index_mean"]["point"]
        fi_ref = ref["fluidity"]["strict"]["index_mean"]["point"]
        if fi is not None and fi_ref is not None and fi < fi_ref - 0.05:
            signals.append(f"fluidity_strict_mean={fi:.3f} vs clean {fi_ref:.3f}")
        mdd = cell["decode"]["min_decode_deadline_s"]["p99"]
        mdd_ref = ref["decode"]["min_decode_deadline_s"]["p99"]
        if mdd is not None and mdd_ref is not None and mdd > mdd_ref * 2:
            signals.append(f"min_decode_deadline_p99={mdd:.4f}s vs clean {mdd_ref:.4f}s")
        if "multi_token_deltas" in cell["flags"]:
            n = cell["flags"]["multi_token_deltas"]
            signals.append(f"multi_token_deltas flag on {n} requests")
    launch = (report.get("startup", {}).get("launches") or [{}])[0]
    if clean and launch.get("readiness_lead_s") is not None:
        clean_launch = (clean.get("startup", {}).get("launches") or [{}])[0]
        ref_lead = clean_launch.get("readiness_lead_s") or 0.0
        if launch["readiness_lead_s"] > ref_lead + 0.1:
            signals.append(
                f"readiness_lead={launch['readiness_lead_s']:.2f}s vs clean {ref_lead:.2f}s"
            )
    return signals


def _evaluate_dir(plan: dict[str, Any], d: Path, timing: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    report = ev_mod.evaluate(plan, d, "native")[0]
    timing["evaluate_s"][d.name] = round(time.perf_counter() - t0, 3)
    return {
        "report_schema_version": ev_mod.REPORT_SCHEMA_VERSION,
        "plan_id": plan["plan_id"],
        "events_dir": str(d.relative_to(TASK)),
        **report,
    }


def discrimination_rows(
    reports: dict[str, dict[str, Any]], labels: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    clean = reports.get("clean")
    rows = []
    for name, report in reports.items():
        expected = labels[name]["expected"]
        signals = observed_signals(report, clean if name != "clean" else None)
        status_ok = report["status"] == expected["status"]
        detected = status_ok and (name in ("clean", "noisy") or bool(signals))
        rows.append(
            {
                "fixture": name,
                "family": labels[name]["family"],
                "expected_status": expected["status"],
                "observed_status": report["status"],
                "expected_signal": expected["signal"],
                "observed_signals": signals,
                "detected": detected,
            }
        )
    return rows


def control_rows(controls: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for name, rep in controls:
        totals = rep["population"]["totals"]
        rejected = totals["failed"] + totals["unfinished"] + totals["evidence_invalid"]
        aa_decision = (rep.get("aa_control") or {}).get("decision")
        fp = rep["status"] != "valid" or rejected or aa_decision in ("regression", "improvement")
        rows.append(
            {
                "fixture": name,
                "status": rep["status"],
                "rejections": rejected,
                "offered": totals["offered"],
                "aa_decision": aa_decision,
                "false_positive": bool(fp),
            }
        )
    return rows


def main() -> int:
    plan = load_plan(PLAN)
    host = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "note": "CPU mock host; injected mock timings scaled by fixtures/manifest.json "
        "time_scale. NOT GPU.",
    }
    manifest = json.loads((SUITE / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
    timing: dict[str, Any] = {
        "host": host,
        "time_scale": manifest["time_scale"],
        "evaluate_s": {},
        "generation_s_from_manifest": {
            name: info["wall_s_cpu_mock"]
            for name, info in manifest["public"].items()
            if "wall_s_cpu_mock" in info
        },
    }

    reports: dict[str, dict[str, Any]] = {}
    labels: dict[str, dict[str, Any]] = {}
    for d in sorted(PUBLIC.iterdir()):
        if not (d / "label.json").is_file():
            continue
        labels[d.name] = json.loads((d / "label.json").read_text(encoding="utf-8"))
        reports[d.name] = _evaluate_dir(plan, d, timing)
        _write(VALIDATION / "reports" / "public" / f"{d.name}.report.json", reports[d.name])
        md_path = VALIDATION / "reports" / "public" / f"{d.name}.report.md"
        md_path.write_text(ev_mod.summarize(reports[d.name]), encoding="utf-8")

    rows = discrimination_rows(reports, labels)
    _write(VALIDATION / "discrimination.json", rows)
    md = [
        "# Discrimination table (CPU mock fixtures)",
        "",
        "Generated by `validation/build_validation.py` from `evaluate.py` reports; "
        "nothing hand-edited.",
        "",
        "| fixture | family | expected status | observed status | expected signal "
        "| observed signals (machine-derived) | detected |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        md.append(
            f"| {r['fixture']} | {r['family']} | {r['expected_status']} | {r['observed_status']} | "
            f"{r['expected_signal']} | {'<br>'.join(r['observed_signals']) or '-'} | "
            f"{'yes' if r['detected'] else 'NO'} |"
        )

    heldout_key = json.loads((VALIDATION / "heldout_key.json").read_text(encoding="utf-8"))
    heldout_reports: dict[str, dict[str, Any]] = {}
    for d in sorted(HELDOUT.iterdir()):
        heldout_reports[d.name] = _evaluate_dir(plan, d, timing)
        _write(
            VALIDATION / "reports" / "heldout" / f"{d.name}.report.json", heldout_reports[d.name]
        )

    controls = [(n, reports[n]) for n in ("clean", "noisy")] + [
        (n, heldout_reports[n])
        for n in heldout_reports
        if heldout_key.get(n, {}).get("family") == "control"
    ]
    c_rows = control_rows(controls)
    fp_count = sum(r["false_positive"] for r in c_rows)
    fp_rate = fp_count / len(c_rows)
    _write(
        VALIDATION / "controls.json",
        {
            "controls": c_rows,
            "false_positive_rate": fp_rate,
            "definition": "a control counts as a false positive if its status is not valid, "
            "any request was rejected, or the within-run A/A decision is confident",
        },
    )
    md += [
        "",
        f"## Control false-positive rate: {fp_count}/{len(c_rows)} = {fp_rate:.2f}",
        "",
        "| control fixture | status | rejected/offered | A/A decision | false positive |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in c_rows:
        md.append(
            f"| {r['fixture']} | {r['status']} | {r['rejections']}/{r['offered']} | "
            f"{r['aa_decision']} | {'YES' if r['false_positive'] else 'no'} |"
        )

    held_rows = []
    for name, truth in heldout_key.items():
        rep = heldout_reports[name]
        totals = rep["population"]["totals"]
        held_rows.append(
            {
                "fixture": name,
                "profile": truth["profile"],
                "expected_status": truth["expected"]["status"],
                "observed_status": rep["status"],
                "match": rep["status"] == truth["expected"]["status"],
                "rejections": totals["failed"] + totals["unfinished"],
            }
        )
    _write(VALIDATION / "heldout_results.json", held_rows)
    md += [
        "",
        "## Held-out fixtures (opaque names; key only consulted here, after evaluation)",
        "",
        "| fixture | true profile | expected | observed | rejections | match |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in held_rows:
        md.append(
            f"| {r['fixture']} | {r['profile']} | {r['expected_status']} | "
            f"{r['observed_status']} | {r['rejections']} | {'yes' if r['match'] else 'NO'} |"
        )
    (VALIDATION / "discrimination.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    base = ev_mod.evaluate(plan, PUBLIC / "clean", "native")
    for other_name in ("noisy", "slow_decode", "late_first_token"):
        other = ev_mod.evaluate(plan, PUBLIC / other_name, "native")
        _write(
            VALIDATION / f"comparison_clean_vs_{other_name}.json",
            ev_mod.compare_runs(plan, base, other),
        )

    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=SUITE,
        capture_output=True,
        text=True,
        check=False,
    )
    timing["unittest_s"] = round(time.perf_counter() - t0, 2)
    timing["unittest_tail"] = proc.stderr.strip().splitlines()[-3:]
    timing["unittest_returncode"] = proc.returncode
    timing["fixture_generation_total_s"] = round(
        sum(timing["generation_s_from_manifest"].values()), 1
    )
    timing["evaluate_total_s"] = round(sum(timing["evaluate_s"].values()), 2)
    _write(VALIDATION / "timing.json", timing)
    gen = timing["generation_s_from_manifest"]
    last_line = timing["unittest_tail"][-1] if timing["unittest_tail"] else ""
    tmd = [
        "# Measured wall time — CPU mock host (NOT GPU)",
        "",
        f"Host: `{host['platform']}`, Python {host['python']}. "
        f"Mock delays scaled by time_scale={timing['time_scale']}.",
        "",
        f"- fixture generation (runner + cold-started mock, {len(gen)} public fixtures): "
        f"{timing['fixture_generation_total_s']} s total, per fixture: "
        + ", ".join(f"{k}={v}s" for k, v in gen.items()),
        f"- evaluate.py over {len(timing['evaluate_s'])} fixtures: "
        f"{timing['evaluate_total_s']} s total",
        f"- unittest suite: {timing['unittest_s']} s (exit {timing['unittest_returncode']}; "
        f"last line: `{last_line}`)",
        "",
        "These numbers measure the candidate tooling on a CPU; they say nothing about llm-d "
        "or MI355X.",
    ]
    (VALIDATION / "timing.md").write_text("\n".join(tmd) + "\n", encoding="utf-8")
    print("\n".join(md))
    ok = all(r["detected"] for r in rows) and all(r["match"] for r in held_rows)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
