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

def _task_summaries(sid):
    rows = api_v2.list_followups(sid)["items"]
    return {"total":len(rows), "items":[{**{k:r[k] for k in ("id","customer_id","customer_name","owner","due_date","status")},
        "email_subject":(r.get("email_draft") or {}).get("subject")} for r in rows[:50]]}

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
                "controls": {"pages": ["dashboard", "customers", "follow-ups", "insights"],
                    "industry": [{"value": i, "label": label} for i, label in sorted({(p.industry_id or "unknown", p.industry_label or "Unknown") for p in profiles})],
                    "segment": [{"value": s["id"], "label": s["label"]} for s in segments],
                    "action": ["all", "upcoming", "inactivity", "discovery"],
                    "retention": ["all", "lower", "moderate", "higher"],
                    "customer_view": ["accounts", "follow-ups"],
                    "customer_tab": ["activity", "portfolio", "next-step"], "customer_activity_view": ["monthly", "quarter"], "action_limit": [5,10,12],
                    "dashboard_display_limit": [100,200,500,1000], "pagination": "20 accounts per customer page; action_limit per dashboard page",
                    "account_owner": "User-supplied teammate or team name (e.g. Team A); no authoritative directory exists"},
                "followups": _task_summaries(sid) if workspace["page"] == "follow-ups" or (workspace["page"] == "customers" and workspace["customer_view"] == "follow-ups") else [],
                "chart_views": ["industry", "activity", "portfolio", "sector_activity", "sector_outlook", "sector_correlation"],
                "opportunities": _opportunity_summary(runtime) if workspace["page"] == "dashboard" else None,
                "insights": {**api_v2.sectors(sid), **api_v2.insights_evidence(sid)} if workspace["page"] == "insights" else None}
    return {**workspace, "data_mode": "mock", "source_reference_date": service.FIXTURE["reference_date"],
            "controls": {"pages": ["dashboard", "customers", "follow-ups", "insights"],
                         "industry": ["all", *service.FIXTURE["sector_labels"]],
                         "segment": ["all", "Frequent", "Intermittent", "Occasional"],
                         "action": ["all", "upcoming", "inactivity", "discovery"],
                         "customer_tab": ["activity", "portfolio", "next-step"], "customer_activity_view": ["monthly", "quarter"],
                         "action_limit": [5, 10, 12]},
            "followups": service.list_followups() if workspace["page"] == "follow-ups" else [],
            "chart_views": ["industry", "activity", "portfolio"]}

@tool
def list_customers(runtime: ToolRuntime[TurnContext], industry: str | None = None, segment: str | None = None, action: str | None = None, retention: Literal["all", "lower", "moderate", "higher"] | None = None, query: str | None = None, offset: int | None = None, limit: int = 10) -> dict:
    """Read a short ranked account list (default 10; limit 1–50), inheriting current CUSTOMER filters. Request only as many accounts as needed. Use all/empty query to reset. Retention tiers are review signals, not churn probabilities. Does not change UI. Use get_opportunity_cohort for date-scoped Dashboard members."""
    runtime.context.consume()
    current = runtime.context.workspace.filters
    industry = industry if industry is not None else current.industry or "all"
    segment = segment if segment is not None else current.segment or "all"
    action = action if action is not None else current.action or "all"
    retention = retention if retention is not None else current.retention or "all"
    query = query if query is not None else current.query or ""
    offset = runtime.context.workspace.customer_offset if offset is None else offset
    if offset < 0:
        raise ValueError("Offset must be nonnegative")
    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50")
    if runtime.context.workspace.snapshot_id:
        result = api_v2.list_customers(snapshot_id=runtime.context.workspace.snapshot_id,
            industry_id=None if industry == "all" else industry, segment_id=None if segment == "all" else segment,
            action=None if action == "all" else action, retention=None if retention == "all" else retention,
            query=query, sort="priority", limit=limit, offset=offset)
        for item in result["items"]:
            action = item.get("primary_action")
            if action:
                item["reason_count"] = len(action["reasons"])
                action["reasons"] = [{k: r[k] for k in ("id", "type", "title", "explanation", "quantity", "quantity_unit", "status")} for r in action["reasons"][:3]]
        return result
    rows = service.filter_customers(Filters(industry=industry, segment=segment, action=action, query=query))
    return {"source": "mock", "total": len(rows), "customers": [
        {k: c[k] for k in ("id", "name", "industry", "segment", "action", "priority", "reason")}
        for c in rows[offset:offset+limit]]}

@tool
def open_customer_preview(customer_id: str, runtime: ToolRuntime[TurnContext]) -> dict:
    """Open a known account's Dashboard preparation drawer, keeping the opportunity filters/cluster. For Customers use select_customer. Does not alter workflow."""
    runtime.context.consume()
    if not runtime.context.workspace.snapshot_id:
        raise ValueError("Customer preview requires the integrated workspace")
    data.get_customer_detail(runtime.context.workspace.snapshot_id, customer_id)
    runtime.context.workspace.customer_id = customer_id
    runtime.context.workspace.opportunity_drawer_id = customer_id
    runtime.context.workspace.customer_tab = "activity"
    runtime.context.workspace.page = "dashboard"
    runtime.context.workspace.page_snapshot = None
    emit(runtime, "ui.control.set", {"control": "dashboard.preview", "value": customer_id})
    return emit(runtime, "ui.navigate", {"page": "dashboard"})

@tool
def set_workspace_view(runtime: ToolRuntime[TurnContext], customer_view: Literal["accounts", "follow-ups"] | None = None,
    customer_offset: int | None = None, dashboard_offset: int | None = None,
    display_limit: Literal[100,200,500,1000] | None = None, close_preview: bool = False) -> dict:
    """Switch Customers Accounts/Follow-ups, paginate either list (offset is zero-based), change Dashboard plotted sample, or close its preview. Sample never changes cohort totals. Opens Customers when customer_view supplied."""
    runtime.context.consume()
    w = runtime.context.workspace
    if customer_offset is not None and (customer_offset < 0 or customer_offset % 20):
        raise ValueError("Customer offset must be a nonnegative multiple of 20")
    if dashboard_offset is not None and (dashboard_offset < 0 or dashboard_offset % w.action_limit):
        raise ValueError("Dashboard offset must be a multiple of the current action limit")
    commands = []
    for control, value, field in (("customers.view",customer_view,"customer_view"),
        ("customers.offset",customer_offset,"customer_offset"), ("dashboard.offset",dashboard_offset,"dashboard_offset"),
        ("dashboard.display_limit",display_limit,"opportunity_display_limit")):
        if value is not None:
            setattr(w, field, value)
            commands.append(emit(runtime, "ui.control.set", {"control":control,"value":value}))
    if close_preview:
        w.opportunity_drawer_id = None
        commands.append(emit(runtime,"ui.control.set",{"control":"dashboard.preview","value":None}))
    if customer_view is not None:
        w.page = "customers"
        commands.append(emit(runtime,"ui.navigate",{"page":"customers"}))
    if not commands:
        raise ValueError("Specify a view, pagination offset, display limit, or close_preview")
    w.page_snapshot = None
    return {"status":"proposed", "events":[c["event"] for c in commands]}

@tool
def get_customer_evidence(runtime: ToolRuntime[TurnContext], customer_id: str = "") -> dict:
    """Read selected or specified customer history, forecast, reasons and observed portfolio from the active snapshot."""
    runtime.context.consume()
    if runtime.context.workspace.snapshot_id:
        scope = runtime.context.workspace.opportunity_filters if runtime.context.workspace.page == "dashboard" else None
        params = {"window_days": scope.window_days, "include_past_due": scope.include_past_due, "include_inferred": scope.include_inferred} if scope else {}
        detail = api_v2.customer_detail(customer_id or runtime.context.workspace.customer_id, runtime.context.workspace.snapshot_id, **params)
        detail["requirement_count"] = sum(detail["requirement_tier_counts"].values())
        detail["requirement_tier_counts"] = detail["requirement_tier_counts"]
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
def set_customer_filters(runtime: ToolRuntime[TurnContext], industry: str | None = None, segment: str | None = None, action: str | None = None, retention: str | None = None, query: str | None = None) -> dict:
    """Set exact dropdown/search values. Use 'all' to reset a dropdown. Action values: upcoming (shown as Calibration need), inactivity (Reduced activity), discovery (Service to explore). Retention is a measured risk tier (lower/moderate/higher). Navigate separately if needed."""
    runtime.context.consume()
    filters = Filters(industry=industry, segment=segment, action=action, retention=retention, query=query)
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
    runtime.context.workspace.customer_offset = 0
    runtime.context.workspace.page_snapshot = None
    runtime.context.workspace.visible_customer_ids = []
    return emit(runtime, "customers.filters.set", values)

@tool
def navigate_workspace(page: Literal["dashboard", "customers", "follow-ups", "insights"], runtime: ToolRuntime[TurnContext]) -> dict:
    """Open Dashboard, Customers or Insights; follow-ups remains a compatible legacy route."""
    runtime.context.consume()
    runtime.context.workspace.page = page
    runtime.context.workspace.page_snapshot = None
    runtime.context.workspace.visible_customer_ids = []
    if page == "follow-ups":
        runtime.context.workspace.customer_view = "follow-ups"
    return emit(runtime, "ui.navigate", {"page": page})

@tool
def select_customer(customer_id: str, runtime: ToolRuntime[TurnContext]) -> dict:
    """Open a known customer and clear filters so the selected account remains visible."""
    runtime.context.consume()
    if runtime.context.workspace.snapshot_id:
        data.get_customer_detail(runtime.context.workspace.snapshot_id, customer_id)
    else:
        service.customer(customer_id)
    filters = {"industry": "all", "segment": "all", "action": "all", "retention": "all", "query": ""}
    emit(runtime, "customers.filters.set", filters)
    runtime.context.workspace.filters = Filters(**filters)
    runtime.context.workspace.customer_id = customer_id
    runtime.context.workspace.page_snapshot = None
    runtime.context.workspace.customer_view = "accounts"
    runtime.context.workspace.page = "customers"
    emit(runtime, "customers.select", {"customer_id": customer_id})
    return emit(runtime, "ui.navigate", {"page": "customers"})

@tool
def set_customer_tab(tab: Literal["activity", "portfolio", "next-step"], runtime: ToolRuntime[TurnContext], activity_view: Literal["monthly", "quarter"] | None = None) -> dict:
    """Switch the customer detail tab; optionally show 24 months (monthly) or 3 months (quarter) of historical bars, followed by a shaded three-month forecast window."""
    runtime.context.consume()
    runtime.context.workspace.customer_tab = tab
    runtime.context.workspace.page_snapshot = None
    payload = {"control": "customers.tab", "value": tab}
    if activity_view is not None:
        runtime.context.workspace.customer_activity_view = activity_view
        payload["activity_view"] = activity_view
    return emit(runtime, "ui.control.set", payload)

@tool
def set_action_limit(limit: Literal[5, 10, 12], runtime: ToolRuntime[TurnContext]) -> dict:
    """Set Dashboard shortlist size to 5, 10 or 12 accounts."""
    runtime.context.consume()
    runtime.context.workspace.action_limit = limit
    runtime.context.workspace.dashboard_offset = 0
    runtime.context.workspace.page_snapshot = None
    return emit(runtime, "ui.control.set", {"control": "dashboard.action_limit", "value": limit})

@tool
def create_chart(view: Literal["industry", "activity", "portfolio", "sector_activity", "sector_outlook", "sector_correlation"], runtime: ToolRuntime[TurnContext], customer_id: str = "") -> dict:
    """Create a chart INSIDE CHAT ONLY: industry population, customer observed activity/portfolio, sector activity, next-month sector outlook, or movement correlation. Call multiple times for multiple charts. Sector correlation is descriptive, not a joint forecast."""
    runtime.context.consume()
    sid = runtime.context.workspace.snapshot_id
    if sid and view.startswith("sector_"):
        sectors = api_v2.sectors(sid)["sectors"]
        if view == "sector_activity":
            rows = sorted(sectors["history"], key=lambda r: -sum(p["calibration_events"] for p in r["monthly"]))[:5]
            if not rows: raise ValueError("Sector history unavailable")
            labels = [p["month"] for p in rows[0]["monthly"]][-50:]
            datasets = [Dataset(name=r["label"], values=[p["calibration_events"] for p in r["monthly"]][-50:]) for r in rows]
            chart = ChartArtifact(id=f"{view}-{sid}", title="Observed sector activity · top 5 by historical volume", kind="line", labels=labels, datasets=datasets, unit="calibrations", source=api_v2._mode(sid))
        elif view == "sector_outlook":
            forecasts = [r for r in sectors["forecasts"] if r["expected"] is not None]
            if not forecasts: raise ValueError("Sector forecast unavailable")
            names = {r["industry_id"]:r["label"] for r in sectors["history"]}
            chart = ChartArtifact(id=f"{view}-{sid}", title=f"Sector outlook · {forecasts[0]['forecast_month']}", kind="bar",
                labels=[names[r["industry_id"]] for r in forecasts], datasets=[Dataset(name="Expected calibrations",values=[r["expected"] for r in forecasts])], unit="calibrations", source=api_v2._mode(sid))
        else:
            corr = sectors["correlation"]
            if not corr: raise ValueError("Sector correlation unavailable")
            chart = ChartArtifact(id=f"{view}-{sid}", title=f"Sector movement correlation · {corr['window_start']}–{corr['window_end']}", kind="heatmap", labels=corr["labels"],
                datasets=[Dataset(name=name,values=row) for name,row in zip(corr["labels"],corr["values"])], unit="correlation", source=api_v2._mode(sid))
        return emit(runtime,"artifact.created",chart.model_dump())
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


def _opportunity_summary(runtime, cluster_id=None, use_current=True):
    workspace = runtime.context.workspace
    if not workspace.snapshot_id:
        return {"status": "unavailable", "reason": "Opportunity models require a v2 snapshot"}
    from ..data.opportunities import compose
    selected = workspace.opportunity_cluster if use_current else cluster_id
    result = compose(workspace.snapshot_id, api_v2._metadata(workspace.snapshot_id), workspace.opportunity_filters,
        selected, display_limit=1, limit=workspace.action_limit, offset=workspace.dashboard_offset, scenario=workspace.commercial_scenario).model_dump()
    return {k: result[k] for k in ("metadata", "model_version", "selection_revision", "filters", "selected_cluster",
        "matching_count", "selected_count", "unassigned_count", "filter_options", "clusters", "quality", "metrics",
        "forecast_supported", "overdue_count", "unassigned_owner_count", "items", "scenario")}

@tool
def get_opportunity_cohort(runtime: ToolRuntime[TurnContext], cluster_id: str | None = None, use_current_selection: bool = True) -> dict:
    """Read full-cohort totals and ranked members for current opportunity filters. Use current selection or inspect a specified cluster without changing the page."""
    runtime.context.consume()
    return _opportunity_summary(runtime, cluster_id, use_current_selection)

@tool
def set_opportunity_filters(runtime: ToolRuntime[TurnContext], industry: str | None = None, segment: str | None = None,
    group: str | None = None, purpose: Literal["all", "upcoming", "inactivity", "discovery"] | None = None,
    window_days: Literal[30,60,90] | None = None, include_inferred: bool | None = None, include_past_due: bool | None = None) -> dict:
    """Change Dashboard opportunity filters; exact sector/equipment/segment IDs come from get_opportunity_cohort. Reset a dropdown with all. Clears cluster selection."""
    runtime.context.consume()
    from ...contracts.opportunities import OpportunityFilters
    values = {k:v for k,v in locals().items() if k != "runtime" and v is not None and k in OpportunityFilters.model_fields}
    merged = OpportunityFilters(**{**runtime.context.workspace.opportunity_filters.model_dump(), **values})
    from ..data.opportunities import compose
    compose(runtime.context.workspace.snapshot_id, api_v2._metadata(runtime.context.workspace.snapshot_id), merged, display_limit=1, limit=1)
    runtime.context.workspace.page_snapshot = None
    runtime.context.workspace.opportunity_filters = merged
    runtime.context.workspace.opportunity_cluster = None
    runtime.context.workspace.dashboard_offset = 0
    runtime.context.workspace.visible_customer_ids = []
    emit(runtime, "opportunities.filters.set", values)
    runtime.context.workspace.page = "dashboard"
    return emit(runtime, "ui.navigate", {"page":"dashboard"})

@tool
def select_opportunity_cluster(cluster_id: Literal["all", "act-now", "plan-larger", "focused-follow-up", "nurture", "needs-evidence"], runtime: ToolRuntime[TurnContext]) -> dict:
    """Select a Dashboard opportunity group and synchronize cards/table. all resets selection. Group labels are available in get_opportunity_cohort."""
    runtime.context.consume()
    runtime.context.workspace.page_snapshot = None
    runtime.context.workspace.opportunity_cluster = None if cluster_id == "all" else cluster_id
    runtime.context.workspace.page = "dashboard"
    emit(runtime, "opportunities.cluster.select", {"cluster_id":runtime.context.workspace.opportunity_cluster})
    return emit(runtime, "ui.navigate", {"page":"dashboard"})
