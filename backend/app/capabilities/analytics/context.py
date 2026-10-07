"""Read-only analytics context for API composition; no training imports."""

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ...contracts import sales_v2 as v2
from .features import next_month_window
from .service import DEFAULT_ROOT, load_outputs


@dataclass(frozen=True)
class AnalyticsContext:
    reason: str | None = None
    predictions_ready: bool = False
    sectors_ready: bool = False
    _predictions: dict[str, str] = field(default_factory=dict, repr=False)
    _files: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def available(self) -> bool:
        return bool(self._files)

    def prediction(self, customer_id: str) -> v2.CustomerPrediction | None:
        raw = self._predictions.get(customer_id)
        return v2.CustomerPrediction.model_validate_json(raw) if raw else None

    def payload(self, name: str):
        raw = self._files.get(name)
        return json.loads(raw) if raw is not None else None

    def readiness(self, module: str) -> v2.ModuleReadiness:
        ready = self.predictions_ready if module == "predictions" else self.sectors_ready
        reason = None if ready else self.reason or "No supported results for this snapshot"
        return v2.ModuleReadiness(status="ready" if ready else "unavailable", reason=reason)


@lru_cache(maxsize=8)
def _context(snapshot_id: str, reference: str, complete: str,
             customer_ids: tuple[str, ...], root: Path) -> AnalyticsContext:
    # Cache successes only. Missing files may be published while the API runs.
    outputs = load_outputs(snapshot_id, root)
    meta = outputs["manifest"]
    if meta["reference_date"] != reference or meta["source_complete_through_month"] != complete:
        raise ValueError("Analytics source dates differ from the data snapshot")
    predictions = outputs["predictions"]
    if {p["customer_id"] for p in predictions} != set(customer_ids):
        raise ValueError("Analytics customer coverage differs from the data snapshot")
    window = next_month_window(reference)
    version = meta["model_version"]
    for prediction in predictions:
        for name in ("activity", "calibration_volume"):
            part = prediction[name]
            if (part["window_start"], part["window_end"]) != window:
                raise ValueError("Analytics forecast horizon differs from the data snapshot")
            if part["model_version"] != version:
                raise ValueError("Analytics model versions differ")
    for name in ("sectors", "model_report"):
        if outputs[name]["model_version"] != version:
            raise ValueError("Analytics model versions differ")
    return AnalyticsContext(
        predictions_ready=bool(meta["activity_ready"] or meta["volume_ready"]),
        sectors_ready=bool(outputs["sectors"]["history"]),
        _predictions={p["customer_id"]: json.dumps(p, allow_nan=False) for p in predictions},
        _files={name: json.dumps(outputs[name], allow_nan=False)
                for name in ("segments", "sectors", "model_report")},
    )


def for_snapshot(snapshot: dict) -> AnalyticsContext:
    """Accept Member 1's validated loader result; reject incompatible artifacts."""
    manifest = snapshot["manifest"]
    root = Path(os.getenv("PECAL_ANALYTICS_ROOT", str(DEFAULT_ROOT))).resolve()
    customer_ids = snapshot.setdefault("_analytics_customer_ids", tuple(sorted(p.customer_id for p in snapshot["profiles"])))
    try:
        return _context(manifest.snapshot_id, manifest.reference_date,
                        manifest.complete_through_month,
                        customer_ids, root)
    except FileNotFoundError:
        return AnalyticsContext(reason="Analytics artifacts have not been published for this snapshot")
    except (OSError, ValueError, KeyError, TypeError):
        return AnalyticsContext(reason="Analytics artifacts failed snapshot compatibility checks")
