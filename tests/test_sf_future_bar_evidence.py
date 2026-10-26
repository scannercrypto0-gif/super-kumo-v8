"""Post-decision evidence schema tests (not exchange custody verification)."""
import unittest

from research_wp_r0.future_bar_evidence import FutureBarEvidence


def fixture(**changes):
    value = {
        "schema_version": "research-future-bars-1",
        "inputs_digest": "a" * 64,
        "decision_cutoff_ms": 999,
        "symbol": "BTCUSDT",
        "interval_ms": 1000,
        "independent_custody": "NOT_VERIFIED",
        "bars": [
            {"open_ms": 1000, "close_ms": 1999, "open": 100, "high": 110,
             "low": 95, "close": 105, "volume": 10, "observed_at_ms": 2000},
            {"open_ms": 2000, "close_ms": 2999, "open": 105, "high": 115,
             "low": 100, "close": 110, "volume": 10, "observed_at_ms": 3000},
        ],
    }
    value.update(changes)
    return value


class FutureEvidenceTests(unittest.TestCase):
    def test_deterministic_commitment(self):
        self.assertEqual(FutureBarEvidence(fixture()).digest,
                         FutureBarEvidence(fixture()).digest)

    def test_rejects_wrong_input_digest(self):
        with self.assertRaises(ValueError):
            FutureBarEvidence(fixture(inputs_digest="wrong"))

    def test_rejects_future_bar_at_decision(self):
        bars = fixture()["bars"]
        bars[0]["open_ms"] = 999
        with self.assertRaises(ValueError):
            FutureBarEvidence(fixture(bars=bars))

    def test_rejects_gap_and_duplicate(self):
        for start in (1999, 3000):
            bars = fixture()["bars"]
            bars[1]["open_ms"] = start
            with self.subTest(start=start), self.assertRaises(ValueError):
                FutureBarEvidence(fixture(bars=bars))

    def test_rejects_inconsistent_prices(self):
        bars = fixture()["bars"]
        bars[0]["high"] = 99
        with self.assertRaises(ValueError):
            FutureBarEvidence(fixture(bars=bars))

    def test_rejects_custody_self_attestation(self):
        with self.assertRaises(ValueError):
            FutureBarEvidence(fixture(independent_custody="VERIFIED"))


if __name__ == "__main__":
    unittest.main()
