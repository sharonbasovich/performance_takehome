"""Noise-aware keep/revert decision rule.

Each metric is compared as a speedup ratio of medians (baseline vs candidate)
with a seeded bootstrap confidence interval. A difference counts only when the
interval excludes 1.0 *and* the point estimate clears a minimum effect size;
otherwise the metric is ``no_change``. Correctness failures override everything.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

METRIC_DIRECTIONS: dict[str, bool] = {
    # metric -> lower_is_better
    "ttft_s": True,
    "ftgr_tok_s": False,
    "startup_s": True,
}
PRIMARY_METRICS: tuple[str, ...] = ("ttft_s", "ftgr_tok_s")
SECONDARY_METRICS: tuple[str, ...] = ("startup_s",)


@dataclass(frozen=True)
class MetricComparison:
    """Bootstrap comparison of one metric. ``speedup`` > 1 means the candidate is better."""

    metric: str
    baseline_n: int
    candidate_n: int
    baseline_median: float | None
    candidate_median: float | None
    speedup: float | None
    ci_low: float | None
    ci_high: float | None
    verdict: str  # improved | regressed | no_change | insufficient
    detail: str = ""


@dataclass(frozen=True)
class Decision:
    """Final verdict for one attempt."""

    outcome: str  # improved | regressed | no_change | gate_failed
    kept: bool
    reason: str
    comparisons: tuple[MetricComparison, ...] = field(default_factory=tuple)

    def comparison(self, metric: str) -> MetricComparison | None:
        """Look up the comparison for ``metric``."""
        for comp in self.comparisons:
            if comp.metric == metric:
                return comp
        return None


def _finite(values: Sequence[float]) -> list[float]:
    return [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]


def _speedup(base_median: float, cand_median: float, lower_is_better: bool) -> float | None:
    if base_median <= 0 or cand_median <= 0:
        return None
    return base_median / cand_median if lower_is_better else cand_median / base_median


Samples = Mapping[str, Sequence[float]] | Sequence[float]


def _groups(values: Samples) -> dict[str, list[float]]:
    """Normalise samples to ``group -> finite values`` (a flat list is one group)."""
    if isinstance(values, Mapping):
        return {str(k): _finite(v) for k, v in values.items()}
    return {"all": _finite(values)}


def _geo_mean(values: Sequence[float]) -> float:
    return math.exp(sum(math.log(v) for v in values) / len(values))


def bootstrap_speedup(
    baseline: Samples,
    candidate: Samples,
    *,
    lower_is_better: bool,
    iterations: int = 2000,
    confidence: float = 0.90,
    seed: int = 0,
) -> tuple[float | None, float | None, float | None]:
    """Return ``(speedup, ci_low, ci_high)`` from a seeded, stratified percentile bootstrap.

    Samples are grouped (by benchmark prompt); only groups present on both sides
    are compared. Per group the speedup is the ratio of medians; the reported
    speedup is the geometric mean of the per-group ratios, so heterogeneous
    prompts (short vs long prefill) do not inflate the uncertainty the way a
    pooled median would. Each bootstrap iteration resamples within every group.
    """
    base_groups = _groups(baseline)
    cand_groups = _groups(candidate)
    shared = [g for g in base_groups if g in cand_groups and base_groups[g] and cand_groups[g]]
    if not shared:
        return None, None, None

    def aggregate(pick: Callable[[list[float]], list[float]]) -> float | None:
        ratios: list[float] = []
        for g in shared:
            b = statistics.median(pick(base_groups[g]))
            c = statistics.median(pick(cand_groups[g]))
            r = _speedup(b, c, lower_is_better)
            if r is None:
                return None
            ratios.append(r)
        return _geo_mean(ratios)

    point = aggregate(lambda xs: xs)
    if point is None:
        return None, None, None
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(iterations):
        value = aggregate(lambda xs: rng.choices(xs, k=len(xs)))
        if value is not None:
            draws.append(value)
    if not draws:
        return point, None, None
    draws.sort()
    alpha = (1.0 - confidence) / 2.0
    lo = draws[max(0, min(len(draws) - 1, int(math.floor(alpha * (len(draws) - 1)))))]
    hi = draws[max(0, min(len(draws) - 1, int(math.ceil((1 - alpha) * (len(draws) - 1)))))]
    return point, lo, hi


def compare_metric(
    metric: str,
    baseline: Samples,
    candidate: Samples,
    *,
    min_effect: float,
    min_samples: int,
    iterations: int = 2000,
    confidence: float = 0.90,
    seed: int = 0,
) -> MetricComparison:
    """Classify one metric as improved / regressed / no_change / insufficient."""
    lower_is_better = METRIC_DIRECTIONS[metric]
    base = [v for vs in _groups(baseline).values() for v in vs]
    cand = [v for vs in _groups(candidate).values() for v in vs]
    if len(base) < min_samples or len(cand) < min_samples:
        return MetricComparison(
            metric,
            len(base),
            len(cand),
            statistics.median(base) if base else None,
            statistics.median(cand) if cand else None,
            None,
            None,
            None,
            "insufficient",
            f"need >= {min_samples} finite samples per side",
        )
    speedup, lo, hi = bootstrap_speedup(
        baseline,
        candidate,
        lower_is_better=lower_is_better,
        iterations=iterations,
        confidence=confidence,
        seed=seed,
    )
    bm, cm = statistics.median(base), statistics.median(cand)
    if speedup is None or lo is None or hi is None:
        return MetricComparison(
            metric,
            len(base),
            len(cand),
            bm,
            cm,
            speedup,
            lo,
            hi,
            "insufficient",
            "non-positive medians or no shared sample groups",
        )
    if lo > 1.0 and speedup >= 1.0 + min_effect:
        verdict, detail = (
            "improved",
            f"CI [{lo:.4f}, {hi:.4f}] excludes 1 and effect {speedup - 1:+.2%} >= {min_effect:.0%}",
        )
    elif hi < 1.0 and speedup <= 1.0 - min_effect:
        verdict, detail = (
            "regressed",
            f"CI [{lo:.4f}, {hi:.4f}] excludes 1 and effect {speedup - 1:+.2%} "
            f"<= -{min_effect:.0%}",
        )
    else:
        verdict, detail = (
            "no_change",
            f"CI [{lo:.4f}, {hi:.4f}] includes 1 or effect {speedup - 1:+.2%} "
            f"below {min_effect:.0%}",
        )
    return MetricComparison(metric, len(base), len(cand), bm, cm, speedup, lo, hi, verdict, detail)


def startup_hard_gate(baseline: Samples, candidate: Samples, limit: float) -> str | None:
    """Reason string when the candidate's startup median exceeds ``limit`` x baseline, else None.

    Works with a single sample per side. A candidate without any finite positive startup
    sample fails the gate (the baseline side always has one when a comparison is possible).
    """
    base = [v for vs in _groups(baseline).values() for v in vs if math.isfinite(v) and v > 0]
    cand = [v for vs in _groups(candidate).values() for v in vs if math.isfinite(v) and v > 0]
    if limit <= 0 or not base:
        return None
    if not cand:
        return "startup hard gate: candidate produced no finite startup sample"
    ratio = statistics.median(cand) / statistics.median(base)
    if ratio > limit:
        return (
            f"startup hard gate: candidate startup {statistics.median(cand):.3f}s is "
            f"{ratio:.2f}x the last-good {statistics.median(base):.3f}s (limit {limit:.2f}x)"
        )
    return None


def decide(
    baseline: Mapping[str, Samples],
    candidate: Mapping[str, Samples],
    *,
    gates_passed: bool,
    gate_summary: str = "",
    min_effect: float = 0.03,
    min_samples: int = 3,
    iterations: int = 2000,
    confidence: float = 0.90,
    seed: int = 0,
    startup_regression_limit: float = 1.5,
) -> Decision:
    """Apply the keep/revert rule.

    * any correctness gate failure -> ``gate_failed``, never kept;
    * startup hard gate: with only one cold start per side (the default
      measurement), a candidate whose startup median is more than
      ``startup_regression_limit`` x the baseline median is ``regressed``
      regardless of the primary metrics; with >= ``min_samples`` startups per
      side the bootstrap comparison applies as well;
    * any primary metric significantly worse -> ``regressed``;
    * otherwise >= 1 primary metric significantly better -> ``improved`` (kept),
      unless the startup bootstrap says it regressed significantly, which
      downgrades to ``regressed``;
    * otherwise ``no_change`` (not kept: the last-good image is already as good).
    """
    comparisons = tuple(
        compare_metric(
            metric,
            baseline.get(metric, ()),
            candidate.get(metric, ()),
            min_effect=min_effect,
            min_samples=min_samples,
            iterations=iterations,
            confidence=confidence,
            seed=seed,
        )
        for metric in (*PRIMARY_METRICS, *SECONDARY_METRICS)
    )
    if not gates_passed:
        return Decision(
            "gate_failed", False, gate_summary or "correctness gate failed", comparisons
        )
    by_metric = {c.metric: c for c in comparisons}
    primary = [by_metric[m] for m in PRIMARY_METRICS]
    secondary = [by_metric[m] for m in SECONDARY_METRICS]
    startup = startup_hard_gate(
        baseline.get("startup_s", ()), candidate.get("startup_s", ()), startup_regression_limit
    )
    if startup is not None:
        return Decision("regressed", False, startup, comparisons)
    if any(c.verdict == "regressed" for c in primary):
        bad = ", ".join(f"{c.metric} x{c.speedup:.3f}" for c in primary if c.verdict == "regressed")
        return Decision("regressed", False, f"primary metric regressed: {bad}", comparisons)
    if all(c.verdict == "insufficient" for c in primary):
        return Decision(
            "no_change", False, "insufficient samples for every primary metric", comparisons
        )
    if any(c.verdict == "improved" for c in primary):
        if any(c.verdict == "regressed" for c in secondary):
            bad = ", ".join(
                f"{c.metric} x{c.speedup:.3f}" for c in secondary if c.verdict == "regressed"
            )
            return Decision(
                "regressed", False, f"primary improved but secondary regressed: {bad}", comparisons
            )
        good = ", ".join(f"{c.metric} x{c.speedup:.3f}" for c in primary if c.verdict == "improved")
        return Decision("improved", True, f"significant improvement: {good}", comparisons)
    return Decision("no_change", False, "no primary metric moved significantly", comparisons)
