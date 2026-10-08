"""Build the empirical retention (return) curve sidecar for a snapshot.

Usage: uv run python -m analysis.build_retention --snapshot-id private-snapshot

Reads the compact snapshot history with plain JSON (no contract validation;
shape is checked minimally) and writes retention.json next to the published
analytics artifacts. Frozen v3 artifacts are never modified. Refuses to
overwrite an existing sidecar unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from backend.app.capabilities.analytics.features import month_index
from backend.app.capabilities.analytics.retention import (
    FORWARD_WINDOW_MONTHS,
    HORIZON_MONTHS,
    VERSION,
    forward_curve,
    retention_for,
    return_curve,
    silence_episodes,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--horizon", type=int, default=HORIZON_MONTHS)
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
    end = month_index(manifest["complete_through_month"])

    histories: dict[str, dict[int, int]] = defaultdict(dict)
    for row in raw["history"]:
        histories[row["customer_id"]][month_index(row["month"])] = int(
            row["calibration_events"]
        )

    all_episodes = []
    per_customer_active = {}
    for customer_id, history in histories.items():
        active = sorted(t for t, events in history.items() if events > 0)
        per_customer_active[customer_id] = active
        all_episodes.extend(silence_episodes(active, end, horizon=args.horizon))
    curve = return_curve(all_episodes, horizon=args.horizon)
    forward = forward_curve(
        all_episodes, horizon=args.horizon, window=FORWARD_WINDOW_MONTHS
    )

    tiers: dict[str, int] = {"lower": 0, "moderate": 0, "higher": 0}
    unavailable = 0
    for active in per_customer_active.values():
        result = retention_for(active, end, forward)
        if result is None:
            unavailable += 1
        else:
            tiers[result["tier"]] += 1

    payload = {
        "version": VERSION,
        "snapshot_id": args.snapshot_id,
        "reference_date": manifest["reference_date"],
        "horizon_months": args.horizon,
        "forward_window_months": FORWARD_WINDOW_MONTHS,
        "episodes": len(all_episodes),
        "episode_unit": "silence episodes after repeated activity; repeated origins for an account are not independent",
        "cumulative_curve": curve,
        "forward_curve": forward,
        "tier_distribution_at_reference": {**tiers, "unavailable": unavailable},
    }
    json.dumps(payload, allow_nan=False)

    target_dir = args.analytics_root / args.snapshot_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "retention.json"
    if target.exists() and not args.force:
        raise FileExistsError(f"Sidecar already published: {target} (use --force to rebuild)")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "path": str(target),
                "episodes": len(all_episodes),
                "tiers": tiers,
                "unavailable": unavailable,
                "regular_d9": forward["regular"][9] if len(forward["regular"]) > 9 else None,
                "irregular_d9": forward["irregular"][9] if len(forward["irregular"]) > 9 else None,
            }
        )
    )


if __name__ == "__main__":
    main()
