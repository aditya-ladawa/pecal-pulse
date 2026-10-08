"""Intermittent-demand volume challengers for the 3-month horizon.

Per-account calibration demand is lumpy and sparse, the textbook case where
plain averages underperform. These pure functions implement the classical
baselines plus a shrinkage estimator; offline evaluation (same
train/calibration/validation/test windows as the analytics pipeline)
decides whether any of them beats the selected method. No fitting state is
kept: every forecast is a closed-form function of history up to ``cutoff``.
"""

from __future__ import annotations

CROSTON_ALPHA = 0.1
TSB_ALPHA = 0.1
TSB_BETA = 0.1
POOLED_PRIOR_STRENGTH = 4.0


def _monthly_series(month_events: dict[int, int], cutoff: int, months: int) -> list[int]:
    return [month_events.get(t, 0) for t in range(cutoff - months + 1, cutoff + 1)]


def croston_3m(month_events: dict[int, int], cutoff: int, alpha: float = CROSTON_ALPHA) -> float:
    """Croston (1972): separate exponential smoothing of nonzero demand sizes
    and inter-arrival intervals; 3-month total is 3 × size/interval."""
    series = _monthly_series(month_events, cutoff, cutoff - min(month_events) + 1) if month_events else []
    size = interval = None
    since = 0
    for demand in series:
        since += 1
        if demand > 0:
            size = float(demand) if size is None else alpha * demand + (1 - alpha) * size
            interval = float(since) if interval is None else alpha * since + (1 - alpha) * interval
            since = 0
    if size is None or not interval:
        return 0.0
    return max(0.0, 3.0 * size / interval)


def tsb_3m(
    month_events: dict[int, int],
    cutoff: int,
    alpha: float = TSB_ALPHA,
    beta: float = TSB_BETA,
) -> float:
    """Teunter-Syntetos-Babai: Croston with probability (not interval)
    updating, which handles highly intermittent series better."""
    series = _monthly_series(month_events, cutoff, cutoff - min(month_events) + 1) if month_events else []
    size = prob = None
    for demand in series:
        if demand > 0:
            size = float(demand) if size is None else alpha * demand + (1 - alpha) * size
            prob = 1.0 if prob is None else beta * 1.0 + (1 - beta) * prob
        else:
            if prob is not None:
                prob = beta * 0.0 + (1 - beta) * prob
    if size is None or prob is None:
        return 0.0
    return max(0.0, 3.0 * size * prob)


def pooled_12m(
    own_12m_total: float,
    industry_12m_mean: float | None,
    active_months: int,
    prior_strength: float = POOLED_PRIOR_STRENGTH,
) -> float:
    """Shrink sparse accounts toward their industry mean (partial pooling).

    weight = active / (active + prior_strength): accounts with long own
    history keep their own average; thin histories borrow industry strength.
    Returns a 3-month total."""
    own = own_12m_total / 4.0
    if industry_12m_mean is None:
        return max(0.0, own)
    weight = active_months / (active_months + prior_strength)
    return max(0.0, weight * own + (1 - weight) * industry_12m_mean / 4.0)


def industry_12m_means(
    histories: dict[str, dict[int, int]],
    industries: dict[str, str],
    cutoffs: list[int],
) -> dict[tuple[str, int], float | None]:
    """Mean 12-month calibration total per (industry, cutoff)."""
    by_industry: dict[str, list[str]] = {}
    for customer_id, industry in industries.items():
        if customer_id in histories:
            by_industry.setdefault(industry, []).append(customer_id)
    means: dict[tuple[str, int], float | None] = {}
    for cutoff in cutoffs:
        for industry in set(industries.values()):
            members = by_industry.get(industry, [])
            totals = [
                sum(histories[c].get(t, 0) for t in range(cutoff - 11, cutoff + 1))
                for c in members
            ]
            means[(industry, cutoff)] = sum(totals) / len(totals) if totals else None
    return means
