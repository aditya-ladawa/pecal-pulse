"""Member 1: normalized snapshot loading (plan §4A, §5 seam).

Seams (names per plan §5):
    load_snapshot(snapshot_id) -> validated section rows + manifest
    get_customer_profile -> profile/history/portfolio/requirements (see
        get_customer_detail, which also returns instruments and events)

Snapshots are immutable JSON documents. The loader validates every row
against the frozen v2 contracts and rejects mismatched snapshot_ids.
The synthetic fixture ships in data/mock/; real extracts live in
data/runtime/snapshots/<snapshot_id>.json (gitignored, never committed).
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from ...contracts import sales_v2 as v2

ROOT = Path(__file__).resolve().parents[4]
MOCK_SNAPSHOT_FILE = ROOT / "data/mock/v2_snapshot_synthetic.json"
RUNTIME_SNAPSHOT_DIR = ROOT / "data/runtime/snapshots"

_SECTION_MODELS = {
    "profiles": v2.CustomerProfile,
    "history": v2.MonthlyHistoryRow,
    "portfolio": v2.PortfolioRow,
    "instruments": v2.InstrumentRecord,
    "events": v2.InstrumentEvent,
    "requirements": v2.Requirement,
}


def available_snapshots() -> list[str]:
    ids = []
    if MOCK_SNAPSHOT_FILE.exists():
        manifest = json.loads(MOCK_SNAPSHOT_FILE.read_text())["manifest"]
        ids.append(manifest["snapshot_id"])
    if RUNTIME_SNAPSHOT_DIR.is_dir():
        for file in sorted(RUNTIME_SNAPSHOT_DIR.glob("*.json")):
            try:
                manifest = json.loads(file.read_text())["manifest"]
                if manifest["snapshot_id"] not in ids:
                    ids.append(manifest["snapshot_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def _snapshot_path(snapshot_id: str) -> Path:
    raw = json.loads(MOCK_SNAPSHOT_FILE.read_text())
    if raw["manifest"]["snapshot_id"] == snapshot_id:
        return MOCK_SNAPSHOT_FILE
    if not re.fullmatch(r"[A-Za-z0-9_-]+", snapshot_id):
        raise ValueError("Invalid snapshot ID")
    candidate = RUNTIME_SNAPSHOT_DIR / f"{snapshot_id}.json"
    if candidate.is_file():
        raw = json.loads(candidate.read_text())
        if raw.get("manifest", {}).get("snapshot_id") == snapshot_id:
            return candidate
    raise ValueError(f"Unknown snapshot: {snapshot_id}")


@lru_cache(maxsize=8)
def load_snapshot(snapshot_id: str) -> dict:
    """Load and contract-validate one immutable snapshot document."""
    raw = json.loads(_snapshot_path(snapshot_id).read_text())
    manifest = v2.SnapshotManifest.model_validate(raw["manifest"])
    if manifest.snapshot_id != snapshot_id:
        raise ValueError("snapshot_id mismatch inside snapshot document")
    validated = {"manifest": manifest}
    for section, model in _SECTION_MODELS.items():
        validated[section] = [
            model.model_validate(row) for row in raw.get(section, [])
        ]
    validated["month_grid"] = list(raw.get("month_grid", []))
    validated["industry_labels"] = list(raw.get("industry_labels", []))
    validated["equipment_group_labels"] = list(raw.get("equipment_group_labels", []))
    return validated


def get_manifest(snapshot_id: str) -> v2.SnapshotManifest:
    return load_snapshot(snapshot_id)["manifest"]


def list_customers(snapshot_id: str) -> list[v2.CustomerProfile]:
    return load_snapshot(snapshot_id)["profiles"]


def get_customer_detail(snapshot_id: str, customer_id: str) -> dict:
    """Profile + history + portfolio + instruments + events + requirements."""
    snapshot = load_snapshot(snapshot_id)
    if "_customer_index" not in snapshot:
        index = {p.customer_id: {"profile": p, **{name: [] for name in ("history", "portfolio", "instruments", "events", "requirements")}} for p in snapshot["profiles"]}
        keys = {"history": "customer_id", "portfolio": "customer_id", "instruments": "current_customer_id", "events": "historical_customer_id", "requirements": "customer_id"}
        for section, key in keys.items():
            for row in snapshot[section]:
                customer = getattr(row, key)
                if customer in index:
                    index[customer][section].append(row)
        snapshot["_customer_index"] = index
    detail = snapshot["_customer_index"].get(customer_id)
    if detail is None:
        raise ValueError(f"Unknown customer: {customer_id}")
    return detail



def recency_months(snapshot_id: str, customer_id: str) -> int | None:
    """Months from reference date back to the latest nonzero history month."""
    snapshot = load_snapshot(snapshot_id)
    reference = snapshot["manifest"].reference_date[:7]
    active = sorted(
        h.month for h in get_customer_detail(snapshot_id, customer_id)["history"]
        if h.calibration_events > 0
    )
    if not active:
        return None
    latest = active[-1]
    return (int(reference[:4]) - int(latest[:4])) * 12 + (
        int(reference[5:7]) - int(latest[5:7])
    )
