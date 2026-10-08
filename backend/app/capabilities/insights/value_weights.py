"""Relative commercial weights per equipment group (explicit assumptions).

No price, revenue or margin fields exist in the extract, so expected
commercial value is expressed in relative points, never euros. Every group
defaults to 1.0 (pure volume ranking). Sales can override with a JSON file
``{group_id: weight}`` via ``PECAL_VALUE_WEIGHTS``; unknown groups fall
back to 1.0 and non-positive files are rejected.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_WEIGHT = 1.0


@lru_cache(maxsize=4)
def load_weights(path: str | None = None) -> dict[str, float]:
    """Return {group_id: positive weight}; empty means all defaults."""
    target = path or os.getenv("PECAL_VALUE_WEIGHTS")
    if not target:
        return {}
    payload = json.loads(Path(target).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Value weights file must map group_id to weight")
    weights = {}
    for group_id, weight in payload.items():
        value = float(weight)
        if value <= 0:
            raise ValueError(f"Non-positive weight for group {group_id}")
        weights[str(group_id)] = value
    return weights


def unit_value(group_id: str | None, weights: dict[str, float] | None = None) -> float:
    table = weights if weights is not None else load_weights()
    if group_id is None:
        return DEFAULT_WEIGHT
    return table.get(group_id, DEFAULT_WEIGHT)
