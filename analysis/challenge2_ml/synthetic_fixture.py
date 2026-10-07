"""Deterministic long-history fixture using Member 1's canonical contracts."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.capabilities.analytics.features import iso_month, month_index


def make_fixture() -> dict:
    start = month_index("2024-01")
    profiles, monthly = [], []
    for i in range(30):
        customer_id = f"synthetic-customer-{i:02d}"
        industry_id = "synthetic-a" if i < 15 else "synthetic-b"
        profiles.append({"customer_id": customer_id, "display_name": f"Synthetic account {i:02d}",
                         "name_source": "identifier", "industry_id": industry_id,
                         "industry_label": industry_id})
        seen = False
        for offset in range(36):
            # A recurring account, intermittent account and sparse account are present.
            if i == 29:
                events = 1 if offset == 35 else 0
            elif i % 3 == 0:
                events = 2 + i % 4 if offset % 2 == 0 else 0
            elif i % 3 == 1:
                events = 1 + i % 5 if offset % 3 == 0 else 0
            else:
                events = 1 + i % 3 if offset % 4 == 0 else 0
            seen = seen or events > 0
            if seen:
                monthly.append({"customer_id": customer_id, "month": iso_month(start + offset),
                    "calibration_events": events, "distinct_instruments": events,
                    "equipment_group_count": min(events, 1 + (i % 3)), "lab_count": int(events > 0)})
    return {"manifest": {"snapshot_id": "synthetic-analytics-v2",
        "extracted_at": "2026-01-01T00:00:00Z", "reference_date": "2026-12-31",
        "complete_through_month": "2026-12", "history_start": "2024-01",
        "source_tables": ["profiles", "history"], "row_counts": {"profiles": len(profiles), "history": len(monthly)},
        "field_coverage": {}, "quality_flags": ["synthetic"]},
        "profiles": profiles, "history": monthly,
        "month_grid": [iso_month(start + i) for i in range(36)], "portfolio": []}


if __name__ == "__main__":
    target = Path("data/mock/analytics_normalized.json")
    target.write_text(json.dumps(make_fixture(), indent=2) + "\n", encoding="utf-8")
    print(target)
