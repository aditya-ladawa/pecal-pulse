"""Peer portfolio prevalence by industry (plan §Member 3.1, §4C).

Account-level ownership of an *observed calibrated category*: each account
contributes at most 1 to a group's numerator/denominator, regardless of how
many calibration rows it has. The target account is always excluded from its
own peer set. ``Unknown``/``Sonstiges`` industries never produce
specific-industry discovery assertions.
"""

from __future__ import annotations

from .models import PeerOpportunity, PortfolioRow

RANKING_VERSION = "rank-v1"

DEFAULT_MIN_PEER_ACCOUNTS = 20
DEFAULT_MIN_PREVALENCE = 0.25

# Industries too vague for a specific discovery claim. Matching is
# case-insensitive and whitespace-tolerant; labels travel with IDs.
EXCLUDED_INDUSTRIES = {"unknown", "sonstiges", ""}


def normalize_industry(value: str | None) -> str:
    return (value or "").strip().lower().removeprefix("ind-")


def owns_category(row: PortfolioRow) -> bool:
    """Account-level ownership test for one portfolio row.

    Uses distinct instruments where exported; when the export counts only
    calibration rows (``distinct_instruments=None``), any positive
    calibration count implies at least one observed instrument. An
    explicit ``distinct_instruments=0`` always means not owned, even if
    row counts disagree. Row counts never inflate the peer denominator —
    each account votes at most once per category.
    """
    if row.distinct_instruments is not None:
        return row.distinct_instruments > 0
    return row.calibration_events > 0


def build_peer_index(
    portfolios: list[PortfolioRow],
    industry_by_customer: dict[str, str],
) -> dict[str, dict[str, set[str]]]:
    """Map industry_id -> group_id -> set(customer_id).

    The industry mapping is required: ``PortfolioRow`` carries no industry
    and unmapped rows must never silently join a peer set.
    """
    return add_to_peer_index({}, portfolios, industry_by_customer)


def add_to_peer_index(
    index: dict[str, dict[str, set[str]]],
    portfolios: list[PortfolioRow],
    industry_by_customer: dict[str, str] | None = None,
) -> dict[str, dict[str, set[str]]]:
    """Merge rows into an existing index (lets callers stream snapshots).

    ``PortfolioRow`` carries no industry; pass ``industry_by_customer`` when
    the caller keeps profiles separately. Rows whose customer has no known
    industry mapping are skipped — they must not silently join a peer set.
    """
    for row in portfolios:
        if not owns_category(row):
            continue
        industry_id = None
        if industry_by_customer is not None:
            industry_id = industry_by_customer.get(row.customer_id)
        if industry_id is None:
            continue
        index.setdefault(industry_id, {}).setdefault(row.group_id, set()).add(
            row.customer_id
        )
    return index


def industry_peer_count(
    index: dict[str, dict[str, set[str]]], industry_id: str
) -> int:
    """Eligible peer accounts in an industry (union over groups)."""
    groups = index.get(industry_id, {})
    owners: set[str] = set()
    for customers in groups.values():
        owners.update(customers)
    return len(owners)


def get_peer_opportunities(
    *,
    target_customer_id: str,
    target_industry_id: str | None,
    owned_group_ids: set[str],
    peer_index: dict[str, dict[str, set[str]]],
    group_labels: dict[str, str] | None = None,
    industry_customer_count: dict[str, int] | None = None,
    window_start: str,
    window_end: str,
    min_peer_accounts: int = DEFAULT_MIN_PEER_ACCOUNTS,
    min_prevalence: float = DEFAULT_MIN_PREVALENCE,
) -> list[PeerOpportunity]:
    """Categories peers own that the target account has never calibrated.

    An absent category supports a *discovery question*; it never establishes
    owned equipment, competitor use, or missed sales. Every result discloses
    its denominator (``peer_count``) and window.
    """
    group_labels = group_labels or {}
    if target_industry_id is None or normalize_industry(target_industry_id) in (
        EXCLUDED_INDUSTRIES
    ):
        return []

    groups = peer_index.get(target_industry_id, {})
    # Union of peer owners, excluding the target account itself.
    peers: set[str] = set()
    for customers in groups.values():
        peers.update(customers)
    peers.discard(target_customer_id)
    peer_count = len(peers)
    if industry_customer_count is not None:
        # Callers with a full profile list can supply the true industry
        # denominator (including accounts with no portfolio rows). Prefer it
        # when it is larger than the portfolio union.
        peer_count = max(
            peer_count,
            industry_customer_count.get(target_industry_id, 0)
            - (1 if target_customer_id else 0),
        )
    if peer_count < min_peer_accounts:
        return []

    opportunities: list[PeerOpportunity] = []
    for group_id in sorted(groups):
        if group_id in owned_group_ids:
            continue
        owners = set(groups[group_id])
        owners.discard(target_customer_id)
        prevalence = len(owners) / peer_count if peer_count else 0.0
        if prevalence < min_prevalence:
            continue
        label = group_labels.get(group_id, group_id)
        opportunities.append(
            PeerOpportunity(
                group_id=group_id,
                group_label=label,
                industry_id=target_industry_id,
                peer_count=peer_count,
                peers_with_group=len(owners),
                prevalence=round(prevalence, 4),
                window_start=window_start,
                window_end=window_end,
                question=(
                    f"{len(owners)} of {peer_count} peer accounts "
                    f"({prevalence:.0%}) in this industry calibrate "
                    f"{label}. Ask whether {label} equipment is used "
                    "on site or calibrated elsewhere — do not assume "
                    "ownership."
                ),
                evidence_refs=[f"peer:{target_industry_id}:{group_id}"],
            )
        )
    # Deterministic order: prevalence desc, then group_id asc.
    opportunities.sort(key=lambda o: (-o.prevalence, o.group_id))
    return opportunities
