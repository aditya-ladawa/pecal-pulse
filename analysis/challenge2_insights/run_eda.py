"""Reproducible Member 3 example report on the synthetic fixture.

Reads analysis/challenge2_insights/fixtures/synthetic_snapshot.json,
runs peer discovery (lowered thresholds so the small fixture yields
results), builds + ranks account actions, prints one preparation card
and EDA aggregates. Same functions Member 1 / agent tools call.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.capabilities.insights import (  # noqa: E402
    SnapshotStats,
    account_coverage,
    build_account_action,
    build_preparation,
    category_prevalence_by_industry,
    get_peer_opportunities,
    get_ranked_actions,
    opportunity_type_distribution,
)
from backend.app.capabilities.insights.models import (  # noqa: E402
    CustomerPrediction,
    CustomerProfile,
    PortfolioRow,
    Requirement,
)
from backend.app.capabilities.insights.peers import add_to_peer_index  # noqa: E402

FIXTURE = json.loads(
    (ROOT / "analysis/challenge2_insights/fixtures/synthetic_snapshot.json").read_text()
)


def main() -> None:
    profiles = {p["customer_id"]: CustomerProfile(**p) for p in FIXTURE["profiles"]}
    industry_by_customer = {c: p.industry_id or "" for c, p in profiles.items()}
    portfolios = [PortfolioRow(**r) for r in FIXTURE["portfolios"]]
    stats = SnapshotStats(**FIXTURE["stats"])
    labels = FIXTURE["group_labels"]

    index = add_to_peer_index({}, portfolios, industry_by_customer)
    owned: dict[str, set[str]] = {}
    for row in portfolios:
        owned.setdefault(row.customer_id, set()).add(row.group_id)

    peers = {
        cid: get_peer_opportunities(
            target_customer_id=cid,
            target_industry_id=profiles[cid].industry_id,
            owned_group_ids=owned.get(cid, set()),
            peer_index=index,
            group_labels=labels,
            window_start=FIXTURE["window_start"],
            window_end=FIXTURE["window_end"],
            min_peer_accounts=2,
            min_prevalence=0.25,
        )
        for cid in profiles
    }

    reqs: dict[str, list[Requirement]] = {}
    for r in FIXTURE["requirements"]:
        reqs.setdefault(r["customer_id"], []).append(Requirement(**r))
    preds = {p["customer_id"]: CustomerPrediction(**p) for p in FIXTURE["predictions"]}

    actions = get_ranked_actions(
        snapshot_id=FIXTURE["snapshot_id"],
        customer_ids=sorted(profiles),
        requirements_by_customer=reqs,
        predictions_by_customer=preds,
        peers_by_customer=peers,
        workflows_by_customer={},
        stats=stats,
    )

    print(f"snapshot={FIXTURE['snapshot_id']} reference={FIXTURE['reference_date']}")
    print(f"peer thresholds used here: min_accounts=2 min_prevalence=0.25 (fixture-small)")
    print("\n== ranked queue ==")
    for action in actions:
        print(
            f"{action.customer_id} score={action.priority_score:.1f} "
            f"primary={action.primary_type} readiness={action.readiness} "
            f"reasons={[r.type + ':' + r.status for r in action.reasons]}"
        )

    print("\n== preparation card: C-AUTO-001 ==")
    target = next((a for a in actions if a.customer_id == "C-AUTO-001"), None)
    if target is not None:
        card = build_preparation(
            profile=profiles["C-AUTO-001"],
            action=target,
            peer_opportunities=peers["C-AUTO-001"],
            prediction=preds.get("C-AUTO-001"),
            requirements=reqs.get("C-AUTO-001", []),
            workflow=None,
            reference_date=FIXTURE["reference_date"],
        )
        for fact in card.facts:
            print(f"FACT [{','.join(fact.evidence_refs)}] {fact.text}")
        for unknown in card.unknowns:
            print(f"UNKNOWN {unknown}")
        for question in card.questions:
            print(f"ASK {question}")
        print(f"NEXT {card.suggested_next_step}")

    print("\n== EDA: category prevalence by industry ==")
    for row in category_prevalence_by_industry(
        portfolios=portfolios,
        industry_by_customer=industry_by_customer,
        window_start=FIXTURE["window_start"],
        window_end=FIXTURE["window_end"],
    ):
        print(
            f"{row['industry_id']}/{row['group_id']}: "
            f"{row['accounts_with_group']}/{row['eligible_accounts']} "
            f"= {row['prevalence']:.0%}"
        )
    print("\n== EDA: opportunity mix ==")
    for row in opportunity_type_distribution(actions):
        print(f"{row['type']}: {row['reasons']} reasons across {row['accounts']} accounts")
    cov = account_coverage(customer_ids=sorted(profiles), actions=actions)
    print(f"\n== EDA: coverage == {cov}")


if __name__ == "__main__":
    main()
