"""Member 1: shared v2 contract invariants + synthetic fixture validity.

These tests pin the frozen contract (plan §4), not an implementation:
every fixture row must validate, IDs must join across exports, and
unsupported dates must stay unknown rather than becoming fake exact dates.
"""

import json
import unittest
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from backend.app.contracts import sales_v2 as v2

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "data/mock/v2_snapshot_synthetic.json").read_text())


class SyntheticFixtureTests(unittest.TestCase):
    def test_manifest_counts_match_sections(self):
        manifest = v2.SnapshotManifest.model_validate(FIXTURE["manifest"])
        sections = {
            "profiles": FIXTURE["profiles"],
            "history": FIXTURE["history"],
            "portfolio": FIXTURE["portfolio"],
            "instruments": FIXTURE["instruments"],
            "events": FIXTURE["events"],
            "requirements": FIXTURE["requirements"],
        }
        for table, rows in sections.items():
            self.assertEqual(manifest.row_counts[table], len(rows), table)

    def test_all_rows_validate(self):
        TypeAdapter(list[v2.CustomerProfile]).validate_python(FIXTURE["profiles"])
        TypeAdapter(list[v2.MonthlyHistoryRow]).validate_python(FIXTURE["history"])
        TypeAdapter(list[v2.PortfolioRow]).validate_python(FIXTURE["portfolio"])
        TypeAdapter(list[v2.InstrumentRecord]).validate_python(FIXTURE["instruments"])
        TypeAdapter(list[v2.InstrumentEvent]).validate_python(FIXTURE["events"])
        TypeAdapter(list[v2.Requirement]).validate_python(FIXTURE["requirements"])

    def test_ids_join_across_exports(self):
        profiles = {p["customer_id"] for p in FIXTURE["profiles"]}
        instruments = {i["instrument_id"] for i in FIXTURE["instruments"]}
        for req in FIXTURE["requirements"]:
            self.assertIn(req["customer_id"], profiles)
            self.assertIn(req["instrument_id"], instruments)

    def test_unknown_means_unknown(self):
        for req in FIXTURE["requirements"]:
            if req["kind"] == "unknown":
                self.assertIsNone(req["window_start"], req["id"])
                self.assertIsNone(req["window_end"], req["id"])
                self.assertTrue(req["unknowns"], req["id"])
                self.assertEqual(req["eligibility"], "review_required", req["id"])

    def test_stopped_is_excluded(self):
        stopped = [i for i in FIXTURE["instruments"] if i["stopped"] is True]
        self.assertTrue(stopped, "fixture must cover the stopped case")
        reqs = {r["instrument_id"]: r for r in FIXTURE["requirements"]}
        for inst in stopped:
            self.assertEqual(reqs[inst["instrument_id"]]["eligibility"], "excluded")

    def test_identifier_fallback_has_no_invented_name(self):
        for profile in FIXTURE["profiles"]:
            if profile["name_source"] == "identifier":
                self.assertIn(profile["customer_id"], profile["display_name"])


class ContractInvariantTests(unittest.TestCase):
    def test_snooze_requires_end_date(self):
        with self.assertRaises(ValidationError):
            v2.SuppressionRecord.model_validate(
                {
                    "reason_id": "R1",
                    "status": "snoozed",
                    "until": None,
                    "note": "waiting",
                    "updated_at": "2026-09-01T08:00:00Z",
                }
            )

    def test_empty_workflow_patch_rejected(self):
        with self.assertRaises(ValidationError):
            v2.WorkflowPatch.model_validate({"checks": None, "suppression": None})

    def test_correlation_matrix_must_be_square(self):
        with self.assertRaises(ValidationError):
            v2.SectorCorrelation.model_validate(
                {
                    "industry_ids": ["a", "b"],
                    "labels": ["A", "B"],
                    "values": [[1.0]],
                    "pair_sample_counts": [[10]],
                    "window_start": "2024-01",
                    "window_end": "2026-08",
                    "warnings": [],
                }
            )

    def test_v2_filters_accept_snapshot_ids(self):
        filters = v2.FiltersV2.model_validate(
            {"industry": "IND-AUTOMOTIVE", "segment": "seg-3", "action": "upcoming"}
        )
        self.assertEqual(filters.segment, "seg-3")


if __name__ == "__main__":
    unittest.main()
