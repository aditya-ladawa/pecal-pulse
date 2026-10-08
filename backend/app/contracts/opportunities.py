"""Opportunity map and cohort totals: scores, forecasts and scenarios have explicit units."""
from typing import Literal
from pydantic import Field
from .sales_v2 import StrictModel, ResponseMetadata, Followup

class OpportunityFilters(StrictModel):
    industry: str = 'all'
    segment: str = 'all'
    group: str = 'all'
    purpose: Literal['all', 'upcoming', 'inactivity', 'discovery'] = 'all'
    window_days: Literal[30, 60, 90] = 90
    include_inferred: bool = True
    include_past_due: bool = False

class ScenarioAssumptions(StrictModel):
    currency: Literal['EUR'] = 'EUR'
    unit_contribution: float = Field(ge=0, le=100000)
    source: str = Field(min_length=1, max_length=150)

class OpportunityPoint(StrictModel):
    customer_id: str
    display_name: str
    industry_id: str
    industry_label: str
    segment_id: str | None = None
    segment_label: str | None = None
    cluster_id: str | None = None
    urgency_score: float | None = Field(default=None, ge=0, le=100)
    size_score: float | None = Field(default=None, ge=0, le=100)
    size_basis: str | None = None
    components: dict[str, float | None]
    due_recorded: int = Field(ge=0)
    due_inferred: int = Field(ge=0)
    due_selected_category: int = Field(ge=0)
    activity_flagged: bool
    inactivity_supported: bool
    activity_probability: float | None = Field(default=None, ge=0, le=1)
    expected_calibrations: float | None = Field(default=None, ge=0)
    forecast_start: str | None = None
    forecast_end: str | None = None
    priority_score: float = Field(ge=0, le=100)
    priority_components: dict[str, float | None] = Field(default_factory=dict)
    reasons: list[str]
    reason_types: list[str]
    next_action: str
    readiness: str
    owner: str | None = None
    group_ids: list[str]

class ClusterSummary(StrictModel):
    id: str
    label: str
    color: str
    urgency: float
    size: float
    matching_count: int

class CohortMetric(StrictModel):
    label: str
    value: float | None
    unit: str
    scope: str
    definition: str
    caption: str

class OpportunityResponse(StrictModel):
    metadata: ResponseMetadata
    rule_version: str
    ranking_version: str = "rank-v2"
    ranking_weights: dict[str, float] = Field(default_factory=dict)
    model_version: str
    selection_revision: str
    filters: OpportunityFilters
    selected_cluster: str | None
    filter_options: dict[str, list[dict[str, str]]]
    matching_count: int
    selected_count: int
    unassigned_count: int
    displayed_count: int
    points: list[OpportunityPoint]
    clusters: list[ClusterSummary]
    quality: dict
    metrics: list[CohortMetric]
    recorded_total: int
    inferred_total: int
    forecast_supported: int
    inactivity_supported: int
    overdue_count: int
    unassigned_owner_count: int
    due_followups: list[Followup]
    items: list[OpportunityPoint]
    limit: int
    offset: int
    scenario: dict | None = None
