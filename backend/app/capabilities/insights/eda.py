"""Small aggregate EDA behind the insight services (plan §Member 3.6).

Same calculations feed screen/chart data and agent answers: supply
aggregate rows + metric definitions, not frontend code or chart JS.
All inputs are account-level portfolio rows / ranked actions.
"""

from __future__ import annotations

from .models import AccountAction, PortfolioRow


def category_prevalence_by_industry(
    *,
    portfolios: list[PortfolioRow],
    industry_by_customer: dict[str, str],
    window_start: str,
    window_end: str,
) -> list[dict]:
    """Per (industry, group): eligible accounts, owners, prevalence.

    Denominator = accounts in the industry with ≥1 portfolio row
    (account-level ownership). Numerator = accounts owning the group.
    """
    owners_by_industry: dict[str, set[str]] = {}
    owners_by_pair: dict[tuple[str, str], set[str]] = {}
    labels: dict[tuple[str, str], str] = {}
    for row in portfolios:
        if row.distinct_instruments <= 0:
            continue
        industry = industry_by_customer.get(row.customer_id)
        if industry is None:
            continue
        owners_by_industry.setdefault(industry, set()).add(row.customer_id)
        owners_by_pair.setdefault((industry, row.group_id), set()).add(
            row.customer_id
        )
        labels[(industry, row.group_id)] = row.group_label
    rows: list[dict] = []
    for (industry, group_id), owners in sorted(owners_by_pair.items()):
        denom = len(owners_by_industry[industry])
        rows.append(
            {
                "industry_id": industry,
                "group_id": group_id,
                "group_label": labels[(industry, group_id)],
                "eligible_accounts": denom,
                "accounts_with_group": len(owners),
                "prevalence": round(len(owners) / denom, 4) if denom else 0.0,
                "window_start": window_start,
                "window_end": window_end,
                "metric": "account-level ownership of an observed calibrated category",
            }
        )
    rows.sort(key=lambda r: (-r["prevalence"], r["industry_id"], r["group_id"]))
    return rows


def opportunity_type_distribution(actions: list[AccountAction]) -> list[dict]:
    """Count of unsuppressed reasons by type across the ranked queue."""
    counts = {"upcoming": 0, "inactivity": 0, "discovery": 0}
    accounts_with = {"upcoming": 0, "inactivity": 0, "discovery": 0}
    for action in actions:
        seen: set[str] = set()
        for reason in action.reasons:
            if reason.status == "suppressed":
                continue
            counts[reason.type] += 1
            seen.add(reason.type)
        for kind in seen:
            accounts_with[kind] += 1
    return [
        {
            "type": kind,
            "reasons": counts[kind],
            "accounts": accounts_with[kind],
            "metric": "unsuppressed reasons in the ranked queue",
        }
        for kind in ("upcoming", "inactivity", "discovery")
    ]


def account_coverage(
    *,
    customer_ids: list[str],
    actions: list[AccountAction],
) -> dict:
    """How many accounts the proactive queue covers, and why others miss out."""
    covered = {a.customer_id for a in actions}
    return {
        "accounts_total": len(customer_ids),
        "accounts_with_action": len(covered),
        "accounts_without_action": len(set(customer_ids) - covered),
        "metric": "accounts with ≥1 unsuppressed reason / all accounts",
    }
