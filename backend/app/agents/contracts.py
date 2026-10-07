from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID
from pydantic import Field
from ..capabilities.sales.models import ChatContext, StrictModel

class PageMetric(StrictModel):
    label: str = Field(max_length=150)
    value: float
    unit: str = Field(max_length=50)
    scope: str = Field(max_length=300)
    definition: str = Field(max_length=1000)

class PageSnapshot(StrictModel):
    page: Literal["dashboard", "customers", "follow-ups"]
    title: str = Field(max_length=150)
    metrics: list[PageMetric] = Field(default_factory=list, max_length=20)

class WorkspaceContext(ChatContext):
    page_snapshot: PageSnapshot | None = None
    snapshot_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$", max_length=100)
    reference_date: str | None = None
    visible_customer_ids: list[str] = Field(default_factory=list, max_length=100)
    action_limit: Literal[5, 10, 12] = 10
    customer_tab: Literal["activity", "portfolio", "next-step"] = "activity"
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
