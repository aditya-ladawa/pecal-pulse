"""Versioned sales/UI boundary. Commands contain data, never executable UI code."""

from typing import Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Filters(StrictModel):
    industry: str | None = None
    segment: Literal["all", "Frequent", "Intermittent", "Occasional"] | None = None
    action: Literal["all", "upcoming", "inactivity", "discovery"] | None = None
    query: str | None = None


class NavigatePayload(StrictModel):
    page: Literal["dashboard", "customers", "follow-ups"]


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
    values: list[float]


class ChartArtifact(StrictModel):
    id: str
    title: str
    kind: Literal["bar", "line"]
    labels: list[str] = Field(min_length=1, max_length=50)
    datasets: list[Dataset] = Field(min_length=1, max_length=5)
    unit: Literal["calibrations", "instruments", "customers"]
    source: Literal["mock"] = "mock"

    @model_validator(mode="after")
    def matching_lengths(self):
        if any(len(d.values) != len(self.labels) for d in self.datasets):
            raise ValueError("Every dataset must match the label count")
        return self


class AddArtifact(StrictModel):
    type: Literal["artifact.created"]
    payload: ChartArtifact


class CustomerTabControl(StrictModel):
    control: Literal["customers.tab"]
    value: Literal["activity", "portfolio", "next-step"]

class ActionLimitControl(StrictModel):
    control: Literal["dashboard.action_limit"]
    value: Literal[5, 10, 12]

class SetControl(StrictModel):
    type: Literal["ui.control.set"]
    payload: Annotated[CustomerTabControl | ActionLimitControl, Field(discriminator="control")]

UiCommand = Annotated[
    Navigate | SetFilters | SelectCustomer | AddArtifact | SetControl, Field(discriminator="type")
]


class ChatContext(StrictModel):
    page: Literal["dashboard", "customers", "follow-ups"] = "dashboard"
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
