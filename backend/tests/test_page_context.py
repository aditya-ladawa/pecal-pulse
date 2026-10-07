import unittest
from types import SimpleNamespace
from backend.app.agents.contracts import WorkspaceContext, TurnContext
from backend.app.capabilities.workspace.tools import get_workspace_context


class PageContextTests(unittest.TestCase):
    def context(self):
        return WorkspaceContext(page="dashboard", customer_id="DEMO-1001", page_snapshot={
            "page": "dashboard", "title": "Your next conversation", "metrics": [{
                "label": "Recorded upcoming needs", "value": 144, "unit": "instruments",
                "scope": "All workspace customers; next 30 days",
                "definition": "Recorded dates only, not inferred dates or orders.",
            }],
        })

    def test_displayed_dashboard_total_is_available_without_customer_substitution(self):
        runtime = SimpleNamespace(context=TurnContext(self.context()))
        result = get_workspace_context.func(runtime)
        metric = result["page_snapshot"]["metrics"][0]
        self.assertEqual(metric["label"], "Recorded upcoming needs")
        self.assertEqual(metric["value"], 144)
        self.assertEqual(metric["unit"], "instruments")
        self.assertIn("All workspace", metric["scope"])

    def test_navigation_does_not_relabel_old_dashboard_snapshot_as_customer_metrics(self):
        context = self.context()
        context.page = "customers"
        result = get_workspace_context.func(SimpleNamespace(context=TurnContext(context)))
        self.assertIsNone(result["page_snapshot"])

    def test_snapshot_tools_use_shared_customer_data(self):
        from backend.app.capabilities.workspace.tools import get_customer_evidence, set_customer_filters
        context = WorkspaceContext(page="customers", customer_id="SYN-001", snapshot_id="synthetic-v1")
        runtime = SimpleNamespace(context=TurnContext(context))
        detail = get_customer_evidence.func(runtime)
        self.assertEqual(detail["metadata"]["snapshot_id"], "synthetic-v1")
        self.assertEqual(detail["profile"]["customer_id"], "SYN-001")
        self.assertIn("requirement_count", detail)
        result = set_customer_filters.func(runtime, industry="IND-AUTOMOTIVE")
        self.assertEqual(result["event"]["payload"]["industry"], "IND-AUTOMOTIVE")
