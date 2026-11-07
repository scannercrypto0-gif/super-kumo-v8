"""Recovery v2 structural fixtures only, NOT owner E: original execution."""
import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, digest, migrate_store_v2,
)
from research_wp_r0.aql_factory_f_f2_recovery_diagnostic_v1 import (
    RECOVERY_SHA, RECOVERY_RAW_BYTES_SHA, MONTHS,
)
from research_wp_r0.aql_factory_f_f2_recovery_research_v2 import (
    SCHEMA, REPORT, validate_recovery_research_input,
    run_recovery_research_v2,
)
from research_wp_r0.aql_factory_authentic_research_admission import seal
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
    _month_boundaries,
)


# Exact Work235 frozen StrategyDefinition envelopes from 6acbcc7,
# TEST_ONLY fixture identity; not independent strategy/policy approval.
FROZEN_WORK235 = json.loads("{\"test_momentum@v1\":{\"definition\":{\"entry\":{\"left\":{\"field\":\"value\",\"lag\":0,\"name\":\"trend\",\"op\":\"indicator\"},\"op\":\"gt\",\"right\":{\"op\":\"constant\",\"value\":100}},\"exit\":{\"left\":{\"field\":\"value\",\"lag\":1,\"name\":\"trend\",\"op\":\"indicator\"},\"op\":\"lt\",\"right\":{\"op\":\"constant\",\"value\":99}},\"indicators\":[{\"constraints\":{\"period\":{\"max\":20,\"min\":2,\"type\":\"int\"}},\"indicator_id\":\"SMA_v1\",\"name\":\"trend\",\"parameters\":{\"period\":3},\"version\":\"1\"}],\"risk\":{\"entry_ttl_bars\":2,\"holding_bars\":10,\"max_exposure\":1,\"max_leverage\":1,\"stop_fraction\":0.02,\"target_fraction\":0.04,\"unit\":\"ENTRY_NOTIONAL\"},\"schema_version\":\"1\",\"scope\":\"RESEARCH_ONLY\",\"strategy_id\":\"test_momentum\",\"strategy_version\":\"v1\",\"timing\":{\"ambiguity\":\"REJECT\",\"decision\":\"CONFIRMED_CLOSE\",\"entry_execution\":\"NEXT_ELIGIBLE_OPEN\"}},\"digest\":\"5d293f892fd829a9d1c1d2933612bbb4f2d57b4445deefce06436959824cb55b\"},\"test_reversion@v1\":{\"definition\":{\"entry\":{\"left\":{\"field\":\"value\",\"lag\":0,\"name\":\"trend\",\"op\":\"indicator\"},\"op\":\"gt\",\"right\":{\"op\":\"constant\",\"value\":100}},\"exit\":{\"left\":{\"field\":\"value\",\"lag\":1,\"name\":\"trend\",\"op\":\"indicator\"},\"op\":\"lt\",\"right\":{\"op\":\"constant\",\"value\":99}},\"indicators\":[{\"constraints\":{\"period\":{\"max\":20,\"min\":2,\"type\":\"int\"}},\"indicator_id\":\"SMA_v1\",\"name\":\"trend\",\"parameters\":{\"period\":3},\"version\":\"1\"}],\"risk\":{\"entry_ttl_bars\":2,\"holding_bars\":10,\"max_exposure\":1,\"max_leverage\":1,\"stop_fraction\":0.02,\"target_fraction\":0.04,\"unit\":\"ENTRY_NOTIONAL\"},\"schema_version\":\"1\",\"scope\":\"RESEARCH_ONLY\",\"strategy_id\":\"test_reversion\",\"strategy_version\":\"v1\",\"timing\":{\"ambiguity\":\"REJECT\",\"decision\":\"CONFIRMED_CLOSE\",\"entry_execution\":\"NEXT_ELIGIBLE_OPEN\"}},\"digest\":\"d00ccc44f76785ffec3a17786b3f71303e6d6176809f8d96435c6f8e1c570a1e\"}}")


def _body_and_sha(body, key="sha256"):
    return {**body,key:digest(body)}


def _source_receipts():
    receipts=[]
    for i,month in enumerate(MONTHS):
        start,end=_month_boundaries(month)
        body={
            "schema":"aql.core.f2-recovery-readonly-source.v1",
            "month":month,"dataset_id":
                "BINANCE-SPOT-BTCUSDT-15M-"+month+"-F-v1",
            "status":"SOURCE_BACKED_RECOVERY_READBACK_ONLY",
            "recovery_file_sha256":RECOVERY_SHA,
            "recovery_raw_bytes_sha256":RECOVERY_RAW_BYTES_SHA,
            "recovery_internal_canonical_recomputed":False,
            "opaque_recovery_file_pin_verified":True,
            "original_f2_report_sha256":None,
            "source_zip_sha256":f"{i+1:064x}",
            "manifest_integrity_sha256":f"{i+21:064x}",
            "warehouse_receipt_sha256":f"{i+41:064x}",
            "core245_native_query_sha256":f"{i+61:064x}",
            "core253_local_query_sha256":f"{i+81:064x}",
            "dual_map_sha256":f"{i+101:064x}",
            "bar_count":(end-start)//900000,
            "start_ms":start,"end_exclusive_ms":end,
            "decision_cutoff_ms":end+1000,
            "no_write_tree_fingerprint_sha256":f"{i+121:064x}",
            "historical_pit":"NOT_ATTESTED",
            "source_ack_sha256":None,"strategy_approval_sha256":None,
            "factory_consumer_ack_sha256":None,
            "secretary_state":"NOT_ENQUEUED","trading_authority":"NONE",
        }
        receipts.append(_body_and_sha(body,"receipt_sha256"))
    return receipts


def _bars(month):
    first,_=_month_boundaries(month)
    values=[100.0,100.3,100.6,101.0,101.2,101.3,101.5,101.4]
    rows=[]
    for i,price in enumerate(values):
        start=first+i*900000
        open_price=price-0.1
        body={"open_ms":start,"close_ms":start+899999,
              "open":open_price,"high":price+0.1,
              "low":open_price-0.1,"close":price,
              "volume":10.0,"known_at_ms":None,"quality":"FINAL"}
        rows.append({**body,"bar_sha256":seal(body)["artifact_sha256"]})
    return rows


def fixture_packet():
    sources=_source_receipts()
    bymonth={r["month"]:r for r in sources}
    focus="2024-01"
    yearend=_month_boundaries(focus)[1]
    cutoff=_bars(focus)[-1]["close_ms"]+1
    window={"train_end_exclusive_ms":cutoff,
            "embargo_ms":259200000,
            "holdout_start_ms":cutoff+259200000,
            "holdout_end_exclusive_ms":yearend+259200000}
    attempts=[]
    for month in list(MONTHS)+["2024-02","2024-08"]:
        for identity in sorted(FROZEN_WORK235):
            attempts.append({
                "attempt_id":"F2RV2-"+month+"-"+identity,
                "candidate_id":identity,"month":month,
                "state":("DIAGNOSTIC_EVALUATED_NOT_SELECTED"
                         if month in bymonth else "UNKNOWN"),
                "source_receipt_sha256":(
                    bymonth[month]["source_zip_sha256"]
                    if month in bymonth else None),
            })
    def graph(field):
        return digest([[m,bymonth[m][field]] for m in MONTHS])
    body={
        "schema":SCHEMA,
        "experiment_id":"DIAG-F4-RECOVERY-V2-TEST",
        "purpose":"RECOVERY_RESEARCH_ONLY_NOT_F5",
        "local_source_mode":"OWNER_PRIVATE_READ_ONLY",
        "recovery_evidence_file_sha256":RECOVERY_SHA,
        "recovery_raw_bytes_sha256":RECOVERY_RAW_BYTES_SHA,
        "original_f2_report_sha256":None,
        "recovery_core_receipts":sources,
        "scanner_receipt_sha256":"c"*64,
        "strategy_definitions":copy.deepcopy(FROZEN_WORK235),
        "attempts":attempts,
        "source_manifest_sha256":graph("manifest_integrity_sha256"),
        "core_245_query_sha256":graph("core245_native_query_sha256"),
        "core_253_query_sha256":graph("core253_local_query_sha256"),
        "warehouse_graph_sha256":graph("warehouse_receipt_sha256"),
        "dual_map_graph_sha256":graph("dual_map_sha256"),
        "config_sha256":"d"*64,
        "code_sha256":"e"*64,
        "environment_sha256":"f"*64,
        "trial_packet":{
            "schema":"aql.factory.f.recovery-focus.v2",
            "diagnostic_month":focus,
            "strategy_id":"test_momentum@v1",
            "strategy":copy.deepcopy(FROZEN_WORK235["test_momentum@v1"]),
            "source_bytes_sha256":bymonth[focus]["source_zip_sha256"],
            "source_manifest_sha256":bymonth[focus]["manifest_integrity_sha256"],
            "dataset_id":bymonth[focus]["dataset_id"],
            "dataset_version":1,
            "availability":"RETROSPECTIVE_NON_PIT",
            "market":"SPOT","width_ms":900000,"bars":_bars(focus),
        },
        "operator_policy":{
            "schema":"aql.factory.f.owner-authorized-recovery-policy.v2",
            "owner_operator_authorized":True,
            "costs":{
                "fee_entry_bps":"1","fee_exit_bps":"1",
                "spread_entry_bps":"1","spread_exit_bps":"1",
                "slippage_entry_bps":"1","slippage_exit_bps":"1",
                "funding_bps_per_bar":"0",
            },
            "research_window":window,
            "direction":"LONG","ambiguity_policy":"UNKNOWN_ON_INTRABAR_TOUCH",
            "focus_month":focus,"focus_strategy_id":"test_momentum@v1",
        },
        "source_coverage":{
            "new_admitted_months":10,"new_admitted_bars":29376,
            "retained_inventory_months":["2024-02","2024-08"],
            "retained_inventory_status":"INVENTORY_ONLY_NOT_READBACK",
            "historical_pit":"NOT_ATTESTED",
            "source_rights_assurance":"LOCAL_OPERATOR_DECLARED_NOT_INDEPENDENT",
        },
        "historical_pit":"NOT_ATTESTED","holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE",
    }
    return _body_and_sha(body)


def reseal(packet):
    packet["sha256"]=digest({k:v for k,v in packet.items() if k!="sha256"})


class FactoryRecoveryResearchV2(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db=Path(tmp.name)/"recovery-v2.sqlite"

    def test_true_20_plus_4_with_no_53_or_inventory_hash(self):
        packet=fixture_packet()
        definitions, parents=validate_recovery_research_input(packet)
        self.assertEqual(set(definitions),set(FROZEN_WORK235))
        self.assertEqual(len(parents),10)
        self.assertEqual(len(packet["attempts"]),24)
        self.assertEqual(sum(x["source_receipt_sha256"] is None
                             for x in packet["attempts"]),4)
        self.assertNotIn("trials",packet["trial_packet"])
        self.assertFalse(self.db.exists())

    def test_immutable_sqlite_v2_first_and_restart_replay(self):
        packet=fixture_packet()
        self.assertEqual(migrate_store_v2(self.db)["status"],"UPGRADED_V2")
        first=run_recovery_research_v2(packet,self.db)
        second=run_recovery_research_v2(packet,self.db)
        self.assertEqual((first["store_status"],second["store_status"]),
                         ("STORED_IMMUTABLE","REPLAY_IDENTICAL"))
        self.assertEqual(first["attempt_count"],second["attempt_count"])
        self.assertEqual(first["attempt_count"],24)
        self.assertEqual(first["feb_aug_inventory_unknown"],4)
        self.assertEqual(first["diagnostic_evaluated"],20)
        for key in ("lab_sha256","experiment_sha256","result_sha256"):
            self.assertEqual(first[key],second[key])
        for row in (first,second):
            self.assertEqual(digest({k:v for k,v in row.items()
                                     if k!="receipt_sha256"}),
                             row["receipt_sha256"])
            self.assertEqual(row["trading_authority"],"NONE")
            self.assertIsNone(row["original_f2_report_sha256"])
            self.assertFalse(row["selected"])
        self.assertNotEqual(first["receipt_sha256"],second["receipt_sha256"])
        with sqlite3.connect(self.db) as con:
            doc=json.loads(con.execute(
                "SELECT document FROM recovery_research_v2").fetchone()[0])
        self.assertEqual(sum(x["source_receipt_sha256"] is None
                             for x in doc["attempts"]),4)

    def test_forged_or_missing_inventories_and_53_fake_trials_rejected(self):
        for mutation in ("feb_sha","feb_state","missing","duplicate",
                         "missing_core_month","tampered_core_receipt",
                         "mutated_frozen_strategy",
                         "wrong_month","fifty_three","tampered_parent",
                         "f5_escalation","selected","policy_cost",
                         "future","unclosed","missing_cost",
                         "unapproved_policy","policy_focus_swap","bad_raw_pin"):
            with self.subTest(mutation=mutation):
                p=fixture_packet()
                if mutation=="feb_sha":
                    next(x for x in p["attempts"] if x["month"]=="2024-02")[
                        "source_receipt_sha256"]="a"*64
                elif mutation=="feb_state":
                    next(x for x in p["attempts"] if x["month"]=="2024-02")[
                        "state"]="DIAGNOSTIC_EVALUATED_NOT_SELECTED"
                elif mutation=="missing":
                    p["attempts"].pop()
                elif mutation=="duplicate":
                    p["attempts"][0]["attempt_id"]=p["attempts"][1]["attempt_id"]
                elif mutation=="wrong_month":
                    p["attempts"][0]["month"]="2024-02"
                elif mutation=="missing_core_month":
                    p["recovery_core_receipts"].pop()
                elif mutation=="tampered_core_receipt":
                    p["recovery_core_receipts"][0]["source_zip_sha256"]="f"*64
                elif mutation=="mutated_frozen_strategy":
                    raw=p["strategy_definitions"]["test_momentum@v1"]
                    raw["definition"]["entry"]["right"]["value"]=111
                    d=StrategyDefinition(raw["definition"],
                                         registry=IndicatorRegistryV2())
                    raw["digest"]=d.digest
                    p["trial_packet"]["strategy"]=raw
                elif mutation=="fifty_three":
                    p["trial_packet"]["trials"]=[{}]*53
                elif mutation=="tampered_parent":
                    p["warehouse_graph_sha256"]="a"*64
                elif mutation=="f5_escalation":
                    p["factory_consumer_ack_sha256"]="a"*64
                elif mutation=="selected":
                    p["attempts"][0]["state"]="SELECTED"
                elif mutation=="policy_cost":
                    p["operator_policy"]["costs"]["fee_entry_bps"]="-5"
                elif mutation=="future":
                    p["trial_packet"]["bars"][-1]["close_ms"]+=900000
                    b=p["trial_packet"]["bars"][-1]
                    b["bar_sha256"]=seal({k:v for k,v in b.items()
                                          if k!="bar_sha256"})["artifact_sha256"]
                elif mutation=="unclosed":
                    p["trial_packet"]["bars"][-1]["quality"]="OPEN"
                    b=p["trial_packet"]["bars"][-1]
                    b["bar_sha256"]=seal({k:v for k,v in b.items()
                                          if k!="bar_sha256"})["artifact_sha256"]
                elif mutation=="missing_cost":
                    del p["operator_policy"]["costs"]["spread_exit_bps"]
                elif mutation=="unapproved_policy":
                    p["operator_policy"]["owner_operator_authorized"]=False
                elif mutation=="policy_focus_swap":
                    p["operator_policy"]["focus_month"]="2024-03"
                elif mutation=="bad_raw_pin":
                    p["recovery_raw_bytes_sha256"]="f"*64
                reseal(p)
                with self.assertRaises((ResultsStoreError,ValueError,KeyError)):
                    run_recovery_research_v2(p,self.db)
                self.assertFalse(self.db.exists())

    def test_missing_explicit_policy_has_field_only_private_wait(self):
        p=fixture_packet()
        del p["operator_policy"]["costs"]["fee_exit_bps"]
        reseal(p)
        with self.assertRaisesRegex(ResultsStoreError,
                                    "PRIVATE_WAIT_MISSING_FIELDS:.*fee_exit_bps"):
            run_recovery_research_v2(p,self.db)
        self.assertFalse(self.db.exists())

    def test_windows_sqlite_native_first_replay_and_tamper_cleanup(self):
        """Close all native handles before deleting SQLite on Windows.

        Exercises first registration, identical replay, and a tampered-record
        failure in two separate temporary folders with deterministic cleanup.
        No ignore_errors or suppressed PermissionError: NTFS must delete the
        SQLite files with no live Factory readback handle.
        """
        with tempfile.TemporaryDirectory() as location:
            db=Path(location)/"windows-native-replay.sqlite"
            packet=fixture_packet()
            self.assertEqual(migrate_store_v2(db)["status"],"UPGRADED_V2")
            first=run_recovery_research_v2(packet,db)
            replay=run_recovery_research_v2(packet,db)
            self.assertEqual(first["store_status"],"STORED_IMMUTABLE")
            self.assertEqual(replay["store_status"],"REPLAY_IDENTICAL")
            for key in ("lab_sha256","experiment_sha256","result_sha256"):
                self.assertEqual(first[key],replay[key])
            self.assertNotEqual(first["receipt_sha256"],
                                replay["receipt_sha256"])
            # Native Windows file delete while test objects are still alive.
            db.unlink()
            self.assertFalse(db.exists())
        with tempfile.TemporaryDirectory() as location:
            db=Path(location)/"windows-native-tamper.sqlite"
            packet=fixture_packet()
            migrate_store_v2(db)
            run_recovery_research_v2(packet,db)
            with sqlite3.connect(db) as con:
                con.execute(
                    "UPDATE recovery_research_v2 SET document='{}'")
            with self.assertRaises(ResultsStoreError):
                run_recovery_research_v2(packet,db)
            db.unlink()
            self.assertFalse(db.exists())

    def test_conflicting_replay_or_sqlite_tamper_fails_closed(self):
        p=fixture_packet()
        migrate_store_v2(self.db)
        run_recovery_research_v2(p,self.db)
        changed=copy.deepcopy(p)
        changed["operator_policy"]["costs"]["fee_entry_bps"]="2"
        reseal(changed)
        with self.assertRaises(ResultsStoreError):
            run_recovery_research_v2(changed,self.db)
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE recovery_research_v2 SET document='{}'")
        with self.assertRaises(ResultsStoreError):
            run_recovery_research_v2(p,self.db)


if __name__ == "__main__":
    unittest.main()
