"""Factory H generic Scanner→Factory→Lab integration, synthetic only.

Actual Scanner #277 code and exact Work235 fixtures are overlaid byte-for-byte
by the focused CI from pinned commit; NEVER owner-private E: evidence.
"""
from __future__ import annotations
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError,digest,migrate_store_v2,
)
from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import (
    SCHEMA,COST_SCHEMA,run_factory_h_generic_research,_verified,_execution,
)
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import StrategyDefinition
from tools.scanner_strategy_f import research_strategy_plugin as scanner
from tools.scanner_strategy_f.test_research_strategy_plugin import (
    synthetic_query,
)
from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES


def _seal(body):
    return {**body,"sha256":digest(body)}


def case_for(index=0, *,missing=None,extra_bps="1"):
    work=json.loads((FIXTURES/"strategies.json").read_text())
    if index in (0,1):
        frozen=work[index]
        definition=frozen["payload"]["definition"]
        plugin=scanner.register_strategy_plugin(
            definition,config_digest=frozen["payload"]["config_digest"],
            source_spec_receipt=frozen)
    else:
        updated=copy.deepcopy(work[0]["payload"]["definition"]["definition"])
        updated["strategy_id"]="h_manual_distinct_test"
        updated["indicators"][0]["parameters"]["period"]=5
        updated["entry"]["right"]["value"]=99
        strategy=StrategyDefinition(updated,registry=IndicatorRegistryV2())
        definition=strategy.to_dict()
        plugin=scanner.register_strategy_plugin(
            definition,config_digest=scanner.manual_config_digest(definition),
            origin="MANUAL")
    query=synthetic_query(n=64,missing_index=missing)
    policy=scanner.research_signal_policy(source_class="TEST_ONLY")
    with patch.object(scanner,"query_local",return_value=query) as read:
        batch=scanner.evaluate_strategy_plugin(
            plugin,query,warehouse_root="/test-only-synthetic-no-warehouse",
            policy=policy)
    if read.call_count!=1:
        raise AssertionError("Scanner did not execute one immutable readback")
    scanner.verify_factory_signal_batch(batch)
    meta=Frozen.restore(plugin).data
    signal=Frozen.restore(batch).data
    costs={
        "fee_entry_bps":extra_bps,"fee_exit_bps":extra_bps,
        "spread_entry_bps":extra_bps,"spread_exit_bps":extra_bps,
        "slippage_entry_bps":extra_bps,"slippage_exit_bps":extra_bps,
        "funding_bps_per_bar":"0",
    }
    cost_policy=_seal({
        "schema":COST_SCHEMA,"costs":costs,"market":"SPOT",
        "direction":"LONG","scenario_class":"SYNTHETIC_TEST_EXPLICIT",
        "owner_operator_authorized":False,
        "fill_semantics":"NEXT_ELIGIBLE_OPEN_UNKNOWN_ON_INTRABAR_TOUCH",
        "holdout":"SEALED_UNOPENED","trading_authority":"NONE",
    })
    packet=_seal({
        "schema":SCHEMA,
        "experiment_id":"RESEARCH-H-GENERIC-SYNTHETIC-"+str(index),
        "scanner_signal_batch":batch,
        "strategy_plugin":plugin,
        "scanner_signal_policy":policy,
        "core_query":query,
        "operator_cost_policy":cost_policy,
        "factory_code_sha256":"e"*64,
        "source_query_sha256":query["query_sha256"],
        "source_bytes_sha256":query["source_bytes_sha256"],
        "manifest_integrity_sha256":query["manifest_integrity_sha256"],
        "strategy_definition_sha256":meta["definition_digest"],
        "strategy_plugin_sha256":plugin["sha256"],
        "config_sha256":meta["config_digest"],
        "scanner_policy_sha256":policy["sha256"],
        "scanner_evaluator_code_sha256":meta["evaluator_code_sha256"],
        "decision_cutoff_ms":query["decision_cutoff_ms"],
        "holdout":"SEALED_UNOPENED",
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
    })
    return packet


def reseal(p):
    p["sha256"]=digest({k:v for k,v in p.items() if k!="sha256"})


class GenericFactoryH(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path=Path(d.name)/"generic.sqlite"

    def test_two_frozen_and_one_truly_distinct_manual_reach_lab_replay(self):
        for index in (0,1,2):
            with self.subTest(strategy=index):
                p=case_for(index)
                self.assertNotIn("attempts",p)
                self.assertNotIn("recovery_core_receipts",p)
                if index==2:
                    self.assertEqual(p["strategy_plugin"]["payload"][
                        "strategy_id"],"h_manual_distinct_test")
                    self.assertNotIn(p["strategy_definition_sha256"],{
                        case_for(0)["strategy_definition_sha256"],
                        case_for(1)["strategy_definition_sha256"],
                    })
                migrate_store_v2(self.path)
                first=run_factory_h_generic_research(p,self.path)
                second=run_factory_h_generic_research(p,self.path)
                self.assertEqual(first["store_status"],"STORED_IMMUTABLE")
                self.assertEqual(second["store_status"],"REPLAY_IDENTICAL")
                self.assertNotEqual(first["receipt_sha256"],
                                    second["receipt_sha256"])
                for k in ("package_sha256","trade_ledger_sha256",
                          "scientific_lab_sha256","secretary_receipt_sha256",
                          "experiment_sha256","result_sha256"):
                    self.assertEqual(first[k],second[k])
                self.assertEqual(first["trading_authority"],"NONE")
                self.assertEqual(first["f5"],"BLOCKED_EXTERNAL_INPUT")
                self.assertEqual(first["economic_class"],
                     "EXPLICIT_DECLARED_COST_SCENARIO_NOT_INDEPENDENTLY_ATTESTED")
                conn=sqlite3.connect(self.path)
                try:
                    doc=json.loads(conn.execute(
                        "SELECT document FROM factory_h_research_results_v1 "
                        "WHERE experiment_id=?",(p["experiment_id"],)
                    ).fetchone()[0])
                finally:
                    conn.close()
                ledger=doc["trade_event_ledger"]
                self.assertEqual(ledger["cohort"]["expected_bars"],64)
                self.assertEqual(ledger["cohort"]["decision_slots"],64)
                self.assertEqual(ledger["cohort"]["missing_bars"],0)
                self.assertEqual(ledger["cohort"]["signal_unknown"],
                                 p["scanner_signal_batch"]["payload"][
                                     "signal_counts"]["UNKNOWN"])
                self.assertEqual(ledger["cohort"]["no_signal_bars"],
                                 p["scanner_signal_batch"]["payload"][
                                     "signal_counts"]["NO_SIGNAL"])
                self.assertEqual(doc["scientific_lab"]["ledger_sha256"],
                                 ledger["sha256"])
                self.assertEqual(doc["secretary_research_receipt"][
                    "strategy_approval_sha256"],None)
                self.assertEqual(doc["secretary_research_receipt"][
                    "source_ack_sha256"],None)
                self.assertFalse(doc["scientific_lab"]["uncertainty"][
                    "holdout_opened"])
                if index==2:
                    self.assertGreaterEqual(ledger["cohort"]["modeled_trades"],1)

    def test_incomplete_query_is_all_unknown_without_fake_fill(self):
        p=case_for(2,missing=4)
        migrate_store_v2(self.path)
        first=run_factory_h_generic_research(p,self.path)
        self.assertEqual(first["store_status"],"STORED_IMMUTABLE")
        conn=sqlite3.connect(self.path)
        try:
            doc=json.loads(conn.execute(
                "SELECT document FROM factory_h_research_results_v1"
            ).fetchone()[0])
        finally:
            conn.close()
        cohort=doc["trade_event_ledger"]["cohort"]
        self.assertEqual(cohort["expected_bars"],64)
        self.assertEqual(cohort["observed_bars"],63)
        self.assertEqual(cohort["missing_bars"],1)
        self.assertEqual(cohort["signal_unknown"],64)
        self.assertEqual(cohort["no_signal_bars"],0)
        self.assertEqual(cohort["modeled_trades"],0)
        self.assertIsNone(doc["scientific_lab"]["metrics"][
            "net_compounded_return"])

    def test_zero_cost_is_diagnostic_not_economic_validation(self):
        p=case_for(2,extra_bps="0")
        migrate_store_v2(self.path)
        result=run_factory_h_generic_research(p,self.path)
        self.assertEqual(result["economic_class"],
                         "DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED")

    def test_missing_cost_and_policy_must_not_create_database(self):
        for key in ("operator_cost_policy","scanner_signal_policy"):
            p=case_for(2)
            p.pop(key)
            reseal(p)
            with self.subTest(missing=key):
                with self.assertRaises((ResultsStoreError,ValueError)):
                    run_factory_h_generic_research(p,self.path)
                self.assertFalse(self.path.exists())
        p=case_for(2)
        del p["operator_cost_policy"]["costs"]["fee_entry_bps"]
        p["operator_cost_policy"]["sha256"]=digest({
            k:v for k,v in p["operator_cost_policy"].items()
            if k!="sha256"})
        reseal(p)
        with self.assertRaises((ResultsStoreError,ValueError)):
            run_factory_h_generic_research(p,self.path)
        self.assertFalse(self.path.exists())

    def test_signal_tamper_duplicate_future_and_forged_ack_denied(self):
        for kind in ("tamper","duplicate","future","forged_ack",
                     "forge_policy","bad_parent"):
            p=case_for(2)
            if kind=="tamper":
                p["scanner_signal_batch"]["payload"]["events"][0][
                    "signal_state"]="ENTRY_SIGNAL"
            elif kind=="duplicate":
                events=p["scanner_signal_batch"]["payload"]["events"]
                events[1]=copy.deepcopy(events[0])
                p["scanner_signal_batch"]["sha256"]=digest(
                    p["scanner_signal_batch"]["payload"])
            elif kind=="future":
                p["core_query"]["bars"][-1]["bar_close_ms"]+=900000
                p["core_query"]["query_sha256"]=digest({
                    k:v for k,v in p["core_query"].items()
                    if k!="query_sha256"})
            elif kind=="forged_ack":
                p["strategy_approval_sha256"]="a"*64
            elif kind=="forge_policy":
                p["operator_cost_policy"]["owner_operator_authorized"]=True
                p["operator_cost_policy"]["sha256"]=digest({
                    k:v for k,v in p["operator_cost_policy"].items()
                    if k!="sha256"})
            elif kind=="bad_parent":
                p["source_query_sha256"]="b"*64
            reseal(p)
            with self.subTest(kind=kind):
                with self.assertRaises((ResultsStoreError,ValueError)):
                    run_factory_h_generic_research(p,self.path)
                self.assertFalse(self.path.exists())

    def test_replay_conflict_mutated_sqlite_and_windows_native_unlink(self):
        p=case_for(2)
        migrate_store_v2(self.path)
        run_factory_h_generic_research(p,self.path)
        modified=copy.deepcopy(p)
        modified["operator_cost_policy"]["costs"]["fee_entry_bps"]="2"
        modified["operator_cost_policy"]["sha256"]=digest({
            k:v for k,v in modified["operator_cost_policy"].items()
            if k!="sha256"})
        reseal(modified)
        with self.assertRaises(ResultsStoreError):
            run_factory_h_generic_research(modified,self.path)
        conn=sqlite3.connect(self.path)
        try:
            conn.execute(
                "UPDATE factory_h_research_results_v1 SET document='{}'")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ResultsStoreError):
            run_factory_h_generic_research(p,self.path)
        self.path.unlink()  # Windows WinError32 must fail loudly if leaked.
        self.assertFalse(self.path.exists())


if __name__=="__main__":
    unittest.main()
