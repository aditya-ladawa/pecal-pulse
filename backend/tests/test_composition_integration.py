"""Member 1 × Member 3 integration: the complete correction flow.

Record "timing changed" -> snooze/resolve the old reason -> refresh ->
the suppressed reason disappears while unrelated reasons remain, and the
persisted next step (follow-up) survives. Uses the shared synthetic
snapshot and an isolated temp SQLite database.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app.capabilities import data
from backend.app.contracts import sales_v2 as v2

SNAPSHOT = "synthetic-v1"
TODAY = "2026-10-07"


class CorrectionFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.patch = patch.dict(
            os.environ, {"PECAL_DEMO_DB": str(Path(self.tmp.name) / "flow.sqlite3")}
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def _snooze(self, customer, reason, until="2026-11-01"):
        return data.add_suppression(
            customer,
            v2.SuppressionRecord(
                reason_id=reason,
                status="snoozed",
                until=until,
                note="Timing changed on the call.",
                updated_at="2026-09-01T08:00:00Z",
            ),
            {r.id for r in data.load_snapshot(SNAPSHOT)["requirements"]},
        )

    def test_snoozed_reason_vanishes_others_remain(self):
        before = data.action_for_customer(SNAPSHOT, "SYN-001", TODAY)
        self.assertTrue(any("REQ-001" in r.evidence_refs for r in before.reasons))
        self._snooze("SYN-001", "REQ-001")
        refreshed = data.refresh_after_correction(SNAPSHOT, "SYN-001", today=TODAY)
        self.assertEqual(refreshed["suppressed_requirement_ids"], ["REQ-001"])
        self.assertNotIn("REQ-001", refreshed["active_requirement_ids"])
        self.assertIn("REQ-002", refreshed["active_requirement_ids"])
        action = refreshed["action"]
        self.assertIsNotNone(action)
        for reason in action.reasons:
            self.assertNotIn("REQ-001", reason.evidence_refs)
        # The old reason is gone but the account keeps its other reasons.
        self.assertTrue(action.reasons)

    def test_resolve_then_followup_persists_next_step(self):
        data.add_suppression(
            "SYN-001",
            v2.SuppressionRecord(
                reason_id="REQ-002",
                status="resolved",
                note="Need confirmed by phone.",
                updated_at="2026-09-01T08:00:00Z",
            ),
            {r.id for r in data.load_snapshot(SNAPSHOT)["requirements"]},
        )
        created = data.create_followup_v2(
            v2.FollowupCreateV2(
                customer_id="SYN-001",
                owner="Alex Meyer",
                due_date="2026-10-15",
                note="Agreed callback window.",
                outcome="Timing changed",
                reason_ids=["REQ-001"],
            ),
            "Werkstatt Beispiel GmbH",
        )["payload"]
        refreshed = data.refresh_after_correction(SNAPSHOT, "SYN-001", today=TODAY)
        self.assertIn("REQ-002", refreshed["suppressed_requirement_ids"])
        self.assertEqual(refreshed["workflow"].followups[0].id, created["id"])
        self.assertEqual(refreshed["workflow"].followups[0].status, "open")

    def test_ranking_is_deterministic(self):
        first = data.ranked_queue(SNAPSHOT, TODAY)
        second = data.ranked_queue(SNAPSHOT, TODAY)
        self.assertEqual(
            [(a.customer_id, a.priority_score) for a in first],
            [(a.customer_id, a.priority_score) for a in second],
        )
        scores = [a.priority_score for a in first]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_preparation_is_grounded(self):
        card = data.preparation_for_customer(SNAPSHOT, "SYN-001", TODAY)
        self.assertTrue(card.facts)
        self.assertTrue(card.suggested_next_step)
        self.assertEqual(card.customer_id, "SYN-001")
        self.assertEqual(card.reference_date, "2026-08-31")

    def test_peers_disclose_support(self):
        peers = data.peers_for_customer(SNAPSHOT, "SYN-001")
        for peer in peers:
            self.assertGreaterEqual(peer.peer_count, 20)
            self.assertGreaterEqual(peer.prevalence, 0.25)
            self.assertTrue(peer.question)


if __name__ == "__main__":
    unittest.main()
