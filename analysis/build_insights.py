"""Build the Insights summary sidecar for a snapshot.

Usage: uv run python -m analysis.build_insights --snapshot-id private-snapshot

Aggregates (plain JSON, no contract validation):
- due calendar: supported requirements by window-start month, recorded vs
  inferred, for the 6 months after the reference date, plus a past-due count.
- industry expected calibrations: sums of supported 3-month forecasts.
- retention risk by industry: measured tiers from the retention sidecar.

Frozen analytics artifacts are never modified. Refuses to overwrite an
existing sidecar unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from backend.app.capabilities.analytics.features import month_index
from backend.app.capabilities.analytics.retention import retention_for

INSIGHTS_VERSION = "insights-v1"
FORWARD_MONTHS = 6


def _month_add(base: int, delta: int) -> int:
    return base + delta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument(
        "--analytics-root",
        type=Path,
        default=Path(os.getenv("PECAL_ANALYTICS_ROOT", "data/runtime/analytics-v3")),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = Path("data/runtime/snapshots") / f"{args.snapshot_id}.compact.json"
    if not source.is_file():
        source = Path("data/runtime/snapshots") / f"{args.snapshot_id}.json"
    raw = json.loads(source.read_text(encoding="utf-8"))
    manifest = raw["manifest"]
    if manifest["snapshot_id"] != args.snapshot_id:
        raise ValueError("snapshot_id mismatch inside snapshot document")
    reference = manifest["reference_date"]
    ref_month = month_index(manifest["complete_through_month"])
    window_months = [_month_add(ref_month, d) for d in range(1, FORWARD_MONTHS + 1)]

    from backend.app.capabilities.analytics.features import iso_month

    month_labels = [iso_month(m) for m in window_months]

    # Due calendar from requirement windows (evidence, not model output).
    calendar = [
        {"month": label, "recorded": 0, "inferred": 0} for label in month_labels
    ]
    past_due = 0
    for req in raw.get("requirements", []):
        if req.get("stopped") is True or req.get("eligibility") == "excluded":
            continue
        if req.get("kind") == "unknown" or not req.get("window_start"):
            continue
        start = req["window_start"][:7]
        bucket = next((c for c in calendar if c["month"] == start), None)
        if bucket is not None:
            key = "recorded" if req.get("kind") == "recorded" else "inferred"
            bucket[key] += 1
        elif req.get("window_end") and req["window_end"] < reference:
            past_due += 1

    profiles = {p["customer_id"]: p for p in raw["profiles"]}
    industry_of = {
        cid: (p.get("industry_id") or "unknown", p.get("industry_label") or "Unknown")
        for cid, p in profiles.items()
    }

    # Industry expected calibrations from supported forecasts.
    predictions_path = args.analytics_root / args.snapshot_id / "predictions.json"
    industry_expected: dict[str, dict] = {}
    if predictions_path.is_file():
        for pred in json.loads(predictions_path.read_text(encoding="utf-8")):
            volume = pred.get("calibration_volume", {})
            if volume.get("support", {}).get("status") != "supported":
                continue
            expected = volume.get("expected_total")
            if expected is None:
                continue
            industry_id, label = industry_of.get(
                pred["customer_id"], ("unknown", "Unknown")
            )
            entry = industry_expected.setdefault(
                industry_id, {"label": label, "expected": 0.0, "accounts": 0}
            )
            entry["expected"] += expected
            entry["accounts"] += 1
        for entry in industry_expected.values():
            entry["expected"] = round(entry["expected"], 1)

    # Retention risk by industry from the measured curve.
    retention_by_industry: dict[str, dict] = {}
    retention_path = args.analytics_root / args.snapshot_id / "retention.json"
    if retention_path.is_file():
        sidecar = json.loads(retention_path.read_text(encoding="utf-8"))
        end = month_index(manifest["complete_through_month"])
        active: dict[str, list[int]] = defaultdict(list)
        for row in raw["history"]:
            if int(row["calibration_events"]) > 0:
                active[row["customer_id"]].append(month_index(row["month"]))
        for customer_id, months in active.items():
            result = retention_for(sorted(months), end, sidecar["forward_curve"])
            industry_id, label = industry_of.get(customer_id, ("unknown", "Unknown"))
            entry = retention_by_industry.setdefault(
                industry_id,
                {"label": label, "lower": 0, "moderate": 0, "higher": 0, "unavailable": 0},
            )
            entry[result["tier"] if result else "unavailable"] += 1

    payload = {
        "version": INSIGHTS_VERSION,
        "snapshot_id": args.snapshot_id,
        "reference_date": reference,
        "due_calendar": {"months": calendar, "past_due": past_due},
        "industry_expected": industry_expected,
        "retention_by_industry": retention_by_industry,
    }
    json.dumps(payload, allow_nan=False)
    target = args.analytics_root / args.snapshot_id / "insights_summary.json"
    if target.exists() and not args.force:
        raise FileExistsError(f"Sidecar already published: {target} (use --force to rebuild)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "path": str(target),
                "due_total": sum(c["recorded"] + c["inferred"] for c in calendar),
                "past_due": past_due,
                "industries_with_forecast": len(industry_expected),
                "industries_with_retention": len(retention_by_industry),
            }
        )
    )


if __name__ == "__main__":
    main()
