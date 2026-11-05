"""Private F4 E2E command: a real Lab smoke requires a trusted positive witness.

These are fail-closed negative tests, NOT synthetic success of actual original
historical data. The private positive test is deliberately unavailable in CI.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_factory_f_private_original_cohort_v1 import (
    validate_input,run_private_cohort,ResultsStoreError,
)


class FactoryFPrivateE2EGate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"private.sqlite"
    def test_unapproved_untrusted_packet_never_executes_lab_or_writes_db(self):
        with self.assertRaises(ResultsStoreError):
            run_private_cohort({}, {}, "f"*64, self.db)
        self.assertFalse(self.db.exists())
    def test_missing_external_authority_blocks_before_any_lab(self):
        data={
            "schema":"aql.factory.f.private-original-cohort-input.v1",
            "experiment_id":"F-NO-TRUST","batch_id":"F-NO-TRUST",
            "market":"BINANCE:SPOT:USDT","symbol":"BTCUSDT",
            "timeframe":"15m","policy_id":
            "btc-spot-15m-retrospective-non-pit-v1",
            "policy_draft_sha256":"a"*64,
        }
        with self.assertRaises(ResultsStoreError):
            validate_input(data,{}, "a"*64)
        self.assertFalse(self.db.exists())
    def test_public_runner_never_opens_original_private_files(self):
        from research_wp_r0.aql_factory_f_private_original_cohort_v1 import _load
        with self.assertRaises(ResultsStoreError):
            _load(Path(self.tmp.name)/"not-available-original.json",50_000_000)
        self.assertFalse(self.db.exists())
    def test_reject_oversized_or_symlinked_raw_input(self):
        from research_wp_r0.aql_factory_f_private_original_cohort_v1 import _load
        bad=Path(self.tmp.name)/"bad.json"
        bad.write_text("{}")
        with self.assertRaises(ResultsStoreError):
            _load(bad,1)


if __name__=="__main__":
    unittest.main()
