"""Member 1: snapshot loader + requirement inference tests."""

import unittest

from backend.app.capabilities import data
from backend.app.capabilities.data import requirements

SNAPSHOT = "synthetic-v1"
REFERENCE = "2026-08-31"


class SnapshotLoaderTests(unittest.TestCase):
    def test_synthetic_snapshot_available(self):
        self.assertIn(SNAPSHOT, data.available_snapshots())

    def test_unknown_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            data.load_snapshot("no-such-snapshot")

    def test_detail_unknown_customer_rejected(self):
        with self.assertRaises(ValueError):
            data.get_customer_detail(SNAPSHOT, "no-such-customer")

    def test_recency_from_history(self):
        # SYN-001 latest active month is 2026-08 -> recency 0.
        self.assertEqual(data.recency_months(SNAPSHOT, "SYN-001"), 0)
        # SYN-002 has no active months -> unknown, not zero.
        self.assertIsNone(data.recency_months(SNAPSHOT, "SYN-002"))


class InferenceTierTests(unittest.TestCase):
    def setUp(self):
        snapshot = data.load_snapshot(SNAPSHOT)
        self.instruments = snapshot["instruments"]
        self.events = snapshot["events"]
        self.stored = {r.instrument_id: r for r in snapshot["requirements"]}

    def test_inference_reproduces_stored_tiers(self):
        inferred = {
            r.instrument_id: r
            for r in requirements.infer_requirements(
                self.instruments, self.events, REFERENCE
            )
        }
        self.assertEqual(set(inferred), set(self.stored))
        for instrument_id, want in self.stored.items():
            got = inferred[instrument_id]
            self.assertEqual(got.kind, want.kind, instrument_id)
            self.assertEqual(got.eligibility, want.eligibility, instrument_id)

    def test_all_four_tiers_covered(self):
        kinds = {r.kind for r in self.stored.values()}
        self.assertEqual(
            kinds, {"recorded", "nominal_interval", "repeat_history", "unknown"}
        )

    def test_implausible_recorded_date_falls_through(self):
        (inst,) = [i for i in self.instruments if i.instrument_id == "INST-002"]
        bad = inst.model_copy(
            update={"recorded_due_date": "2024-01-01", "stopped": False}
        )  # due before last calibration
        (req,) = requirements.infer_requirements([bad], [], REFERENCE)
        self.assertEqual(req.kind, "nominal_interval")

    def test_repeat_history_needs_three_positive_gaps(self):
        (inst,) = [i for i in self.instruments if i.instrument_id == "INST-004"]
        self.assertEqual(inst.instrument_id, "INST-004")
        (req,) = requirements.infer_requirements([inst], self.events, REFERENCE)
        # INST-004 has no own events -> unknown, never a fabricated window.
        self.assertEqual(req.kind, "unknown")
        self.assertIsNone(req.window_start)

    def test_null_stop_stays_review_required(self):
        (req,) = [
            r
            for r in requirements.infer_requirements(
                self.instruments, self.events, REFERENCE
            )
            if r.instrument_id == "INST-004"
        ]
        self.assertEqual(req.eligibility, "review_required")


if __name__ == "__main__":
    unittest.main()
