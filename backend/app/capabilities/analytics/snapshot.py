"""Adapt Member 1 JSON or typed loader results to analytics input."""

from pydantic import BaseModel

from ...contracts import sales_v2 as v2
from .features import iso_month, month_index


def _json_value(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def normalize_snapshot(snapshot: dict) -> dict:
    """Use the canonical `manifest`, `profiles`, `history`, `month_grid` seam.

    Missing covered months stay missing. They must never be interpreted as
    zero calibration counts by predictive features or sector correlation.
    """
    raw = _json_value(snapshot)
    if "monthly_history" in raw:
        raise ValueError("Use Member 1's canonical history section, not monthly_history")
    manifest = v2.SnapshotManifest.model_validate(raw["manifest"])
    raw["manifest"] = manifest.model_dump()
    for section, model in (("profiles", v2.CustomerProfile),
                           ("history", v2.MonthlyHistoryRow),
                           ("portfolio", v2.PortfolioRow)):
        raw[section] = [model.model_validate(row).model_dump() for row in raw.get(section, [])]
    start = month_index(manifest.history_start)
    end = month_index(manifest.complete_through_month)
    if start > end:
        raise ValueError("History start follows complete-through month")
    grid = raw.get("month_grid", [])
    if len(grid) != len(set(grid)) or grid != sorted(grid):
        raise ValueError("month_grid must be unique and ordered")
    if any(not start <= month_index(month) <= end for month in grid):
        raise ValueError("month_grid extends outside the manifest window")
    raw["month_grid"] = grid
    if any(row["month"] not in grid for row in raw["history"]):
        raise ValueError("History row outside the covered month_grid")
    # Full normalized exports zero-fill only after the first observed row.
    # Sparse demo fixtures are accepted, with analytics explicitly unavailable.
    if grid == [iso_month(month) for month in range(start, end + 1)]:
        by_customer = {}
        for row in raw["history"]:
            by_customer.setdefault(row["customer_id"], set()).add(month_index(row["month"]))
        for customer_id, months in by_customer.items():
            if months != set(range(min(months), end + 1)):
                raise ValueError(f"Uncovered customer months must not become zeros: {customer_id}")
    return raw
