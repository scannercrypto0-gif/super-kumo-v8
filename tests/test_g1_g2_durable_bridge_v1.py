"""Offline end-to-end G1 committed final bar -> explicit Scanner -> durable G2."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aql.models.bar import MarketBar, BarState
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.observation.contracts import HORIZONS_MS, digest
from aql.observation.durable_bridge_v1 import (
    DurableG2Bridge, BridgeStop, SCANNER_SCHEMA,
)


def fixture(bar_open=None, *, final=True, source="binance_ws"):
    now = int(time.time()*1000)
    start = bar_open if bar_open is not None else (now//60000-2)*60000
    bar = MarketBar(symbol="BTCUSDT",interval="1m",bar_open=start,
        bar_close=start+59999,open=100.,high=103.,low=98.,close=102.,
        volume=10.,is_final=final,source=source,
        ingested_at=now-1000,state=BarState.RECEIVED)
    return bar.with_checksum()


def scanner(bar, receipt, *, key="test-opportunity-1"):
    available = max(bar.ingested_at, receipt["commit_return_observed_at_ms"])
    body=dict(schema=SCANNER_SCHEMA,opportunity_key=key,origin="SCANNER_EXPLICIT",
              policy="TEST_ONLY",decision="OPPORTUNITY",authority="NONE",
              bar_key=bar.stable_key(),bar_checksum=bar.checksum,
              symbol=bar.symbol,interval=bar.interval,bar_close_ms=bar.bar_close,
              bar_available_ms=available,decision_ms=available+1,
              strategy_definition_sha256="1"*64,strategy_config_sha256="2"*64,
              scanner_policy_sha256="3"*64,decision_receipt_sha256="4"*64)
    return {**body,"sha256":digest(body)}


class DurableG1G2(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.j=DurableJournal(str(root/"g1-journal.sqlite"))
        self.s=OperationalStore(str(root/"g1-store.sqlite"))
        self.db=root/"g2.sqlite"
        self.g=DurableG2Bridge(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def committed(self, bar=None):
        bar=bar or fixture()
        self.j.commit(bar)
        self.s.upsert(bar)
        self.j.mark_persisted(bar.stable_key())
        proof=self.j.commit_receipt(bar.stable_key())
        return bar,scanner(bar,proof)

    def accept(self, bar, event):
        return self.g.accept(self.j,self.s,bar,event,
                             now_ms=event["decision_ms"]+1)

    def test_full_three_horizons_and_durable_restart(self):
        bar,event=self.committed()
        sid,state=self.accept(bar,event)
        self.assertEqual(state,"STORED_DURABLE")
        self.assertEqual(self.accept(bar,event),(sid,"REPLAY_IDENTICAL"))
        self.assertEqual(self.g.readback()["snapshots"],1)
        self.g=DurableG2Bridge(self.db)
        self.assertEqual(self.g.readback()["snapshots"],1)
        for h in HORIZONS_MS:
            self.assertEqual(self.g.horizon_state(sid,h,event["decision_ms"]+h),"pending")
        for i,h in enumerate(HORIZONS_MS):
            t=event["decision_ms"]+h
            kwargs=dict(observed_ms=t,received_ms=t+1,source="fixture",
                        evidence_id=f"sealed-observation-{i}")
            if i==1:
                kwargs["missing_reason"]="NO_ELIGIBLE_SOURCE"
            else:
                kwargs["value"]="up"
            self.assertEqual(self.g.observe(sid,h,**kwargs),"STORED_DURABLE")
            self.assertEqual(self.g.observe(sid,h,**kwargs),"REPLAY_IDENTICAL")
            self.assertEqual(self.g.horizon_state(sid,h,t),"pending")
            self.assertEqual(self.g.horizon_state(sid,h,t+1),
                             "missing" if i==1 else "mature")
        self.assertEqual(DurableG2Bridge(self.db).readback()["observations"],3)
        self.assertEqual(DurableG2Bridge(self.db).readback()["trading_authority"],"NONE")

    def test_no_automatic_opportunity_without_scanner(self):
        bar,_=self.committed()
        with self.assertRaises(BridgeStop):
            self.g.accept(self.j,self.s,bar,None,now_ms=int(time.time()*1000))
        self.assertEqual(self.g.readback()["snapshots"],0)

    def test_nonfinal_and_recovered_denied(self):
        b,e=self.committed()
        for mutated in (dict(b.to_dict(),is_final=False),
                        dict(b.to_dict(),source="binance_rest_recovery")):
            other=MarketBar.from_dict(mutated).with_checksum()
            with self.assertRaises(BridgeStop):
                self.accept(other,e)
        self.assertEqual(self.g.readback()["snapshots"],0)

    def test_forged_scanner_or_wrong_identity_denied(self):
        b,e=self.committed()
        for other in ({**e,"sha256":"f"*64},
                      {**e,"policy":"APPROVED"},
                      {**e,"bar_key":"wrong"}):
            with self.assertRaises(BridgeStop):
                self.accept(b,other)

    def test_missing_g1_commit_and_store_denied(self):
        b=fixture()
        self.j.commit(b)
        proof=self.j.commit_receipt(b.stable_key())
        with self.assertRaises(BridgeStop):
            self.accept(b,scanner(b,proof))
        self.assertEqual(self.g.readback()["snapshots"],0)

    def test_future_and_stale_opportunity_denied(self):
        b,e=self.committed()
        future={**e,"decision_ms":e["decision_ms"]+100_000}
        future["sha256"]=digest({k:v for k,v in future.items() if k!="sha256"})
        with self.assertRaises(BridgeStop):
            self.accept(b,future)
        stale={**e,"decision_ms":e["bar_available_ms"]+6001}
        stale["sha256"]=digest({k:v for k,v in stale.items() if k!="sha256"})
        with self.assertRaises(BridgeStop):
            self.accept(b,stale)

    def test_crash_boundary_retry_and_conflicting_opportunity(self):
        b,e=self.committed()
        # G1 is committed; G2 was never called (simulated inter-stage crash).
        self.g=DurableG2Bridge(self.db)
        sid,_=self.accept(b,e)
        conflict={**e,"strategy_config_sha256":"9"*64}
        conflict["sha256"]=digest({k:v for k,v in conflict.items() if k!="sha256"})
        with self.assertRaises(BridgeStop):
            self.accept(b,conflict)
        self.assertEqual(DurableG2Bridge(self.db).readback()["snapshots"],1)

    def test_duplicate_conflicting_observation_and_tamper(self):
        b,e=self.committed()
        sid,_=self.accept(b,e)
        t=e["decision_ms"]+HORIZONS_MS[0]
        base=dict(observed_ms=t,received_ms=t+1,source="fixture",
                  evidence_id="obs-1",value="up")
        self.g.observe(sid,HORIZONS_MS[0],**base)
        with self.assertRaises(BridgeStop):
            self.g.observe(sid,HORIZONS_MS[0],**{**base,"value":"down"})
        with self.assertRaises(Exception):
            self.g.observe(sid,HORIZONS_MS[1],observed_ms=t,
                received_ms=t,source="fixture",evidence_id="early",value="up")
        import sqlite3
        conn=sqlite3.connect(self.db)
        conn.execute("UPDATE events SET payload='{}' WHERE seq=1")
        conn.commit()
        conn.close()
        with self.assertRaises((BridgeStop,KeyError)):
            DurableG2Bridge(self.db)


if __name__ == "__main__":
    unittest.main()
