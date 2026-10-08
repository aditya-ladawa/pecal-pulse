"""Evaluate intermittent-demand volume challengers on pipeline windows.

Usage: uv run python -m analysis.evaluate_volume --snapshot-id private-snapshot

Reuses the analytics pipeline's chronological train/calibration/validation/
test customer-origin windows and MAE selection rule, then scores Croston,
TSB and industry-pooled estimators on validation (selection) and test
(descriptive). Writes a volume_reliability.json sidecar with segment-level
test error for the served method. Frozen v3 artifacts are never modified.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from backend.app.capabilities.analytics import pipeline
from backend.app.capabilities.analytics.features import month_index
from backend.app.capabilities.analytics.volume_methods import (
    croston_3m,
    industry_12m_means,
    pooled_12m,
    tsb_3m,
)


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
    start, end = month_index(manifest["history_start"]), month_index(manifest["complete_through_month"])

    histories: dict[str, dict[int, int]] = defaultdict(dict)
    for row in raw["history"]:
        histories[row["customer_id"]][month_index(row["month"])] = int(row["calibration_events"])
    industries = {p["customer_id"]: (p.get("industry_id") or "unknown") for p in raw["profiles"]}

    records = pipeline._observations(
        {c: {t: {"calibration_events": e} for t, e in h.items()} for c, h in histories.items()},
        start,
        end,
    )
    if not records:
        raise ValueError("No validation windows; snapshot too short for evaluation")

    cutoffs = sorted({r["cutoff"] for rows in records.values() for r in rows})
    industry_means = industry_12m_means(histories, industries, cutoffs)

    def challengers(customer_id, cutoff):
        events = histories[customer_id]
        active = sum(1 for t, e in events.items() if t <= cutoff and e > 0)
        own_12m = sum(events.get(t, 0) for t in range(cutoff - 11, cutoff + 1))
        return {
            "croston_3m": croston_3m(events, cutoff),
            "tsb_3m": tsb_3m(events, cutoff),
            "pooled_12m": pooled_12m(
                own_12m, industry_means.get((industries.get(customer_id, "unknown"), cutoff)), active
            ),
        }

    evaluations: dict[str, dict] = {}
    for name in ("croston_3m", "tsb_3m", "pooled_12m"):
        evaluations[name] = {}
        for stage in ("validation", "test"):
            rows = records[stage]
            actual = [r["volume"] for r in rows]
            predicted = [challengers(r["customer_id"], r["cutoff"])[name] for r in rows]
            evaluations[name][stage] = pipeline._volume_metrics(
                np.asarray(actual), np.asarray(predicted)
            )

    served = json.loads(
        (args.analytics_root / args.snapshot_id / "model_report.json").read_text(encoding="utf-8")
    )
    served_method = served["selected_volume"]
    served_metrics = served["volume_metrics"][served_method]["test"]

    segments = {
        s["id"]: s["label"]
        for s in json.loads(
            (args.analytics_root / args.snapshot_id / "segments.json").read_text(encoding="utf-8")
        )
    }
    seg_of = {}
    for row in json.loads(
        (args.analytics_root / args.snapshot_id / "predictions.json").read_text(encoding="utf-8")
    ):
        seg_of[row["customer_id"]] = row.get("segment_id")
    by_segment: dict[str, dict] = {}
    for segment_id, label in segments.items():
        actual, predicted = [], []
        for r in records["test"]:
            if seg_of.get(r["customer_id"]) != segment_id:
                continue
            actual.append(r["volume"])
            predicted.append(r["baselines"][served_method])
        if actual:
            by_segment[segment_id] = {
                "label": label,
                **pipeline._volume_metrics(np.asarray(actual), np.asarray(predicted)),
            }

    payload = {
        "snapshot_id": args.snapshot_id,
        "reference_date": manifest["reference_date"],
        "served_method": served_method,
        "served_test": served_metrics,
        "challengers": evaluations,
        "segment_test": by_segment,
        "selection_rule": "validation MAE, mirroring the analytics pipeline",
    }
    json.dumps(payload, allow_nan=False)
    target = args.analytics_root / args.snapshot_id / "volume_reliability.json"
    if target.exists() and not args.force:
        raise FileExistsError(f"Sidecar already published: {target} (use --force to rebuild)")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = [
        (name, evaluations[name]["validation"]["mae"], evaluations[name]["test"]["mae"],
         evaluations[name]["test"]["wape"])
        for name in evaluations
    ]
    served_val = served["volume_metrics"][served_method]["validation"]["mae"]
    print(json.dumps({
        "served": {"method": served_method, "validation_mae": served_val, **served_metrics},
        "challengers": [
            {"method": n, "validation_mae": v, "test_mae": t, "test_wape": w}
            for n, v, t, w in rows
        ],
        "winner_validation_mae": min([served_val] + [v for _, v, _, _ in rows]),
        "segment_test_wape": {k: v["wape"] for k, v in by_segment.items()},
    }, indent=1))


if __name__ == "__main__":
    main()
