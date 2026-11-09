"""Cross-owner exact-head integration: actual Scanner #277 producer -> Core #281 G2."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCANNER_ROOT = os.environ.get("AQL_PINNED_SCANNER_ROOT")
if not SCANNER_ROOT or not (Path(SCANNER_ROOT) / "tools/scanner_strategy_f/g1_g2_explicit_opportunity.py").is_file():
    raise RuntimeError("PINNED_SCANNER_SOURCE_REQUIRED_NO_SYNTHETIC_FALLBACK")

sys.path.insert(0, str(Path(SCANNER_ROOT).resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from src.aql.models.bar import MarketBar as ScannerMarketBar
from tools.scanner_strategy_f.g1_g2_explicit_opportunity import (
    emit_explicit_opportunity, explicit_test_decision, test_only_policy,
    verify_opportunity, SCHEMA as PRODUCER_SCHEMA,
)
from aql.models.bar import MarketBar, BarState
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.observation.contracts import HORIZONS_MS, digest
from aql.observation.durable_bridge_v1 import DurableG2Bridge, BridgeStop, SCANNER_SCHEMA


class ExactHeadScannerProducerToCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.j = DurableJournal(str(root/"source.sqlite"))
        self.s = OperationalStore(str(root/"store.sqlite"))
        self.g2_path = root/"obs.sqlite"
        self.g = DurableG2Bridge(self.g2_path)
        now = int(time.time()*1000)
        start = (now // 60000 - 2)*60000
        self.bar = MarketBar(
            symbol="BTCUSDT",interval="1m",bar_open=start,
            bar_close=start+59999,open=99.,high=103.,low=98.,
            close=101.,volume=1.5,is_final=True,source="binance_ws",
            ingested_at=now-500,state=BarState.RECEIVED,
        ).with_checksum()
        self.j.commit(self.bar)
        self.s.upsert(self.bar)
        self.j.mark_persisted(self.bar.stable_key())
        self.commit = self.j.commit_receipt(self.bar.stable_key())
        self.now = max(int(time.time()*1000),self.commit["commit_return_observed_at_ms"])+1

    def tearDown(self):
        self.tmp.cleanup()

    def actual_emitter(self):
        self.assertEqual(PRODUCER_SCHEMA,SCANNER_SCHEMA)
        policy = test_only_policy()
        decision = explicit_test_decision(
            symbol=self.bar.symbol, interval=self.bar.interval,
            bar_close_ms=self.bar.bar_close, decision_cutoff_ms=self.now,
            strategy_id="explicit_real_scanner_test", strategy_version="1",
            strategy_definition_sha256="a"*64, strategy_config_sha256="b"*64,
            strategy_evaluator_sha256="c"*64, decision_state="ENTRY_SIGNAL",
        )
        # Scanner module imports src.aql.MarketBar: convert only in-memory
        # representation, retaining identical checksum, source and G1 identity.
        scanner_bar=ScannerMarketBar.from_dict(self.bar.to_dict())
        actual=emit_explicit_opportunity(
            bar=scanner_bar,journal=self.j,store=self.s,
            decision=decision,policy=policy,decision_ms=self.now,
        )
        self.assertEqual(verify_opportunity(actual),actual)
        return actual

    def test_actual_scanner_emission_through_restart_and_three_horizons(self):
        event = self.actual_emitter()
        sid,status=self.g.accept(self.j,self.s,self.bar,event,now_ms=self.now+1)
        self.assertEqual(status,"STORED_DURABLE")
        self.assertEqual(self.g.accept(self.j,self.s,self.bar,event,now_ms=self.now+1),
                         (sid,"REPLAY_IDENTICAL"))
        self.g=DurableG2Bridge(self.g2_path)
        self.assertEqual(self.g.readback()["snapshots"],1)
        for i,h in enumerate(HORIZONS_MS):
            t=self.now+h
            self.assertEqual(self.g.horizon_state(sid,h,t),"pending")
            params=dict(observed_ms=t,received_ms=t+1,source="TEST_ONLY",
                        evidence_id="actual-scanner-linked-synthetic-"+str(i))
            if i==1:
                params["missing_reason"]="NO_OBSERVATION_SOURCE"
            else:
                params["value"]="UP"
            self.assertEqual(self.g.observe(sid,h,**params),"STORED_DURABLE")
            self.assertEqual(self.g.horizon_state(sid,h,t+1),
                             "missing" if i==1 else "mature")
        self.assertEqual(DurableG2Bridge(self.g2_path).readback()["observations"],3)

    def test_actual_scanner_event_forgery_and_time_drift_denied(self):
        event=self.actual_emitter()
        altered=dict(event,g1_receipt_ms=event["g1_receipt_ms"]-1)
        altered["sha256"]=digest({k:v for k,v in altered.items() if k!="sha256"})
        with self.assertRaises(BridgeStop):
            self.g.accept(self.j,self.s,self.bar,altered,now_ms=self.now+1)
        with self.assertRaises(BridgeStop):
            self.g.accept(self.j,self.s,self.bar,event,now_ms=self.now-1)
        self.assertEqual(self.g.readback()["snapshots"],0)


if __name__ == "__main__":
    unittest.main()
