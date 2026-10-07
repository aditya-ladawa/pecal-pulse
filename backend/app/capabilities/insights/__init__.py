"""Member 3 sales-intelligence capability (peer discovery + ranking + prep)."""

from .service import (  # noqa: F401
    DEFAULT_MIN_PEER_ACCOUNTS,
    DEFAULT_MIN_PREVALENCE,
    DEFAULT_WEIGHTS,
    RANKING_VERSION,
    SnapshotStats,
    account_coverage,
    build_account_action,
    build_peer_index,
    build_preparation,
    category_prevalence_by_industry,
    evidence_lookup,
    get_evidence,
    get_peer_opportunities,
    get_ranked_actions,
    opportunity_type_distribution,
    rank_actions,
    split_followups_first,
)
