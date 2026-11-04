"""Core #253 actual source-backed TEST_ONLY ROC rule calculation; no original private bytes."""
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib
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

    def test_24_bar_existing_roc_kernel_entry_exit(self):
        count=24
        lines=[]
        for i in range(count):
            close=100+3*i if i<12 else 136-4*(i-12)
            lines.append(",".join(map(str,(
                START+i*WIDTH,close,close+1,close-1,close,5,
                START+(i+1)*WIDTH-1,500,10,2,200,0,
            ))))
        csv=("\\n".join(lines)+"\\n").encode()
        sink=BytesIO()
        with ZipFile(sink,"w",compression=ZIP_DEFLATED) as z:
            z.writestr("BTCUSDT-15m-2024-02.csv",csv)
        raw=sink.getvalue()
        sha=lambda b:hashlib.sha256(b).hexdigest()
        cs=(sha(raw)+"  BTCUSDT-15m-2024-02.zip\\n").encode()
        w={**self.w,"archive_sha256":sha(raw),"csv_member_sha256":sha(csv),
           "checksum_sha256":sha(cs),"archive_bytes":len(raw),
           "checksum_bytes":len(cs),"observed_bars":count,
           "end_exclusive_ms":START+count*WIDTH}
        cutoff=START+count*WIDTH+10000
        with TemporaryDirectory() as td:
            root=Path(td)/"core"
            _,warehouse,_,_=run_authorized_original_intake(
                root,raw,cs,w,vault=RawVault(Path(td)/"vault"),
                cutoff_ms=cutoff,test_only=True)
            result=calculate_one_original_test_strategy(
                root,warehouse,start_ms=START,
                end_exclusive_ms=START+count*WIDTH,cutoff_ms=cutoff)
            self.assertEqual(result["decision_slots"],23)
            self.assertEqual(result["decision_counts"]["UNKNOWN"],5)
            self.assertGreater(result["decision_counts"]["ENTRY_TRIGGERED"],0)
            self.assertGreater(result["decision_counts"]["EXIT_TRIGGERED"],0)

    def test_reject_wrong_strategy_digest(self):
        wrong=deepcopy(default_test_strategy())
        wrong["digest"]="0"*64
        with self.assertRaises(ValueError):
            self.calculate(definition=wrong)


if __name__=="__main__":
    unittest.main()
