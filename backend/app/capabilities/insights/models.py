"""Member 3 — sales-intelligence contracts.

Mirrors plan.md §4C (Member 1/3 → UI) plus the minimal Member 1/2 inputs
Member 3 consumes. These are the canonical insight I/O shapes until the
shared ``backend/app/contracts/sales_v2.py`` freeze lands (owned by
Member 1); at that point these models become thin aliases/imports and
Member 1 composes them into screen responses.

Conventions (plan §4): IDs opaque strings; dates YYYY-MM-DD;
``null`` = unknown/unsupported (zero = measured zero); probabilities /
prevalence / components in [0,1]; priority score in [0,100].
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


# ---------------------------------------------------------------------------
# Minimal Member 1 inputs (profiles / portfolio / requirements / workflow)
# ---------------------------------------------------------------------------


class CustomerProfile(StrictModel):
    customer_id: str
    display_name: str
    name_source: Literal["verified", "identifier"] = "identifier"
    industry_id: str | None = None
    industry_label: str | None = None


class PortfolioRow(StrictModel):
    """One observed calibrated category per account.

    One row per (customer, group) with distinct-instrument counts where
    exported. ``distinct_instruments=None`` means the export counts
    calibration rows per group and has no distinct-instrument measure —
    never zero observed (mirrors the shared contract). A row exists only
    when the account calibrated that category in the window.
    """

    customer_id: str
    group_id: str
    group_label: str
    distinct_instruments: int | None = Field(default=None, ge=0)
    calibration_events: int = Field(ge=0)
    window_start: str
    window_end: str


class Requirement(StrictModel):
    id: str
    customer_id: str
    instrument_id: str
    group_id: str | None = None
    kind: Literal["recorded", "nominal_interval", "repeat_history", "unknown"] = (
        "unknown"
    )
    window_start: str | None = None
    window_end: str | None = None
    method: str = ""
    evidence_dates: list[str] = Field(default_factory=list)
    positive_gap_count: int = Field(default=0, ge=0)
    stopped: bool | None = None
    eligibility: Literal["review_required", "eligible", "excluded"] = "review_required"
    unknowns: list[str] = Field(default_factory=list)


class WorkflowChecks(StrictModel):
    quotation_order: Literal["unknown", "reported_none", "in_progress"] = "unknown"
    recent_contact: Literal["unknown", "checked"] = "unknown"
    contact_details: Literal["unknown", "supplied"] = "unknown"
    checked_at: str | None = None
    checked_by: str | None = None


class SuppressionRecord(StrictModel):
    reason_id: str
    status: Literal["snoozed", "resolved"]
    until: str | None = None
    note: str = ""
    updated_at: str = ""


class WorkflowFollowup(StrictModel):
    id: str
    customer_id: str
    due_date: str
    note: str = ""
    status: Literal["open", "done"] = "open"


class AccountWorkflow(StrictModel):
    account_owner: str | None = None
    checks: WorkflowChecks = Field(default_factory=WorkflowChecks)
    suppressions: list[SuppressionRecord] = Field(default_factory=list)
    followups: list[WorkflowFollowup] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Minimal Member 2 inputs (predictions)
# ---------------------------------------------------------------------------


class Support(StrictModel):
    status: Literal["supported", "insufficient_history", "unavailable"] = "unavailable"
    reason: str | None = None
    history_months: int = Field(default=0, ge=0)
    active_months: int = Field(default=0, ge=0)


class InactivitySignal(StrictModel):
    flagged: bool = False
    recency_to_cadence: float | None = None
    recent_volume: int = Field(default=0, ge=0)
    baseline_volume: float | None = None
    deficit_fraction: float | None = None
    rule_version: str = "inactivity-v1"
    reasons: list[str] = Field(default_factory=list)
    support: Support = Field(default_factory=Support)


class CustomerPrediction(StrictModel):
    """Minimal prediction view Member 3 consumes (plan §4B subset)."""

    snapshot_id: str
    customer_id: str
    reference_date: str
    segment_id: str | None = None
    activity_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    activity_window_start: str | None = None
    activity_window_end: str | None = None
    activity_support: Support = Field(default_factory=Support)
    expected_volume_3m: float | None = Field(default=None, ge=0.0)
    recency_months: int | None = None
    cadence_months: float | None = None
    inactivity: InactivitySignal = Field(default_factory=InactivitySignal)


# ---------------------------------------------------------------------------
# Member 3 outputs (plan §4C)
# ---------------------------------------------------------------------------


class ActionReason(StrictModel):
    id: str
    type: Literal["upcoming", "inactivity", "discovery"]
    title: str
    explanation: str
    evidence_refs: list[str] = Field(default_factory=list)
    instrument_ids: list[str] = Field(default_factory=list)
    quantity: int | float | None = None
    quantity_unit: Literal[
        "instruments", "calibration_events", "categories"
    ] | None = None
    window_start: str | None = None
    window_end: str | None = None
    status: Literal["review_required", "eligible", "suppressed"] = "review_required"
    suppression_reason: str | None = None
    unknowns: list[str] = Field(default_factory=list)


class AccountAction(StrictModel):
    snapshot_id: str
    customer_id: str
    primary_type: Literal["upcoming", "inactivity", "discovery"]
    reasons: list[ActionReason] = Field(min_length=1)
    priority_score: float = Field(ge=0.0, le=100.0)
    components: dict[str, float | None] = Field(
        default_factory=lambda: {
            "timing": None,
            "quantity": None,
            "activity_deviation": None,
            "evidence": None,
        }
    )
    ranking_version: str = "rank-v1"
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "timing": 0.35,
            "quantity": 0.30,
            "activity_deviation": 0.20,
            "evidence": 0.15,
        }
    )
    readiness: Literal["review_required", "eligible"] = "review_required"
    suggested_next_step: str = ""


class PeerOpportunity(StrictModel):
    group_id: str
    group_label: str
    industry_id: str
    peer_count: int = Field(ge=0)
    peers_with_group: int = Field(ge=0)
    prevalence: float = Field(ge=0.0, le=1.0)
    window_start: str
    window_end: str
    question: str
    evidence_refs: list[str] = Field(default_factory=list)


class PreparationFact(StrictModel):
    text: str
    evidence_refs: list[str] = Field(default_factory=list)


class PreparationCard(StrictModel):
    customer_id: str
    reference_date: str
    facts: list[PreparationFact] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    suggested_next_step: str = ""
