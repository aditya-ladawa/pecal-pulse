"""Account-level action construction + transparent ranking (plan §Member 3.2-3.3, §4C).

Reasons keep distinct ``upcoming`` / ``inactivity`` / ``discovery`` types.
Duplicate instrument signals for the same group+window bundle into one
reason with deduplicated instrument quantities. Stop / resolution / snooze
rules apply *before* ranking; missing live checks yield
``review_required``, never outreach-ready.

Priority components (default weights 30/25/15/15/15 — business assumptions,
not ML-derived commercial value) are normalized against a frozen snapshot
(``SnapshotStats``) so scores are comparable within one snapshot. Missing
components stay explicit ``null`` and contribute 0 to the score (absent
data is never scored as strong evidence). Ranking is deterministic: score
desc, then customer_id asc, then reason id asc.

The ``expected_value`` component is P(activity) × expected 3-month volume ×
the account's relative unit value, normalized by the snapshot maximum. Unit
values default to 1.0 per equipment group (pure volume ranking) unless
sales supplies relative weights; scores are therefore priority points,
never euros.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict

from .models import (
    AccountAction,
    AccountWorkflow,
    ActionReason,
    CustomerPrediction,
    PeerOpportunity,
    Requirement,
)
from .value_weights import load_weights, unit_value

RANKING_VERSION = "rank-v2"
DEFAULT_WEIGHTS = {
    "timing": 0.30,
    "quantity": 0.25,
    "activity_deviation": 0.15,
    "evidence": 0.15,
    "expected_value": 0.15,
}

EVIDENCE_BY_REQUIREMENT_KIND = {
    "recorded": 1.0,
    "nominal_interval": 0.7,
    "repeat_history": 0.6,
    "unknown": 0.0,
}


class SnapshotStats(BaseModel):
    """Frozen-snapshot normalization anchors for ranking.

    Member 1 publishes these once per snapshot; every account in the same
    snapshot ranks against the same anchors.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    reference_date: str  # YYYY-MM-DD
    max_instruments_per_account: int = 1
    max_calibration_events_3m: float = 1.0
    p90_instruments_per_account: float = 1.0
    # Snapshot maximum of P(activity) × expected 3-month volume × unit
    # value; None when analytics predictions are unavailable (mock mode).
    max_expected_value: float | None = None


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def reason_id_for(customer_id: str, kind: str, basis: str) -> str:
    return f"{customer_id}:{kind}:{basis}"


def suppression_for(
    reason_id: str, workflow: AccountWorkflow | None, today: str
) -> tuple[bool, str | None]:
    """Return (suppressed, reason). Snooze needs an end date; resolution needs a note.

    A snooze applies only while ``today <= until``; an expired snooze
    releases the reason. A resolution suppresses until explicitly cleared
    (no ``until`` needed) but requires a non-empty note to count.
    """
    if workflow is None:
        return False, None
    today_d = _parse_day(today)
    for record in workflow.suppressions:
        if record.reason_id != reason_id:
            continue
        if record.status == "resolved":
            if record.note.strip():
                return True, "resolved"
            continue
        if record.status == "snoozed":
            if not record.until:
                continue
            until_d = _parse_day(record.until)
            if until_d is None or today_d is None:
                return True, "snoozed"
            if today_d <= until_d:
                return True, f"snoozed_until_{record.until}"
    return False, None


def build_upcoming_reasons(
    *,
    customer_id: str,
    requirements: list[Requirement],
    workflow: AccountWorkflow | None,
    today: str,
    reference_date: str | None = None,
) -> list[ActionReason]:
    """Bundle supported windows within 90 days either side of the source reference.

    This configurable-in-code outreach policy is a business assumption, not a
    prediction. Older and far-future records remain in the evidence workspace.
    Workflow suppression uses today independently of the historical horizon.
    """
    reference = _parse_day(reference_date or today)
    if reference is None:
        return []
    earliest, latest = reference - timedelta(days=90), reference + timedelta(days=90)
    # Group by (group, window_start, window_end); excluded kinds never rank.
    buckets: dict[tuple[str, str | None, str | None], list[Requirement]] = {}
    for req in requirements:
        if req.customer_id != customer_id:
            continue
        if req.eligibility == "excluded" or req.stopped is True or req.kind == "unknown" or req.window_start is None or req.window_end is None:
            continue
        start, end = _parse_day(req.window_start), _parse_day(req.window_end)
        if start is None or end is None or end < start or end < earliest or start > latest:
            continue
        key = (req.group_id or "__ungrouped__", req.window_start, req.window_end)
        buckets.setdefault(key, []).append(req)
    reasons: list[ActionReason] = []
    for (group_id, window_start, window_end) in sorted(
        buckets, key=lambda k: (k[0] or "", k[1] or "", k[2] or "")
    ):
        reqs = buckets[(group_id, window_start, window_end)]
        instruments = sorted({r.instrument_id for r in reqs})
        kinds = {r.kind for r in reqs}
        best_kind = (
            "recorded"
            if "recorded" in kinds
            else "nominal_interval"
            if "nominal_interval" in kinds
            else "repeat_history"
            if "repeat_history" in kinds
            else "unknown"
        )
        unknowns: list[str] = []
        for r in reqs:
            unknowns.extend(r.unknowns)
        unknowns = sorted(set(unknowns))
        if best_kind != "recorded" and "due window is inferred, not recorded" not in unknowns:
            unknowns = sorted(unknowns + ["due window is inferred, not recorded"])
        rid = reason_id_for(
            customer_id, "upcoming", f"{group_id or '__ungrouped__'}:{window_start}:{window_end}"
        )
        suppressed, suppression_reason = suppression_for(rid, workflow, today)
        any_review = any(r.eligibility == "review_required" for r in reqs)
        status: str
        if suppressed:
            status = "suppressed"
        elif best_kind == "unknown" or any_review or unknowns:
            status = "review_required"
        else:
            status = "eligible"
        overdue = _parse_day(window_end) < reference
        if overdue:
            status = "review_required" if not suppressed else status
            unknowns = sorted(set(unknowns) | {"past-due record; completion or changed timing must be checked"})
        label = group_id if group_id != "__ungrouped__" else "equipment"
        methods = sorted({r.method for r in reqs if r.method})
        method_txt = f" Method: {'; '.join(methods)}." if methods else ""
        reasons.append(
            ActionReason(
                id=rid,
                type="upcoming",
                title=f"{len(instruments)} instrument(s) {'past due for review' if overdue else 'due'} — {label}",
                explanation=(
                    f"{len(instruments)} distinct instrument(s) in {label} "
                    f"fall in window {window_start}…{window_end} "
                    f"({best_kind}).{method_txt} Confirm timing and batch size."
                ),
                evidence_refs=sorted({r.id for r in reqs}),
                instrument_ids=instruments,
                quantity=len(instruments),
                quantity_unit="instruments",
                window_start=window_start,
                window_end=window_end,
                status=status,  # type: ignore[arg-type]
                suppression_reason=suppression_reason,
                unknowns=unknowns,
            )
        )
    reasons.sort(key=lambda r: r.id)
    return reasons


def build_inactivity_reason(
    *,
    customer_id: str,
    prediction: CustomerPrediction | None,
    workflow: AccountWorkflow | None,
    today: str,
) -> ActionReason | None:
    if prediction is None or not prediction.inactivity.flagged:
        return None
    sig = prediction.inactivity
    rid = reason_id_for(customer_id, "inactivity", "review")
    suppressed, suppression_reason = suppression_for(rid, workflow, today)
    unknowns = ["alternate explanations unchecked (seasonality, site closure, provider switch)"]
    if sig.support.status != "supported":
        unknowns.append(f"history support: {sig.support.status}")
    status: str
    if suppressed:
        status = "suppressed"
    else:
        # Inactivity is always a review signal, never auto-eligible:
        # it needs a human check of alternate explanations.
        status = "review_required"
    rec = (
        f"{sig.recency_to_cadence:.1f}× observed cadence"
        if sig.recency_to_cadence is not None
        else "unknown cadence ratio"
    )
    deficit = (
        f"{sig.deficit_fraction:.0%} below baseline"
        if sig.deficit_fraction is not None
        else "no measured deficit"
    )
    return ActionReason(
        id=rid,
        type="inactivity",
        title="Unusual inactivity — review",
        explanation=(
            f"No expected activity pattern: recency {rec}, {deficit} "
            f"(recent {sig.recent_volume} vs baseline {sig.baseline_volume}). "
            f"Reasons: {'; '.join(sig.reasons) if sig.reasons else 'rule review'}. "
            "This is a retention-review signal, not a churn label."
        ),
        evidence_refs=[f"prediction:{prediction.customer_id}:{prediction.snapshot_id}"],
        instrument_ids=[],
        quantity=sig.recent_volume,
        quantity_unit="calibration_events",
        window_start=None,
        window_end=None,
        status=status,  # type: ignore[arg-type]
        suppression_reason=suppression_reason,
        unknowns=sorted(unknowns),
    )


def build_discovery_reasons(
    *,
    customer_id: str,
    opportunities: list[PeerOpportunity],
    workflow: AccountWorkflow | None,
    today: str,
) -> list[ActionReason]:
    reasons: list[ActionReason] = []
    for opp in opportunities:
        rid = reason_id_for(customer_id, "discovery", opp.group_id)
        suppressed, suppression_reason = suppression_for(rid, workflow, today)
        status = "suppressed" if suppressed else "review_required"
        reasons.append(
            ActionReason(
                id=rid,
                type="discovery",
                title=f"Peer category to ask about — {opp.group_label}",
                explanation=(
                    f"{opp.question} "
                    f"(window {opp.window_start}…{opp.window_end})."
                ),
                evidence_refs=[f"peer:{opp.industry_id}:{opp.group_id}"],
                instrument_ids=[],
                quantity=1,
                quantity_unit="categories",
                window_start=None,
                window_end=None,
                status=status,  # type: ignore[arg-type]
                suppression_reason=suppression_reason,
                unknowns=["customer use of this category is unknown"],
            )
        )
    reasons.sort(key=lambda r: r.id)
    return reasons


# ---------------------------------------------------------------------------
# Priority components
# ---------------------------------------------------------------------------


def timing_component(reason: ActionReason, reference_date: str) -> float | None:
    ref = _parse_day(reference_date)
    start = _parse_day(reason.window_start)
    if ref is None or start is None:
        # Inactivity/discovery have no due window: neutral-low, explicit.
        if reason.type == "inactivity":
            return 0.6
        if reason.type == "discovery":
            return 0.3
        return None
    delta = (start - ref).days
    if delta <= 30:
        return 1.0
    if delta <= 60:
        return 0.7
    if delta <= 90:
        return 0.4
    return 0.1


def quantity_component(reason: ActionReason, stats: SnapshotStats) -> float | None:
    if reason.quantity is None:
        return None
    if reason.quantity_unit == "instruments":
        denom = max(stats.p90_instruments_per_account, 1.0)
        return max(0.0, min(1.0, float(reason.quantity) / denom))
    if reason.quantity_unit == "calibration_events":
        denom = max(stats.max_calibration_events_3m, 1.0)
        return max(0.0, min(1.0, float(reason.quantity) / denom))
    if reason.quantity_unit == "categories":
        return 0.3 if (reason.quantity or 0) >= 1 else 0.0
    return None


def activity_deviation_component(
    reason: ActionReason, prediction: CustomerPrediction | None
) -> float | None:
    if prediction is None:
        return None
    if reason.type == "inactivity":
        deficit = prediction.inactivity.deficit_fraction
        if deficit is not None:
            return max(0.0, min(1.0, deficit))
        ratio = prediction.inactivity.recency_to_cadence
        if ratio is not None:
            # recency 1× cadence → 0, ≥3× cadence → 1
            return max(0.0, min(1.0, (ratio - 1.0) / 2.0))
        return 0.5 if prediction.inactivity.flagged else 0.0
    if reason.type == "upcoming":
        prob = prediction.activity_probability
        if prob is None:
            return None
        return max(0.0, min(1.0, prob))
    # Discovery is not an activity-deviation claim.
    return None


def evidence_component(
    reason: ActionReason, requirements_by_id: dict[str, Requirement]
) -> float | None:
    if reason.type == "discovery":
        return 0.5  # peer support is suggestive, never conclusive
    if reason.type == "inactivity":
        return 0.6
    scores = [
        EVIDENCE_BY_REQUIREMENT_KIND.get(
            requirements_by_id[r].kind, 0.0
        )
        for r in (reason.evidence_refs or [])
        if r in requirements_by_id
    ]
    if not scores:
        return None
    return max(scores)


def account_unit_value(
    requirements: list[Requirement],
    weights: dict[str, float] | None = None,
) -> float:
    """Mean relative unit value over the account's supported requirement groups.

    Falls back to 1.0 without grouped requirements: every calibration event
    counts the same until sales supplies relative group values.
    """
    groups = {
        r.group_id
        for r in requirements
        if r.group_id and r.stopped is not True and r.eligibility != "excluded"
    }
    if not groups:
        return 1.0
    return sum(unit_value(group, weights) for group in groups) / len(groups)


def expected_value_component(
    reason: ActionReason,
    prediction: CustomerPrediction | None,
    unit: float,
    max_expected_value: float | None,
) -> float | None:
    """Normalized P(activity) × expected volume × unit value, upcoming only.

    Inactivity/discovery carry no value claim (None, never zero-as-weak).
    """
    if reason.type != "upcoming" or prediction is None:
        return None
    prob = prediction.activity_probability
    expected = prediction.expected_volume_3m
    if prob is None or expected is None or not max_expected_value:
        return None
    return max(0.0, min(1.0, prob * expected * unit / max_expected_value))


def score_reason(
    reason: ActionReason,
    *,
    prediction: CustomerPrediction | None,
    requirements_by_id: dict[str, Requirement],
    stats: SnapshotStats,
    weights: dict[str, float] | None = None,
    unit_value_amount: float = 1.0,
) -> tuple[float, dict[str, float | None]]:
    """Return (score_0_100, components). Missing components → null, +0."""
    weights = weights or DEFAULT_WEIGHTS
    components: dict[str, float | None] = {
        "timing": timing_component(reason, stats.reference_date),
        "quantity": quantity_component(reason, stats),
        "activity_deviation": activity_deviation_component(reason, prediction),
        "evidence": evidence_component(reason, requirements_by_id),
        "expected_value": expected_value_component(
            reason, prediction, unit_value_amount, stats.max_expected_value
        ),
    }
    total = 0.0
    for key, weight in weights.items():
        value = components.get(key)
        if value is not None:
            total += weight * max(0.0, min(1.0, value))
    return round(total * 100.0, 2), components


def live_checks_missing(workflow: AccountWorkflow | None) -> bool:
    """True when no live verification has been recorded.

    Readiness rule (plan §4C): missing live checks make an action
    ``review_required``, not outreach-ready. A reason is outreach-ready
    only after a human records at least a quotation check or a recent
    contact check. Anonymous demo users are acceptable; the check values
    themselves are what matter.
    """
    if workflow is None:
        return True
    return (
        workflow.checks.quotation_order == "unknown"
        and workflow.checks.recent_contact == "unknown"
    )


def build_account_action(
    *,
    snapshot_id: str,
    customer_id: str,
    requirements: list[Requirement],
    prediction: CustomerPrediction | None,
    peer_opportunities: list[PeerOpportunity],
    workflow: AccountWorkflow | None,
    stats: SnapshotStats,
    weights: dict[str, float] | None = None,
    today: str | None = None,
) -> AccountAction | None:
    """Pure ranking function consumed by Member 1 recompute + agent tools."""
    weights = weights or dict(DEFAULT_WEIGHTS)
    today = today or stats.reference_date
    requirements_by_id = {r.id: r for r in requirements}
    unit = account_unit_value(requirements)

    reasons = (
        build_upcoming_reasons(
            customer_id=customer_id,
            requirements=requirements,
            workflow=workflow,
            today=today,
            reference_date=stats.reference_date,
        )
        + (
            [r]
            if (r := build_inactivity_reason(
                customer_id=customer_id,
                prediction=prediction,
                workflow=workflow,
                today=today,
            ))
            else []
        )
        + build_discovery_reasons(
            customer_id=customer_id,
            opportunities=peer_opportunities,
            workflow=workflow,
            today=today,
        )
    )
    active = [r for r in reasons if r.status != "suppressed"]
    if not active:
        return None

    if live_checks_missing(workflow):
        downgraded: list[ActionReason] = []
        for r in active:
            if r.status == "eligible":
                unknowns = sorted(set(r.unknowns) | {"live quotation/contact checks unchecked"})
                downgraded.append(r.model_copy(update={"status": "review_required", "unknowns": unknowns}))
            else:
                downgraded.append(r)
        active = downgraded

    scored = [
        (score_reason(r, prediction=prediction,
                      requirements_by_id=requirements_by_id,
                      stats=stats, weights=weights, unit_value_amount=unit), r)
        for r in active
    ]
    # Deterministic: score desc, then reason id asc.
    scored.sort(key=lambda item: (-item[0][0], item[1].id))
    (best_score, best_components), best_reason = scored[0]

    # Account components: best available per dimension across reasons
    # (transparent: max evidence, not an average that hides the best lead).
    merged: dict[str, float | None] = {}
    for key in weights:
        values = [s[1][key] for s, _ in scored if s[1].get(key) is not None]
        merged[key] = max(values) if values else None
    total = sum(
        weights[k] * merged[k] for k in weights if merged.get(k) is not None
    )
    priority = round(total * 100.0, 2)

    readiness = (
        "eligible" if any(r.status == "eligible" for _, r in scored) else "review_required"
    )
    ordered_reasons = [r for _, r in scored]
    next_steps = {
        "upcoming": "Confirm timing and batch size for the due window.",
        "inactivity": "Check whether the usual batch was delayed or moved elsewhere.",
        "discovery": "Ask whether the peer-calibrated category is used on site.",
    }
    return AccountAction(
        snapshot_id=snapshot_id,
        customer_id=customer_id,
        primary_type=best_reason.type,
        reasons=ordered_reasons,
        priority_score=priority,
        components=merged,
        ranking_version=RANKING_VERSION,
        weights=weights,
        readiness=readiness,
        suggested_next_step=next_steps[best_reason.type],
    )


def rank_actions(actions: list[AccountAction]) -> list[AccountAction]:
    """Deterministic queue order: score desc, customer_id asc."""
    return sorted(actions, key=lambda a: (-a.priority_score, a.customer_id))


def split_followups_first(
    actions: list[AccountAction],
    workflows: dict[str, AccountWorkflow],
    today: str,
) -> tuple[list[AccountAction], list[AccountAction]]:
    """Agreed due follow-ups form a separate deadline-first section.

    Returns (followup_due_first, proactive_rest). An account with an open
    follow-up due on/before ``today`` sorts deadline-first by due date;
    everything else keeps ranked order. Pure helper for Member 1's
    composition layer.
    """
    today_d = _parse_day(today)
    due: list[tuple[str, AccountAction]] = []
    rest: list[AccountAction] = []
    for action in actions:
        workflow = workflows.get(action.customer_id)
        earliest: str | None = None
        if workflow:
            for f in workflow.followups:
                if f.status != "open":
                    continue
                if today_d is not None:
                    due_d = _parse_day(f.due_date)
                    if due_d is not None and due_d > today_d:
                        continue
                if earliest is None or f.due_date < earliest:
                    earliest = f.due_date
        if earliest is not None:
            due.append((earliest, action))
        else:
            rest.append(action)
    due.sort(key=lambda item: (item[0], -item[1].priority_score, item[1].customer_id))
    return [a for _, a in due], rank_actions(rest)
