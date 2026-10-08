"""Member 1: v2 HTTP composition tests (isolated temp SQLite)."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app

SNAPSHOT = "synthetic-v1"


class V2ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.env = patch.dict(
            os.environ, {"PECAL_DEMO_DB": str(Path(cls.tmp.name) / "api.sqlite3"),
                         "PECAL_ANALYTICS_ROOT": str(Path(cls.tmp.name) / "analytics")}
        )
        cls.env.start()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.tmp.cleanup()

    def test_bootstrap_shape_and_readiness(self):
        res = self.client.get("/api/v2/bootstrap", params={"snapshot_id": SNAPSHOT})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["metadata"]["contract_version"], "2")
        self.assertEqual(body["metadata"]["snapshot_id"], SNAPSHOT)
        self.assertEqual(body["metadata"]["mode"], "mock")
        modules = body["metadata"]["modules"]
        self.assertEqual(modules["data"]["status"], "ready")
        self.assertEqual(modules["predictions"]["status"], "unavailable")
        self.assertEqual(modules["insights"]["status"], "ready")
        self.assertEqual(body["kpis"]["customers"]["value"], 3)
        self.assertEqual(len(body["actions"]), 1)
        self.assertEqual(body["actions"][0]["customer_id"], "SYN-001")

    def test_unknown_snapshot_is_404(self):
        res = self.client.get("/api/v2/bootstrap", params={"snapshot_id": "nope"})
        self.assertEqual(res.status_code, 404)

    def test_customers_list_filters_and_pagination(self):
        res = self.client.get("/api/v2/customers", params={"snapshot_id": SNAPSHOT})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 3)
        res = self.client.get(
            "/api/v2/customers",
            params={"snapshot_id": SNAPSHOT, "industry_id": "IND-AUTOMOTIVE"},
        )
        self.assertEqual(res.json()["total"], 1)
        res = self.client.get(
            "/api/v2/customers", params={"snapshot_id": SNAPSHOT, "query": "syn-002"}
        )
        self.assertEqual(res.json()["total"], 1)
        res = self.client.get(
            "/api/v2/customers",
            params={"snapshot_id": SNAPSHOT, "limit": 1, "offset": 2},
        )
        body = res.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(len(body["items"]), 1)

    def test_customers_unknown_ids_and_empty_matches(self):
        res = self.client.get("/api/v2/customers/SYN-999", params={"snapshot_id": SNAPSHOT})
        self.assertEqual(res.status_code, 404)
        res = self.client.get(
            "/api/v2/customers",
            params={"snapshot_id": SNAPSHOT, "industry_id": "IND-NOBODY"},
        )
        self.assertEqual((res.status_code, res.json()["items"]), (200, []))

    def test_action_filter_matches_reason_types(self):
        res = self.client.get(
            "/api/v2/customers", params={"snapshot_id": SNAPSHOT, "action": "upcoming"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 1)
        res = self.client.get(
            "/api/v2/customers", params={"snapshot_id": SNAPSHOT, "action": "discovery"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 0)

    def test_customer_detail_sections(self):
        res = self.client.get("/api/v2/customers/SYN-001", params={"snapshot_id": SNAPSHOT})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["requirements"]), 5)
        self.assertEqual(len(body["history"]), 3)
        self.assertEqual(len(body["portfolio"]), 2)
        self.assertIsNone(body["prediction"])
        action = body["action"]
        self.assertIsNotNone(action)
        self.assertEqual(action["customer_id"], "SYN-001")
        self.assertTrue(action["reasons"])
        self.assertEqual(body["peer_opportunities"], [])
        self.assertTrue(body["preparation"]["facts"])
        self.assertTrue(body["preparation"]["suggested_next_step"])
        self.assertIn("workflow", body)

    def test_sectors_and_model_report_unavailable(self):
        self.assertEqual(
            self.client.get("/api/v2/sectors", params={"snapshot_id": SNAPSHOT}).status_code,
            503,
        )
        self.assertEqual(
            self.client.get("/api/v2/model-report", params={"snapshot_id": SNAPSHOT}).status_code,
            503,
        )

    def test_contracts_endpoint(self):
        res = self.client.get("/api/v2/contracts")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["version"], "2")

    def test_followup_lifecycle(self):
        created = self.client.post(
            "/api/v2/followups",
            params={"snapshot_id": SNAPSHOT},
            json={
                "customer_id": "SYN-001",
                "owner": "Alex Meyer",
                "due_date": "2026-09-20",
                "note": "Timing changed on the call.",
                "outcome": "Timing changed",
                "reason_ids": ["REQ-001"],
            },
        )
        self.assertEqual(created.status_code, 201)
        envelope = created.json()
        self.assertEqual(envelope["type"], "followup.created")
        task_id = envelope["payload"]["id"]
        updated = self.client.patch(f"/api/v2/followups/{task_id}", json={"status": "done"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["type"], "followup.updated")
        missing = self.client.patch("/api/v2/followups/task-missing", json={"status": "done"})
        self.assertEqual(missing.status_code, 404)

    def test_followup_rejects_unknown_customer_and_reason(self):
        bad_customer = self.client.post(
            "/api/v2/followups",
            params={"snapshot_id": SNAPSHOT},
            json={
                "customer_id": "SYN-999",
                "owner": "Alex Meyer",
                "due_date": "2026-09-20",
                "note": "x",
                "outcome": "Timing to confirm",
            },
        )
        self.assertEqual(bad_customer.status_code, 404)
        bad_reason = self.client.post(
            "/api/v2/followups",
            params={"snapshot_id": SNAPSHOT},
            json={
                "customer_id": "SYN-001",
                "owner": "Alex Meyer",
                "due_date": "2026-09-20",
                "note": "x",
                "outcome": "Timing to confirm",
                "reason_ids": ["REQ-999"],
            },
        )
        self.assertEqual(bad_reason.status_code, 404)

    def test_workflow_patch_roundtrip(self):
        res = self.client.patch(
            "/api/v2/customers/SYN-002/workflow",
            params={"snapshot_id": SNAPSHOT},
            json={
                "checks": {"quotation_order": "in_progress", "checked_by": "HW"},
                "suppression": {
                    "reason_id": "REQ-006",
                    "status": "snoozed",
                    "until": "2026-10-15",
                    "note": "Waiting for shutdown window.",
                    "updated_at": "2026-09-01T08:00:00Z",
                },
            },
        )
        self.assertEqual(res.status_code, 200)
        envelope = res.json()
        self.assertEqual(envelope["type"], "customer.workflow.updated")
        workflow = envelope["payload"]["workflow"]
        self.assertEqual(workflow["checks"]["quotation_order"], "in_progress")
        self.assertEqual(len(workflow["suppressions"]), 1)
        self.assertEqual(envelope["payload"]["suppressed_requirement_ids"], ["REQ-006"])
        bad_reason = self.client.patch(
            "/api/v2/customers/SYN-002/workflow",
            params={"snapshot_id": SNAPSHOT},
            json={
                "suppression": {
                    "reason_id": "REQ-999",
                    "status": "resolved",
                    "note": "x",
                    "updated_at": "2026-09-01T08:00:00Z",
                }
            },
        )
        self.assertEqual(bad_reason.status_code, 404)

    def test_v1_routes_still_serve(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/bootstrap").status_code, 200)

    def test_insights_evidence_falls_back_without_sidecars(self):
        res = self.client.get(
            "/api/v2/insights-evidence", params={"snapshot_id": SNAPSHOT}
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["retention"])
        self.assertIsNone(body["volume"])
        self.assertIsNone(body["summary"])

    def test_retention_filter_without_sidecar_matches_nothing(self):
        res = self.client.get(
            "/api/v2/customers",
            params={"snapshot_id": SNAPSHOT, "retention": "higher"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
