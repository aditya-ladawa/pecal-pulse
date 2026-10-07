"""Member 3 — focused invariant tests (not copies of the implementation).

Covers plan §Member 3.7: stopped/resolved/snoozed reasons, portfolio
denominator, target-account exclusion, sparse industries, account-level
deduplication, deterministic ranking, unknown inputs.
"""

import json
import unittest
from pathlib import Path

from backend.app.capabilities.insights import (
    SnapshotStats,
    build_account_action,
    build_peer_index,
    build_preparation,
    category_prevalence_by_industry,
    get_peer_opportunities,
    get_ranked_actions,
    rank_actions,
)
from backend.app.capabilities.insights.actions import (
    build_upcoming_reasons,
)
from backend.app.capabilities.insights.models import (
    AccountWorkflow,
    CustomerPrediction,
    CustomerProfile,
    PortfolioRow,
    Requirement,
    SuppressionRecord,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "analysis/challenge2_insights/fixtures/synthetic_snapshot.json").read_text()
)


def _req(**over):
    base = {
        "id": "R-x",
        "customer_id": "C-AUTO-001",
        "instrument_id": "I-1",
        "group_id": "G-CALIPER",
        "kind": "recorded",
        "window_start": "2026-09-05",
        "window_end": "2026-09-25",
        "method": "recorded due date",
        "evidence_dates": ["2025-09-10"],
        "positive_gap_count": 0,
        "stopped": False,
        "eligibility": "eligible",
        "unknowns": [],
    }
    base.update(over)
    return Requirement(**base)


def _stats() -> SnapshotStats:
    return SnapshotStats(**FIXTURE["stats"])


def _industry_map() -> dict[str, str]:
    return {p["customer_id"]: p["industry_id"] for p in FIXTURE["profiles"]}


def _portfolios() -> list[PortfolioRow]:
    return [PortfolioRow(**r) for r in FIXTURE["portfolios"]]


class PeerDiscoveryTests(unittest.TestCase):
    def test_target_account_excluded_from_peers(self):
        # C-AUTO-002 owns TORQUE; with lowered thresholds it must NOT be
        # offered its own category back as a discovery.
        index = build_peer_index(_portfolios(), _industry_map())
        industry_by_customer = _industry_map()
        # rebuild with industry mapping (PortfolioRow carries no industry)
        from backend.app.capabilities.insights.peers import add_to_peer_index

        index = add_to_peer_index({}, _portfolios(), industry_by_customer)
        opps = get_peer_opportunities(
            target_customer_id="C-AUTO-002",
            target_industry_id="AUTO",
            owned_group_ids={"G-CALIPER", "G-TORQUE"},
            peer_index=index,
            group_labels=FIXTURE["group_labels"],
            window_start="2025-09-01",
            window_end="2026-08-31",
            min_peer_accounts=2,
            min_prevalence=0.25,
        )
        self.assertEqual(opps, [])

    def test_sparse_industry_returns_no_opportunities_at_default_thresholds(self):
        from backend.app.capabilities.insights.peers import add_to_peer_index

        index = add_to_peer_index({}, _portfolios(), _industry_map())
        opps = get_peer_opportunities(
            target_customer_id="C-AUTO-001",
            target_industry_id="AUTO",
            owned_group_ids={"G-CALIPER"},
            peer_index=index,
            group_labels=FIXTURE["group_labels"],
            window_start="2025-09-01",
            window_end="2026-08-31",
        )
        # Only 3 peers < default minimum of 20.
        self.assertEqual(opps, [])

    def test_lowered_thresholds_yield_disclosed_denominator(self):
        from backend.app.capabilities.insights.peers import add_to_peer_index

        index = add_to_peer_index({}, _portfolios(), _industry_map())
        opps = get_peer_opportunities(
            target_customer_id="C-AUTO-001",
            target_industry_id="AUTO",
            owned_group_ids={"G-CALIPER"},
            peer_index=index,
            group_labels=FIXTURE["group_labels"],
            window_start="2025-09-01",
            window_end="2026-08-31",
            min_peer_accounts=2,
            min_prevalence=0.25,
        )
        self.assertEqual(len(opps), 1)
        opp = opps[0]
        self.assertEqual(opp.group_id, "G-TORQUE")
        # 3 peers (002, 003, 004 own TORQUE after excluding target).
        self.assertEqual(opp.peer_count, 3)
        self.assertEqual(opp.peers_with_group, 3)
        self.assertAlmostEqual(opp.prevalence, 1.0)
        self.assertIn("do not assume", opp.question.lower())

    def test_unknown_industry_never_produces_discovery(self):
        from backend.app.capabilities.insights.peers import add_to_peer_index

        index = add_to_peer_index({}, _portfolios(), _industry_map())
        for unknown in ("Unknown", "Sonstiges", " unknown ", None):
            opps = get_peer_opportunities(
                target_customer_id="C-UNK-001",
                target_industry_id=unknown,
                owned_group_ids=set(),
                peer_index=index,
                group_labels=FIXTURE["group_labels"],
                window_start="2025-09-01",
                window_end="2026-08-31",
                min_peer_accounts=1,
                min_prevalence=0.0,
            )
            self.assertEqual(opps, [], f"industry={unknown!r}")

    def test_row_counts_do_not_inflate_denominator(self):
        rows = _portfolios() + [
            PortfolioRow(
                customer_id="C-AUTO-002",
                group_id="G-TORQUE",
                group_label="Torque tools",
                distinct_instruments=99,
                calibration_events=999,
                window_start="2025-09-01",
                window_end="2026-08-31",
            )
        ]
        from backend.app.capabilities.insights.peers import add_to_peer_index

        index = add_to_peer_index({}, rows, _industry_map())
        # Same account twice in one category still counts once.
        self.assertEqual(index["AUTO"]["G-TORQUE"], {"C-AUTO-002", "C-AUTO-003", "C-AUTO-004"})


class ActionConstructionTests(unittest.TestCase):
    def test_duplicate_instruments_bundle_into_one_reason(self):
        reqs = [
            _req(id="R-1", instrument_id="I-1"),
            _req(id="R-2", instrument_id="I-2"),
            _req(id="R-1b", instrument_id="I-1"),  # duplicate row, same instrument
        ]
        reasons = build_upcoming_reasons(
            customer_id="C-AUTO-001", requirements=reqs, workflow=None, today="2026-08-31"
        )
        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0].quantity, 2)
        self.assertEqual(reasons[0].instrument_ids, ["I-1", "I-2"])

    def test_stopped_instruments_never_rank(self):
        reqs = [_req(id="R-s", instrument_id="I-9", stopped=True)]
        action = build_account_action(
            snapshot_id="s",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=None,
            peer_opportunities=[],
            workflow=None,
            stats=_stats(),
        )
        self.assertIsNone(action)

    def test_snoozed_reason_disappears_while_unrelated_remain(self):
        reqs = [
            _req(id="R-1", instrument_id="I-1", group_id="G-A",
                 window_start="2026-09-01", window_end="2026-09-10"),
            _req(id="R-2", instrument_id="I-2", group_id="G-B",
                 window_start="2026-09-01", window_end="2026-09-10"),
        ]
        from backend.app.capabilities.insights.actions import reason_id_for

        snoozed_id = reason_id_for("C-AUTO-001", "upcoming", "G-A:2026-09-01:2026-09-10")
        workflow = AccountWorkflow(
            suppressions=[
                SuppressionRecord(
                    reason_id=snoozed_id,
                    status="snoozed",
                    until="2026-12-31",
                    note="not now",
                    updated_at="2026-08-01",
                )
            ]
        )
        action = build_account_action(
            snapshot_id="s",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=None,
            peer_opportunities=[],
            workflow=workflow,
            stats=_stats(),
            today="2026-08-31",
        )
        assert action is not None
        ids = [r.id for r in action.reasons]
        self.assertNotIn(snoozed_id, ids)
        self.assertEqual(len(ids), 1)

    def test_expired_snooze_releases_the_reason(self):
        reqs = [_req(id="R-1", instrument_id="I-1")]
        from backend.app.capabilities.insights.actions import reason_id_for

        rid = reason_id_for(
            "C-AUTO-001", "upcoming", "G-CALIPER:2026-09-05:2026-09-25"
        )
        workflow = AccountWorkflow(
            suppressions=[
                SuppressionRecord(
                    reason_id=rid, status="snoozed", until="2026-08-01",
                    note="old", updated_at="2026-07-01",
                )
            ]
        )
        action = build_account_action(
            snapshot_id="s",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=None,
            peer_opportunities=[],
            workflow=workflow,
            stats=_stats(),
            today="2026-08-31",
        )
        assert action is not None
        self.assertIn(rid, [r.id for r in action.reasons])

    def test_resolution_requires_a_note(self):
        reqs = [_req(id="R-1", instrument_id="I-1")]
        from backend.app.capabilities.insights.actions import reason_id_for

        rid = reason_id_for(
            "C-AUTO-001", "upcoming", "G-CALIPER:2026-09-05:2026-09-25"
        )
        empty_note = AccountWorkflow(
            suppressions=[
                SuppressionRecord(
                    reason_id=rid, status="resolved", note="",
                    updated_at="2026-08-01",
                )
            ]
        )
        action = build_account_action(
            snapshot_id="s",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=None,
            peer_opportunities=[],
            workflow=empty_note,
            stats=_stats(),
            today="2026-08-31",
        )
        # Empty note → resolution ignored, reason stays.
        assert action is not None
        self.assertIn(rid, [r.id for r in action.reasons])

    def test_missing_live_checks_force_review_required(self):
        reqs = [_req(id="R-1", instrument_id="I-1")]  # otherwise eligible
        action = build_account_action(
            snapshot_id="s",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=None,
            peer_opportunities=[],
            workflow=AccountWorkflow(),  # all checks unknown
            stats=_stats(),
        )
        assert action is not None
        self.assertEqual(action.readiness, "review_required")
        self.assertTrue(
            all(r.status != "eligible" for r in action.reasons)
        )

    def test_recorded_live_checks_allow_eligible(self):
        from backend.app.capabilities.insights.models import WorkflowChecks

        reqs = [_req(id="R-1", instrument_id="I-1")]
        workflow = AccountWorkflow(
            checks=WorkflowChecks(quotation_order="reported_none", recent_contact="checked")
        )
        action = build_account_action(
            snapshot_id="s",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=None,
            peer_opportunities=[],
            workflow=workflow,
            stats=_stats(),
        )
        assert action is not None
        self.assertEqual(action.readiness, "eligible")

    def test_unknown_prediction_stays_explicit_not_strong(self):
        reqs = [_req(id="R-1", instrument_id="I-1")]
        action = build_account_action(
            snapshot_id="s",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=None,
            peer_opportunities=[],
            workflow=None,
            stats=_stats(),
        )
        assert action is not None
        self.assertIsNone(action.components["activity_deviation"])

    def test_same_input_gives_same_ranked_evidence(self):
        def build_once():
            reqs = [Requirement(**r) for r in FIXTURE["requirements"]
                    if r["customer_id"] == "C-AUTO-001"]
            pred = CustomerPrediction(** next(
                p for p in FIXTURE["predictions"] if p["customer_id"] == "C-AUTO-001"))
            return build_account_action(
                snapshot_id="synth-2026-08-31",
                customer_id="C-AUTO-001",
                requirements=reqs,
                prediction=pred,
                peer_opportunities=[],
                workflow=None,
                stats=_stats(),
            )
        first = build_once()
        second = build_once()
        assert first is not None and second is not None
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_queue_order_deterministic_on_ties(self):
        actions = get_ranked_actions(
            snapshot_id="s",
            customer_ids=["C-B", "C-A"],
            requirements_by_customer={
                "C-A": [_req(id="R-a", customer_id="C-A")],
                "C-B": [_req(id="R-b", customer_id="C-B")],
            },
            predictions_by_customer={},
            peers_by_customer={},
            workflows_by_customer={},
            stats=_stats(),
        )
        # Identical scores → customer_id asc.
        self.assertEqual([a.customer_id for a in actions], ["C-A", "C-B"])
        again = rank_actions(list(reversed(actions)))
        self.assertEqual([a.customer_id for a in again], ["C-A", "C-B"])


class PreparationTests(unittest.TestCase):
    def test_preparation_grounds_every_fact_and_asks_peer_question(self):
        from backend.app.capabilities.insights.peers import add_to_peer_index

        profile = CustomerProfile(
            customer_id="C-AUTO-001", display_name="C-AUTO-001",
            industry_id="AUTO", industry_label="Automotive",
        )
        reqs = [Requirement(**r) for r in FIXTURE["requirements"]
                if r["customer_id"] == "C-AUTO-001"]
        pred = CustomerPrediction(** next(
            p for p in FIXTURE["predictions"] if p["customer_id"] == "C-AUTO-001"))
        index = add_to_peer_index({}, _portfolios(), _industry_map())
        opps = get_peer_opportunities(
            target_customer_id="C-AUTO-001",
            target_industry_id="AUTO",
            owned_group_ids={"G-CALIPER"},
            peer_index=index,
            group_labels=FIXTURE["group_labels"],
            window_start="2025-09-01",
            window_end="2026-08-31",
            min_peer_accounts=2,
            min_prevalence=0.25,
        )
        action = build_account_action(
            snapshot_id="synth-2026-08-31",
            customer_id="C-AUTO-001",
            requirements=reqs,
            prediction=pred,
            peer_opportunities=opps,
            workflow=None,
            stats=_stats(),
        )
        assert action is not None
        card = build_preparation(
            profile=profile,
            action=action,
            peer_opportunities=opps,
            prediction=pred,
            requirements=reqs,
            workflow=None,
            reference_date="2026-08-31",
        )
        self.assertTrue(card.facts)
        for fact in card.facts:
            self.assertTrue(fact.evidence_refs, f"ungrounded fact: {fact.text}")
        self.assertTrue(any("Torque" in q for q in card.questions))
        self.assertNotIn("owns torque tools", " ".join(card.questions).lower())

    def test_category_prevalence_reports_denominator(self):
        rows = category_prevalence_by_industry(
            portfolios=_portfolios(),
            industry_by_customer=_industry_map(),
            window_start="2025-09-01",
            window_end="2026-08-31",
        )
        auto_torque = next(
            r for r in rows if r["industry_id"] == "AUTO" and r["group_id"] == "G-TORQUE"
        )
        self.assertEqual(auto_torque["eligible_accounts"], 4)
        self.assertEqual(auto_torque["accounts_with_group"], 3)
        self.assertAlmostEqual(auto_torque["prevalence"], 0.75)


if __name__ == "__main__":
    unittest.main()
