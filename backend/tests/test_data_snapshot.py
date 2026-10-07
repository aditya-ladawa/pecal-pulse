"""Member 1: snapshot loader + requirement inference + builder tests."""

import unittest

from backend.app.capabilities import data
from backend.app.capabilities.data import requirements
from backend.app.capabilities.data.build_snapshot import build_snapshot as make_snapshot

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


def extract_inputs():
    monthly = [
        {"customer": "C1", "month": "2026-07", "calibrations": 2, "instruments": 1, "equipment_groups": 1, "labs": 1},
        {"customer": "C1", "month": "2026-07", "calibrations": 1, "instruments": 1, "equipment_groups": 0, "labs": 0},
        {"customer": "C1", "month": "2026-09", "calibrations": 5, "instruments": 2, "equipment_groups": 1, "labs": 1},
        {"customer": "C2", "month": "2026-08", "calibrations": 0, "instruments": 0, "equipment_groups": 0, "labs": 0},
    ]
    industry = [
        {"customer": "C1", "industry": "Automotive"},
        {"customer": "C2", "industry": "Unknown"},
    ]
    groups = [{"customer": "C1", "equipment_group": "Calipers", "calibrations": 3}]
    instruments = [
        {
            "instrument": "UUID-1",
            "customer": "C1",
            "equipment_group": "Calipers",
            "last_calibration": "2025-10-10",
            "recorded_due": None,
            "nominal_interval": 12,
            "interval_unit": "Monate",
            "stopped": 0,
        },
        {
            "instrument": "UUID-2",
            "customer": "C1",
            "equipment_group": "Calipers",
            "last_calibration": "2025-01-01",
            "recorded_due": None,
            "nominal_interval": 400,
            "interval_unit": "Tage",
            "stopped": None,
        },
        {
            "instrument": "UUID-3",
            "customer": "C1",
            "equipment_group": "Calipers",
            "last_calibration": None,
            "recorded_due": None,
            "nominal_interval": 6,
            "interval_unit": "Furlongs",
            "stopped": 1,
        },
    ]
    return monthly, industry, groups, instruments, []


def build_test_doc():
    monthly, industry, groups, instruments, events = extract_inputs()
    return make_snapshot(
        monthly,
        industry,
        groups,
        instruments,
        events,
        snapshot_id="test-build",
        extracted_at="2026-09-01T08:00:00Z",
        reference_date="2026-08-31",
        complete_through_month="2026-08",
        history_start="2024-01",
    )


class SnapshotBuilderTests(unittest.TestCase):
    def test_duplicates_summed_and_september_dropped(self):
        doc = build_test_doc()
        self.assertIn("duplicate_month_rows_summed:1", doc["manifest"]["quality_flags"])
        self.assertIn("out_of_range_month_rows_dropped:1", doc["manifest"]["quality_flags"])
        july = [h for h in doc["history"] if h["customer_id"] == "C1" and h["month"] == "2026-07"]
        self.assertEqual(len(july), 1)
        self.assertEqual(july[0]["calibration_events"], 3)

    def test_zero_fill_between_first_seen_and_complete(self):
        doc = build_test_doc()
        months = sorted(h["month"] for h in doc["history"] if h["customer_id"] == "C1")
        self.assertEqual(months, ["2026-07", "2026-08"])
        # C2 first seen in 2026-08: no invented earlier history.
        c2 = sorted(h["month"] for h in doc["history"] if h["customer_id"] == "C2")
        self.assertEqual(c2, ["2026-08"])

    def test_identifier_names_and_unknown_industry(self):
        doc = build_test_doc()
        by_id = {p["customer_id"]: p for p in doc["profiles"]}
        self.assertEqual(by_id["C1"]["industry_id"], "IND-AUTOMOTIVE")
        self.assertEqual(by_id["C1"]["display_name"], "Account C1")
        self.assertIsNone(by_id["C2"]["industry_id"])
        self.assertIsNone(by_id["C2"]["industry_label"])

    def test_interval_units_and_stop_tristate(self):
        doc = build_test_doc()
        nominal = [i for i in doc["instruments"] if i["nominal_interval_months"] == 12]
        self.assertEqual(len(nominal), 1)
        self.assertFalse(nominal[0]["stopped"])
        day_based = [i for i in doc["instruments"] if i["nominal_interval_months"] == 13]
        self.assertEqual(day_based[0]["quality_flags"], ["day_unit_converted_to_months"])
        unknown_unit = [i for i in doc["instruments"] if i["nominal_interval_months"] is None]
        self.assertEqual(len(unknown_unit), 1)
        self.assertTrue(unknown_unit[0]["stopped"])
        # Instrument UUIDs are hashed, never raw.
        self.assertNotIn("UUID-1", {i["instrument_id"] for i in doc["instruments"]})

    def test_manifest_counts_match(self):
        doc = build_test_doc()
        counts = doc["manifest"]["row_counts"]
        for section in ("profiles", "history", "portfolio", "instruments", "events", "requirements"):
            self.assertEqual(counts[section], len(doc[section]), section)

    def test_builder_without_instruments_still_builds(self):
        monthly, industry, groups, _, _ = extract_inputs()
        doc = make_snapshot(
            monthly,
            industry,
            groups,
            None,
            None,
            snapshot_id="test-noinst",
            extracted_at="2026-09-01T08:00:00Z",
            reference_date="2026-08-31",
            complete_through_month="2026-08",
            history_start="2024-01",
        )
        self.assertIn("instrument_level_not_exported", doc["manifest"]["quality_flags"])
        self.assertEqual(doc["requirements"], [])


if __name__ == "__main__":
    unittest.main()
