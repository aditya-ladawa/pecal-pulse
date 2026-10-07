import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import TypeAdapter, ValidationError

from backend.app.capabilities.sales import service
from backend.app.capabilities.sales.models import (
    ChartArtifact,
    FollowupCreate,
    UiCommand,
)


class SalesContractTests(unittest.TestCase):
    def test_commands_reject_executable_payloads(self):
        with self.assertRaises(ValidationError):
            TypeAdapter(UiCommand).validate_python(
                {"type": "ui.execute_javascript", "payload": {"code": "alert(1)"}}
            )

    def test_chart_rejects_misaligned_series(self):
        artifact = service.industry_chart().model_dump()
        artifact["datasets"][0]["values"] = [1]
        with self.assertRaises(ValidationError):
            ChartArtifact.model_validate(artifact)

    def test_followup_survives_connection_and_status_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ, {"PECAL_DEMO_DB": str(Path(directory) / "test.sqlite3")}
            ):
                request = FollowupCreate(
                    customer_id="DEMO-1001",
                    owner="Alex Meyer",
                    due_date="2026-11-01",
                    note="Confirm the batch timing.",
                    outcome="Timing changed",
                )
                created = service.create_followup(request)["payload"]
                self.assertIn(created, service.bootstrap()["followups"])
                service.update_followup(created["id"], "done")
                reloaded = next(
                    f
                    for f in service.bootstrap()["followups"]
                    if f["id"] == created["id"]
                )
                self.assertEqual(reloaded["status"], "done")
                self.assertEqual(reloaded["customer_id"], request.customer_id)

    def test_missing_customer_does_not_create_a_task(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ, {"PECAL_DEMO_DB": str(Path(directory) / "test.sqlite3")}
            ):
                before = service.list_followups()
                request = FollowupCreate(
                    customer_id="unknown",
                    owner="Alex Meyer",
                    due_date="2026-11-01",
                    note="Should be rejected.",
                    outcome="Timing to confirm",
                )
                with self.assertRaises(ValueError):
                    service.create_followup(request)
                self.assertEqual(service.list_followups(), before)


if __name__ == "__main__":
    unittest.main()
