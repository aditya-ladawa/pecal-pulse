"""Build Member 2 artifacts from Member 1's normalized JSON snapshot.

Usage: python -m analysis.challenge2_ml.run path/to/snapshot.json --output data/runtime/analytics
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from threadpoolctl import threadpool_limits

from backend.app.capabilities.analytics.pipeline import build_outputs
from backend.app.capabilities.analytics.service import publish_outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path, nargs="?")
    parser.add_argument("--snapshot-id", help="Load Member 1's typed snapshot by ID")
    parser.add_argument("--output", type=Path, default=Path("data/runtime/analytics"))
    args = parser.parse_args()
    if (args.snapshot is None) == (args.snapshot_id is None):
        parser.error("Provide either a snapshot JSON path or --snapshot-id")
    if args.snapshot_id:
        from backend.app.capabilities.data.service import load_snapshot
        snapshot = load_snapshot(args.snapshot_id)
    else:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    with threadpool_limits(limits=1):
        outputs = build_outputs(snapshot)
    target = publish_outputs(outputs, args.output)
    report = outputs["model_report"]
    print(json.dumps({"path": str(target), "snapshot_id": report["snapshot_id"],
        "supported_customers": report["supported_customers"],
        "selected_activity": report["selected_activity"],
        "selected_volume": report["selected_volume"]}))


if __name__ == "__main__":
    main()
