from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID
from pydantic import Field
from ..capabilities.sales.models import ChatContext, StrictModel
from ..contracts.opportunities import OpportunityFilters, ScenarioAssumptions

class PageMetric(StrictModel):
    label: str = Field(max_length=150)
    value: float | None
    unit: str = Field(max_length=50)
    scope: str = Field(max_length=300)
    definition: str = Field(max_length=1000)

class PageSnapshot(StrictModel):
    page: Literal["dashboard", "customers", "follow-ups", "insights"]
    title: str = Field(max_length=150)
    metrics: list[PageMetric] = Field(default_factory=list, max_length=20)
    sections: list[str] = Field(default_factory=list, max_length=20)
    visible_rows: list[dict] = Field(default_factory=list, max_length=100)
    loading: bool = False

class WorkspaceContext(ChatContext):
    opportunity_filters: OpportunityFilters = Field(default_factory=OpportunityFilters)
    opportunity_cluster: Literal["act-now", "plan-larger", "focused-follow-up", "nurture", "needs-evidence"] | None = None
    opportunity_model_version: str | None = None
    opportunity_selection_revision: str | None = None
    commercial_scenario: ScenarioAssumptions | None = None
    customer_view: Literal["accounts", "follow-ups"] = "accounts"
    customer_offset: int = Field(default=0, ge=0, le=100000)
    dashboard_offset: int = Field(default=0, ge=0, le=100000)
    opportunity_drawer_id: str | None = None
    opportunity_display_limit: Literal[100, 200, 500, 1000] = 200
    current_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    page_snapshot: PageSnapshot | None = None
    snapshot_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$", max_length=100)
    reference_date: str | None = None
    visible_customer_ids: list[str] = Field(default_factory=list, max_length=100)
    action_limit: Literal[5, 10, 12] = 10
    customer_tab: Literal["activity", "portfolio", "next-step"] = "activity"
    customer_activity_view: Literal["monthly", "quarter"] = "monthly"
    artifact_ids: list[str] = Field(default_factory=list, max_length=50)

class AgentChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    context: WorkspaceContext = Field(default_factory=WorkspaceContext)
    thread_id: UUID | None = None

@dataclass
class TurnContext:
    workspace: WorkspaceContext
    events: list[dict] = field(default_factory=list)
    tool_calls: int = 0

    def consume(self):
        self.tool_calls += 1
        if self.tool_calls > 12:
            raise ValueError("Tool budget exceeded; please narrow the request.")
