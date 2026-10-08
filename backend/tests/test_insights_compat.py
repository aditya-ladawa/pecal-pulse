"""Member 3 — shared-contract compatibility tests.

Vectors mirror the frozen shapes on Member 1/2 branches (shared §4A/4B/4C)
as plain dicts: nested Member 2 predictions, full-field Member 1
workflows, row-count portfolios with ``distinct_instruments=None``, and
shared-style stopped+excluded requirements. No imports from Member 1/2
modules — only the shapes they publish.
"""

import unittest

from backend.app.capabilities.insights import (
    SnapshotStats,
    action_to_shared_payload,
    build_peer_index,
    category_prevalence_by_industry,
    get_peer_opportunities,
    owns_category,
    prediction_from_shared,
    ranking_fn_for_composition,
    workflow_from_shared,
)

STATS = SnapshotStats(
    snapshot_id="synthetic-v1",
    reference_date="2026-08-31",
    max_instruments_per_account=10,
    max_calibration_events_3m=12.0,
    p90_instruments_per_account=8.0,
)

# Requirement rows exactly as Member 1's synthetic-v1 snapshot publishes.
SHARED_REQUIREMENTS = [
    {"customer_id": "SYN-001", "eligibility": "eligible",
     "evidence_dates": ["2026-07-02", "2026-09-15"], "group_id": "GRP-CALIPER",
     "id": "REQ-001", "instrument_id": "INST-001", "kind": "recorded",
     "method": "recorded_due_date", "positive_gap_count": 0, "stopped": False,
     "unknowns": [], "window_end": "2026-09-15", "window_start": "2026-09-15"},
    {"customer_id": "SYN-001", "eligibility": "eligible",
     "evidence_dates": ["2025-10-10"], "group_id": "GRP-GAUGE",
     "id": "REQ-002", "instrument_id": "INST-002", "kind": "nominal_interval",
     "method": "nominal_interval_12m_from_last_calibration",
     "positive_gap_count": 0, "stopped": False, "unknowns": [],
     "window_end": "2026-11-10", "window_start": "2026-09-10"},
    {"customer_id": "SYN-001", "eligibility": "excluded",
     "evidence_dates": ["2025-05-01"], "group_id": "GRP-GAUGE",
     "id": "REQ-005", "instrument_id": "INST-005", "kind": "recorded",
     "method": "recorded_but_stopped", "positive_gap_count": 0,
     "stopped": True, "unknowns": [],
     "window_end": "2025-05-01", "window_start": "2025-05-01"},
]

SHARED_PROFILE = {
    "customer_id": "SYN-001", "display_name": "Werkstatt Beispiel GmbH",
    "industry_id": "IND-AUTOMOTIVE", "industry_label": "Automotive",
    "name_source": "verified",
}

# Nested Member 2 prediction shape (cf. challenge2_ml/example_prediction.json).
SHARED_PREDICTION = {
    "snapshot_id": "synthetic-v1", "customer_id": "SYN-001",
    "reference_date": "2026-08-31", "segment_id": "segment-4",
    "activity": {
        "target": "any_calibration_next_3_months", "probability": 0.8,
        "window_start": "2026-09", "window_end": "2026-11",
        "model_version": "analytics-v2",
        "support": {"status": "supported", "reason": None,
                     "history_months": 24, "active_months": 18},
    },
    "calibration_volume": {
        "metric": "calibration_events", "horizon_months": 3,
        "window_start": "2026-09", "window_end": "2026-11",
        "expected_total": 9.0, "lower": None, "upper": None,
        "interval_level": None, "monthly": None,
        "method": "same_3_months_last_year", "model_version": "analytics-v2",
        "support": {"status": "supported", "reason": None,
                     "history_months": 24, "active_months": 18},
    },
    "recency_months": 0, "cadence_months": 1.0,
    "inactivity": {
        "flagged": False, "recency_to_cadence": 0.5, "recent_volume": 9,
        "baseline_volume": 8.0, "deficit_fraction": 0.0,
        "rule_version": "inactivity-v1", "reasons": [],
        "support": {"status": "supported", "reason": None,
                     "history_months": 24, "active_months": 18},
    },
    "explanation": [],
}

SHARED_WORKFLOW = {
    "account_owner": None,
    "checks": {"quotation_order": "unknown", "recent_contact": "unknown",
               "contact_details": "unknown", "checked_at": None,
               "checked_by": None},
    "suppressions": [], "followups": [],
}


class SharedShapeTests(unittest.TestCase):
    def test_ranking_fn_matches_composition_call_shape(self):
        """Same positional call Member 1's refresh_after_correction makes."""
        rank = ranking_fn_for_composition(STATS)
        action = rank(SHARED_PROFILE, SHARED_REQUIREMENTS, None, [], SHARED_WORKFLOW)
        assert action is not None
        types = sorted({r.type for r in action.reasons})
        self.assertEqual(types, ["upcoming"])
        # REQ-005 (stopped+excluded) contributes no instrument.
        instruments = [i for r in action.reasons for i in r.instrument_ids]
        self.assertNotIn("INST-005", instruments)
        self.assertIn("INST-001", instruments)
        self.assertIn("INST-002", instruments)

    def test_nested_prediction_flattens_into_ranking(self):
        pred = prediction_from_shared(SHARED_PREDICTION)
        self.assertAlmostEqual(pred.activity_probability, 0.8)
        self.assertEqual(pred.activity_window_start, "2026-09")
        self.assertAlmostEqual(pred.expected_volume_3m, 9.0)
        rank = ranking_fn_for_composition(STATS)
        action = rank(
            SHARED_PROFILE, SHARED_REQUIREMENTS[:1], SHARED_PREDICTION, [],
            SHARED_WORKFLOW)
        assert action is not None
        self.assertIsNotNone(action.components["activity_deviation"])

    def test_output_payload_is_shared_section_4c_shaped(self):
        rank = ranking_fn_for_composition(STATS)
        action = rank(SHARED_PROFILE, SHARED_REQUIREMENTS, None, [], SHARED_WORKFLOW)
        assert action is not None
        payload = action_to_shared_payload(action)
        self.assertEqual(
            sorted(payload.keys()),
            ["components", "customer_id", "primary_type", "priority_score",
             "ranking_version", "readiness", "reasons", "snapshot_id",
             "suggested_next_step", "weights"],
        )
        self.assertEqual(
            sorted(payload["components"].keys()),
            ["activity_deviation", "evidence", "expected_value", "quantity", "timing"],
        )
        self.assertTrue(0 <= payload["priority_score"] <= 100)

    def test_shared_workflow_resolution_suppresses(self):
        from backend.app.capabilities.insights.actions import reason_id_for

        rid = reason_id_for("SYN-001", "upcoming", "GRP-CALIPER:2026-09-15:2026-09-15")
        workflow = {
            **SHARED_WORKFLOW,
            "suppressions": [{
                "reason_id": rid, "status": "resolved",
                "until": None, "note": "batch received",
                "updated_at": "2026-08-20",
            }],
        }
        wf = workflow_from_shared(workflow)
        rank = ranking_fn_for_composition(STATS)
        action = rank(SHARED_PROFILE, SHARED_REQUIREMENTS, None, [], wf)
        assert action is not None
        self.assertNotIn(rid, [r.id for r in action.reasons])
        # The unrelated GAUGE reason remains.
        self.assertTrue(any("GRP-GAUGE" in r.id for r in action.reasons))

    def test_null_windows_and_group_sort_without_crashing(self):
        """Shared unknown requirements carry null group/windows (cf. REQ-004)."""
        reqs = [
            {"customer_id": "SYN-002", "eligibility": "review_required",
             "evidence_dates": [], "group_id": None,
             "id": "REQ-006", "instrument_id": "INST-006", "kind": "unknown",
             "method": "no_usable_date_evidence", "positive_gap_count": 0,
             "stopped": None,
             "unknowns": ["no recorded due date"],
             "window_end": None, "window_start": None},
            {**SHARED_REQUIREMENTS[0], "customer_id": "SYN-002"},
        ]
        rank = ranking_fn_for_composition(STATS)
        action = rank(
            {**SHARED_PROFILE, "customer_id": "SYN-002"}, reqs, None, [],
            SHARED_WORKFLOW)
        assert action is not None
        self.assertEqual(len(action.reasons), 1)
        self.assertTrue(all(r.unknowns for r in action.reasons))

    def test_null_distinct_falls_back_to_row_presence(self):
        from backend.app.capabilities.insights import portfolio_from_shared

        present = portfolio_from_shared({
            "customer_id": "A", "group_id": "G", "group_label": "G",
            "distinct_instruments": None, "calibration_events": 4,
            "window_start": "2025-09-01", "window_end": "2026-08-31"})
        absent_zero = portfolio_from_shared({
            "customer_id": "B", "group_id": "G", "group_label": "G",
            "distinct_instruments": 0, "calibration_events": 4,
            "window_start": "2025-09-01", "window_end": "2026-08-31"})
        self.assertTrue(owns_category(present))
        self.assertFalse(owns_category(absent_zero))
        index = build_peer_index(
            [present, absent_zero], {"A": "IND", "B": "IND"})
        self.assertEqual(index["IND"]["G"], {"A"})
        opps = get_peer_opportunities(
            target_customer_id="T", target_industry_id="IND",
            owned_group_ids=set(), peer_index=index,
            group_labels={"G": "G"},
            window_start="2025-09-01", window_end="2026-08-31",
            min_peer_accounts=1, min_prevalence=0.25)
        self.assertEqual(opps[0].peer_count, 1)
        self.assertEqual(opps[0].peers_with_group, 1)
        rows = category_prevalence_by_industry(
            portfolios=[present, absent_zero],
            industry_by_customer={"A": "IND", "B": "IND"},
            window_start="2025-09-01", window_end="2026-08-31")
        self.assertEqual(rows[0]["eligible_accounts"], 1)
        self.assertEqual(rows[0]["accounts_with_group"], 1)


if __name__ == "__main__":
    unittest.main()
