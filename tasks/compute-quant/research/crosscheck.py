"""Context and cross-checks that are *not* curve inputs.

* different-hardware quotes translated through the synthetic performance ratio, with the
  measurement uncertainty propagated (weak cross-check only; memory/software differ);
* usage commitments (a discount on current usage, not a forward);
* spot/preemptible prices (0% SLA: a different product);
* the flexibility premium between cancellable and reserved current-month capacity;
* expired same-provider quotes as the only historical hint for price variability.
"""

from __future__ import annotations

import math
from decimal import Decimal

from .comparability import (
    AS_OF_EXPIRED,
    AS_OF_VALID,
    CLASS_COMMITMENT,
    CLASS_FLEXIBLE,
    CLASS_RESERVED,
    CLASS_SPOT,
    TIER_COMPARABLE,
)
from .normalize import NormalizedQuote
from .schema import Case, PerformanceRow


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _valid_comparable(items: list[NormalizedQuote]) -> list[NormalizedQuote]:
    return [
        item
        for item in items
        if item.usable
        and item.classification.as_of_status == AS_OF_VALID
        and item.classification.tier == TIER_COMPARABLE
    ]


def performance_cross_check(
    items: list[NormalizedQuote], performance: tuple[PerformanceRow, ...], case: Case
) -> list[dict[str, object]]:
    """Translate valid different-hardware quotes into reference-GPU equivalents."""
    ref_rows = [row for row in performance if row.gpu == case.reference_product.gpu]
    out: list[dict[str, object]] = []
    for item in items:
        c, q = item.classification, item.quote
        if not item.usable or c.as_of_status != AS_OF_VALID or q.gpu == case.reference_product.gpu:
            continue
        other_rows = [row for row in performance if row.gpu == q.gpu]
        entry: dict[str, object] = {
            "quote_id": q.id,
            "gpu": q.gpu,
            "contract_class": c.contract_class,
            "normalized_usd_per_gpu_hour": _f(item.single_gpu_equivalent),
            "status": "cross-check-only",
        }
        if not ref_rows or not other_rows:
            entry["note"] = (
                "no matching performance measurement for both GPUs; no translation possible"
            )
            entry["equivalent_usd_per_reference_gpu_hour"] = None
            out.append(entry)
            continue
        ref, other = ref_rows[0], other_rows[0]
        if ref.workload != other.workload:
            entry["note"] = "performance rows measure different workloads; not translatable"
            entry["equivalent_usd_per_reference_gpu_hour"] = None
            out.append(entry)
            continue
        ratio = float(ref.output_tokens_per_s) / float(other.output_tokens_per_s)
        rel_unc = math.sqrt(
            float(ref.relative_uncertainty) ** 2 + float(other.relative_uncertainty) ** 2
        )
        price = float(item.single_gpu_equivalent or 0)
        comparable_same_class = [
            float(peer.single_gpu_equivalent or 0)
            for peer in _valid_comparable(items)
            if peer.classification.contract_class == c.contract_class and peer.quote.side == q.side
        ]
        entry.update(
            {
                "performance_ids": [ref.id, other.id],
                "workload": ref.workload,
                "throughput_ratio_reference_over_quote_gpu": ratio,
                "ratio_relative_uncertainty": rel_unc,
                "equivalent_usd_per_reference_gpu_hour": price * ratio,
                "equivalent_low": price * ratio * (1 - rel_unc),
                "equivalent_high": price * ratio * (1 + rel_unc),
                "comparable_same_class_prices": sorted(comparable_same_class),
                "note": (
                    "throughput parity on one synthetic dense-decode workload; ignores memory "
                    f"({q.memory_gib} vs {case.reference_product.memory_gib} "
                    "GiB), software and demand mix"
                ),
            }
        )
        out.append(entry)
    return out


def commitment_context(items: list[NormalizedQuote], case: Case) -> list[dict[str, object]]:
    """Usage commitments on the same hardware: discount on current usage, never a forward."""
    minimum = case.quote_common_terms.get("usage_commitment_minimum_monthly_gpu_hours")
    out = []
    for item in _valid_comparable(items):
        if item.classification.contract_class != CLASS_COMMITMENT:
            continue
        q = item.quote
        out.append(
            {
                "quote_id": q.id,
                "normalized_usd_per_gpu_hour": _f(item.single_gpu_equivalent),
                "commitment_months": q.commitment_months,
                "capacity_guaranteed": q.capacity_guaranteed,
                "delivery_window": None,
                "minimum_monthly_gpu_hours_per_common_terms": minimum,
                "treatment": (
                    "NOT a forward: no delivery window, no guaranteed capacity, postpaid spend "
                    "commitment; shown as the provider's "
                    "willingness to discount predictable current "
                    "usage, and as a soft long-run cross-check only"
                ),
            }
        )
    return out


def spot_context(items: list[NormalizedQuote], case: Case) -> list[dict[str, object]]:
    """Preemptible/spot quotes for the same hardware: a different (0% SLA) product."""
    flexible_asks = [
        float(peer.single_gpu_equivalent or 0)
        for peer in _valid_comparable(items)
        if peer.classification.contract_class == CLASS_FLEXIBLE and peer.quote.side == "ask"
    ]
    out = []
    for item in items:
        c = item.classification
        if not item.usable or c.as_of_status != AS_OF_VALID or c.contract_class != CLASS_SPOT:
            continue
        if item.quote.gpu != case.reference_product.gpu:
            continue
        price = float(item.single_gpu_equivalent or 0)
        out.append(
            {
                "quote_id": item.quote.id,
                "normalized_usd_per_gpu_hour": price,
                "sla_pct": _f(item.quote.sla_pct),
                "discount_vs_cheapest_flexible_on_demand_ask": (
                    None if not flexible_asks else 1 - price / min(flexible_asks)
                ),
                "treatment": "context only: preemptible with "
                "no SLA is not comparable to reserved capacity",
            }
        )
    return out


def flexibility_premium(items: list[NormalizedQuote], case: Case) -> dict[str, object] | None:
    """Cancellable vs reserved current-month asks at the same gpu_count (payment-normalized)."""
    base = month_start_tenor_zero(items, case)
    if base is None:
        return None
    reserved, flexible = base
    return {
        "reserved_quote_id": reserved.quote.id,
        "flexible_quote_id": flexible.quote.id,
        "reserved_usd_per_gpu_hour": _f(reserved.usd_per_gpu_hour),
        "flexible_usd_per_gpu_hour": _f(flexible.usd_per_gpu_hour),
        "flexible_over_reserved": float(flexible.usd_per_gpu_hour)
        / float(reserved.usd_per_gpu_hour),
        "note": (
            "price of cancel-anytime hourly access relative to a non-cancellable reserved month at "
            "the same quantity; the embedded cancellation option is why flexible asks bound "
            "reserved prices from above rather than equal them"
        ),
    }


def month_start_tenor_zero(
    items: list[NormalizedQuote], case: Case
) -> tuple[NormalizedQuote, NormalizedQuote] | None:
    for reserved in _valid_comparable(items):
        if (
            reserved.classification.contract_class != CLASS_RESERVED
            or 0 not in reserved.classification.tenor_months
        ):
            continue
        for flexible in _valid_comparable(items):
            if (
                flexible.classification.contract_class == CLASS_FLEXIBLE
                and flexible.quote.side == reserved.quote.side == "ask"
                and flexible.quote.gpu_count == reserved.quote.gpu_count
                and flexible.quote.unit != "node_month"
            ):
                return reserved, flexible
    return None


def historical_variability(items: list[NormalizedQuote], case: Case) -> list[dict[str, object]]:
    """Expired quotes paired with the current quote of the same provider/kind/gpu_count."""
    out = []
    for old in items:
        c = old.classification
        if not old.usable or c.as_of_status != AS_OF_EXPIRED or c.tier != TIER_COMPARABLE:
            continue
        for new in _valid_comparable(items):
            if (
                new.quote.provider == old.quote.provider
                and new.quote.kind == old.quote.kind
                and new.quote.side == old.quote.side
                and new.quote.gpu_count == old.quote.gpu_count
                and new.quote.unit == old.quote.unit
            ):
                months = (new.quote.observed_at - old.quote.observed_at).total_seconds() / (
                    30.4375 * 86400
                )
                old_p, new_p = float(old.usd_per_gpu_hour), float(new.usd_per_gpu_hour)
                log_move = math.log(new_p / old_p)
                out.append(
                    {
                        "expired_quote_id": old.quote.id,
                        "current_quote_id": new.quote.id,
                        "months_apart": months,
                        "expired_usd_per_gpu_hour": old_p,
                        "current_usd_per_gpu_hour": new_p,
                        "log_move": log_move,
                        "implied_vol_per_sqrt_month": abs(log_move) / math.sqrt(months)
                        if months > 0
                        else None,
                        "treatment": (
                            "expired price is never a current level; "
                            "the pair only informs the declared "
                            "horizon-widening parameter, and one pair "
                            "cannot estimate volatility reliably"
                        ),
                    }
                )
    return out
