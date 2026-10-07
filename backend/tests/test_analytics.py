import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from analysis.challenge2_ml.synthetic_fixture import make_fixture
from backend.app.capabilities.analytics.features import (feature_row, index_history,
    inactivity_evidence, month_index, next_month_window, support)
from backend.app.capabilities.analytics.pipeline import build_outputs
from backend.app.capabilities.analytics.sectors import build_sectors
from backend.app.capabilities.analytics.service import (get_prediction, load_outputs,
    publish_outputs, validate_outputs)


class AnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = make_fixture()
        cls.outputs = build_outputs(cls.fixture)

    def test_chronological_stages_and_live_horizon(self):
        report = self.outputs["model_report"]
        stages = report["stage_cutoffs"]
        index = month_index
        self.assertLessEqual(index(stages["train_end"]) + 3, index(stages["calibration"]))
        self.assertLessEqual(index(stages["calibration"]) + 3, index(stages["validation"]))
        self.assertLessEqual(index(stages["validation"]) + 3, index(stages["test_start"]))
        self.assertEqual(next_month_window("2026-12-31"), ("2027-01", "2027-03"))
        self.assertTrue(self.outputs["manifest"]["ready"])
        self.assertIsNotNone(report["selected_activity"])
        self.assertIsNotNone(report["selected_volume"])

    def test_unsupported_customer_has_no_prediction(self):
        row = next(p for p in self.outputs["predictions"] if p["customer_id"] == "synthetic-customer-29")
        self.assertIsNone(row["activity"]["probability"])
        self.assertIsNone(row["calibration_volume"]["expected_total"])
        self.assertEqual(row["activity"]["support"]["status"], "insufficient_history")

    def test_features_do_not_see_future_rows(self):
        history = index_history(self.fixture["monthly_history"], "2026-12")["synthetic-customer-00"]
        cutoff = month_index("2025-06")
        before, _ = feature_row(history, cutoff)
        history[month_index("2026-12")] = {"calibration_events": 100000,
            "distinct_instruments": 1, "equipment_group_count": 1, "lab_count": 1}
        after, _ = feature_row(history, cutoff)
        self.assertEqual(before, after)

    def test_sector_correlations_require_support(self):
        sector = self.outputs["sectors"]
        correlation = sector["correlation"]
        self.assertEqual(correlation["method"], "pearson_log1p_monthly_change")
        self.assertEqual(correlation["pair_sample_counts"][0][1], 35)
        self.assertAlmostEqual(correlation["values"][0][1], correlation["values"][1][0])
        self.assertEqual(len(sector["forecasts"]), 2)
        self.assertEqual(sector["forecasts"][0]["validation_months"], 6)
        self.assertEqual(sector["forecasts"][0]["test_months"], 6)

    def test_identical_histories_leave_segments_unassigned(self):
        fixture = make_fixture()
        original = [r for r in fixture["monthly_history"] if r["customer_id"] == "synthetic-customer-00"]
        fixture["monthly_history"] = [{**row, "customer_id": profile["customer_id"]}
                                     for profile in fixture["profiles"] for row in original]
        output = build_outputs(fixture)
        self.assertEqual(output["segments"], [])
        self.assertTrue(all(p["segment_id"] is None for p in output["predictions"]))
        self.assertTrue(all(p["activity"]["probability"] is None for p in output["predictions"]))
        self.assertTrue(all(p["calibration_volume"]["expected_total"] is not None for p in output["predictions"]))

    def test_constant_and_short_sector_series_are_unknown(self):
        profile = [{"customer_id": "a", "industry_id": "one", "industry_label": "One"}]
        history = {"a": {month_index("2024-01") + i: {"calibration_events": 2} for i in range(36)}}
        result = build_sectors(profile, history, "2024-01", "2026-12")
        self.assertIsNone(result["correlation"]["values"][0][0])
        result = build_sectors(profile, history, "2024-01", "2024-12")
        self.assertEqual(result["correlation"]["pair_sample_counts"][0][0], 11)
        self.assertIsNone(result["correlation"]["values"][0][0])

    def test_holdout_labels_do_not_choose_models(self):
        fixture = make_fixture()
        # Test labels begin after validation labels end (2026-04 onward).
        for row in fixture["monthly_history"]:
            if row["month"] >= "2026-05":
                row["calibration_events"] *= 50
        output = build_outputs(fixture)
        for key in ("selected_activity", "selected_volume"):
            self.assertEqual(output["model_report"][key], self.outputs["model_report"][key])

    def test_rejects_unsupported_forecast_and_unsafe_snapshot_id(self):
        invalid = deepcopy(self.outputs)
        invalid["predictions"][-1]["calibration_volume"]["expected_total"] = 1
        with self.assertRaises(ValueError):
            validate_outputs(invalid)
        for snapshot_id in ("../escape", "a:b", "a\\b"):
            with self.assertRaises(ValueError):
                load_outputs(snapshot_id)

    def test_immutable_publication_and_mismatch_rejection(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            root = Path(folder)
            publish_outputs(self.outputs, root)
            loaded = load_outputs("synthetic-analytics-v1", root)
            self.assertEqual(len(loaded["predictions"]), 30)
            self.assertIsNotNone(get_prediction("synthetic-customer-00", "synthetic-analytics-v1", root))
            with self.assertRaises(FileExistsError):
                publish_outputs(self.outputs, root)
            loaded["predictions"][0]["snapshot_id"] = "different"
            with self.assertRaises(ValueError):
                validate_outputs(loaded)


if __name__ == "__main__":
    unittest.main()
