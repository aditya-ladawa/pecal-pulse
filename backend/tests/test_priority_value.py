"""Unit tests for the expected-value ranking component (synthetic only)."""

import unittest

from backend.app.capabilities.insights.actions import (
    DEFAULT_WEIGHTS,
    RANKING_VERSION,
    account_unit_value,
    expected_value_component,
)
from backend.app.capabilities.insights.models import Requirement
from backend.app.capabilities.insights.value_weights import load_weights, unit_value


def _requirement(group_id="g1", kind="recorded"):
    return Requirement(
        id=f"r-{group_id}-{kind}",
        customer_id="c1",
        instrument_id="i1",
        group_id=group_id,
        kind=kind,
        eligibility="eligible",
        stopped=False,
        window_start="2026-09-01",
        window_end="2026-09-30",
        method="test",
        unknowns=[],
    )


class _Reason:
    def __init__(self, type):
        self.type = type


class _Prediction:
    def __init__(self, prob, expected):
        self.activity_probability = prob
        self.expected_volume_3m = expected


class TestValueWeights(unittest.TestCase):
    def test_default_is_one(self):
        load_weights.cache_clear()
        self.assertEqual(unit_value("anything"), 1.0)
        self.assertEqual(unit_value(None), 1.0)

    def test_rejects_non_positive_file(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"g1": 0.0}, handle)
            path = handle.name
        load_weights.cache_clear()
        try:
            with self.assertRaises(ValueError):
                load_weights(path)
        finally:
            load_weights.cache_clear()


class TestExpectedValue(unittest.TestCase):
    def test_upcoming_normalized(self):
        reason = _Reason("upcoming")
        prediction = _Prediction(0.8, 100.0)
        self.assertAlmostEqual(
            expected_value_component(reason, prediction, 1.0, 200.0), 0.4
        )

    def test_capped_at_one(self):
        reason = _Reason("upcoming")
        prediction = _Prediction(1.0, 500.0)
        self.assertEqual(
            expected_value_component(reason, prediction, 2.0, 100.0), 1.0
        )

    def test_non_upcoming_is_null_not_zero(self):
        prediction = _Prediction(0.9, 300.0)
        self.assertIsNone(
            expected_value_component(_Reason("inactivity"), prediction, 1.0, 100.0)
        )
        self.assertIsNone(
            expected_value_component(_Reason("discovery"), prediction, 1.0, 100.0)
        )

    def test_missing_inputs_are_null(self):
        reason = _Reason("upcoming")
        self.assertIsNone(
            expected_value_component(reason, _Prediction(None, 50.0), 1.0, 100.0)
        )
        self.assertIsNone(
            expected_value_component(reason, _Prediction(0.5, None), 1.0, 100.0)
        )
        self.assertIsNone(
            expected_value_component(reason, _Prediction(0.5, 50.0), 1.0, None)
        )

    def test_account_unit_value_blends_groups(self):
        reqs = [_requirement("g1"), _requirement("g2")]
        self.assertAlmostEqual(
            account_unit_value(reqs, {"g1": 2.0, "g2": 4.0}), 3.0
        )

    def test_account_unit_value_defaults(self):
        self.assertEqual(account_unit_value([]), 1.0)
        self.assertEqual(
            account_unit_value([_requirement("unknown-group")]), 1.0
        )

    def test_weights_cover_five_components(self):
        self.assertEqual(
            sorted(DEFAULT_WEIGHTS),
            ["activity_deviation", "evidence", "expected_value", "quantity", "timing"],
        )
        self.assertAlmostEqual(sum(DEFAULT_WEIGHTS.values()), 1.0)
        self.assertEqual(RANKING_VERSION, "rank-v2")


if __name__ == "__main__":
    unittest.main()
