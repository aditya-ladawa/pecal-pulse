"""Member 1: v2 read composition + workflow writes (plan §4D/E).

Serves the frozen snapshot and composes Member 2/3 outputs when their
modules merge. Until then those sections are explicit unavailable states —
never mock numbers inside historical records. Existing /api/* routes stay
functional; the mock UI is untouched.
"""

import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import TypeAdapter

from ..capabilities import data
from ..capabilities.analytics.context import for_snapshot as analytics_for_snapshot
from ..capabilities.sales.models import FollowupUpdate as FollowupStatusUpdate
from ..contracts import sales_v2 as v2
from ..realtime.publisher import publish

router = APIRouter(prefix="/api/v2")

DEFAULT_SNAPSHOT = os.getenv("PECAL_SNAPSHOT", "synthetic-v1")
WORKFLOW_TODAY = os.getenv("PECAL_TODAY", "2026-10-07")


def _mode(snapshot_id: str) -> Literal["mock", "historical"]:
    return "mock" if snapshot_id.startswith("synthetic") else "historical"


def _metadata(snapshot_id: str) -> v2.ResponseMetadata:
    manifest = data.get_manifest(snapshot_id)
    analytics = analytics_for_snapshot(data.load_snapshot(snapshot_id))
    return v2.ResponseMetadata(
        snapshot_id=snapshot_id,
        reference_date=manifest.reference_date,
        mode=_mode(snapshot_id),
        workflow_today=WORKFLOW_TODAY,
        modules={
            "data": v2.ModuleReadiness(status="ready"),
            "predictions": analytics.readiness("predictions"),
            "insights": v2.ModuleReadiness(status="ready"),
            "sectors": analytics.readiness("sectors"),
        },
    )


def _require_snapshot(snapshot_id: str) -> None:
    if snapshot_id not in data.available_snapshots():
        raise HTTPException(404, f"Unknown snapshot: {snapshot_id}")


def _recency(snapshot_id: str, customer_id: str) -> int | None:
    return data.recency_months(snapshot_id, customer_id)


@router.get("/bootstrap")
def bootstrap(snapshot_id: str = DEFAULT_SNAPSHOT):
    _require_snapshot(snapshot_id)
    manifest = data.get_manifest(snapshot_id)
    profiles = data.list_customers(snapshot_id)
    industries = sorted(
        {(p.industry_id or "unknown", p.industry_label or "Unknown") for p in profiles}
    )
    snapshot = data.load_snapshot(snapshot_id)
    analytics = analytics_for_snapshot(snapshot)
    by_kind: dict[str, int] = {}
    eligible = 0
    for req in snapshot["requirements"]:
        by_kind[req.kind] = by_kind.get(req.kind, 0) + 1
        if req.eligibility == "eligible":
            eligible += 1
    valid_customer_ids = {p.customer_id for p in profiles}
    open_followups = sorted(
        (f for f in data.list_followups_v2() if f.status == "open" and f.customer_id in valid_customer_ids),
        key=lambda f: f.due_date,
    )
    _, proactive = data.split_queue(snapshot_id, WORKFLOW_TODAY)
    return {
        "metadata": _metadata(snapshot_id).model_dump(),
        "filter_options": {
            "industries": [
                {"value": value, "label": label} for value, label in industries
            ],
            "segments": [
                {"value": s["id"], "label": s["label"]}
                for s in analytics.payload("segments") or []
            ],
            "actions": ["upcoming", "inactivity", "discovery"],
        },
        "kpis": {
            "customers": {"value": len(profiles), "unit": "customers"},
            "eligible_requirements": {"value": eligible, "unit": "instruments"},
            "requirements_by_kind": by_kind,
            "open_followups": {"value": len(open_followups), "unit": "followups"},
            "reference_date": manifest.reference_date,
        },
        "actions": [a.model_dump() for a in proactive[:10]],
        "due_followups": [f.model_dump() for f in open_followups[:10]],
        "sectors": analytics.payload("sectors"),
    }


@router.get("/customers")
def list_customers(
    snapshot_id: str = DEFAULT_SNAPSHOT,
    industry_id: str | None = None,
    segment_id: str | None = None,
    action: Literal["upcoming", "inactivity", "discovery"] | None = None,
    query: str | None = None,
    sort: Literal["priority", "name"] = "name",
    limit: int = 20,
    offset: int = 0,
):
    _require_snapshot(snapshot_id)
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be within 1..100")
    if offset < 0:
        raise HTTPException(422, "offset must be >= 0")
    profiles = data.list_customers(snapshot_id)
    analytics = analytics_for_snapshot(data.load_snapshot(snapshot_id))
    if industry_id:
        profiles = [p for p in profiles if (p.industry_id or "unknown") == industry_id]
    predictions_by_customer = {p.customer_id: analytics.prediction(p.customer_id) for p in profiles}
    queue = data.ranked_queue(snapshot_id, WORKFLOW_TODAY)
    actions_by_customer = {a.customer_id: a for a in queue}
    if action is not None:
        profiles = [
            p
            for p in profiles
            if any(
                r.type == action
                for a in [actions_by_customer.get(p.customer_id)]
                if a is not None
                for r in a.reasons
            )
        ]
    if segment_id:
        profiles = [p for p in profiles
                    if (prediction := predictions_by_customer[p.customer_id]) is not None
                    and prediction.segment_id == segment_id]
    if query:
        needle = query.lower()
        profiles = [
            p
            for p in profiles
            if needle in (p.display_name + " " + p.customer_id).lower()
        ]
    if sort == "priority":
        profiles = sorted(
            profiles,
            key=lambda p: (
                -actions_by_customer[p.customer_id].priority_score
                if p.customer_id in actions_by_customer
                else float("inf"),
                p.customer_id,
            ),
        )
    else:
        profiles = sorted(profiles, key=lambda p: p.display_name.lower())
    total = len(profiles)
    return {
        "metadata": _metadata(snapshot_id).model_dump(),
        "items": [
            v2.CustomerSummary(
                profile=p,
                segment_id=(predictions_by_customer[p.customer_id].segment_id
                            if predictions_by_customer[p.customer_id] is not None else None),
                activity_probability=(predictions_by_customer[p.customer_id].activity.probability
                                      if predictions_by_customer[p.customer_id] is not None else None),
                primary_action=actions_by_customer.get(p.customer_id),
                recency_months=_recency(snapshot_id, p.customer_id),
            ).model_dump()
            for p in profiles[offset : offset + limit]
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: str, snapshot_id: str = DEFAULT_SNAPSHOT):
    _require_snapshot(snapshot_id)
    try:
        detail = data.get_customer_detail(snapshot_id, customer_id)
    except ValueError:
        raise HTTPException(404, f"Unknown customer: {customer_id}")
    manifest = data.get_manifest(snapshot_id)
    action = data.action_for_customer(snapshot_id, customer_id, WORKFLOW_TODAY)
    prediction = analytics_for_snapshot(data.load_snapshot(snapshot_id)).prediction(customer_id)
    return {
        "metadata": _metadata(snapshot_id).model_dump(),
        "profile": detail["profile"].model_dump(),
        "history": [h.model_dump() for h in detail["history"]],
        "portfolio": [p.model_dump() for p in detail["portfolio"]],
        "requirements": [r.model_dump() for r in detail["requirements"]],
        "prediction": prediction.model_dump() if prediction is not None else None,
        "action": action.model_dump() if action is not None else None,
        "peer_opportunities": [
            p.model_dump() for p in data.peers_for_customer(snapshot_id, customer_id)
        ],
        "preparation": data.preparation_for_customer(
            snapshot_id, customer_id, WORKFLOW_TODAY
        ).model_dump(),
        "workflow": data.get_workflow(customer_id).model_dump(),
    }


@router.get("/sectors")
def sectors(snapshot_id: str = DEFAULT_SNAPSHOT):
    _require_snapshot(snapshot_id)
    analytics = analytics_for_snapshot(data.load_snapshot(snapshot_id))
    if not analytics.available:
        raise HTTPException(503, analytics.reason)
    return {"metadata": _metadata(snapshot_id).model_dump(),
            "sectors": analytics.payload("sectors")}


@router.get("/model-report")
def model_report(snapshot_id: str = DEFAULT_SNAPSHOT):
    _require_snapshot(snapshot_id)
    analytics = analytics_for_snapshot(data.load_snapshot(snapshot_id))
    if not analytics.available:
        raise HTTPException(503, analytics.reason)
    return {"metadata": _metadata(snapshot_id).model_dump(),
            "model_report": analytics.payload("model_report")}


@router.get("/followups")
def list_followups(snapshot_id: str = DEFAULT_SNAPSHOT):
    _require_snapshot(snapshot_id)
    valid_customer_ids = {p.customer_id for p in data.list_customers(snapshot_id)}
    return {
        "metadata": _metadata(snapshot_id).model_dump(),
        "items": [f.model_dump() for f in data.list_followups_v2() if f.customer_id in valid_customer_ids],
        "workflow_today": WORKFLOW_TODAY,
    }


@router.get("/contracts")
def contracts():
    return {
        "version": "2",
        "snapshot": {
            name: model.model_json_schema()
            for name, model in {
                "manifest": v2.SnapshotManifest,
                "profile": v2.CustomerProfile,
                "history_row": v2.MonthlyHistoryRow,
                "portfolio_row": v2.PortfolioRow,
                "instrument": v2.InstrumentRecord,
                "event": v2.InstrumentEvent,
                "requirement": v2.Requirement,
            }.items()
        },
        "prediction": {
            name: model.model_json_schema()
            for name, model in {
                "prediction": v2.CustomerPrediction,
                "segment": v2.SegmentSummary,
                "sector_correlation": v2.SectorCorrelation,
            }.items()
        },
        "actions": {
            name: model.model_json_schema()
            for name, model in {
                "action_reason": v2.ActionReason,
                "account_action": v2.AccountAction,
                "peer_opportunity": v2.PeerOpportunity,
                "preparation": v2.PreparationCard,
            }.items()
        },
        "workflow": {
            name: model.model_json_schema()
            for name, model in {
                "followup": v2.Followup,
                "workflow": v2.AccountWorkflow,
                "followup_create": v2.FollowupCreateV2,
                "workflow_patch": v2.WorkflowPatch,
            }.items()
        },
    }


def _known_reason_ids(snapshot_id, customer_id, detail):
    known = {r.id for r in detail["requirements"]}
    action = data.action_for_customer(snapshot_id, customer_id, WORKFLOW_TODAY)
    if action is not None:
        known.update(r.id for r in action.reasons)
    known.update(r.reason_id for r in data.get_workflow(customer_id).suppressions)
    return known


@router.post("/followups", status_code=201)
def create_followup(request: v2.FollowupCreateV2, snapshot_id: str = DEFAULT_SNAPSHOT):
    _require_snapshot(snapshot_id)
    try:
        detail = data.get_customer_detail(snapshot_id, request.customer_id)
    except ValueError:
        raise HTTPException(404, f"Unknown customer: {request.customer_id}")
    known = _known_reason_ids(snapshot_id, request.customer_id, detail)
    unknown = [rid for rid in request.reason_ids if rid not in known]
    if unknown:
        raise HTTPException(404, f"Unknown reason ids: {sorted(unknown)}")
    event = data.create_followup_v2(request, detail["profile"].display_name)
    data.refresh_after_correction(snapshot_id, request.customer_id)
    return event


@router.patch("/followups/{task_id}")
def update_followup(task_id: str, request: FollowupStatusUpdate):
    try:
        return data.update_followup_status(task_id, request.status)
    except ValueError:
        raise HTTPException(404, f"Unknown follow-up: {task_id}")


@router.patch("/customers/{customer_id}/workflow")
def update_workflow(
    customer_id: str, patch: v2.WorkflowPatch, snapshot_id: str = DEFAULT_SNAPSHOT
):
    _require_snapshot(snapshot_id)
    try:
        detail = data.get_customer_detail(snapshot_id, customer_id)
    except ValueError:
        raise HTTPException(404, f"Unknown customer: {customer_id}")
    known = _known_reason_ids(snapshot_id, customer_id, detail)
    if patch.suppression is not None and patch.suppression.reason_id not in known:
        raise HTTPException(404, "Unknown reason id")
    workflow = data.get_workflow(customer_id)
    if "account_owner" in patch.model_fields_set:
        from ..capabilities.data.workflow import update_owner
        if patch.account_owner is not None and not patch.account_owner.strip():
            raise HTTPException(422, "Owner must not be blank")
        workflow = update_owner(customer_id, patch.account_owner.strip() if patch.account_owner else None)
    if patch.checks is not None:
        workflow = data.update_checks(customer_id, patch.checks)
    if patch.suppression is not None:
        try:
            workflow = data.add_suppression(customer_id, patch.suppression, known)
        except ValueError as exc:
            raise HTTPException(404, str(exc))
    refreshed = data.refresh_after_correction(snapshot_id, customer_id)
    return publish(
        "customer.workflow.updated",
        {
            "customer_id": customer_id,
            "workflow": workflow.model_dump(),
            "action": refreshed["action"],
            "suppressed_requirement_ids": refreshed["suppressed_requirement_ids"],
        },
        "backend",
    )


@router.get("/opportunities")
def opportunities(snapshot_id: str = DEFAULT_SNAPSHOT, industry: str = "all", segment: str = "all", group: str = "all",
    purpose: Literal["all", "upcoming", "inactivity", "discovery"] = "all", window_days: Literal[30,60,90] = 90,
    include_inferred: bool = True, include_past_due: bool = False, cluster_id: str | None = None,
    display_limit: int = Query(default=500, ge=0, le=10000), limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0), unit_contribution: float | None = Query(default=None, ge=0, le=100000),
    assumption_source: str = Query(default="", max_length=150)):
    from ..contracts.opportunities import OpportunityFilters, ScenarioAssumptions
    from ..capabilities.data.opportunities import compose
    _require_snapshot(snapshot_id)
    if unit_contribution is not None and not assumption_source.strip():
        raise HTTPException(422, "Supply the source of your contribution assumption")
    scenario = ScenarioAssumptions(unit_contribution=unit_contribution, source=assumption_source.strip()) if unit_contribution is not None else None
    try:
        return compose(snapshot_id, _metadata(snapshot_id), OpportunityFilters(industry=industry, segment=segment,
            group=group, purpose=purpose, window_days=window_days, include_inferred=include_inferred,
            include_past_due=include_past_due), cluster_id, display_limit, limit, offset, scenario).model_dump()
    except ValueError as exc:
        raise HTTPException(422, str(exc))
