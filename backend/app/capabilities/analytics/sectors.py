"""Sector history, univariate forecast and supported correlations."""

from __future__ import annotations

from collections import defaultdict
from math import isfinite

import numpy as np

from .features import iso_month, month_index


def build_sectors(profiles: list[dict], histories: dict[str, dict[int, dict]],
                  history_start: str, complete_through_month: str) -> dict:
    start, end = month_index(history_start), month_index(complete_through_month)
    industries: dict[str, dict] = {}
    for profile in profiles:
        industry_id = profile.get("industry_id")
        if industry_id is None:
            continue
        sector = industries.setdefault(industry_id, {"industry_id": industry_id,
            "label": profile.get("industry_label") or industry_id, "customer_ids": set(),
            "counts": defaultdict(int)})
        customer_id = profile["customer_id"]
        sector["customer_ids"].add(customer_id)
        for month, row in histories.get(customer_id, {}).items():
            if start <= month <= end:
                sector["counts"][month] += row["calibration_events"]
    ids = sorted(industries)
    months = list(range(start, end + 1))
    history = []
    forecasts = []
    warnings = []
    changes = {}
    for industry_id in ids:
        item = industries[industry_id]
        values = [item["counts"].get(t, 0) for t in months]
        history.append({"industry_id": industry_id, "label": item["label"],
                        "customers": len(item["customer_ids"]),
                        "monthly": [{"month": iso_month(t), "calibration_events": v}
                                    for t, v in zip(months, values)]})
        changes[industry_id] = np.diff(np.log1p(values))
        if len(item["customer_ids"]) < 20:
            warnings.append(f"{industry_id}: fewer than 20 accounts; sector estimates may be unstable")
        # Compare two strictly past-only one-step forecasts over the last 12 points.
        errors = {"last_month": [], "trailing_3_mean": []}
        for i in range(max(3, len(values) - 12), len(values)):
            errors["last_month"].append(abs(values[i] - values[i - 1]))
            errors["trailing_3_mean"].append(abs(values[i] - sum(values[i - 3:i]) / 3))
        # Select on the first half of the walk-forward points, then report
        # the untouched second half. Short histories remain unavailable.
        split = len(errors["last_month"]) // 2
        method = min(errors, key=lambda key: sum(errors[key][:split]) / split) if split >= 3 else None
        expected = (float(values[-1]) if method == "last_month" else
                    sum(values[-3:]) / 3 if method else None)
        forecasts.append({"industry_id": industry_id, "metric": "calibration_events",
                          "method": method, "forecast_month": iso_month(end + 1),
                          "expected": expected, "validation_mae":
                          {key: sum(value[:split]) / split if split else None for key, value in errors.items()},
                          "test_mae": {key: sum(value[split:]) / len(value[split:])
                                       if value[split:] else None for key, value in errors.items()},
                          "validation_months": split, "test_months": len(errors["last_month"]) - split,
                          "support": "supported" if method else "insufficient_history"})
    matrix = [[None for _ in ids] for _ in ids]
    samples = [[0 for _ in ids] for _ in ids]
    for i, left in enumerate(ids):
        for j in range(i, len(ids)):
            right = ids[j]
            a, b = changes[left], changes[right]
            n = min(len(a), len(b))
            samples[i][j] = samples[j][i] = n
            if n < 24 or np.std(a) == 0 or np.std(b) == 0:
                value = None
            else:
                value = float(np.corrcoef(a, b)[0, 1])
                value = value if isfinite(value) else None
            matrix[i][j] = matrix[j][i] = value
    return {"history": history, "forecasts": forecasts,
            "cohort_definition": "Fixed customer industry membership at snapshot reference date",
            "correlation": {"industry_ids": ids,
                "labels": [industries[ident]["label"] for ident in ids],
                "values": matrix, "pair_sample_counts": samples,
                "method": "pearson_log1p_monthly_change",
                "window_start": iso_month(start + 1) if start < end else iso_month(start),
                "window_end": iso_month(end), "warnings": warnings}}
