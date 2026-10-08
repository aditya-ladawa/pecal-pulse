"""Unit tests for intermittent-demand volume challengers (synthetic only)."""

import unittest

from backend.app.capabilities.analytics.volume_methods import (
    croston_3m,
    industry_12m_means,
    pooled_12m,
    tsb_3m,
)


def series(events: dict[int, int]) -> dict[int, int]:
    return dict(events)


class TestCroston(unittest.TestCase):
    def test_empty_history_is_zero(self):
        self.assertEqual(croston_3m({}, 10), 0.0)

    def test_regular_monthly_demand(self):
        # 10 units every month: ~10 per month -> ~30 per quarter.
        history = series({t: 10 for t in range(0, 24)})
        self.assertAlmostEqual(croston_3m(history, 23), 30.0, delta=1.0)

    def test_sparse_demand_scales_with_interval(self):
        # 12 units every 4th month over a long burn-in: ~3 per month -> ~9/quarter.
        history = series({t: 12 if t % 4 == 0 else 0 for t in range(0, 120)})
        self.assertAlmostEqual(croston_3m(history, 119), 9.0, delta=2.0)

    def test_sparser_series_forecasts_less(self):
        dense = series({t: 12 if t % 2 == 0 else 0 for t in range(0, 120)})
        sparse = series({t: 12 if t % 8 == 0 else 0 for t in range(0, 120)})
        self.assertGreater(croston_3m(dense, 119), croston_3m(sparse, 119))

    def test_never_negative(self):
        self.assertGreaterEqual(croston_3m(series({0: 5}), 30), 0.0)


class TestTSB(unittest.TestCase):
    def test_empty_history_is_zero(self):
        self.assertEqual(tsb_3m({}, 10), 0.0)

    def test_regular_monthly_demand(self):
        history = series({t: 10 for t in range(0, 24)})
        self.assertAlmostEqual(tsb_3m(history, 23), 30.0, delta=1.0)

    def test_sparser_than_croston_for_intermittent(self):
        history = series({t: 12 if t % 6 == 0 else 0 for t in range(0, 24)})
        self.assertLessEqual(tsb_3m(history, 23), croston_3m(history, 23))


class TestPooled(unittest.TestCase):
    def test_long_history_keeps_mostly_own_average(self):
        # weight 24/(24+4): mostly own average with slight industry pull.
        self.assertAlmostEqual(pooled_12m(400.0, 40.0, 24), 87.1, delta=0.5)
        self.assertLess(
            pooled_12m(400.0, 40.0, 24), pooled_12m(400.0, 40.0, 240)
        )

    def test_thin_history_shrinks_to_industry(self):
        pooled = pooled_12m(400.0, 40.0, 1)
        self.assertLess(pooled, 100.0)
        self.assertGreater(pooled, 10.0)

    def test_missing_industry_falls_back_to_own(self):
        self.assertAlmostEqual(pooled_12m(120.0, None, 2), 30.0)


class TestIndustryMeans(unittest.TestCase):
    def test_mean_twelve_month_total(self):
        histories = {
            "a": {t: 10 for t in range(0, 12)},
            "b": {t: 20 for t in range(0, 12)},
            "c": {t: 5 for t in range(0, 12)},
        }
        industries = {"a": "x", "b": "x", "c": "y"}
        means = industry_12m_means(histories, industries, [11])
        self.assertAlmostEqual(means[("x", 11)], 180.0)
        self.assertAlmostEqual(means[("y", 11)], 60.0)

    def test_unknown_customer_skipped(self):
        means = industry_12m_means({}, {"ghost": "x"}, [11])
        self.assertIsNone(means[("x", 11)])


if __name__ == "__main__":
    unittest.main()
