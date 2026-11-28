"""Focused offline tests for research-only timeframe projections."""
import unittest
from datetime import datetime, timezone

from aql.research_timeframes import MINUTE, WEEK_ORIGIN_MS, project_finalized_1m


def make_bars(count, start=0):
    return [
        dict(symbol="BTCUSDT", interval="1m", open_ms=start + i * MINUTE,
             final=True, o="10", h="12", l="9", c="11", v="2.5",
             source_sha256=f"{i + 1:064x}",
             available_at_ms=start + (i + 1) * MINUTE + 100)
        for i in range(count)
    ]


class TestResearchTimeframes(unittest.TestCase):
    def test_5m_closed_projection(self):
        result = project_finalized_1m(make_bars(5), "5m")
        self.assertEqual(result["v"], "12.5")
        self.assertEqual(result["available_at_ms"], 5 * MINUTE + 100)
        self.assertEqual(result["trading_authority"], "NONE")
        self.assertEqual(result["pit_oos"], "NOT_ATTESTED")
        self.assertEqual(len(result["constituent_sha256"]), 5)
        self.assertEqual(result, project_finalized_1m(make_bars(5), "5m"))

    def test_week_monday_utc(self):
        start = WEEK_ORIGIN_MS + 56 * 86_400_000
        self.assertEqual(project_finalized_1m(make_bars(10080, start), "1w")["open_ms"], start)
        with self.assertRaisesRegex(ValueError, "UTC_WINDOW_MISALIGNED"):
            project_finalized_1m(make_bars(10080, start + 86_400_000), "1w")

    def test_missing_and_duplicate(self):
        bars = make_bars(5)
        bars[3]["open_ms"] = bars[2]["open_ms"]
        with self.assertRaisesRegex(ValueError, "GAP_DUPLICATE_OR_PROVISIONAL"):
            project_finalized_1m(bars, "5m")

    def test_provisional_denied(self):
        bars = make_bars(5)
        bars[-1]["final"] = False
        with self.assertRaisesRegex(ValueError, "GAP_DUPLICATE_OR_PROVISIONAL"):
            project_finalized_1m(bars, "5m")

    def test_no_pit_promotion(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_CLASS_UNSUPPORTED"):
            project_finalized_1m(make_bars(5), "5m", source_class="PIT_APPROVED")

    def test_invalid_source_digest(self):
        bars = make_bars(5)
        bars[1]["source_sha256"] = "unverified"
        with self.assertRaisesRegex(ValueError, "SOURCE_DIGEST_REQUIRED"):
            project_finalized_1m(bars, "5m")

    def test_unsupported_interval(self):
        with self.assertRaisesRegex(ValueError, "INTERVAL_UNSUPPORTED"):
            project_finalized_1m(make_bars(5), "2m")


if __name__ == "__main__":
    unittest.main()
