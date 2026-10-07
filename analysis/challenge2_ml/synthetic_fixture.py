"""Deterministic long-history fixture using Member 1's canonical contracts."""

from __future__ import annotations

import json
import argparse
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


def make_demo_fixture() -> dict:
    """Synthetic data for data/API/analytics/insights integration, never a real export."""
    snapshot = make_fixture()
    # End at the source's planned complete-month cutoff; use 36 synthetic months.
    start = month_index("2023-09")
    for row in snapshot["history"]:
        row["month"] = iso_month(month_index(row["month"]) - 4)
        if row["customer_id"] == "synthetic-customer-00" and row["month"] >= "2026-03":
            for name in ("calibration_events", "distinct_instruments", "equipment_group_count", "lab_count"):
                row[name] = 0
    snapshot["month_grid"] = [iso_month(start + i) for i in range(36)]
    for i, profile in enumerate(snapshot["profiles"]):
        profile["industry_id"] = "synthetic-a" if i < 25 else "synthetic-b"
        profile["industry_label"] = f"Synthetic sector {profile['industry_id'][-1].upper()}"
    portfolio = []
    for i, profile in enumerate(snapshot["profiles"]):
        # Null instrument counts exercise Member 1's actual export contract.
        portfolio.append({"customer_id": profile["customer_id"],
                          "group_id": "synthetic-group-a" if i == 0 else "synthetic-group-b",
                          "group_label": "Synthetic category A" if i == 0 else "Synthetic category B",
                          "distinct_instruments": None, "calibration_events": 2 + i % 4,
                          "window_start": "2025-09-01", "window_end": "2026-08-31"})
    snapshot["portfolio"] = portfolio
    snapshot["equipment_group_labels"] = [
        {"group_id": f"synthetic-group-{group}", "group_label": f"Synthetic category {group.upper()}"}
        for group in ("a", "b")]
    snapshot["instruments"] = [
        {"instrument_id": "synthetic-inst-active", "current_customer_id": "synthetic-customer-00",
         "group_id": "synthetic-group-a", "last_calibration_date": "2026-02-15",
         "recorded_due_date": "2026-10-15", "stopped": False},
        {"instrument_id": "synthetic-inst-stopped", "current_customer_id": "synthetic-customer-01",
         "group_id": "synthetic-group-b", "last_calibration_date": "2026-07-15",
         "recorded_due_date": "2026-10-15", "stopped": True},
    ]
    snapshot["events"] = [
        {"event_id": f"synthetic-event-{i}", "instrument_id": inst["instrument_id"],
         "historical_customer_id": inst["current_customer_id"],
         "calibration_date": inst["last_calibration_date"], "group_id": inst["group_id"]}
        for i, inst in enumerate(snapshot["instruments"])]
    snapshot["requirements"] = [
        {"id": f"synthetic-req-{i}", "customer_id": inst["current_customer_id"],
         "instrument_id": inst["instrument_id"], "group_id": inst["group_id"],
         "kind": "recorded", "window_start": inst["recorded_due_date"],
         "window_end": inst["recorded_due_date"], "method": "synthetic_recorded_due_date",
         "evidence_dates": [inst["last_calibration_date"], inst["recorded_due_date"]],
         "positive_gap_count": 0, "stopped": inst["stopped"],
         "eligibility": "excluded" if inst["stopped"] else "eligible", "unknowns": []}
        for i, inst in enumerate(snapshot["instruments"])]
    snapshot["manifest"].update({
        "snapshot_id": "synthetic-analytics-demo-v1", "reference_date": "2026-08-31",
        "extracted_at": "2026-09-01T00:00:00Z", "complete_through_month": "2026-08",
        "history_start": "2023-09", "quality_flags": ["synthetic", "not_historical_performance",
                                                                   "synthetic_instrument_events_are_not_full_history"],
        "source_tables": ["profiles", "history", "portfolio", "instruments", "events", "requirements"],
        "row_counts": {name: len(snapshot[name])
                       for name in ("profiles", "history", "portfolio", "instruments", "events", "requirements")},
    })
    return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Generate the registered API integration demo")
    args = parser.parse_args()
    snapshot = make_demo_fixture() if args.demo else make_fixture()
    target = (Path("data/runtime/snapshots") / f"{snapshot['manifest']['snapshot_id']}.json"
              if args.demo else Path("data/mock/analytics_normalized.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if args.demo and target.exists():
        parser.error(f"Immutable demo snapshot already exists: {target}")
    target.write_text(json.dumps(snapshot, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(target)
