"""Workflow tools use temporary local stores; no provider calls or outreach."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from langchain_core.messages import AIMessage
from backend.app.agents.contracts import AgentChatRequest, TurnContext, WorkspaceContext
from backend.app.agents.react_agent import agent_lifespan
from backend.app.agents.settings import Settings
from backend.app.capabilities import data
from backend.app.capabilities.workspace import tools, workflow_tools as actions
from backend.app.contracts import sales_v2 as v2
from backend.tests.test_chat_agent import call, model


class SalesActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ,{"PECAL_DEMO_DB":str(Path(self.temp.name)/"workflow.sqlite3")})
        env.start()
        self.addCleanup(env.stop)
        self.runtime = SimpleNamespace(context=TurnContext(WorkspaceContext(snapshot_id="synthetic-v1",page="customers",current_date="2026-10-08")))

    def test_assignment_batch_validates_all_accounts_before_writing(self):
        with self.assertRaises(ValueError):
            actions.assign_accounts.func(["SYN-001","not-an-account"],"Team A",self.runtime)
        self.assertIsNone(data.get_workflow("SYN-001").account_owner)
        self.assertEqual(self.runtime.context.events,[])
        result = actions.assign_accounts.func(["SYN-001","SYN-002","SYN-001"],"Team A",self.runtime)
        self.assertEqual(result["assigned_count"],2)
        for cid in result["customer_ids"]:
            self.assertEqual(data.get_workflow(cid).account_owner,"Team A")
        self.assertEqual(self.runtime.context.events[-1]["type"],"accounts.assigned")

    def test_individual_drafts_persist_and_repeat_does_not_duplicate(self):
        actions.assign_accounts.func(["SYN-001","SYN-002"],"Team B",self.runtime)
        first = actions.draft_followup_emails.func(["SYN-001"],self.runtime,language="en")
        repeat = actions.draft_followup_emails.func(["SYN-001"],self.runtime,language="en")
        self.assertFalse(first["sent"])
        self.assertEqual(first["count"],1)
        self.assertEqual([f["id"] for f in first["followups"]],[f["id"] for f in repeat["followups"]])
        self.assertEqual(len(data.list_followups_v2()),1)
        for task in first["followups"]:
            self.assertEqual(task["owner"],"Team B")
            self.assertEqual(task["due_date"],"2026-10-08")
            self.assertEqual(task["email_draft"]["status"],"draft")
            self.assertNotIn("probability",task["email_draft"]["body"])
            self.assertTrue(task["email_draft"]["review_notes"])

    def test_unsupported_account_in_draft_batch_does_not_save_partial_tasks(self):
        with self.assertRaises(ValueError):
            actions.draft_followup_emails.func(["SYN-001","SYN-002"],self.runtime)
        self.assertEqual(data.list_followups_v2(),[])

    def test_bad_draft_batch_and_bad_dates_leave_no_tasks(self):
        with self.assertRaises(ValueError):
            actions.draft_followup_emails.func(["SYN-001","missing"],self.runtime)
        with self.assertRaises(ValueError):
            actions.draft_followup_emails.func(["SYN-001"],self.runtime,due_date="2026-02-30")
        self.assertEqual(data.list_followups_v2(),[])

    def test_explicit_checks_update_only_supplied_fields(self):
        actions.update_customer_checks.func("SYN-001",self.runtime,quotation_order="in_progress")
        checks = data.get_workflow("SYN-001").checks
        self.assertEqual(checks.quotation_order,"in_progress")
        self.assertEqual(checks.contact_details,"unknown")
        self.assertEqual(self.runtime.context.events[-1]["type"],"customer.workflow.updated")

    def test_preview_preserves_filters_and_invalid_account_emits_nothing(self):
        tools.set_opportunity_filters.func(self.runtime,industry="IND-AUTOMOTIVE")
        before = self.runtime.context.workspace.opportunity_filters.model_dump()
        tools.open_customer_preview.func("SYN-001",self.runtime)
        self.assertEqual(self.runtime.context.workspace.opportunity_filters.model_dump(),before)
        self.assertEqual(self.runtime.context.workspace.opportunity_drawer_id,"SYN-001")
        count = len(self.runtime.context.events)
        with self.assertRaises(ValueError):
            tools.open_customer_preview.func("missing",self.runtime)
        self.assertEqual(len(self.runtime.context.events),count)

    def test_followups_view_exposes_saved_tasks_even_on_customers_route(self):
        actions.record_followup.func("SYN-001","Team A","2026-10-10","Confirm timing",self.runtime)
        tools.set_workspace_view.func(self.runtime,customer_view="follow-ups")
        context = tools.get_workspace_context.func(self.runtime)
        self.assertEqual(context["page"],"customers")
        self.assertEqual(context["followups"]["total"],1)
        self.assertEqual(context["followups"]["items"][0]["owner"],"Team A")


class SalesActionGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_assignment_draft_followup_path_and_restored_drafts(self):
        with TemporaryDirectory() as root, patch.dict(os.environ,{"PECAL_DEMO_DB":str(Path(root)/"tasks.sqlite3")}):
            settings = Settings(checkpoint_path=str(Path(root)/"chat.sqlite3"),openrouter_api_key="")
            fake = model(call("assign_accounts",{"customer_ids":["SYN-001"],"owner":"Team A"}),
                         call("draft_followup_emails",{"customer_ids":["SYN-001"],"language":"de"}),
                         call("set_workspace_view",{"customer_view":"follow-ups"}),AIMessage(content="Draft saved for review."))
            async with agent_lifespan(settings,fake) as agent:
                reply = await agent.reply(AgentChatRequest(message="Assign and draft",context=WorkspaceContext(snapshot_id="synthetic-v1",page="customers",current_date="2026-10-08")))
                kinds = [e["type"] for e in reply["events"]]
                self.assertIn("accounts.assigned",kinds)
                self.assertIn("followup.created",kinds)
                self.assertIn("ui.control.set",kinds)
                task = data.list_followups_v2()[0]
                self.assertEqual(task.email_draft.language,"de")
                history = await agent.history(reply["thread_id"])
                self.assertIn("followup.created",history["items"][-1]["actions"])
