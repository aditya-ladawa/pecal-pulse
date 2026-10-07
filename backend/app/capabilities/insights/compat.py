"""Shared-contract adapters (Member 1 `sales_v2` / Member 2 outputs → local models).

Member 1 owns the frozen `backend/app/contracts/sales_v2.py`; Member 2
emits predictions in that nested shape. This module keeps Member 3's
models canonical (per team decision) and coerces shared-shape inputs —
plain dicts or pydantic objects with `model_dump`, never imports of
Member 1/2 modules — into them. Differences handled here:

- `CustomerPrediction` is nested in the shared contract
  (`activity.probability`, `calibration_volume.expected_total`, …) but
  flat locally.
- `PortfolioRow.distinct_instruments` may be `None` (row-count export);
  presence falls back to `calibration_events > 0` via `owns_category`.
- `AccountWorkflow.followups` carries extra screen fields upstream; only
  the workflow fields Member 3 reads are projected.
- Shared `Requirement(stopped=True)` always arrives with
  `eligibility="excluded"` (upstream validator); both spellings skip
  ranking here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .actions import SnapshotStats, build_account_action
from .models import (
    AccountAction,
    AccountWorkflow,
    CustomerPrediction,
    CustomerProfile,
    PeerOpportunity,
    PortfolioRow,
    Requirement,
)

__all__ = [
    "as_dict",
    "profile_from_shared",
    "portfolio_from_shared",
    "requirement_from_shared",
    "prediction_from_shared",
    "workflow_from_shared",
    "ranking_fn_for_composition",
    "action_to_shared_payload",
]


def as_dict(obj: Any) -> dict:
    if isinstance(obj, Mapping):
        return dict(obj)
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump()
    raise TypeError(f"cannot coerce {type(obj).__name__} to a mapping")


def _project(data: dict, fields: set[str]) -> dict:
    return {k: v for k, v in data.items() if k in fields}


def profile_from_shared(obj: Any) -> CustomerProfile:
    return CustomerProfile.model_validate(
        _project(as_dict(obj), set(CustomerProfile.model_fields))
    )


def portfolio_from_shared(obj: Any) -> PortfolioRow:
    return PortfolioRow.model_validate(
        _project(as_dict(obj), set(PortfolioRow.model_fields))
    )


def requirement_from_shared(obj: Any) -> Requirement:
    return Requirement.model_validate(
        _project(as_dict(obj), set(Requirement.model_fields))
    )


def prediction_from_shared(obj: Any) -> CustomerPrediction:
    """Flatten a shared nested prediction (or an already-flat local one)."""
    data = as_dict(obj)
    if "activity" in data and isinstance(data["activity"], Mapping):
        activity = as_dict(data["activity"])
        volume = as_dict(data.get("calibration_volume") or {})
        inactivity = as_dict(data.get("inactivity") or {})
        return CustomerPrediction(
            snapshot_id=data["snapshot_id"],
            customer_id=data["customer_id"],
            reference_date=data["reference_date"],
            segment_id=data.get("segment_id"),
            activity_probability=activity.get("probability"),
            activity_window_start=activity.get("window_start"),
            activity_window_end=activity.get("window_end"),
            activity_support=as_dict(activity.get("support") or {}),
            expected_volume_3m=volume.get("expected_total"),
            recency_months=data.get("recency_months"),
            cadence_months=data.get("cadence_months"),
            inactivity=inactivity,
        )
    return CustomerPrediction.model_validate(
        _project(data, set(CustomerPrediction.model_fields))
    )


def workflow_from_shared(obj: Any | None) -> AccountWorkflow | None:
    if obj is None:
        return None
    data = as_dict(obj)
    followups = [
        _project(
            as_dict(f),
            {"id", "customer_id", "due_date", "note", "status"},
        )
        for f in data.get("followups", [])
    ]
    return AccountWorkflow(
        account_owner=data.get("account_owner"),
        checks=_project(
            as_dict(data.get("checks") or {}),
            {"quotation_order", "recent_contact", "contact_details",
             "checked_at", "checked_by"},
        ),
        suppressions=[
            _project(
                as_dict(s),
                {"reason_id", "status", "until", "note", "updated_at"},
            )
            for s in data.get("suppressions", [])
        ],
        followups=followups,
    )


def peers_from_shared(objs: list[Any]) -> list[PeerOpportunity]:
    return [
        PeerOpportunity.model_validate(
            _project(as_dict(o), set(PeerOpportunity.model_fields))
        )
        for o in objs
    ]


def ranking_fn_for_composition(
    stats: SnapshotStats,
    weights: dict[str, float] | None = None,
    today: str | None = None,
) -> Callable:
    """Build the `ranking_fn` Member 1's composition layer injects.

    Called positionally as
    `ranking_fn(profile, requirements, prediction, peers, workflow)` —
    matching `composition.refresh_after_correction` — with each argument
    either local-shaped or shared-shaped. Returns a local `AccountAction`
    (or `None`); `action_to_shared_payload` renders it for the shared
    `AccountAction` schema.
    """

    def rank(
        profile: Any,
        requirements: list[Any],
        prediction: Any | None,
        peers: list[Any],
        workflow: Any | None,
    ) -> AccountAction | None:
        prof = profile_from_shared(profile)
        return build_account_action(
            snapshot_id=stats.snapshot_id,
            customer_id=prof.customer_id,
            requirements=[requirement_from_shared(r) for r in requirements],
            prediction=(
                prediction_from_shared(prediction) if prediction is not None else None
            ),
            peer_opportunities=peers_from_shared(peers),
            workflow=workflow_from_shared(workflow),
            stats=stats,
            weights=weights,
            today=today,
        )

    return rank


def action_to_shared_payload(action: AccountAction) -> dict:
    """Render an action as the shared §4C `AccountAction` payload.

    Field-identical by construction (same names, same value domains);
    Member 1 validates it with `v2.AccountAction.model_validate`.
    """
    return action.model_dump()
