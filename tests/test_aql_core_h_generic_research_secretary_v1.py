"""Core H generic Secretary: real disposable SQLite, NOT mock routes or E:."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    build_generic_research_result_route, route_generic_research_result,
    read_generic_research_result_route,
)
from test_aql_core_h_research_secretary_v1 import (
    factory as old_factory, PARENTS as OLD_PARENTS,
)
from research_wp_r0.aql_core_h_research_secretary_v1 import route_research_result


def seal(d, field="sha256"):
    return {**d,field:digest(d)}


S={k:str(i+1)*64 for i,k in enumerate((
    "source_query_sha256","source_bytes_sha256","manifest_integrity_sha256",
    "strategy_definition_sha256","strategy_plugin_sha256","config_sha256",
    "scanner_policy_sha256","scanner_evaluator_code_sha256",
    "factory_code_sha256"))}
CUTOFF=90000000


def docs(*, n=5, observed=5, unknown=0, experiment="RESEARCH-H-GENERIC-MANUAL"):
    coverage="COMPLETE" if observed==n else ("UNKNOWN" if observed==0 else "PARTIAL")
    if observed<n:
        unknown=n
    counts={"NO_SIGNAL":n-unknown,"UNKNOWN":unknown}
    co={"cohort_class":"GENERIC_SCANNER_H","coverage":coverage,
        "expected_bars":n,"observed_bars":observed,
        "missing_bars":n-observed,"decision_slots":n,
        "focus_bar_count":observed,"signal_unknown":unknown,
        "entry_signals":0,"exit_signals":0,
        "no_signal_bars":n-unknown,"modeled_trades":0,"unknown_trades":0}
    events=[{"bar_open_ms":i*900000,"decision_cutoff_ms":(i+1)*900000,
             "scanner_event_sha256": "9"*64,
             "signal_state":"UNKNOWN" if i<unknown else "NO_SIGNAL",
             "execution_state":"UNKNOWN_SOURCE_GAP_NO_FILLS" if observed<n
             else "NO_MODEL_FILL","source_observed":i<observed}
            for i in range(n)]
    packet=seal({"schema":"aql.factory.h.generic-signal-input.v1",
                 "experiment_id":experiment,**S,
                 "decision_cutoff_ms":CUTOFF,
                 "historical_pit":"NOT_ATTESTED",
                 "holdout":"SEALED_UNOPENED",
                 "trading_authority":"NONE",
                 "source_ack_sha256":None,
                 "strategy_approval_sha256":None,
                 "factory_consumer_ack_sha256":None})
    ledger=seal({"schema":"aql.factory.h.generic-trade-event-ledger.v1",
        "input_sha256":packet["sha256"],
        "source_query_sha256":S["source_query_sha256"],
        "source_bytes_sha256":S["source_bytes_sha256"],
        "strategy_digest":S["strategy_definition_sha256"],
        "scanner_plugin_sha256":S["strategy_plugin_sha256"],
        "scanner_policy_sha256":S["scanner_policy_sha256"],
        "scanner_receipt_sha256":"1"*64,
        "config_sha256":S["config_sha256"],
        "code_sha256":S["factory_code_sha256"],
        "policy_sha256":"2"*64,
        "economic_policy_class":"DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED",
        "cohort":co,"decision_counts":counts,"events":events,"outcomes":[],
        "historical_pit":"NOT_ATTESTED","holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE"})
    lab=seal({"schema":"aql.factory.h.scientific-lab-report.v1",
        "experiment_input_sha256":packet["sha256"],
        "ledger_sha256":ledger["sha256"],
        "strategy_digest":S["strategy_definition_sha256"],
        "config_sha256":S["config_sha256"],
        "code_sha256":S["factory_code_sha256"],
        "scanner_receipt_sha256":"1"*64,
        "policy_sha256":"2"*64,
        "cohort":co,"metrics":{"modeled_trade_count":0,"unknown_outcomes":0},
        "uncertainty":{"economic_claim":"NOT_ATTESTED","holdout_opened":False},
        "economic_class":"DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED",
        "assessment":"DESCRIPTIVE_RESEARCH_ONLY_NO_ALPHA_CLAIM",
        "research_ready_for_review":True,
        "paper":"NOT_ACTIVATED","trading_authority":"NONE"})
    ex="3"*64
    result="4"*64
    report=seal({"schema":"aql.factory.h.generic-execution-report.v1",
        "input_sha256":packet["sha256"],"experiment_sha256":ex,
        "result_sha256":result,"ledger_sha256":ledger["sha256"],
        "lab_sha256":lab["sha256"],"scanner_batch_sha256":"1"*64,
        "source_query_sha256":S["source_query_sha256"],
        "source_bytes_sha256":S["source_bytes_sha256"],
        "strategy_definition_sha256":S["strategy_definition_sha256"],
        "config_sha256":S["config_sha256"],
        "factory_code_sha256":S["factory_code_sha256"],
        "cost_policy_sha256":"2"*64,"decision_cutoff_ms":CUTOFF,
        "economic_class":"DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED",
        "historical_pit":"NOT_ATTESTED","holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE","paper":"NOT_ACTIVATED",
        "f5":"BLOCKED_EXTERNAL_INPUT",
        "source_ack_sha256":None,"strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None})
    proposal=seal({"schema":"aql.factory.h.generic-secretary-review-receipt.v1",
        "state":"RESEARCH_RESULT_READY_FOR_REVIEW_NOT_ACK",
        "experiment_input_sha256":packet["sha256"],
        "source_query_sha256":S["source_query_sha256"],
        "source_bytes_sha256":S["source_bytes_sha256"],
        "manifest_integrity_sha256":S["manifest_integrity_sha256"],
        "strategy_definition_sha256":S["strategy_definition_sha256"],
        "strategy_plugin_sha256":S["strategy_plugin_sha256"],
        "config_sha256":S["config_sha256"],
        "scanner_evaluator_code_sha256":S["scanner_evaluator_code_sha256"],
        "factory_code_sha256":S["factory_code_sha256"],
        "scanner_signal_policy_sha256":S["scanner_policy_sha256"],
        "cost_policy_sha256":"2"*64,"decision_cutoff_ms":CUTOFF,
        "experiment_sha256":ex,"result_sha256":result,
        "ledger_sha256":ledger["sha256"],"lab_sha256":lab["sha256"],
        "uncertainty_sha256":digest(lab["uncertainty"]),
        "source_ack_sha256":None,"strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,"trading_authority":"NONE",
        "paper":"NOT_ACTIVATED","historical_pit":"NOT_ATTESTED",
        "holdout":"SEALED_UNOPENED"})
    package=seal({"schema":"aql.factory.h.generic-immutable-package.v1",
        "experiment_id":experiment,"input_sha256":packet["sha256"],
        "factory_report":report,"trade_event_ledger":ledger,
        "scientific_lab":lab,"secretary_research_receipt":proposal,
        "economic_class":"DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED",
        "holdout":"SEALED_UNOPENED","f5":"BLOCKED_EXTERNAL_INPUT",
        "historical_pit":"NOT_ATTESTED","trading_authority":"NONE"})
    outer=seal({"schema":"aql.factory.h.generic-research-result.v1",
        "experiment_id":experiment,"input_sha256":packet["sha256"],
        "package_sha256":package["sha256"],"factory_report_sha256":report["sha256"],
        "trade_ledger_sha256":ledger["sha256"],
        "scientific_lab_sha256":lab["sha256"],
        "secretary_receipt_sha256":proposal["sha256"],
        "experiment_sha256":ex,"result_sha256":result,
        "scanner_batch_sha256":"1"*64,"cost_policy_sha256":"2"*64,
        "economic_class":"DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED",
        "store_status":"STORED_IMMUTABLE","paper":"NOT_ACTIVATED",
        "f5":"BLOCKED_EXTERNAL_INPUT","holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE"},"receipt_sha256")
    return packet,package,outer


def reseal(doc,field="sha256"):
    doc[field]=digest({k:v for k,v in doc.items() if k!=field})


class GenericResearchSecretarySQLite(unittest.TestCase):
    def test_complete_partial_unknown_and_restart(self):
        with TemporaryDirectory() as temp:
            for i,(n,observed) in enumerate(((5,5),(7,4),(3,0))):
                p,h,r=docs(n=n,observed=observed,
                           experiment=f"RESEARCH-H-GENERIC-{i}")
                first=route_generic_research_result(temp,p,h,r)
                replay=route_generic_research_result(temp,p,h,r)
                reader=read_generic_research_result_route(temp,p["experiment_id"])
                self.assertEqual(first,replay)
                self.assertEqual(first,reader)
                self.assertEqual(first["expected_bar_count"],n)
                self.assertEqual(first["missing_bar_count"],n-observed)
                self.assertEqual(first["unknown_signal_count"],n if observed<n else 0)
                self.assertEqual(first["state"],"WAIT_RESEARCH_REVIEW")
                for k in ("source_ack_sha256","strategy_approval_sha256",
                          "factory_consumer_ack_sha256","research_review_ack_sha256"):
                    self.assertIsNone(first[k])
                self.assertEqual(first["trading_authority"],"NONE")
            c=sqlite3.connect(Path(temp)/"warehouse.sqlite")
            try:
                self.assertEqual(c.execute(
                    "SELECT COUNT(*) FROM h_generic_research_events"
                ).fetchone()[0],3)
                self.assertEqual(c.execute(
                    "SELECT COUNT(*) FROM price_bars").fetchone()[0],0)
            finally:
                c.close()

    def test_replay_store_status_changes_not_identity(self):
        with TemporaryDirectory() as temp:
            p,h,r=docs()
            a=route_generic_research_result(temp,p,h,r)
            r["store_status"]="REPLAY_IDENTICAL"
            reseal(r,"receipt_sha256")
            b=route_generic_research_result(temp,p,h,r)
            self.assertEqual(a,b)

    def test_replay_conflicting_policy_and_ledger_denied(self):
        with TemporaryDirectory() as temp:
            p,h,r=docs()
            route_generic_research_result(temp,p,h,r)
            p2,h2,r2=docs(experiment=p["experiment_id"])
            h2["trade_event_ledger"]["policy_sha256"]="5"*64
            reseal(h2["trade_event_ledger"])
            # No independent trust is minted by the forged reseal.
            with self.assertRaises(ValueError):
                route_generic_research_result(temp,p2,h2,r2)

    def test_negative_tamper_future_counts_and_authority(self):
        for label,change in (
            ("forged_ack",lambda p,h,r:h["secretary_research_receipt"].__setitem__(
                "strategy_approval_sha256","a"*64)),
            ("future",lambda p,h,r:h["trade_event_ledger"]["events"][0].__setitem__(
                "bar_open_ms",CUTOFF)),
            ("ledger_parent",lambda p,h,r:h["trade_event_ledger"].__setitem__(
                "source_query_sha256","0"*64)),
            ("denominator",lambda p,h,r:h["trade_event_ledger"]["cohort"].__setitem__(
                "missing_bars",5)),
            ("lab",lambda p,h,r:h["scientific_lab"].__setitem__(
                "assessment","APPROVED")),
            ("paper",lambda p,h,r:r.__setitem__("paper","ACTIVATED")),
            ("bad_sha",lambda p,h,r:h["factory_report"].__setitem__(
                "lab_sha256","x"*64)),
        ):
            p,h,r=docs()
            change(p,h,r)
            with self.subTest(label=label),self.assertRaises(ValueError):
                build_generic_research_result_route(p,h,r)

    def test_trace_tamper_detected_and_f2_route_survives(self):
        with TemporaryDirectory() as temp:
            p,h,r=docs()
            route_generic_research_result(temp,p,h,r)
            legacy=route_research_result(temp,old_factory(),**OLD_PARENTS)
            self.assertEqual(legacy["state"],"WAIT_RESEARCH_REVIEW")
            c=sqlite3.connect(Path(temp)/"warehouse.sqlite")
            try:
                c.execute("UPDATE h_generic_research_events SET event_sha='0'")
                c.commit()
            finally:
                c.close()
            with self.assertRaisesRegex(ValueError,"GENERIC_EVENT_TAMPER"):
                read_generic_research_result_route(temp,p["experiment_id"])


if __name__=="__main__":
    unittest.main()
