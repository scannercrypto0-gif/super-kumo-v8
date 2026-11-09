"""Narrow real-G1-SQLite smoke + adversarial synthetic G1→Scanner opportunity."""
from __future__ import annotations

import copy
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.aql.g1_integrity import fingerprint, content
from src.aql.models.bar import MarketBar, BarState
from src.aql.observation.contracts import ContextValue, CONTEXT_KEYS, DecisionSnapshot
from src.aql.journal.durable_journal import DurableJournal
from src.aql.storage.operational_store import OperationalStore
from tools.scanner_strategy_f import g1_g2_explicit_opportunity as op


class OpportunityBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="aql-g1-g2-test-")
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.journal=DurableJournal(str(root/"g1-journal.sqlite"))
        self.store=OperationalStore(str(root/"g1-store.sqlite"))
        self.now=1_704_067_200_000
        self.bar=MarketBar(
            symbol="BTCUSDT",interval="1m",
            bar_open=self.now-60000,
            bar_close=self.now-1,
            open=100.0,high=101.0,low=99.0,close=100.4,
            volume=10.0,is_final=True,source="binance_ws",
            ingested_at=self.now+1000,state=BarState.RECEIVED,
        ).with_checksum()
        self.policy=op.test_only_policy()
        self.identity={
            "strategy_id":"test_only_sma_explicit",
            "strategy_version":"v1",
            "strategy_definition_sha256":"1"*64,
            "strategy_config_sha256":"2"*64,
            "strategy_evaluator_sha256":"3"*64,
        }

    def commit(self):
        # Core G1 real durable journal/store, no mocked completion receipt.
        with patch("src.aql.journal.durable_journal.time.time",
                   return_value=(self.now+2000)/1000),patch(
                "src.aql.g1_integrity.time.time",
                return_value=(self.now+2000)/1000):
            self.assertTrue(self.journal.commit(self.bar))
            self.assertTrue(self.store.upsert(self.bar))
            self.journal.mark_persisted(self.bar.stable_key())
        self.assertEqual(self.journal.commit_receipt(
            self.bar.stable_key())["status"],
            "SQLITE_COMMIT_RETURN_OBSERVED")

    def decision(self,**changes):
        d=dict(symbol=self.bar.symbol,interval=self.bar.interval,
               bar_close_ms=self.bar.bar_close,
               decision_cutoff_ms=self.now+5000,
               decision_state="ENTRY_SIGNAL",**self.identity)
        d.update(changes)
        return op.explicit_test_decision(**d)

    def emit(self,*,bar=None,decision=None,policy=None,decision_ms=None,
             existing=None):
        return op.emit_explicit_opportunity(
            bar=self.bar if bar is None else bar,
            journal=self.journal,store=self.store,
            decision=self.decision() if decision is None else decision,
            policy=self.policy if policy is None else policy,
            decision_ms=self.now+5000 if decision_ms is None else decision_ms,
            existing=existing,
        )

    def test_real_g1_commit_to_explicit_opportunity_and_g2_smoke(self):
        self.commit()
        a=self.emit()
        self.assertEqual(a,self.emit(existing=a))
        self.assertEqual(a["source_availability"],
                         "G1_COMMIT_RECEIPT_OBSERVED_TEST_ONLY")
        self.assertEqual(a["source_bar_close_ms"],self.bar.bar_close)
        self.assertEqual(a["g1_content_digest"],fingerprint(content(self.bar)))
        self.assertEqual(a["policy_sha256"],self.policy["sha256"])
        self.assertEqual(a["decision_state"],"ENTRY_SIGNAL")
        self.assertEqual(a["trading_authority"],"NONE")
        self.assertFalse(a["orders_enabled"])
        self.assertTrue(all(a[k] is None for k in (
            "source_ack_sha256","strategy_approval_sha256",
            "factory_consumer_ack_sha256",
        )))
        # Core G2 native DecisionSnapshot contract, no unearned PIT context.
        ctx={k:ContextValue(None,None,None,None,"unknown")
             for k in CONTEXT_KEYS}
        s=DecisionSnapshot(
            opportunity_key=a["opportunity_key"],
            source=a["source_availability"],
            event_ms=a["source_bar_close_ms"],
            receipt_ms=a["g1_receipt_ms"],
            decision_ms=a["decision_ms"],
            disposition="observed", context=ctx,
            freshness_limit_ms=0,
        )
        self.assertEqual(s.opportunity_key,a["opportunity_key"])
        self.assertIn(a["opportunity_key"],s.serialized())
        self.assertEqual(op.verify_opportunity(a),a)

    def test_no_decision_no_final_or_provisional_late_recovered_bar(self):
        self.commit()
        for changes in (
            {"is_final":False},
            {"source":"binance_rest_recovery"},
            {"ingested_at":self.now+6000},
            {"bar_close":self.now+6000},
            {"checksum":"f"*64},
        ):
            bar=copy.deepcopy(self.bar)
            for k,v in changes.items():
                setattr(bar,k,v)
            if "source" in changes or "bar_close" in changes:
                bar.with_checksum()
            with self.subTest(changes=changes),self.assertRaises(
                    op.OpportunityRejected):
                self.emit(bar=bar)
        # No explicit action is not a new opportunity, even when bar exists.
        for state in ("NO_SIGNAL","UNKNOWN"):
            with self.assertRaises(op.OpportunityRejected):
                self.decision(decision_state=state)
        with self.assertRaises(op.OpportunityRejected):
            self.emit(decision_ms=self.now-1)

    def test_missing_commit_or_store_fail_closed(self):
        with self.assertRaises(op.OpportunityRejected):
            self.emit()
        with patch("src.aql.journal.durable_journal.time.time",
                   return_value=(self.now+2000)/1000),patch(
                "src.aql.g1_integrity.time.time",
                return_value=(self.now+2000)/1000):
            self.journal.commit(self.bar)
        with self.assertRaises(op.OpportunityRejected):
            self.emit()
        self.assertEqual(self.store.count(),0)

    def test_wrong_policy_config_decision_sha_and_duplicate(self):
        self.commit()
        good=self.emit()
        for key,value in (
            ("strategy_config_sha256","b"*64),
            ("decision_state","EXIT_SIGNAL"),
            ("strategy_definition_sha256","c"*64),
        ):
            d=self.decision(**{key:value})
            if key=="decision_state":
                with self.assertRaises(op.OpportunityRejected):
                    self.emit(decision=d,existing=good)
            else:
                # Different identity is a distinct opportunity, never an
                # idempotent retry of the original opportunity.
                with self.assertRaises(op.OpportunityRejected):
                    self.emit(decision=d,existing=good)
        forged=copy.deepcopy(good)
        forged["strategy_decision_sha256"]="0"*64
        with self.assertRaises(op.OpportunityRejected):
            op.verify_opportunity(forged)
        forged=copy.deepcopy(self.policy)
        forged["policy_class"]="LIVE_APPROVED"
        forged["sha256"]=op.g2_digest({
            k:v for k,v in forged.items() if k!="sha256"})
        with self.assertRaises(op.OpportunityRejected):
            self.emit(policy=forged)

    def test_decision_cutoff_mismatch_and_future(self):
        self.commit()
        with self.assertRaises(op.OpportunityRejected):
            self.emit(decision=self.decision(
                decision_cutoff_ms=self.now+4000))
        with self.assertRaises(op.OpportunityRejected):
            self.decision(bar_close_ms=self.now+6000)
        with self.assertRaises(op.OpportunityRejected):
            self.emit(decision=self.decision(
                symbol="ETHUSDT"))
        with self.assertRaises(op.OpportunityRejected):
            self.emit(decision=self.decision(
                interval="15m"))

    def test_conflicting_journal_store_replay_refused(self):
        self.commit()
        conflict=copy.deepcopy(self.bar)
        conflict.close=110.0
        conflict.with_checksum()
        with self.assertRaises(Exception):
            self.journal.commit(conflict)
        with self.assertRaises(op.OpportunityRejected):
            self.emit()

    def test_real_core_eligibility_receipt_digest_and_maturity(self):
        self.commit()
        r=self.journal.commit_receipt(self.bar.stable_key())
        self.assertEqual(r["content_digest"],fingerprint(content(self.bar)))
        a=self.emit()
        self.assertEqual(a["g1_receipt_sha256"],op.g2_digest(r))
        self.assertGreater(a["g1_receipt_ms"],self.bar.bar_close)
        self.assertLessEqual(a["g1_receipt_ms"],a["decision_ms"])
        # There is no 4/24/72h outcome in the Scanner packet: Core owns it.
        self.assertNotIn("observations",a)
        self.assertNotIn("orders",a)


if __name__=="__main__":
    unittest.main()
