"""Preparation cards: known facts, unknowns, questions, next step.

The LLM may phrase these facts but must not invent inputs: every fact
carries ``evidence_refs`` back to requirements / predictions / peer
results, and anything unverified lands in ``unknowns`` or ``questions``.
"""

from __future__ import annotations

from .models import (
    AccountAction,
    AccountWorkflow,
    CustomerPrediction,
    CustomerProfile,
    PeerOpportunity,
    PreparationCard,
    PreparationFact,
    Requirement,
)


def build_preparation(
    *,
    profile: CustomerProfile,
    action: AccountAction | None,
    peer_opportunities: list[PeerOpportunity],
    prediction: CustomerPrediction | None,
    requirements: list[Requirement],
    workflow: AccountWorkflow | None,
    reference_date: str,
) -> PreparationCard:
    facts: list[PreparationFact] = []
    unknowns: list[str] = []
    questions: list[str] = []

    industry = profile.industry_label or profile.industry_id or "unknown industry"
    facts.append(
        PreparationFact(
            text=f"{profile.display_name} operates in {industry}.",
            evidence_refs=[f"profile:{profile.customer_id}"],
        )
    )

    if prediction is not None:
        if prediction.activity_probability is not None:
            facts.append(
                PreparationFact(
                    text=(
                        f"Activity probability "
                        f"{prediction.activity_probability:.0%} for "
                        f"{prediction.activity_window_start}…"
                        f"{prediction.activity_window_end}."
                    ),
                    evidence_refs=[
                        f"prediction:{prediction.customer_id}:{prediction.snapshot_id}"
                    ],
                )
            )
        else:
            unknowns.append("activity probability unsupported for this account")
        if prediction.inactivity.flagged:
            facts.append(
                PreparationFact(
                    text=(
                        "Flagged for unusual inactivity review: "
                        + "; ".join(prediction.inactivity.reasons)
                        if prediction.inactivity.reasons
                        else "Flagged for unusual inactivity review."
                    ),
                    evidence_refs=[
                        f"prediction:{prediction.customer_id}:{prediction.snapshot_id}"
                    ],
                )
            )
    else:
        unknowns.append("no prediction available for this account")

    if action is not None:
        for reason in action.reasons:
            if reason.status == "suppressed":
                continue
            facts.append(
                PreparationFact(
                    text=f"{reason.title}: {reason.explanation}",
                    evidence_refs=list(reason.evidence_refs),
                )
            )
            unknowns.extend(reason.unknowns)
    else:
        unknowns.append("no proactive reasons for this account")

    for opp in peer_opportunities:
        questions.append(opp.question)
    if action is not None:
        for reason in action.reasons:
            if reason.type == "upcoming" and reason.status != "suppressed":
                questions.append(
                    "Can you confirm the timing and batch size for "
                    f"{reason.quantity} instrument(s) due "
                    f"{reason.window_start}…{reason.window_end}?"
                )
            elif reason.type == "inactivity" and reason.status != "suppressed":
                questions.append(
                    "Was the usual calibration batch delayed, reduced, "
                    "or moved to another provider?"
                )

    if workflow is not None:
        if workflow.checks.quotation_order == "unknown":
            unknowns.append("live quotation status unchecked")
        if workflow.checks.recent_contact == "unknown":
            unknowns.append("recent contact unchecked")
        if workflow.checks.contact_details == "unknown":
            unknowns.append("contact details unchecked")

    # Deduplicate while preserving order.
    unknowns = list(dict.fromkeys(unknowns))
    questions = list(dict.fromkeys(questions))

    suggested = action.suggested_next_step if action else (
        "No proactive action — record any manual follow-up if needed."
    )
    return PreparationCard(
        customer_id=profile.customer_id,
        reference_date=reference_date,
        facts=facts,
        unknowns=unknowns,
        questions=questions,
        suggested_next_step=suggested,
    )


def evidence_lookup(
    *,
    requirements: list[Requirement],
    prediction: CustomerPrediction | None,
    opportunities: list[PeerOpportunity],
    action: AccountAction | None,
) -> dict[str, dict]:
    """Resolve evidence refs to the underlying records for agent/API use."""
    by_req = {r.id: r.model_dump() for r in requirements}
    table: dict[str, dict] = {}
    for rid, payload in by_req.items():
        table[rid] = {"kind": "requirement", "record": payload}
    if prediction is not None:
        table[f"prediction:{prediction.customer_id}:{prediction.snapshot_id}"] = {
            "kind": "prediction",
            "record": prediction.model_dump(),
        }
    for opp in opportunities:
        table[f"peer:{opp.industry_id}:{opp.group_id}"] = {
            "kind": "peer_opportunity",
            "record": opp.model_dump(),
        }
    if action is not None:
        for reason in action.reasons:
            table[reason.id] = {"kind": "action_reason", "record": reason.model_dump()}
    return table
