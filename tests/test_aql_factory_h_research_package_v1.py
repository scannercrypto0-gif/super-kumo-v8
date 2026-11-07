"""Package H focused research-only Factory/Lab tests over structural fixtures.

Never owner private E: source or signed F5 scientific acceptance.
"""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, migrate_store_v2, digest,
)
from research_wp_r0.aql_factory_h_trade_event_ledger_v1 import (
    build_trade_event_ledger,verify_trade_event_ledger,
)
from research_wp_r0.aql_factory_h_scientific_lab_v1 import (
    evaluate_immutable_ledger,secretary_research_receipt,
)
from research_wp_r0.aql_factory_h_research_package_v1 import (
    run_factory_h_research,
)
from test_aql_factory_f_f2_recovery_research_v2 import fixture_packet,reseal


class FactoryHResearch(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"h-research.sqlite"
        self.packet=fixture_packet()

    def test_ledger_denominators_and_immutable_package_restart(self):
        migrate_store_v2(self.db)
        one=run_factory_h_research(self.packet,self.db)
        two=run_factory_h_research(self.packet,self.db)
        self.assertEqual(one["store_status"],"STORED_IMMUTABLE")
        self.assertEqual(two["store_status"],"REPLAY_IDENTICAL")
        self.assertEqual(one["factory_store_status"],"STORED_IMMUTABLE")
        self.assertEqual(two["factory_store_status"],"REPLAY_IDENTICAL")
        for key in ("package_sha256","trade_ledger_sha256",
                    "scientific_lab_sha256","secretary_receipt_sha256",
                    "factory_experiment_sha256","factory_result_sha256",
                    "factory_lab_sha256"):
            self.assertEqual(one[key],two[key])
        self.assertNotEqual(one["receipt_sha256"],two["receipt_sha256"])
        for result in (one,two):
            self.assertEqual(result["receipt_sha256"],
                             digest({k:v for k,v in result.items()
                                     if k!="receipt_sha256"}))
            self.assertEqual(result["trading_authority"],"NONE")
            self.assertEqual(result["f5"],"BLOCKED_EXTERNAL_INPUT")
        ledger=build_trade_event_ledger(self.packet)
        self.assertEqual(ledger["cohort"]["original_bars"],29376)
        self.assertEqual(ledger["cohort"]["attempts"],24)
        self.assertEqual(ledger["cohort"]["inventory_unknown"],4)
        self.assertEqual(ledger["cohort"]["decision_slots"],7)
        self.assertEqual(ledger["cohort"]["focus_bar_count"],8)
        self.assertEqual(ledger["historical_pit"],"NOT_ATTESTED")
        verify_trade_event_ledger(self.packet,ledger)
        lab=evaluate_immutable_ledger(ledger)
        self.assertEqual(lab["metrics"]["modeled_trade_count"],
                         ledger["cohort"]["modeled_trades"])
        self.assertTrue(lab["uncertainty"]["in_sample_only"])
        self.assertIsNone(lab["metrics"]["sharpe_per_trade_unannualized"])

    def test_missing_real_policy_no_store_write(self):
        p=copy.deepcopy(self.packet)
        del p["operator_policy"]["costs"]["fee_entry_bps"]
        reseal(p)
        with self.assertRaises(ResultsStoreError):
            run_factory_h_research(p,self.db)
        self.assertFalse(self.db.exists())

    def test_ledger_reseal_tamper_and_false_ack_denied(self):
        ledger=build_trade_event_ledger(self.packet)
        bad=copy.deepcopy(ledger)
        bad["outcomes"].append({"status":"MODEL_ONLY"})
        bad["sha256"]=digest({k:v for k,v in bad.items()
                              if k!="sha256"})
        with self.assertRaises(ResultsStoreError):
            verify_trade_event_ledger(self.packet,bad)
        with self.assertRaises(ResultsStoreError):
            evaluate_immutable_ledger({**ledger,
              "trading_authority":"LIVE",
              "sha256":digest({k:v for k,v in ledger.items()
                               if k not in ("sha256","trading_authority")}
                              | {"trading_authority":"LIVE"})})

    def test_h_pack_immutable_conflicting_packet_rejected(self):
        migrate_store_v2(self.db)
        run_factory_h_research(self.packet,self.db)
        p=copy.deepcopy(self.packet)
        p["operator_policy"]["costs"]["fee_entry_bps"]="2"
        reseal(p)
        with self.assertRaises(ResultsStoreError):
            run_factory_h_research(p,self.db)

    def test_windows_handles_and_mutated_store_fail_closed(self):
        migrate_store_v2(self.db)
        run_factory_h_research(self.packet,self.db)
        conn=sqlite3.connect(self.db)
        try:
            conn.execute(
                "UPDATE factory_h_research_results_v1 SET document='{}'")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ResultsStoreError):
            run_factory_h_research(self.packet,self.db)
        # No masked WinError 32 on real Windows when removing file.
        self.db.unlink()
        self.assertFalse(self.db.exists())

    def test_holdout_future_no_f5(self):
        p=copy.deepcopy(self.packet)
        p["trial_packet"]["bars"][-1]["open_ms"]+=900000
        reseal(p)
        with self.assertRaises((ResultsStoreError,ValueError)):
            run_factory_h_research(p,self.db)
        self.assertFalse(self.db.exists())


if __name__=="__main__":
    unittest.main()
