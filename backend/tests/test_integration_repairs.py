import unittest
from datetime import date
from backend.app.capabilities.data.requirements import _add_months, infer_requirements
from backend.app.capabilities.data.build_snapshot import build_snapshot
from backend.app.contracts.sales_v2 import InstrumentRecord
from backend.app.capabilities.insights.peers import normalize_industry

class IntegrationRepairTests(unittest.TestCase):
    def test_month_end_and_leap_year_are_preserved(self):
        self.assertEqual(_add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(_add_months(date(2025, 1, 31), 1), date(2025, 2, 28))

    def test_missing_due_evidence_never_confirms_eligibility(self):
        row = InstrumentRecord(instrument_id="i", current_customer_id="c", stopped=False)
        requirement = infer_requirements([row], [], "2026-08-31")[0]
        self.assertEqual(requirement.kind, "unknown")
        self.assertEqual(requirement.eligibility, "review_required")

    def test_portfolio_counts_have_trailing_year_window(self):
        result = build_snapshot([], [{"customer":"c", "industry":"Manufacturing"}],
            [{"customer":"c", "equipment_group":"Length", "calibrations":3}],
            snapshot_id="test-window", extracted_at="2026-10-07T00:00:00Z",
            reference_date="2026-08-31", complete_through_month="2026-08", history_start="2024-01")
        self.assertEqual(result["portfolio"][0]["window_start"], "2025-09-01")
        self.assertEqual(result["portfolio"][0]["window_end"], "2026-08-31")

    def test_canonical_miscellaneous_industry_is_excluded(self):
        self.assertEqual(normalize_industry("IND-SONSTIGES"), "sonstiges")
