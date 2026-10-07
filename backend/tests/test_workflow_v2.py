"""Member 1: workflow persistence tests (isolated temp SQLite)."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app.capabilities import data
from backend.app.contracts import sales_v2 as v2


def make_followup(customer_id="SYN-001"):
    return v2.FollowupCreateV2(
        customer_id=customer_id,
        owner="Alex Meyer",
        due_date="2026-09-15",
        note="Confirm timing.",
        outcome="Timing changed",
        reason_ids=["REQ-001"],
    )


class WorkflowPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "workflow.sqlite3")
        self.patch = patch.dict(os.environ, {"PECAL_DEMO_DB": self.db})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_checks_survive_reconnect(self):
        data.update_checks(
            "SYN-001",
            v2.WorkflowPatchChecks(quotation_order="reported_none", checked_by="AM"),
            checked_by="AM",
        )
        reloaded = data.get_workflow("SYN-001")
        self.assertEqual(reloaded.checks.quotation_order, "reported_none")
        self.assertEqual(reloaded.checks.recent_contact, "unknown")
        self.assertIsNotNone(reloaded.checks.checked_at)

    def test_suppression_is_signal_scoped(self):
        first = v2.SuppressionRecord(
            reason_id="REQ-001",
            status="snoozed",
            until="2026-10-01",
            note="Customer asked to wait.",
            updated_at="2026-09-01T08:00:00Z",
        )
        second = v2.SuppressionRecord(
            reason_id="REQ-002",
            status="resolved",
            until=None,
            note="Need confirmed by phone.",
            updated_at="2026-09-01T09:00:00Z",
        )
        data.add_suppression("SYN-001", first, {"REQ-001", "REQ-002", "REQ-003"})
        workflow = data.add_suppression(
            "SYN-001", second, {"REQ-001", "REQ-002", "REQ-003"}
        )
        self.assertEqual(len(workflow.suppressions), 2)
        # Re-snoozing REQ-001 replaces only that record.
        data.add_suppression(
            "SYN-001",
            first.model_copy(update={"until": "2026-11-01"}),
            {"REQ-001", "REQ-002", "REQ-003"},
        )
        workflow = data.get_workflow("SYN-001")
        self.assertEqual(len(workflow.suppressions), 2)
        by_reason = {s.reason_id: s for s in workflow.suppressions}
        self.assertEqual(by_reason["REQ-001"].until, "2026-11-01")
        self.assertEqual(by_reason["REQ-002"].status, "resolved")

    def test_unknown_reason_rejected(self):
        with self.assertRaises(ValueError):
            data.add_suppression(
                "SYN-001",
                v2.SuppressionRecord(
                    reason_id="REQ-999",
                    status="resolved",
                    note="Nope.",
                    updated_at="2026-09-01T08:00:00Z",
                ),
                {"REQ-001"},
            )

    def test_followup_roundtrip_with_reasons(self):
        created = data.create_followup_v2(
            make_followup(), "Werkstatt Beispiel GmbH"
        )["payload"]
        self.assertEqual(created["status"], "open")
        self.assertNotIn("reason_ids", created)
        workflow = data.get_workflow("SYN-001")
        self.assertIn(created["id"], [f.id for f in workflow.followups])
        data.update_followup_status(created["id"], "done")
        # Repeated same-state updates are safe.
        data.update_followup_status(created["id"], "done")
        reloaded = data.get_workflow("SYN-001")
        self.assertEqual(reloaded.followups[0].status, "done")

    def test_unknown_followup_rejected(self):
        with self.assertRaises(ValueError):
            data.update_followup_status("task-missing", "done")

    def test_customers_are_isolated(self):
        data.update_checks(
            "SYN-001", v2.WorkflowPatchChecks(contact_details="supplied")
        )
        other = data.get_workflow("SYN-002")
        self.assertEqual(other.checks.contact_details, "unknown")
        self.assertEqual(other.followups, [])


class RefreshAfterCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.patch = patch.dict(
            os.environ, {"PECAL_DEMO_DB": str(Path(self.tmp.name) / "refresh.sqlite3")}
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_refresh_without_ranking_fn_returns_no_action(self):
        refreshed = data.refresh_after_correction("synthetic-v1", "SYN-001")
        self.assertEqual(len(refreshed["requirements"]), 5)
        self.assertEqual(len(refreshed["active_requirement_ids"]), 5)
        self.assertEqual(refreshed["suppressed_requirement_ids"], [])
        self.assertIsNone(refreshed["action"])

    def test_resolved_reason_leaves_active_set(self):
        data.add_suppression(
            "SYN-001",
            v2.SuppressionRecord(
                reason_id="REQ-005",
                status="resolved",
                note="Instrument retired.",
                updated_at="2026-09-01T08:00:00Z",
            ),
            {"REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"},
        )
        seen = {}

        def stub_ranking(profile, requirements, prediction, peers, workflow):
            seen["ids"] = [r.id for r in requirements]
            return "ranked"

        refreshed = data.refresh_after_correction(
            "synthetic-v1", "SYN-001", ranking_fn=stub_ranking
        )
        self.assertEqual(refreshed["suppressed_requirement_ids"], ["REQ-005"])
        self.assertNotIn("REQ-005", seen["ids"])
        self.assertEqual(len(seen["ids"]), 4)
        self.assertEqual(refreshed["action"], "ranked")

    def test_expired_snooze_returns_to_active(self):
        data.add_suppression(
            "SYN-001",
            v2.SuppressionRecord(
                reason_id="REQ-001",
                status="snoozed",
                until="2026-09-01",
                note="Wait a week.",
                updated_at="2026-08-20T08:00:00Z",
            ),
            {"REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"},
        )
        refreshed = data.refresh_after_correction(
            "synthetic-v1", "SYN-001", today="2026-10-07"
        )
        self.assertEqual(refreshed["suppressed_requirement_ids"], [])
        self.assertIn("REQ-001", refreshed["active_requirement_ids"])


if __name__ == "__main__":
    unittest.main()
