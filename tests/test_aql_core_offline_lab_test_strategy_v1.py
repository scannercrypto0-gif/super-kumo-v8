"""Core #253 actual source-backed TEST_ONLY ROC rule calculation; no original private bytes."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.raw_vault_offline.vault import RawVault
from research_wp_r0.aql_core_authorized_source_transfer_v1 import run_authorized_original_intake
from research_wp_r0.aql_core_offline_lab_test_strategy_v1 import (
    calculate_one_original_test_strategy,default_test_strategy,
)
from test_aql_core_authorized_source_transfer_v1 import synthetic_test_only,START,N,WIDTH


class CoreLabCalculation(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"core"
        self.vault=RawVault(Path(self.tmp.name)/"raw")
        raw,checksum,w=self.raw,self.checksum,self.w=(*synthetic_test_only(),)
        self.cutoff=START+N*WIDTH+10000
        self.transfer,self.warehouse,self.query,self.msg=run_authorized_original_intake(
            self.root,raw,checksum,w,vault=self.vault,cutoff_ms=self.cutoff,
            test_only=True,
        )

    def calculate(self,**kw):
        return calculate_one_original_test_strategy(
            self.root,self.warehouse,start_ms=START,
            end_exclusive_ms=START+N*WIDTH,cutoff_ms=self.cutoff,**kw,
        )

    def test_existing_roc_kernel_and_source_readback_replay(self):
        result=self.calculate()
        self.assertEqual(result,self.calculate())
        self.assertEqual(result["bar_count"],N)
        self.assertEqual(result["decision_slots"],N-1)
        self.assertEqual(result["decision_counts"]["UNKNOWN"],N-1)
        self.assertEqual(result["source_zip_sha256"],self.w["archive_sha256"])
        self.assertEqual(result["operational_scanner_status"],"UNKNOWN")
        self.assertIsNone(result["historical_known_at_ms"])
        self.assertEqual(result["trading_authority"],"NONE")
        self.assertEqual(result["attempt_denominator"],1)
        self.assertEqual(result["strategy_digest"],default_test_strategy()["digest"])

    def test_source_and_cutoff_mutations_fail_closed(self):
        wrong=deepcopy(self.warehouse)
        wrong["source_zip_sha256"]="0"*64
        with self.assertRaises(ValueError):
            calculate_one_original_test_strategy(
                self.root,wrong,start_ms=START,
                end_exclusive_ms=START+N*WIDTH,cutoff_ms=self.cutoff)
        with self.assertRaises(ValueError):
            calculate_one_original_test_strategy(
                self.root,self.warehouse,start_ms=START,
                end_exclusive_ms=START+N*WIDTH,cutoff_ms=self.cutoff+1)
        wrong=deepcopy(self.warehouse)
        wrong["status"]="OFFLINE_LOCAL_STAGE_ONLY"
        with self.assertRaises(ValueError):
            calculate_one_original_test_strategy(
                self.root,wrong,start_ms=START,
                end_exclusive_ms=START+N*WIDTH,cutoff_ms=self.cutoff)

    def test_reject_wrong_strategy_digest(self):
        wrong=deepcopy(default_test_strategy())
        wrong["digest"]="0"*64
        with self.assertRaises(ValueError):
            self.calculate(definition=wrong)


if __name__=="__main__":
    unittest.main()
