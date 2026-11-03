"""Focused tests for the frozen P2 Breakout adapter; TEST_ONLY invented prices."""
import unittest
from dataclasses import replace

from research_wp_r0.aql_p2_core_producer import (
    BAR_MS, ContractError, HistoricalBarV1, HistoricalSourceV1,
)
from research_wp_r0.aql_p2_breakout_trial import (
    FEB_START, FEB_END, SOURCE_ARCHIVES, frozen_prespec, seal_protocol,
    produce_cohort,
)

H = "a" * 64
J = "b" * 64
K = "c" * 64


def synthetic_cohort():
    dataset = "BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1"
    source = HistoricalSourceV1(dataset, "BINANCE", "SPOT", "BTCUSDT",
                                SOURCE_ARCHIVES[dataset][2], H, J, "UNKNOWN_NOT_ATTESTED")
    bars, rows = [], []
    for i in range((FEB_END-FEB_START)//BAR_MS):
        op = FEB_START+i*BAR_MS
        h = H if i != 20 else K
        bars.append(HistoricalBarV1(op, op+BAR_MS-1, h))
        close = "102" if i == 20 else "100"
        rows.append({"dataset_id": dataset, "open_ms": op,
                     "close_ms": op+BAR_MS-1, "bar_sha256": h,
                     "high": "103" if i == 20 else "101",
                     "low": "99", "close": close})
    return source, tuple(bars), tuple(rows)


class BreakoutTrialTests(unittest.TestCase):
    def test_frozen_protocol_reproducible(self):
        spec, trial = seal_protocol()
        self.assertEqual((spec, trial), seal_protocol())
        self.assertNotEqual(trial.base_definition_sha256, trial.shadow_definition_sha256)
        self.assertEqual(spec["shadow_exclude"], "volatility > 0.03; equality accepted")

    def test_real_contract_synthetic_fixture_not_real_evidence(self):
        source, bars, rows = synthetic_cohort()
        _, trial = seal_protocol()
        got = produce_cohort(source, bars, rows, trial)
        self.assertEqual(len(got), len(bars)-21)
        self.assertEqual(got[0].disposition, "TRIGGERED")
        self.assertEqual(got[0].direction, "LONG")
        self.assertTrue(got[0].direction_evidence_ref.startswith("P2_MODELED_BREAKOUT:"))
        self.assertEqual(got[1].disposition, "NO_SIGNAL")
        self.assertEqual(got, produce_cohort(source, bars, rows, trial))

    def test_tampered_price_mapping_rejected(self):
        source, bars, rows = synthetic_cohort()
        _, trial = seal_protocol()
        changed = list(rows)
        changed[0] = {**changed[0], "bar_sha256": K}
        with self.assertRaisesRegex(ContractError, "UNVERIFIED_BAR_MAPPING"):
            produce_cohort(source, bars, changed, trial)

    def test_unfinalized_rejected(self):
        source, bars, rows = synthetic_cohort()
        _, trial = seal_protocol()
        with self.assertRaisesRegex(ContractError, "UNFINALIZED"):
            produce_cohort(source, (replace(bars[0], finalized=False),)+bars[1:], rows, trial)

    def test_source_pin_rejected(self):
        source, bars, rows = synthetic_cohort()
        _, trial = seal_protocol()
        with self.assertRaisesRegex(ContractError, "SOURCE_ARCHIVE_PIN_DRIFT"):
            produce_cohort(replace(source, source_package_sha256=K), bars, rows, trial)

    def test_no_cross_month_or_partial_cohort(self):
        source, bars, rows = synthetic_cohort()
        _, trial = seal_protocol()
        with self.assertRaisesRegex(ContractError, "COHORT_COVERAGE_MISMATCH"):
            produce_cohort(source, bars[:-1], rows[:-1], trial)


if __name__ == "__main__":
    unittest.main()
