"""Immutable analytics artifact publication and API-facing read functions."""

from __future__ import annotations

import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

FILES = ("manifest", "predictions", "segments", "sectors", "model_report")
DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "data" / "runtime" / "analytics"


def _check_id(snapshot_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", snapshot_id):
        raise ValueError("Invalid snapshot ID")


def validate_outputs(outputs: dict) -> None:
    meta = outputs["manifest"]
    snapshot_id = meta["snapshot_id"]
    reference_date = meta["reference_date"]
    _check_id(snapshot_id)
    seen = set()
    for prediction in outputs["predictions"]:
        if prediction["snapshot_id"] != snapshot_id or prediction["reference_date"] != reference_date:
            raise ValueError("Prediction snapshot/reference mismatch")
        customer_id = prediction["customer_id"]
        if customer_id in seen:
            raise ValueError("Duplicate prediction customer ID")
        seen.add(customer_id)
        activity = prediction["activity"]
        probability = activity["probability"]
        if probability is not None and not 0 <= probability <= 1:
            raise ValueError("Invalid activity probability")
        forecast = prediction["calibration_volume"]
        if forecast["expected_total"] is not None and forecast["expected_total"] < 0:
            raise ValueError("Invalid forecast")
        if activity["window_start"] != forecast["window_start"] or activity["window_end"] != forecast["window_end"]:
            raise ValueError("Activity and volume horizon mismatch")
        if activity["support"]["status"] != "supported" and probability is not None:
            raise ValueError("Unsupported activity probability")
        if forecast["support"]["status"] != "supported" and forecast["expected_total"] is not None:
            raise ValueError("Unsupported volume forecast")
        if forecast["metric"] != "calibration_events" or forecast["horizon_months"] != 3:
            raise ValueError("Unexpected volume target")
    for name in ("sectors", "model_report"):
        payload = outputs[name]
        if payload["snapshot_id"] != snapshot_id or payload["reference_date"] != reference_date:
            raise ValueError(f"{name} snapshot/reference mismatch")
    correlation = outputs["sectors"]["correlation"]
    size = len(correlation["industry_ids"])
    if len(correlation["labels"]) != size:
        raise ValueError("Sector labels do not align")
    for matrix in (correlation["values"], correlation["pair_sample_counts"]):
        if len(matrix) != size or any(len(row) != size for row in matrix):
            raise ValueError("Sector matrix is not square")
    for i in range(size):
        for j in range(size):
            value = correlation["values"][i][j]
            if value is not None and not -1 <= value <= 1:
                raise ValueError("Invalid sector correlation")
            if value != correlation["values"][j][i]:
                raise ValueError("Asymmetric sector correlation")
    # Reject NaN/Infinity before publication; JSON `null` represents unknown.
    json.dumps(outputs, allow_nan=False)


def publish_outputs(outputs: dict, root: Path) -> Path:
    """Publish a new immutable snapshot directory after all files validate."""
    validate_outputs(outputs)
    root.mkdir(parents=True, exist_ok=True)
    target = root / outputs["manifest"]["snapshot_id"]
    if target.exists():
        raise FileExistsError(f"Analytics snapshot already published: {target}")
    with tempfile.TemporaryDirectory(prefix=".analytics-", dir=root) as staging:
        stage = Path(staging)
        for name in FILES:
            (stage / f"{name}.json").write_text(
                json.dumps(outputs[name], ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8")
        os.replace(stage, target)
    return target


@lru_cache(maxsize=8)
def _load_validated_json(snapshot_id: str, root: Path) -> str:
    _check_id(snapshot_id)
    folder = root / snapshot_id
    outputs = {name: json.loads((folder / f"{name}.json").read_text(encoding="utf-8")) for name in FILES}
    validate_outputs(outputs)
    if outputs["manifest"]["snapshot_id"] != snapshot_id:
        raise ValueError("Requested snapshot and published manifest differ")
    return json.dumps(outputs, allow_nan=False)


def load_outputs(snapshot_id: str, root: Path = DEFAULT_ROOT) -> dict:
    """Read/validate an immutable snapshot once; give each caller its own copy."""
    return json.loads(_load_validated_json(snapshot_id, Path(root).resolve()))


def get_prediction(customer_id: str, snapshot_id: str,
                   root: Path = DEFAULT_ROOT) -> dict | None:
    outputs = load_outputs(snapshot_id, root)
    return next((item for item in outputs["predictions"] if item["customer_id"] == customer_id), None)


def get_sectors(snapshot_id: str, root: Path = DEFAULT_ROOT) -> dict:
    return load_outputs(snapshot_id, root)["sectors"]
