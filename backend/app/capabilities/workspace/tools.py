"""Read fresh page context and propose constrained UI actions via the event router."""
from typing import Literal
from langchain.tools import tool, ToolRuntime
from pydantic import TypeAdapter
from ...agents.contracts import TurnContext
from ..sales import service
from ...api import v2 as api_v2
from .. import data
from ..analytics.context import for_snapshot
from ..sales.models import Filters, ChartArtifact, Dataset, UiCommand
from ...realtime.publisher import publish

def emit(runtime, kind, payload):
    command = TypeAdapter(UiCommand).validate_python({"type": kind, "payload": payload})
    event = publish(kind, command.payload.model_dump(exclude_none=True), "agent")
    runtime.context.events.append(event)
    return {"status": "proposed", "event": event}

@tool
def get_workspace_context(runtime: ToolRuntime[TurnContext]) -> dict:
    """Get current page, displayed metric labels/values/definitions, filters, accounts and controls."""
    runtime.context.consume()
    workspace = runtime.context.workspace.model_dump()
    snapshot = workspace.get("page_snapshot")
    if snapshot and snapshot["page"] != workspace["page"]:
        workspace["page_snapshot"] = None
    if runtime.context.workspace.snapshot_id:
        sid = runtime.context.workspace.snapshot_id
        api_v2._require_snapshot(sid)
        profiles = data.list_customers(sid)
        segments = for_snapshot(data.load_snapshot(sid)).payload("segments") or []
        return {**workspace, "data_mode": api_v2._mode(sid),
                "source_reference_date": data.get_manifest(sid).reference_date,
                "controls": {"pages": ["dashboard", "customers", "follow-ups"],
                    "industry": [{"value": i, "label": label} for i, label in sorted({(p.industry_id or "unknown", p.industry_label or "Unknown") for p in profiles})],
                    "segment": [{"value": s["id"], "label": s["label"]} for s in segments],
                    "action": ["all", "upcoming", "inactivity", "discovery"],
                    "customer_tab": ["activity", "portfolio", "next-step"], "action_limit": [5,10,12]},
                "followups": api_v2.list_followups(sid)["items"] if workspace["page"] == "follow-ups" else [],
                "chart_views": ["industry", "activity", "portfolio"]}
    return {**workspace, "data_mode": "mock", "source_reference_date": service.FIXTURE["reference_date"],
            "controls": {"pages": ["dashboard", "customers", "follow-ups"],
                         "industry": ["all", *service.FIXTURE["sector_labels"]],
                         "segment": ["all", "Frequent", "Intermittent", "Occasional"],
                         "action": ["all", "upcoming", "inactivity", "discovery"],
                         "customer_tab": ["activity", "portfolio", "next-step"],
                         "action_limit": [5, 10, 12]},
            "followups": service.list_followups() if workspace["page"] == "follow-ups" else [],
            "chart_views": ["industry", "activity", "portfolio"]}

@tool
def list_customers(runtime: ToolRuntime[TurnContext], industry: str = "all", segment: str = "all", action: str = "all", query: str = "") -> dict:
    """Search observed customers by exact industry/segment/action values or name/ID query."""
    runtime.context.consume()
    if runtime.context.workspace.snapshot_id:
        result = api_v2.list_customers(snapshot_id=runtime.context.workspace.snapshot_id,
            industry_id=None if industry == "all" else industry, segment_id=None if segment == "all" else segment,
            action=None if action == "all" else action, query=query, sort="priority", limit=50, offset=0)
        for item in result["items"]:
            action = item.get("primary_action")
            if action:
                item["reason_count"] = len(action["reasons"])
                action["reasons"] = [{k: r[k] for k in ("id", "type", "title", "explanation", "quantity", "quantity_unit", "status")} for r in action["reasons"][:3]]
        return result
    rows = service.filter_customers(Filters(industry=industry, segment=segment, action=action, query=query))
    return {"source": "mock", "total": len(rows), "customers": [
        {k: c[k] for k in ("id", "name", "industry", "segment", "action", "priority", "reason")}
        for c in rows[:50]]}

@tool
def get_customer_evidence(runtime: ToolRuntime[TurnContext], customer_id: str = "") -> dict:
    """Read selected or specified customer history, forecast, reasons and observed portfolio from the active snapshot."""
    runtime.context.consume()
    if runtime.context.workspace.snapshot_id:
        detail = api_v2.customer_detail(customer_id or runtime.context.workspace.customer_id, runtime.context.workspace.snapshot_id)
        detail["requirement_count"] = len(detail["requirements"])
        detail["requirement_tier_counts"] = {kind: sum(r["kind"] == kind for r in detail["requirements"]) for kind in ("recorded", "nominal_interval", "repeat_history", "unknown")}
        detail["requirements"] = detail["requirements"][:50]
        detail["requirements_display_limit"] = 50
        detail["history"] = detail["history"][-36:]
        if detail.get("action"):
            action = detail["action"]
            detail["action_reason_count"] = len(action["reasons"])
            action["reasons"] = action["reasons"][:10]
            for reason in action["reasons"]:
                reason["evidence_ref_count"] = len(reason["evidence_refs"])
                reason["evidence_refs"] = reason["evidence_refs"][:10]
                reason["instrument_ids"] = reason["instrument_ids"][:10]
        for key in ("facts", "questions"):
            detail["preparation"][key + "_count"] = len(detail["preparation"][key])
            detail["preparation"][key] = detail["preparation"][key][:10]
        return detail
    return {"source": "mock", "reference_date": service.FIXTURE["reference_date"],
            "customer": service.customer(customer_id or runtime.context.workspace.customer_id)}

@tool
def set_customer_filters(runtime: ToolRuntime[TurnContext], industry: str | None = None, segment: str | None = None, action: str | None = None, query: str | None = None) -> dict:
    """Set exact dropdown/search values. Use 'all' to reset a dropdown. Navigate separately if needed."""
    runtime.context.consume()
    filters = Filters(industry=industry, segment=segment, action=action, query=query)
    sid = runtime.context.workspace.snapshot_id
    options = {p.industry_id or "unknown" for p in data.list_customers(sid)} if sid else set(service.FIXTURE["sector_labels"])
    if sid and segment not in (None, "all"):
        segments = for_snapshot(data.load_snapshot(sid)).payload("segments") or []
        if segment not in {s["id"] for s in segments}:
            raise ValueError("Unknown segment. Inspect available options first.")
    if industry is not None and industry not in {"all", *options}:
        raise ValueError("Unknown industry. Inspect available options first.")
    values = filters.model_dump(exclude_none=True)
    merged = {**runtime.context.workspace.filters.model_dump(), **values}
    runtime.context.workspace.filters = Filters(**merged)
    return emit(runtime, "customers.filters.set", values)

@tool
def navigate_workspace(page: Literal["dashboard", "customers", "follow-ups"], runtime: ToolRuntime[TurnContext]) -> dict:
    """Open one of the three application pages."""
    runtime.context.consume()
    runtime.context.workspace.page = page
    return emit(runtime, "ui.navigate", {"page": page})

@tool
def select_customer(customer_id: str, runtime: ToolRuntime[TurnContext]) -> dict:
    """Open a known customer and clear filters so the selected account remains visible."""
    runtime.context.consume()
    if runtime.context.workspace.snapshot_id:
        data.get_customer_detail(runtime.context.workspace.snapshot_id, customer_id)
    else:
        service.customer(customer_id)
    filters = {"industry": "all", "segment": "all", "action": "all", "query": ""}
    emit(runtime, "customers.filters.set", filters)
    runtime.context.workspace.filters = Filters(**filters)
    runtime.context.workspace.customer_id = customer_id
    runtime.context.workspace.page = "customers"
    emit(runtime, "customers.select", {"customer_id": customer_id})
    return emit(runtime, "ui.navigate", {"page": "customers"})

@tool
def set_customer_tab(tab: Literal["activity", "portfolio", "next-step"], runtime: ToolRuntime[TurnContext]) -> dict:
    """Switch the selected customer's activity, portfolio or next-step detail tab."""
    runtime.context.consume()
    runtime.context.workspace.customer_tab = tab
    return emit(runtime, "ui.control.set", {"control": "customers.tab", "value": tab})

@tool
def set_action_limit(limit: Literal[5, 10, 12], runtime: ToolRuntime[TurnContext]) -> dict:
    """Set Dashboard opportunity list size to 5, 10 or all 12 demo accounts."""
    runtime.context.consume()
    runtime.context.workspace.action_limit = limit
    return emit(runtime, "ui.control.set", {"control": "dashboard.action_limit", "value": limit})

@tool
def create_chart(view: Literal["industry", "activity", "portfolio"], runtime: ToolRuntime[TurnContext], customer_id: str = "") -> dict:
    """Create a chart from service data: industry outlook, customer historical activity, or observed portfolio."""
    runtime.context.consume()
    sid = runtime.context.workspace.snapshot_id
    if sid:
        from collections import Counter
        if view == "industry":
            counts = Counter(p.industry_label or "Unknown" for p in data.list_customers(sid))
            labels, values, unit, kind = list(counts), list(counts.values()), "customers", "bar"
            title = "Customer population by industry"
        else:
            detail = data.get_customer_detail(sid, customer_id or runtime.context.workspace.customer_id)
            title = f"{detail['profile'].display_name} · observed {view}"
            if view == "activity":
                rows = detail["history"][-50:]
                labels, values, unit, kind = [r.month for r in rows], [r.calibration_events for r in rows], "calibrations", "line"
            else:
                rows = sorted(detail["portfolio"], key=lambda r: -r.calibration_events)[:50]
                labels, values, unit, kind = [r.group_label for r in rows], [r.calibration_events for r in rows], "calibrations", "bar"
        if not labels:
            raise ValueError("No observed data for this chart")
        chart = ChartArtifact(id=f"{view}-{sid}-{customer_id or runtime.context.workspace.customer_id}", title=title,
            kind=kind, labels=labels, datasets=[Dataset(name="Observed data", values=values)], unit=unit, source=api_v2._mode(sid))
    elif view == "industry":
        chart = service.industry_chart()
    else:
        c = service.customer(customer_id or runtime.context.workspace.customer_id)
        if view == "activity":
            labels, values, unit, kind = c["months"][:len(c["activity"])], c["activity"], "calibrations", "line"
        else:
            labels = [g["name"] for g in c["groups"]]
            values = [g["instruments"] for g in c["groups"]]
            unit, kind = "instruments", "bar"
        chart = ChartArtifact(id=f"{view}-{c['id']}", title=f"{c['name']} · {view}",
                              kind=kind, labels=labels, datasets=[Dataset(name="Observed demo data", values=values)], unit=unit)
    return emit(runtime, "artifact.created", chart.model_dump())
