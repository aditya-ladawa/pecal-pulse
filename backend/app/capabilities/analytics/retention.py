"""Empirical retention (return) curves from observed silence episodes.

No validated churn labels exist, so churn is framed as time-to-return:
given an account went silent after repeated activity, how often did
similarly silent accounts return within H months? Episodes whose H-month
outcome is not fully observed before the history end are dropped
(censored-unknown) and never counted as non-returns.

Stdlib only, so API code can import these helpers without training
dependencies. All inputs use integer month indexes (see
analytics.features.month_index).
"""

from __future__ import annotations

from statistics import median

VERSION = "retention-v1"
HORIZON_MONTHS = 12
FORWARD_WINDOW_MONTHS = 3
# Tier cut-points on the forward return rate, set from the measured
# distribution (regular accounts fall from ~0.9 to ~0.45 as silence grows).
# They are communication buckets, not model parameters.
TIER_CUTS = (0.6, 0.4)
MIN_PRIOR_ACTIVE = 3
MIN_TENURE_MONTHS = 15
REGULAR_MIN_PRIOR_ACTIVE = 4
REGULAR_MAX_MEDIAN_GAP = 6


def _median_gap(active: list[int]) -> float | None:
    gaps = [b - a for a, b in zip(active, active[1:])]
    return float(median(gaps)) if gaps else None


def is_regular(prior_active: int, prior_median_gap: float | None) -> bool:
    """Regular accounts have repeated, reasonably frequent activity."""
    return (
        prior_active >= REGULAR_MIN_PRIOR_ACTIVE
        and prior_median_gap is not None
        and prior_median_gap <= REGULAR_MAX_MEDIAN_GAP
    )


def silence_episodes(
    active_months: list[int],
    end: int,
    horizon: int = HORIZON_MONTHS,
    min_prior_active: int = MIN_PRIOR_ACTIVE,
    min_tenure_months: int = MIN_TENURE_MONTHS,
) -> list[dict]:
    """Build fully-observed silence episodes from sorted active months.

    Each episode starts at an active month with enough prior history.
    Episodes still open at ``end`` with fewer than ``horizon`` elapsed
    months are dropped: their outcome is unknown, not a non-return.
    """
    episodes = []
    for i, last in enumerate(active_months):
        prior = active_months[:i]
        if len(prior) + 1 < min_prior_active:
            continue
        if last - active_months[0] + 1 < min_tenure_months:
            continue
        prior_gaps_median = _median_gap(prior + [last])
        regular = is_regular(len(prior) + 1, prior_gaps_median)
        nxt = active_months[i + 1] if i + 1 < len(active_months) else None
        if nxt is not None:
            episodes.append(
                {
                    "last_active": last,
                    "regular": regular,
                    "silence_months": nxt - last,
                    "returned": True,
                }
            )
        elif end - last >= horizon:
            episodes.append(
                {
                    "last_active": last,
                    "regular": regular,
                    "silence_months": horizon,
                    "returned": False,
                }
            )
        # Else: censored, outcome unknown — dropped.
    return episodes


def return_curve(
    episodes: list[dict], horizon: int = HORIZON_MONTHS
) -> dict[str, list[dict]]:
    """Cumulative return probability by elapsed silence month and stratum.

    For each silence month d, the rate is the fraction of stratum episodes
    that returned within d months. All episodes kept by silence_episodes
    have definitive outcomes, so every stratum episode is in the denominator.
    """
    curve: dict[str, list[dict]] = {}
    for stratum in ("regular", "irregular"):
        group = [e for e in episodes if ("regular" if e["regular"] else "irregular") == stratum]
        points = []
        for d in range(1, horizon + 1):
            returned = sum(1 for e in group if e["returned"] and e["silence_months"] <= d)
            points.append(
                {
                    "silence_months": d,
                    "episodes": len(group),
                    "returned": returned,
                    "return_rate": (returned / len(group)) if group else None,
                }
            )
        curve[stratum] = points
    return curve


def tier_for(
    recency_months: int, regular: bool, curve: dict[str, list[dict]]
) -> dict | None:
    """Map current silence to a measured retention tier.

    ``curve`` is a forward curve from forward_curve: each point gives the
    share of still-silent episodes that returned within the next
    FORWARD_WINDOW_MONTHS months. Tier cut-points (TIER_CUTS) are empirical
    communication buckets on that rate, disclosed in the artifact.
    Silence beyond the measured range uses the last point, flagged.
    """
    stratum = "regular" if regular else "irregular"
    points = curve.get(stratum) or []
    if not points:
        return None
    last = points[-1]["silent_months"]
    clamped = max(0, min(recency_months, last))
    point = points[clamped] if clamped <= last else points[-1]
    if point["return_rate"] is None:
        return None
    probability = float(point["return_rate"])
    high, mid = TIER_CUTS
    tier = "lower" if probability >= high else "moderate" if probability >= mid else "higher"
    return {
        "tier": tier,
        "return_probability": round(probability, 3),
        "silence_months": recency_months,
        "measured_through_months": clamped,
        "beyond_measured_horizon": recency_months > last,
        "forward_window_months": point["forward_window_months"],
        "regular_history": regular,
        "basis_episodes": point["at_risk"],
        "version": VERSION,
    }


def forward_curve(
    episodes: list[dict],
    horizon: int = HORIZON_MONTHS,
    window: int = FORWARD_WINDOW_MONTHS,
) -> dict[str, list[dict]]:
    """Forward return probability for still-silent episodes (hazard view).

    For each elapsed silence month d, among episodes still silent at d
    whose outcome over (d, d + window] is fully observed, the share that
    returned within those next ``window`` months. Returned episodes with
    silence s > d and non-returned episodes (span ``horizon``) are at
    risk; returned episodes with s <= d already left the silent set.
    """
    curve: dict[str, list[dict]] = {}
    for stratum in ("regular", "irregular"):
        group = [e for e in episodes if ("regular" if e["regular"] else "irregular") == stratum]
        points = []
        for d in range(0, horizon - window + 1):
            span = lambda e: e["silence_months"] if e["returned"] else horizon
            at_risk = [e for e in group if span(e) > d]
            returned = [e for e in at_risk if e["returned"] and e["silence_months"] <= d + window]
            points.append(
                {
                    "silent_months": d,
                    "forward_window_months": window,
                    "at_risk": len(at_risk),
                    "returned": len(returned),
                    "return_rate": (len(returned) / len(at_risk)) if at_risk else None,
                }
            )
        curve[stratum] = points
    return curve


def retention_for(
    active_months: list[int], end: int, curve: dict[str, list[dict]]
) -> dict | None:
    """Retention tier for a live account, or None without enough history."""
    if len(active_months) < MIN_PRIOR_ACTIVE:
        return None
    if active_months[-1] - active_months[0] + 1 < MIN_TENURE_MONTHS:
        return None
    recency = end - active_months[-1]
    if recency < 0:
        return None
    regular = is_regular(len(active_months), _median_gap(active_months))
    return tier_for(recency, regular, curve)
