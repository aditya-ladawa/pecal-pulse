"""Shared v2 contracts (plan §4). Owned by Member 1; Members 2/3 import these.

Conventions: opaque string IDs consistent across exports; dates YYYY-MM-DD;
months YYYY-MM; null for unknown (never NaN/Infinity); probabilities and
prevalence in [0,1]; priority score in [0,100]; correlations in [-1,1].
Every artifact shares snapshot_id / reference_date / model-or-rule version.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


DateStr = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
MonthStr = Field(pattern=r"^\d{4}-\d{2}$")
Probability = Field(ge=0, le=1)


# ---------------------------------------------------------------------------
# §4A — Member 1 snapshot exports (local tables/JSON, not passed through chat)
# ---------------------------------------------------------------------------


class MonthlyHistoryRow(StrictModel):
    customer_id: str
    month: str = MonthStr
    calibration_events: int = Field(ge=0)
    distinct_instruments: int = Field(ge=0)
    equipment_group_count: int = Field(ge=0)
    lab_count: int = Field(ge=0)


class CustomerProfile(StrictModel):
    customer_id: str
    display_name: str = Field(min_length=1)
    name_source: Literal["verified", "identifier"]
    industry_id: str | None = None
    industry_label: str | None = None


class PortfolioRow(StrictModel):
    customer_id: str
    group_id: str
    group_label: str
    # Group-level distinct-instrument counts are not in the current export
    # (it counts calibration rows per group). Null means not exported,
    # never zero observed.
    distinct_instruments: int | None = Field(default=None, ge=0)
    calibration_events: int = Field(ge=0)
    window_start: str = DateStr
    window_end: str = DateStr


class InstrumentRecord(StrictModel):
    instrument_id: str
    current_customer_id: str | None = None
    group_id: str | None = None
    last_calibration_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    recorded_due_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    nominal_interval_months: int | None = Field(default=None, gt=0)
    stopped: bool | None = None
    quality_flags: list[str] = Field(default_factory=list)


class InstrumentEvent(StrictModel):
    event_id: str
    instrument_id: str
    historical_customer_id: str
    calibration_date: str = DateStr
    group_id: str | None = None


class SnapshotManifest(StrictModel):
    snapshot_id: str
    extracted_at: str
    reference_date: str = DateStr
    complete_through_month: str = MonthStr
    history_start: str = MonthStr
    source_tables: list[str] = Field(min_length=1)
    row_counts: dict[str, int]
    field_coverage: dict[str, float]
    quality_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def counts_cover_tables(self):
        missing = [t for t in self.source_tables if t not in self.row_counts]
        if missing:
            raise ValueError(f"row_counts missing source tables: {missing}")
        return self


# ---------------------------------------------------------------------------
# §4B — Member 2 prediction outputs (produced by Member 2, served by Member 1)
# ---------------------------------------------------------------------------


class Support(StrictModel):
    status: Literal["supported", "insufficient_history", "unavailable"]
    reason: str | None = None
    history_months: int = Field(ge=0)
    active_months: int = Field(ge=0)


class VolumeMonthPoint(StrictModel):
    month: str = MonthStr
    expected: float = Field(ge=0)
    lower: float | None = Field(default=None, ge=0)
    upper: float | None = Field(default=None, ge=0)


class VolumeForecast(StrictModel):
    metric: Literal["calibration_events", "order_positions"]
    horizon_months: Literal[3] = 3
    window_start: str = MonthStr
    window_end: str = MonthStr
    expected_total: float | None = Field(default=None, ge=0)
    lower: float | None = Field(default=None, ge=0)
    upper: float | None = Field(default=None, ge=0)
    interval_level: float | None = Field(default=None, gt=0, lt=1)
    monthly: list[VolumeMonthPoint] | None = None
    method: str
    model_version: str
    support: Support


class ActivityPrediction(StrictModel):
    target: Literal["any_calibration_next_3_months"] = "any_calibration_next_3_months"
    probability: float | None = Probability
    window_start: str = MonthStr
    window_end: str = MonthStr
    model_version: str
    support: Support


class InactivityEvidence(StrictModel):
    flagged: bool
    recency_to_cadence: float | None = Field(default=None, ge=0)
    recent_volume: int = Field(ge=0)
    baseline_volume: float | None = Field(default=None, ge=0)
    deficit_fraction: float | None = None
    rule_version: str
    reasons: list[str] = Field(default_factory=list)
    support: Support


class FeatureContribution(StrictModel):
    feature: str
    value: float
    contribution: float | None = None


class CustomerPrediction(StrictModel):
    snapshot_id: str
    customer_id: str
    reference_date: str = DateStr
    segment_id: str | None = None
    activity: ActivityPrediction
    calibration_volume: VolumeForecast
    recency_months: int | None = Field(default=None, ge=0)
    cadence_months: float | None = Field(default=None, gt=0)
    inactivity: InactivityEvidence
    explanation: list[FeatureContribution] = Field(default_factory=list)


class SegmentSummary(StrictModel):
    id: str
    label: str
    method: Literal["kmeans"] = "kmeans"
    customers: int = Field(ge=0)
    description: str
    feature_means: dict[str, float] = Field(default_factory=dict)


class SectorCorrelation(StrictModel):
    industry_ids: list[str] = Field(min_length=1)
    labels: list[str] = Field(min_length=1)
    values: list[list[float | None]]
    pair_sample_counts: list[list[int]]
    method: Literal["pearson_log1p_monthly_change"] = "pearson_log1p_monthly_change"
    window_start: str = MonthStr
    window_end: str = MonthStr
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def square_aligned(self):
        n = len(self.industry_ids)
        if len(self.labels) != n:
            raise ValueError("labels must align with industry_ids")
        if len(self.values) != n or any(len(row) != n for row in self.values):
            raise ValueError("values must be a square matrix over industry_ids")
        if len(self.pair_sample_counts) != n or any(
            len(row) != n for row in self.pair_sample_counts
        ):
            raise ValueError("pair_sample_counts must be a square matrix over industry_ids")
        for row in self.values:
            for v in row:
                if v is not None and not -1 <= v <= 1:
                    raise ValueError("correlations must be in [-1,1] or null")
        return self


# ---------------------------------------------------------------------------
# §4C — Member 1/3 requirements, actions and preparation
# ---------------------------------------------------------------------------


class Requirement(StrictModel):
    id: str
    customer_id: str
    instrument_id: str
    group_id: str | None = None
    kind: Literal["recorded", "nominal_interval", "repeat_history", "unknown"]
    window_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    window_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    method: str
    evidence_dates: list[str] = Field(default_factory=list)
    positive_gap_count: int = Field(ge=0, default=0)
    stopped: bool | None = None
    eligibility: Literal["review_required", "eligible", "excluded"]
    unknowns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def stopped_is_excluded(self):
        if self.stopped is True and self.eligibility != "excluded":
            raise ValueError("stopped instruments must be excluded")
        return self


class ActionReason(StrictModel):
    id: str
    type: Literal["upcoming", "inactivity", "discovery"]
    title: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    instrument_ids: list[str] = Field(default_factory=list)
    quantity: float | None = Field(default=None, ge=0)
    quantity_unit: Literal["instruments", "calibration_events", "categories"] | None = None
    window_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    window_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Literal["review_required", "eligible", "suppressed"] = "review_required"
    suppression_reason: str | None = None
    unknowns: list[str] = Field(default_factory=list)


class PriorityComponents(StrictModel):
    timing: float | None = Field(default=None, ge=0, le=1)
    quantity: float | None = Field(default=None, ge=0, le=1)
    activity_deviation: float | None = Field(default=None, ge=0, le=1)
    evidence: float | None = Field(default=None, ge=0, le=1)
    expected_value: float | None = Field(default=None, ge=0, le=1)


class AccountAction(StrictModel):
    snapshot_id: str
    customer_id: str
    primary_type: Literal["upcoming", "inactivity", "discovery"]
    reasons: list[ActionReason] = Field(min_length=1)
    priority_score: float = Field(ge=0, le=100)
    components: PriorityComponents = Field(default_factory=PriorityComponents)
    ranking_version: str
    weights: dict[str, float] = Field(default_factory=dict)
    readiness: Literal["review_required", "eligible"]
    suggested_next_step: str


class PeerOpportunity(StrictModel):
    group_id: str
    group_label: str
    industry_id: str
    peer_count: int = Field(ge=0)
    peers_with_group: int = Field(ge=0)
    prevalence: float = Probability
    window_start: str = DateStr
    window_end: str = DateStr
    question: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def prevalence_matches_counts(self):
        if self.peer_count == 0 and self.peers_with_group != 0:
            raise ValueError("peers_with_group requires a nonzero peer denominator")
        return self


class PreparationFact(StrictModel):
    text: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class PreparationCard(StrictModel):
    customer_id: str
    reference_date: str = DateStr
    facts: list[PreparationFact] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    suggested_next_step: str


# ---------------------------------------------------------------------------
# §4D — screen responses (served by Member 1 composition)
# ---------------------------------------------------------------------------


class ModuleReadiness(StrictModel):
    status: Literal["ready", "unavailable"]
    reason: str | None = None


class ResponseMetadata(StrictModel):
    contract_version: Literal["2"] = "2"
    snapshot_id: str
    reference_date: str = DateStr
    mode: Literal["mock", "historical"]
    workflow_today: str = DateStr
    modules: dict[str, ModuleReadiness] = Field(default_factory=dict)


class CustomerSummary(StrictModel):
    profile: CustomerProfile
    segment_id: str | None = None
    primary_action: AccountAction | None = None
    recency_months: int | None = Field(default=None, ge=0)
    activity_probability: float | None = Field(default=None, ge=0, le=1)


# ---------------------------------------------------------------------------
# §4E — workflow writes (persisted in local SQLite, never the SQL source)
# ---------------------------------------------------------------------------


class Followup(StrictModel):
    id: str
    customer_id: str
    customer_name: str
    owner: str = Field(min_length=1, max_length=100)
    due_date: str = DateStr
    note: str = Field(min_length=1, max_length=2000)
    outcome: Literal[
        "Timing to confirm",
        "Timing changed",
        "Need confirmed",
        "Not applicable",
        "Equipment retired",
    ]
    status: Literal["open", "done"] = "open"
    source: Literal["mock", "manual"] = "manual"


class WorkflowChecks(StrictModel):
    quotation_order: Literal["unknown", "reported_none", "in_progress"] = "unknown"
    recent_contact: Literal["unknown", "checked"] = "unknown"
    contact_details: Literal["unknown", "supplied"] = "unknown"
    checked_at: str | None = None
    checked_by: str | None = None


class SuppressionRecord(StrictModel):
    reason_id: str
    status: Literal["snoozed", "resolved"]
    until: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field(min_length=1)
    updated_at: str

    @model_validator(mode="after")
    def snooze_needs_end_date(self):
        if self.status == "snoozed" and self.until is None:
            raise ValueError("a snooze requires an end date")
        return self


class AccountWorkflow(StrictModel):
    account_owner: str | None = None
    checks: WorkflowChecks = Field(default_factory=WorkflowChecks)
    suppressions: list[SuppressionRecord] = Field(default_factory=list)
    followups: list[Followup] = Field(default_factory=list)


class FollowupCreateV2(StrictModel):
    customer_id: str
    owner: str = Field(min_length=1, max_length=100)
    due_date: str = DateStr
    note: str = Field(min_length=1, max_length=2000)
    outcome: Followup.model_fields["outcome"].annotation
    reason_ids: list[str] = Field(default_factory=list)


class WorkflowPatchChecks(StrictModel):
    quotation_order: WorkflowChecks.model_fields["quotation_order"].annotation | None = None
    recent_contact: WorkflowChecks.model_fields["recent_contact"].annotation | None = None
    contact_details: WorkflowChecks.model_fields["contact_details"].annotation | None = None
    checked_by: str | None = None


class WorkflowPatch(StrictModel):
    account_owner: str | None = Field(default=None, min_length=1, max_length=100)
    checks: WorkflowPatchChecks | None = None
    suppression: SuppressionRecord | None = None

    @model_validator(mode="after")
    def at_least_one_change(self):
        if self.checks is None and self.suppression is None and "account_owner" not in self.model_fields_set:
            raise ValueError("provide owner, checks and/or one suppression record")
        return self


# ---------------------------------------------------------------------------
# §4F — chat context additions (routes owned by Aditya + Codex)
# ---------------------------------------------------------------------------


class FiltersV2(StrictModel):
    industry: str | None = None
    segment: str | None = None
    action: Literal["all", "upcoming", "inactivity", "discovery"] | None = None
    retention: Literal["all", "lower", "moderate", "higher"] | None = None
    query: str | None = None


class ChatContextV2(StrictModel):
    page: Literal["dashboard", "customers", "follow-ups"] = "dashboard"
    customer_id: str | None = None
    filters: FiltersV2 = Field(default_factory=FiltersV2)
    snapshot_id: str | None = None
    thread_id: str | None = None
