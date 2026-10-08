"""Unit tests for the empirical retention curve (synthetic histories only)."""

import unittest

from backend.app.capabilities.analytics.retention import (
    FORWARD_WINDOW_MONTHS,
    HORIZON_MONTHS,
    forward_curve,
    is_regular,
    retention_for,
    return_curve,
    silence_episodes,
    tier_for,
)


def active(start: int, gaps: list[int]) -> list[int]:
    months = [start]
    for gap in gaps:
        months.append(months[-1] + gap)
    return months


class TestSilenceEpisodes(unittest.TestCase):
    def test_returned_episode_kept_with_silence(self):
        months = active(0, [1] * 20 + [3])
        episodes = silence_episodes(months, end=100)
        self.assertTrue(episodes)
        for episode in episodes:
            self.assertIn("silence_months", episode)
            self.assertIn(episode["returned"], (True, False))

    def test_censored_open_episode_dropped(self):
        # Last activity 2 months before end: outcome unknown, must be dropped.
        months = active(0, [1] * 20)
        end = months[-1] + 2
        episodes = silence_episodes(months, end=end)
        self.assertNotIn(months[-1], [e["last_active"] for e in episodes])

    def test_open_episode_beyond_horizon_counts_as_non_return(self):
        months = active(0, [1] * 20)
        end = months[-1] + HORIZON_MONTHS + 4
        episodes = silence_episodes(months, end=end)
        tails = [e for e in episodes if e["last_active"] == months[-1]]
        self.assertEqual(len(tails), 1)
        self.assertFalse(tails[0]["returned"])

    def test_insufficient_history_yields_no_episodes(self):
        self.assertEqual(silence_episodes([0, 5], end=50), [])


class TestReturnCurve(unittest.TestCase):
    def test_curve_monotonic_and_bounded(self):
        months = active(0, [1] * 30 + [4, 8, 2, 10, 3])
        episodes = silence_episodes(months, end=200)
        curve = return_curve(episodes)
        for stratum in ("regular", "irregular"):
            rates = [p["return_rate"] for p in curve[stratum]]
            self.assertEqual(len(rates), HORIZON_MONTHS)
            for rate in rates:
                if rate is not None:
                    self.assertGreaterEqual(rate, 0.0)
                    self.assertLessEqual(rate, 1.0)
            known = [r for r in rates if r is not None]
            self.assertEqual(known, sorted(known))

    def test_empty_stratum_gives_null_rates(self):
        curve = return_curve([])
        for stratum in ("regular", "irregular"):
            self.assertTrue(all(p["return_rate"] is None for p in curve[stratum]))


class TestForwardCurve(unittest.TestCase):
    def test_forward_rates_bounded(self):
        months = active(0, [1] * 30 + [4, 8, 2, 10, 3])
        episodes = silence_episodes(months, end=200)
        curve = forward_curve(episodes)
        for stratum in ("regular", "irregular"):
            self.assertEqual(len(curve[stratum]), HORIZON_MONTHS - FORWARD_WINDOW_MONTHS + 1)
            for point in curve[stratum]:
                rate = point["return_rate"]
                if rate is not None:
                    self.assertGreaterEqual(rate, 0.0)
                    self.assertLessEqual(rate, 1.0)

    def test_still_silent_episodes_stay_at_risk(self):
        # One long silence: at d=0 the episode is at risk and returns in window.
        episodes = [{"last_active": 0, "regular": True, "silence_months": 2, "returned": True}]
        curve = forward_curve(episodes, horizon=6, window=3)
        self.assertEqual(curve["regular"][0]["at_risk"], 1)
        self.assertEqual(curve["regular"][0]["returned"], 1)


class TestTiers(unittest.TestCase):
    def _curve(self):
        rates = [0.9, 0.7, 0.62, 0.55, 0.45, 0.38, 0.3, 0.25, 0.2, 0.15]
        return {
            "regular": [
                {"silent_months": d, "forward_window_months": 3, "at_risk": 100,
                 "returned": 0, "return_rate": r}
                for d, r in enumerate(rates)
            ],
            "irregular": [
                {"silent_months": d, "forward_window_months": 3, "at_risk": 10,
                 "returned": 0, "return_rate": 0.05}
                for d in range(10)
            ],
        }

    def test_tier_thresholds(self):
        curve = self._curve()
        self.assertEqual(tier_for(0, True, curve)["tier"], "lower")
        self.assertEqual(tier_for(2, True, curve)["tier"], "lower")
        self.assertEqual(tier_for(4, True, curve)["tier"], "moderate")
        self.assertEqual(tier_for(5, True, curve)["tier"], "higher")
        self.assertEqual(tier_for(2, False, curve)["tier"], "higher")

    def test_beyond_horizon_flagged(self):
        result = tier_for(99, True, self._curve())
        self.assertTrue(result["beyond_measured_horizon"])
        self.assertEqual(result["measured_through_months"], 9)

    def test_is_regular(self):
        self.assertTrue(is_regular(5, 3.0))
        self.assertFalse(is_regular(2, 1.0))
        self.assertFalse(is_regular(8, 12.0))
        self.assertFalse(is_regular(8, None))

    def test_retention_for_needs_history(self):
        self.assertIsNone(retention_for([0, 5], 50, self._curve()))
        result = retention_for(active(0, [2] * 12), 60, self._curve())
        self.assertIsNotNone(result)
        self.assertIn(result["tier"], ("lower", "moderate", "higher"))


if __name__ == "__main__":
    unittest.main()
