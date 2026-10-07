"""Published analytics -> shared API -> ranking/preparation/correction."""

import json
import os
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from analysis.challenge2_ml.synthetic_fixture import make_demo_fixture, make_fixture
from backend.app.capabilities.analytics.context import for_snapshot
from backend.app.capabilities.analytics.pipeline import build_outputs
from backend.app.capabilities.analytics.service import publish_outputs
from backend.app.capabilities.data import service as data_service
from backend.app.main import app


class AnalyticsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = make_fixture()
        cls.customer = "synthetic-customer-00"
        # Give a previously recurring customer an observable inactivity signal.
        for row in cls.source["history"]:
            if row["customer_id"] == cls.customer and row["month"] >= "2026-07":
                for name in ("calibration_events", "distinct_instruments", "equipment_group_count", "lab_count"):
                    row[name] = 0
        cls.source["requirements"] = [{
            "id": "synthetic-req", "customer_id": cls.customer, "instrument_id": "synthetic-inst",
            "group_id": "synthetic-group", "kind": "recorded", "window_start": "2027-01-15",
            "window_end": "2027-01-15", "method": "recorded_due_date",
            "evidence_dates": ["2027-01-15"], "stopped": False, "eligibility": "eligible",
        }]
        cls.outputs = build_outputs(cls.source)
        cls.snapshot_id = cls.source["manifest"]["snapshot_id"]

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.snapshots = folder / "snapshots"
        self.snapshots.mkdir()
        (self.snapshots / f"{self.snapshot_id}.json").write_text(json.dumps(self.source), encoding="utf-8")
        self.analytics = folder / "analytics"
        for context in (
            patch.object(data_service, "RUNTIME_SNAPSHOT_DIR", self.snapshots),
            patch.dict(os.environ, {"PECAL_ANALYTICS_ROOT": str(self.analytics),
                                    "PECAL_DEMO_DB": str(folder / "workflow.sqlite3")}),
        ):
            context.start()
            self.addCleanup(context.stop)
        data_service.load_snapshot.cache_clear()
        self.addCleanup(data_service.load_snapshot.cache_clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def get(self, path, **params):
        return self.client.get(f"/api/v2/{path}", params={"snapshot_id": self.snapshot_id, **params})

    def test_missing_artifacts_recover_when_published(self):
        before = self.get("bootstrap").json()
        self.assertEqual(before["metadata"]["modules"]["predictions"]["status"], "unavailable")
        self.assertEqual(self.get("sectors").status_code, 503)
        publish_outputs(self.outputs, self.analytics)
        after = self.get("bootstrap").json()
        self.assertEqual(after["metadata"]["modules"]["predictions"]["status"], "ready")
        self.assertTrue(after["filter_options"]["segments"])
        self.assertTrue(after["sectors"]["history"])

    def test_detail_ranking_preparation_and_refresh_keep_prediction(self):
        publish_outputs(self.outputs, self.analytics)
        before = self.get(f"customers/{self.customer}").json()
        self.assertTrue(before["prediction"]["inactivity"]["flagged"])
        self.assertIsNone(before["prediction"]["calibration_volume"]["monthly"])
        self.assertEqual({r["type"] for r in before["action"]["reasons"]}, {"upcoming", "inactivity"})
        self.assertTrue(any(f"prediction:{self.customer}:{self.snapshot_id}" in f["evidence_refs"]
                            for f in before["preparation"]["facts"]))
        response = self.client.patch(
            f"/api/v2/customers/{self.customer}/workflow", params={"snapshot_id": self.snapshot_id},
            json={"suppression": {"reason_id": "synthetic-req", "status": "resolved",
                                  "note": "Timing changed", "updated_at": "2026-12-31T12:00:00Z"}},
        )
        self.assertEqual(response.status_code, 200)
        refreshed = response.json()["payload"]["action"]
        self.assertEqual([r["type"] for r in refreshed["reasons"]], ["inactivity"])
        after = self.get(f"customers/{self.customer}").json()
        self.assertEqual(after["action"], refreshed)
        self.assertEqual(after["prediction"], before["prediction"])

    def test_segments_filter_full_population_and_list_probability(self):
        publish_outputs(self.outputs, self.analytics)
        counts = Counter(p["segment_id"] for p in self.outputs["predictions"] if p["segment_id"] is not None)
        segment = counts.most_common(1)[0][0]
        expected = [p for p in self.outputs["predictions"] if p["segment_id"] == segment]
        result = self.get("customers", segment_id=segment, limit=1, offset=1).json()
        self.assertEqual(result["total"], len(expected))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["segment_id"], segment)
        self.assertIsNotNone(result["items"][0]["activity_probability"])

    def test_sector_and_report_preserve_snapshot_and_units(self):
        publish_outputs(self.outputs, self.analytics)
        for path in ("sectors", "model-report"):
            result = self.get(path)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["metadata"]["snapshot_id"], self.snapshot_id)
        report = self.get("model-report").json()["model_report"]
        self.assertEqual(report["volume_unit"], "calibration_events")
        self.assertEqual(report["label_window"], {"start": "2027-01", "end": "2027-03"})

    def test_unsupported_customer_stays_null(self):
        publish_outputs(self.outputs, self.analytics)
        detail = self.get("customers/synthetic-customer-29").json()
        self.assertIsNone(detail["prediction"]["activity"]["probability"])
        self.assertIsNone(detail["prediction"]["calibration_volume"]["expected_total"])
        self.assertIsNone(detail["action"])

    def test_same_id_with_wrong_source_dates_is_unavailable(self):
        outputs = deepcopy(self.outputs)
        outputs["manifest"]["source_complete_through_month"] = "2026-11"
        publish_outputs(outputs, self.analytics)
        self.assertEqual(self.get("sectors").status_code, 503)
        self.assertIsNone(self.get(f"customers/{self.customer}").json()["prediction"])

    def test_same_id_with_wrong_customers_is_unavailable(self):
        outputs = deepcopy(self.outputs)
        outputs["predictions"][0]["customer_id"] = "foreign-customer"
        publish_outputs(outputs, self.analytics)
        self.assertEqual(self.get("model-report").status_code, 503)

    def test_context_returns_independent_values(self):
        publish_outputs(self.outputs, self.analytics)
        context = for_snapshot(data_service.load_snapshot(self.snapshot_id))
        context.prediction(self.customer).activity.probability = None
        context.payload("sectors")["history"].clear()
        self.assertIsNotNone(context.prediction(self.customer).activity.probability)
        self.assertTrue(context.payload("sectors")["history"])

    def test_demo_fixture_is_shared_and_has_all_three_reason_types(self):
        source = make_demo_fixture()
        snapshot_id = source["manifest"]["snapshot_id"]
        (self.snapshots / f"{snapshot_id}.json").write_text(json.dumps(source), encoding="utf-8")
        publish_outputs(build_outputs(source), self.analytics)
        response = self.client.get(f"/api/v2/customers/{self.customer}", params={"snapshot_id": snapshot_id})
        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["metadata"]["mode"], "mock")
        self.assertEqual(detail["prediction"]["reference_date"], "2026-08-31")
        self.assertEqual({r["type"] for r in detail["action"]["reasons"]},
                         {"upcoming", "inactivity", "discovery"})
        self.assertTrue(all(p["peer_count"] >= 20 for p in detail["peer_opportunities"]))


if __name__ == "__main__":
    unittest.main()
