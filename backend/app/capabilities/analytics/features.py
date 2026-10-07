"""Features from Member 1's normalized, complete-month history contract."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import cos, log1p, pi, sin
from statistics import median, pstdev

FEATURE_NAMES = (
    "recent_3_log", "previous_3_log", "latest_log", "recency_months",
    "active_last_6", "mean_monthly_log", "tenure_log", "group_breadth_log",
    "season_sin", "season_cos", "active_fraction", "cadence_months",
    "gap_variability", "recency_to_cadence", "volume_momentum",
)


def month_index(value: str) -> int:
    year, month = map(int, value.split("-"))
    if not 1 <= month <= 12 or len(value) != 7:
        raise ValueError(f"Invalid ISO month: {value}")
    return year * 12 + month - 1


def iso_month(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def next_month_window(reference_date: str) -> tuple[str, str]:
    day = date.fromisoformat(reference_date)
    # A date in the next month minus one day must equal the reference date.
    from calendar import monthrange
    if day.day != monthrange(day.year, day.month)[1]:
        raise ValueError("Reference date must be a complete month end")
    start = month_index(day.strftime("%Y-%m")) + 1
    return iso_month(start), iso_month(start + 2)


def index_history(rows: list[dict], complete_through_month: str) -> dict[str, dict[int, dict]]:
    end = month_index(complete_through_month)
    output: dict[str, dict[int, dict]] = defaultdict(dict)
    for row in rows:
        customer = row["customer_id"]
        month = month_index(row["month"])
        if month > end:
            raise ValueError("History extends past complete_through_month")
        if month in output[customer]:
            raise ValueError(f"Duplicate customer/month: {customer} {row['month']}")
        for name in ("calibration_events", "distinct_instruments", "equipment_group_count", "lab_count"):
            value = row[name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"Invalid {name} for {customer} {row['month']}")
        output[customer][month] = row
    return dict(output)


def observed_months(history: dict[int, dict], cutoff: int) -> list[int]:
    return sorted(t for t, row in history.items() if t <= cutoff and row["calibration_events"] > 0)


def support(history: dict[int, dict], cutoff: int) -> dict:
    active = observed_months(history, cutoff)
    months = cutoff - active[0] + 1 if active else 0
    eligible = len(active) >= 2 and months >= 12 and active[-1] >= cutoff - 11
    reason = None if eligible else "Need two active months, twelve months of tenure, and activity within the last 12 months"
    return {"status": "supported" if eligible else "insufficient_history", "reason": reason,
            "history_months": months, "active_months": len(active)}


def feature_row(history: dict[int, dict], cutoff: int) -> tuple[list[float], dict]:
    active = observed_months(history, cutoff)
    if not active:
        raise ValueError("No observed calibration before cutoff")
    first = active[0]
    counts = [history.get(t, {}).get("calibration_events", 0) for t in range(first, cutoff + 1)]
    def volume(start: int, end: int) -> int:
        return sum(history.get(t, {}).get("calibration_events", 0) for t in range(start, end + 1))
    recent = volume(cutoff - 2, cutoff)
    previous = volume(cutoff - 5, cutoff - 3)
    gaps = [b - a for a, b in zip(active, active[1:])]
    cadence = float(median(gaps)) if gaps else None
    recency = cutoff - active[-1]
    tenure = cutoff - first + 1
    breadth = max((history.get(t, {}).get("equipment_group_count", 0)
                   for t in range(cutoff - 5, cutoff + 1)), default=0)
    vector = [log1p(recent), log1p(previous), log1p(counts[-1]), float(recency),
              float(sum(c > 0 for c in counts[-6:])), log1p(sum(counts) / tenure),
              log1p(tenure), log1p(breadth), sin(2 * pi * (cutoff % 12) / 12),
              cos(2 * pi * (cutoff % 12) / 12), len(active) / tenure,
              cadence or 0.0, pstdev(gaps) if len(gaps) > 1 else 0.0,
              recency / cadence if cadence else 0.0, log1p(recent) - log1p(previous)]
    return vector, {"recency_months": recency, "cadence_months": cadence,
                    "recent_volume": recent, "active_months": len(active), "tenure_months": tenure}


def volume_baselines(history: dict[int, dict], cutoff: int) -> dict[str, float]:
    def total(start: int, end: int) -> int:
        return sum(history.get(t, {}).get("calibration_events", 0) for t in range(start, end + 1))
    return {"previous_3_months": float(total(cutoff - 2, cutoff)),
            "previous_12_months_divided_by_4": total(cutoff - 11, cutoff) / 4,
            "same_3_months_last_year": float(total(cutoff - 11, cutoff - 9))}


def inactivity_evidence(history: dict[int, dict], cutoff: int) -> dict:
    active = observed_months(history, cutoff)
    months = cutoff - active[0] + 1 if active else 0
    base_support = {"history_months": months, "active_months": len(active)}
    if len(active) < 2 or months < 15:
        return {"flagged": False, "recency_to_cadence": None, "recent_volume": 0 if not active else
                sum(history.get(t, {}).get("calibration_events", 0) for t in range(cutoff - 2, cutoff + 1)),
                "baseline_volume": None, "deficit_fraction": None, "rule_version": "inactivity-v1",
                "reasons": [], "support": {**base_support, "status": "insufficient_history",
                "reason": "Need repeated activity and 15 months of observed tenure"}}
    recent = sum(history.get(t, {}).get("calibration_events", 0) for t in range(cutoff - 2, cutoff + 1))
    prior = sum(history.get(t, {}).get("calibration_events", 0) for t in range(cutoff - 14, cutoff - 2)) / 4
    cadence = float(median(b - a for a, b in zip(active, active[1:])))
    ratio = (cutoff - active[-1]) / cadence
    deficit = max(0.0, (prior - recent) / prior) if prior > 0 else None
    reasons = []
    if ratio > 1.5 and cutoff - active[-1] >= 2:
        reasons.append("Recency exceeds 1.5 times observed median cadence")
    if prior >= 5 and deficit is not None and deficit >= 0.5:
        reasons.append("Recent three-month volume at least 50% below prior-year quarterly average")
    return {"flagged": bool(reasons), "recency_to_cadence": ratio,
            "recent_volume": recent, "baseline_volume": prior, "deficit_fraction": deficit,
            "rule_version": "inactivity-v1", "reasons": reasons,
            "support": {**base_support, "status": "supported", "reason": None}}
