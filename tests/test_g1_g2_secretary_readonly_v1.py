"""Focused Secretary read-only contract tests against the actual Core G2 DB."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from aql.models.bar import MarketBar, BarState
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.observation.contracts import HORIZONS_MS, digest
from aql.observation.durable_bridge_v1 import DurableG2Bridge, BridgeStop, SCANNER_SCHEMA
from aql.observation.secretary_g2_readonly_v1 import (
    consume_verified_opportunity,read_secretary_receipt,SecretaryReadStop,ACK_FIELDS
)


class SecretaryB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db=root/"g2.sqlite"
        self.j=DurableJournal(str(root/"journal.sqlite"))
        self.store=OperationalStore(str(root/"store.sqlite"))
        self.g=DurableG2Bridge(self.db)
        now=int(time.time()*1000)
        opened=(now//60000-2)*60000
        self.bar=MarketBar(symbol="BTCUSDT",interval="1m",
            bar_open=opened,bar_close=opened+59999,
            open=100.,high=110.,low=95.,close=105.,volume=4.,
            is_final=True,source="binance_ws",ingested_at=now-700,
            state=BarState.RECEIVED).with_checksum()
        self.j.commit(self.bar)
        self.store.upsert(self.bar)
        self.j.mark_persisted(self.bar.stable_key())
        r=self.j.commit_receipt(self.bar.stable_key())
        t=r["commit_return_observed_at_ms"]+1
        parents=dict(strategy_id="synthetic_explicit_strategy",
            strategy_version="v1",strategy_definition_sha256="1"*64,
            strategy_config_sha256="2"*64,strategy_evaluator_sha256="3"*64)
        policy_sha="4"*64
        decision=dict(schema="aql.scanner.g1-g2.explicit-test-decision.v1",
            symbol=self.bar.symbol,interval=self.bar.interval,
            bar_close_ms=self.bar.bar_close,decision_cutoff_ms=t,
            decision_state="ENTRY_SIGNAL",test_only=True,**parents)
        key=digest(dict(schema=SCANNER_SCHEMA,
            g1_stable_key=self.bar.stable_key(),policy_sha256=policy_sha,
            **parents))
        o=dict(schema=SCANNER_SCHEMA,opportunity_key=key,
            symbol=self.bar.symbol,interval=self.bar.interval,source="binance_ws",
            source_bar_open_ms=self.bar.bar_open,
            source_bar_close_ms=self.bar.bar_close,
            bar_checksum=self.bar.checksum,g1_stable_key=self.bar.stable_key(),
            g1_content_digest=r["content_digest"],g1_receipt_sha256=digest(r),
            g1_receipt_ms=r["commit_return_observed_at_ms"],
            decision_cutoff_ms=t,decision_ms=t,
            strategy_decision_sha256=digest(decision),
            decision_state="ENTRY_SIGNAL",policy_sha256=policy_sha,
            source_availability="G1_COMMIT_RECEIPT_OBSERVED_TEST_ONLY",
            test_only=True,historical_pit="NOT_ATTESTED",
            source_ack_sha256=None,strategy_approval_sha256=None,
            factory_consumer_ack_sha256=None,trading_authority="NONE",
            orders_enabled=False,**parents)
        o["sha256"]=digest(o)
        self.sid,status=self.g.accept(self.j,self.store,self.bar,o,now_ms=t+1)
        self.assertEqual(status,"STORED_DURABLE")
        self.t=t

    def tearDown(self):
        self.tmp.cleanup()

    def test_readonly_receipt_all_three_maturity_and_restart(self):
        for i,h in enumerate(HORIZONS_MS):
            moment=self.t+h
            params=dict(observed_ms=moment,received_ms=moment+1,
                        source="TEST_ONLY",evidence_id=f"observed-{i}")
            if i==1: params["missing_reason"]="SOURCE_UNKNOWN"
            else: params["value"]="UP"
            self.g.observe(self.sid,h,**params)
        # No future event is readable as of the first horizon.
        early=self.g.read_verified_opportunity(
            self.sid,as_of_ms=self.t+HORIZONS_MS[0]+1)
        self.assertEqual([x["state"] for x in early["horizons"]],
                         ["mature","pending","pending"])
        final_time=self.t+HORIZONS_MS[-1]+1
        self.g=DurableG2Bridge(self.db)
        exp=self.g.read_verified_opportunity(self.sid,as_of_ms=final_time)
        self.assertEqual([x["state"] for x in exp["horizons"]],
                         ["mature","missing","mature"])
        receipt=read_secretary_receipt(self.g,self.sid,as_of_ms=final_time)
        self.assertEqual(receipt,consume_verified_opportunity(exp))
        self.assertEqual(receipt["receipt_sha256"],
                         digest({k:v for k,v in receipt.items()
                                 if k!="receipt_sha256"}))
        self.assertTrue(all(receipt[k] is None for k in ACK_FIELDS))
        self.assertEqual((receipt["orders"],receipt["fills"]),(0,0))
        self.assertEqual(receipt["trading_authority"],"NONE")
        self.assertEqual(read_secretary_receipt(DurableG2Bridge(self.db),
                         self.sid,as_of_ms=final_time),receipt)
        self.assertEqual(self.g.readback()["observations"],3)

    def test_missing_observation_is_unknown_not_mature(self):
        when=self.t+HORIZONS_MS[-1]+100
        exp=self.g.read_verified_opportunity(self.sid,as_of_ms=when)
        self.assertEqual([x["state"] for x in exp["horizons"]],
                         ["UNKNOWN","UNKNOWN","UNKNOWN"])
        result=consume_verified_opportunity(exp)
        self.assertTrue(all(x["evidence_sha256"] is None
                            for x in result["horizons"]))
        self.assertEqual(self.g.readback()["observations"],0)

    def test_forged_ack_and_parent_receipt_refused(self):
        exp=self.g.read_verified_opportunity(
            self.sid,as_of_ms=self.t+1)
        for bad in (
            {**exp,"source_ack_sha256":"a"*64},
            {**exp,"scanner_opportunity_sha256":"f"*64},
        ):
            with self.assertRaises(SecretaryReadStop):
                consume_verified_opportunity(bad)
        altered={**exp,"horizons":exp["horizons"][:-1]}
        altered["sha256"]=digest({k:v for k,v in altered.items()
                                 if k!="sha256"})
        with self.assertRaises(SecretaryReadStop):
            consume_verified_opportunity(altered)

    def test_forged_time_missing_horizon_wrong_id_denied(self):
        exp=self.g.read_verified_opportunity(
            self.sid,as_of_ms=self.t+1)
        edits=[
            lambda z:z["horizons"][0].update(state="mature"),
            lambda z:z["horizons"][0].update(identity="wrong"),
            lambda z:z["horizons"][1].update(horizon_ms=HORIZONS_MS[0]),
            lambda z:z["horizons"].pop(),
        ]
        import copy
        for change in edits:
            forged=copy.deepcopy(exp)
            change(forged)
            forged["sha256"]=digest({k:v for k,v in forged.items()
                                    if k!="sha256"})
            with self.assertRaises(SecretaryReadStop):
                consume_verified_opportunity(forged)

    def test_duplicate_observation_tamper_and_no_source_write(self):
        h=HORIZONS_MS[0]
        t=self.t+h
        params=dict(observed_ms=t,received_ms=t+1,
                    source="TEST_ONLY",evidence_id="evt",value="UP")
        self.assertEqual(self.g.observe(self.sid,h,**params),"STORED_DURABLE")
        self.assertEqual(self.g.observe(self.sid,h,**params),"REPLAY_IDENTICAL")
        before=self.g.readback()
        r=read_secretary_receipt(self.g,self.sid,as_of_ms=t+1)
        self.assertEqual(r["horizons"][0]["state"],"mature")
        self.assertEqual(self.g.readback(),before)
        with self.assertRaises(BridgeStop):
            self.g.observe(self.sid,h,**{**params,"value":"DOWN"})
        import sqlite3
        con=sqlite3.connect(self.db)
        con.execute("UPDATE events SET payload='{}' WHERE seq=1")
        con.commit(); con.close()
        with self.assertRaises((BridgeStop,KeyError)):
            self.g.read_verified_opportunity(self.sid,as_of_ms=t+1)

    def test_asof_before_decision_rejected(self):
        with self.assertRaises(BridgeStop):
            self.g.read_verified_opportunity(self.sid,as_of_ms=self.t-1)


if __name__=="__main__":
    unittest.main()
