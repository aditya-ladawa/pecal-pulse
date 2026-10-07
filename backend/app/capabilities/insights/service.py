"""Typed service facade for Member 1 composition + agent tools.

Plan §5 seams implemented here::

    insights.service.build_account_action(profile, requirements, prediction, peers, workflow)
    insights.service.build_preparation(profile, action, peers, workflow)

Plus queryable helpers: peer comparisons, ranked queues, evidence
retrieval, and aggregate EDA rows with metric definitions. All functions
are pure (no I/O, no imports from data/analytics/agents modules).
"""

from __future__ import annotations

from .actions import (
    DEFAULT_WEIGHTS,
    RANKING_VERSION,
    SnapshotStats,
    build_account_action,
    rank_actions,
    split_followups_first,
)
from .eda import (
    account_coverage,
    category_prevalence_by_industry,
    opportunity_type_distribution,
)
from .models import (
    AccountAction,
    AccountWorkflow,
    CustomerPrediction,
    CustomerProfile,
    PeerOpportunity,
    PortfolioRow,
    PreparationCard,
    Requirement,
)
from .peers import (
    DEFAULT_MIN_PEER_ACCOUNTS,
    DEFAULT_MIN_PREVALENCE,
    build_peer_index,
    get_peer_opportunities,
)
from .preparation import build_preparation, evidence_lookup

__all__ = [
    "DEFAULT_WEIGHTS",
    "RANKING_VERSION",
    "DEFAULT_MIN_PEER_ACCOUNTS",
    "DEFAULT_MIN_PREVALENCE",
    "SnapshotStats",
    "build_account_action",
    "build_preparation",
    "rank_actions",
    "split_followups_first",
    "build_peer_index",
    "get_peer_opportunities",
    "evidence_lookup",
    "category_prevalence_by_industry",
    "opportunity_type_distribution",
    "account_coverage",
]


def get_ranked_actions(
    *,
    snapshot_id: str,
    customer_ids: list[str],
    requirements_by_customer: dict[str, list[Requirement]],
    predictions_by_customer: dict[str, CustomerPrediction],
    peers_by_customer: dict[str, list[PeerOpportunity]],
    workflows_by_customer: dict[str, AccountWorkflow],
    stats: SnapshotStats,
    weights: dict[str, float] | None = None,
    today: str | None = None,
) -> list[AccountAction]:
    """Build + deterministically rank one action per account with reasons."""
    actions: list[AccountAction] = []
    for customer_id in customer_ids:
        action = build_account_action(
            snapshot_id=snapshot_id,
            customer_id=customer_id,
            requirements=requirements_by_customer.get(customer_id, []),
            prediction=predictions_by_customer.get(customer_id),
            peer_opportunities=peers_by_customer.get(customer_id, []),
            workflow=workflows_by_customer.get(customer_id),
            stats=stats,
            weights=weights,
            today=today,
        )
        if action is not None:
            actions.append(action)
    return rank_actions(actions)


def get_evidence(
    *,
    requirements: list[Requirement],
    prediction: CustomerPrediction | None,
    opportunities: list[PeerOpportunity],
    action: AccountAction | None,
    refs: list[str] | None = None,
) -> dict[str, dict]:
    """Retrieve evidence records backing an account's reasons/facts."""
    table = evidence_lookup(
        requirements=requirements,
        prediction=prediction,
        opportunities=opportunities,
        action=action,
    )
    if refs is None:
        return table
    return {ref: table[ref] for ref in refs if ref in table}
