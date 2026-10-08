"""Versioned sales/UI boundary. Commands contain data, never executable UI code."""

from typing import Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from ...contracts.opportunities import OpportunityFilters


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Filters(StrictModel):
    industry: str | None = None
    segment: str | None = Field(default=None, max_length=100)
    action: Literal["all", "upcoming", "inactivity", "discovery"] | None = None
    retention: Literal["all", "lower", "moderate", "higher"] | None = None
    query: str | None = None


class NavigatePayload(StrictModel):
    page: Literal["dashboard", "customers", "follow-ups", "insights"]


class Navigate(StrictModel):
    type: Literal["ui.navigate"]
    payload: NavigatePayload


class SetFilters(StrictModel):
    type: Literal["customers.filters.set"]
    payload: Filters


class SelectPayload(StrictModel):
    customer_id: str


class SelectCustomer(StrictModel):
    type: Literal["customers.select"]
    payload: SelectPayload


class Dataset(StrictModel):
    name: str
    values: list[float | None]


class ChartArtifact(StrictModel):
    id: str
    title: str
    kind: Literal["bar", "line", "heatmap"]
    labels: list[str] = Field(min_length=1, max_length=50)
    datasets: list[Dataset] = Field(min_length=1, max_length=50)
    unit: Literal["calibrations", "instruments", "customers", "correlation"]
    source: Literal["mock", "historical"] = "mock"

    @model_validator(mode="after")
    def matching_lengths(self):
        if any(len(d.values) != len(self.labels) for d in self.datasets):
            raise ValueError("Every dataset must match the label count")
        if self.kind == "heatmap" and (self.unit != "correlation" or len(self.datasets) != len(self.labels)):
            raise ValueError("Correlation heatmap must be square")
        if self.kind != "heatmap" and any(v is None for d in self.datasets for v in d.values):
            raise ValueError("Only heatmaps accept unsupported null cells")
        return self


class AddArtifact(StrictModel):
    type: Literal["artifact.created"]
    payload: ChartArtifact


class CustomerTabControl(StrictModel):
    control: Literal["customers.tab"]
    value: Literal["activity", "portfolio", "next-step"]
    activity_view: Literal["monthly", "quarter"] | None = None

class ActionLimitControl(StrictModel):
    control: Literal["dashboard.action_limit"]
    value: Literal[5, 10, 12]

class CustomerViewControl(StrictModel):
    control: Literal["customers.view"]
    value: Literal["accounts", "follow-ups"]

class PaginationControl(StrictModel):
    control: Literal["customers.offset", "dashboard.offset"]
    value: int = Field(ge=0, le=100000)

class DisplayLimitControl(StrictModel):
    control: Literal["dashboard.display_limit"]
    value: Literal[100, 200, 500, 1000]

class PreviewControl(StrictModel):
    control: Literal["dashboard.preview"]
    value: str | None = Field(default=None, max_length=100)

class SetControl(StrictModel):
    type: Literal["ui.control.set"]
    payload: Annotated[CustomerTabControl | ActionLimitControl | CustomerViewControl | PaginationControl | DisplayLimitControl | PreviewControl, Field(discriminator="control")]


class OpportunityFilterPatch(StrictModel):
    industry: str | None = None
    segment: str | None = None
    group: str | None = None
    purpose: Literal["all", "upcoming", "inactivity", "discovery"] | None = None
    window_days: Literal[30,60,90] | None = None
    include_inferred: bool | None = None
    include_past_due: bool | None = None

class SetOpportunityFilters(StrictModel):
    type: Literal["opportunities.filters.set"]
    payload: OpportunityFilterPatch

class ClusterPayload(StrictModel):
    cluster_id: Literal["act-now", "plan-larger", "focused-follow-up", "nurture", "needs-evidence"] | None = None

class SelectOpportunityCluster(StrictModel):
    type: Literal["opportunities.cluster.select"]
    payload: ClusterPayload

UiCommand = Annotated[
    Navigate | SetFilters | SelectCustomer | AddArtifact | SetControl | SetOpportunityFilters | SelectOpportunityCluster, Field(discriminator="type")
]


class ChatContext(StrictModel):
    page: Literal["dashboard", "customers", "follow-ups", "insights"] = "dashboard"
    customer_id: str | None = None
    filters: Filters = Field(default_factory=Filters)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    context: ChatContext = Field(default_factory=ChatContext)


class FollowupCreate(StrictModel):
    customer_id: str
    owner: str = Field(min_length=1, max_length=100)
    due_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field(min_length=1, max_length=2000)
    outcome: Literal[
        "Timing to confirm",
        "Timing changed",
        "Need confirmed",
        "Not applicable",
        "Equipment retired",
    ]

    @model_validator(mode="after")
    def valid_date(self):
        from datetime import date

        date.fromisoformat(self.due_date)
        return self


class FollowupUpdate(StrictModel):
    status: Literal["open", "done"]
