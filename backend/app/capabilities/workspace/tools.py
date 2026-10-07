"""Read fresh page context and propose constrained UI actions via the event router."""
from typing import Literal
from langchain.tools import tool, ToolRuntime
from pydantic import TypeAdapter
from ...agents.contracts import TurnContext
from ..sales import service
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
    rows = service.filter_customers(Filters(industry=industry, segment=segment, action=action, query=query))
    return {"source": "mock", "total": len(rows), "customers": [
        {k: c[k] for k in ("id", "name", "industry", "segment", "action", "priority", "reason")}
        for c in rows[:50]]}

@tool
def get_customer_evidence(runtime: ToolRuntime[TurnContext], customer_id: str = "") -> dict:
    """Read selected or specified customer's history, forecast, reason and observed portfolio. Synthetic demo only."""
    runtime.context.consume()
    return {"source": "mock", "reference_date": service.FIXTURE["reference_date"],
            "customer": service.customer(customer_id or runtime.context.workspace.customer_id)}

@tool
def set_customer_filters(runtime: ToolRuntime[TurnContext], industry: str | None = None, segment: str | None = None, action: str | None = None, query: str | None = None) -> dict:
    """Set exact dropdown/search values. Use 'all' to reset a dropdown. Navigate separately if needed."""
    runtime.context.consume()
    filters = Filters(industry=industry, segment=segment, action=action, query=query)
    if industry is not None and industry not in ["all", *service.FIXTURE["sector_labels"]]:
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
    if view == "industry":
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
