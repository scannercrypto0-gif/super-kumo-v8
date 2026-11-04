"""Factory #254 contract test: actual existing Factory APIs; all upstream
TEST_ONLY/native Core objects are explicitly schema-shaped synthetic fixtures.
"""
import copy
import unittest

from research_wp_r0.aql_factory_authentic_research_admission import _digest
from research_wp_r0.aql_factory_core_price_rule_port import (
    from_core_original_price_query,
)
from research_wp_r0.aql_factory_opportunity_comparison_gate import (
    assess_opportunity_comparison,
)
from research_wp_r0.aql_factory_unified_backbone_v1 import (
    UnifiedBackboneError, freeze, consume_core_warehouse_query,
    build_lab_experiment_ledger, build_offline_paper_model_trace,
    build_unified_offline_e2e, frozen_work_receipt,
)
from research_wp_r0.strategy_definition import digest as research_digest
from test_aql_factory_core_price_rule_port import (
    core_fixture, repin_admission, repin_price,
)
from test_aql_factory_opportunity_comparison_gate import packet as comparison_packet


def core_assessment(a, p):
    return freeze({
        "schema": "aql.core.chronology-universe-assessment.v1",
        "status": "EVIDENCE_INCOMPLETE",
        "dataset_id": a["dataset_id"],
        "version": a["version"],
        "source_bytes_sha256": a["source_bytes_sha256"],
        "manifest_integrity_sha256": a["manifest_integrity_sha256"],
        "admission_sha256": a["manifest_record_sha256"],
        "price_query_sha256": p["price_query_sha256"],
        "decision_cutoff_ms": a["decision_cutoff_ms"],
        "core_bar_coverage": p["coverage"],
        "chronology": {"evidence_state": "CHRONOLOGY_EVIDENCE_NOT_AVAILABLE"},
        "universe": {"evidence_state": "UNIVERSE_EVIDENCE_NOT_AVAILABLE"},
        "historical_pit": "NOT_ATTESTED",
        "independent_venue_issuance": "NOT_ATTESTED",
        "market_universe_completeness": "NOT_ATTESTED",
        "independent_opportunity_denominator": None,
        "factory_scientific_input": "BLOCKED",
        "work_scientific_e2e": "NOT_CONNECTED",
        "holdout": "UNTOUCHED",
        "trading_authority": "NONE",
    }, "assessment_sha256")


def lab_inputs():
    a,p,plan=core_fixture()
    assessment=core_assessment(a,p)
    source=consume_core_warehouse_query(a,p,assessment)
    cmp_plan=comparison_packet()
    cmp_plan["source_pins"]={
        "archive_sha256":a["source_bytes_sha256"],
        "member_sha256":a["native_csv_member_sha256"],
        "checksum_sha256":a["native_checksum_file_sha256"],
        "core_price_query_sha256":p["price_query_sha256"],
    }
    cmp_report=assess_opportunity_comparison(cmp_plan)
    trial_ledger=[
        {"attempt_id": t["attempt_id"], "candidate_digest": t["candidate_digest"],
         "family_id":"F%03d" % (i % 7+1), "state": t["state"]}
        for i,t in enumerate(plan["trials"])
    ]
    port=from_core_original_price_query(a,p,plan)
    return a,p,assessment,source,cmp_report,trial_ledger,port


def paper_inputs(*, decision="ACCEPT", selected=True):
    n={
        "schema":"aql.strategy-nomination.v1",
        "run_id":"1"*64, "strategy_id":"demo_strategy",
        "strategy_version":"v1", "config_digest":"2"*64,
        "strategy_definition_digest":"3"*64,
        "symbol":"BTCUSDT", "market":"SPOT","timeframe":"15m",
        "cutoff_ms":1700000000000, "source_raw_sha256":"a"*64,
        "source_manifest_sha256":"4"*64,"universe_sha256":"5"*64,
        "feature_evidence":{}, "feature_snapshot_sha256":research_digest({}),
        "status":"SELECTED" if selected else "UNKNOWN",
        "reason_codes":[] if selected else ["TEST_ONLY_UNAVAILABLE"],
        "strategy_screening_rank_score":None,
        "research_profile_score":None,
        "evidence_class":"TEST_ONLY","paper_registry_status":"NOT_CONNECTED",
        "trading_authority":"NONE","publishable":False,
        "delivery_authorized":False,
        "strategy_census":{
            "selected":1 if selected else 0,
            "unknown":0 if selected else 1,
            "rejected":0,"unscanned":0,"ineligible":0,"failed":0},
        "denominator":1,
    }
    n["attempt_id"]=research_digest({"run":n["run_id"],
                                     "strategy":n["config_digest"],
                                     "symbol":n["symbol"]})
    nomination={"payload":n,"sha256":research_digest(n)}
    decision_policy="TEST_ONLY_POLICY_1"
    delivery=research_digest({
        "nomination":nomination["sha256"], "strategy":n["config_digest"],
        "consumer_policy":decision_policy,
        "contract":"aql.paper-strategy-handoff.v1"})
    body={
        "schema":"aql.paper-strategy-decision-receipt.v1",
        "delivery_id":delivery,"nomination_sha256":nomination["sha256"],
        "attempt_id":n["attempt_id"],"strategy_id":n["strategy_id"],
        "strategy_version":n["strategy_version"],
        "config_digest":n["config_digest"],"decision":decision,
        "decision_owner":"STRATEGY_TEST_ONLY_CONSUMER",
        "decision_policy_id":decision_policy,
        "paper_intent_interface":(
            None if decision=="WAIT"
            else {"snapshot_id":nomination["sha256"],"intent_id":delivery,
                  "status":"proposed" if decision=="ACCEPT" else "declined"}),
        "consumer_status":"TEST_ONLY_SINK",
        "paper_execution":"NOT_ACTIVATED","trading_authority":"NONE",
    }
    dec={"payload":body,"sha256":research_digest(body)}
    secretary=freeze({
        "schema":"aql.factory.secretary-offline-delivery.v1",
        "mode":"TEST_ONLY","delivery_state":"ACK_TEST_ONLY_ONLY",
        "delivery_id":delivery,"nomination_sha256":nomination["sha256"],
        "attempt_id":n["attempt_id"],"strategy_id":n["strategy_id"],
        "strategy_version":n["strategy_version"],
        "config_digest":n["config_digest"],
        "source_raw_sha256":n["source_raw_sha256"],
        "cutoff_ms":n["cutoff_ms"],"delivered_ms":n["cutoff_ms"]+1000,
        "real_secretary_ack":None,"trading_authority":"NONE",
    })
    return nomination,dec,secretary


def simulated_events(delivered_ms):
    return [
        {"position_id":"P1","event_id":"e1","kind":"opened",
         "event_ms":delivered_ms+1,"received_ms":delivered_ms+1,
         "source":"TEST_ONLY_PAPER_MODEL","price":"100","reason":None},
        {"position_id":"P1","event_id":"e2","kind":"quote",
         "event_ms":delivered_ms+2,"received_ms":delivered_ms+2,
         "source":"TEST_ONLY_PAPER_MODEL","price":"101","reason":None},
        {"position_id":"P1","event_id":"e3","kind":"closed",
         "event_ms":delivered_ms+3,"received_ms":delivered_ms+3,
         "source":"TEST_ONLY_PAPER_MODEL","price":"101",
         "reason":"SIMULATED_TERMINATION_NOT_EXECUTION"},
    ]


class UnifiedBackboneTests(unittest.TestCase):
    def test_actual_factory_core_price_and_lab_receipts(self):
        a,p,assessment,source,comparison,trials,port=lab_inputs()
        x=build_lab_experiment_ledger(source,comparison,trials,[port])
        self.assertEqual(x["reported_attempts"],1)
        self.assertEqual(x["not_evaluated_attempts"],52)
        self.assertEqual(x["trial_denominator"],53)
        self.assertFalse(x["modeled_returns_recomputed"])
        self.assertIsNone(x["base_shadow_results"])
        self.assertEqual(source["raw_warehouse_query"],
                         "NOT_CONNECTED_CORE_253_PENDING")
        self.assertEqual(build_unified_offline_e2e(source,x)["factory_lab_link"],
                         "CONNECTED_READ_ONLY_RECEIPTS")

    def test_core_missing_warehouse_fail_closed(self):
        a,p,assessment,*_=lab_inputs()
        with self.assertRaises(UnifiedBackboneError):
            consume_core_warehouse_query(a,p,assessment,
                                        warehouse_receipt={"signed":True})
        p=copy.deepcopy(p)
        p["missing_bar_opens"]=[99]
        p["coverage"]="PARTIAL"
        p["required_bar_count"]+=1
        repin_price(p)
        with self.assertRaises(UnifiedBackboneError):
            consume_core_warehouse_query(a,p,assessment)

    def test_core_cutoff_and_source_pin_drift(self):
        a,p,assessment,*_=lab_inputs()
        a=copy.deepcopy(a)
        a["decision_cutoff_ms"]+=1
        repin_admission(a)
        with self.assertRaises(UnifiedBackboneError):
            consume_core_warehouse_query(a,p,assessment)
        a,p,assessment,*_=lab_inputs()
        assessment=copy.deepcopy(assessment)
        assessment["historical_pit"]="ATTESTED"
        assessment["assessment_sha256"]=_digest({
            k:v for k,v in assessment.items() if k!="assessment_sha256"})
        with self.assertRaises(UnifiedBackboneError):
            consume_core_warehouse_query(a,p,assessment)

    def test_core_correction_and_holdout_claims_fail_closed(self):
        a,p,assessment,*_=lab_inputs()
        for case in ("parent-version-1","missing-version-2-parent",
                     "false-holdout","false-source","false-science"):
            with self.subTest(case=case):
                aa,pp,cc=copy.deepcopy((a,p,assessment))
                if case=="parent-version-1":
                    aa["correction_parent_source_sha256"]="e"*64
                    repin_admission(aa)
                    cc["admission_sha256"]=aa["manifest_record_sha256"]
                elif case=="missing-version-2-parent":
                    aa["version"]=2
                    pp["version"]=2
                    repin_admission(aa)
                    repin_price(pp)
                    cc.update(version=2,
                              admission_sha256=aa["manifest_record_sha256"],
                              price_query_sha256=pp["price_query_sha256"])
                elif case=="false-holdout":
                    cc["holdout"]="OPENED"
                elif case=="false-source":
                    aa["authenticated_source"]="ATTESTED"
                    repin_admission(aa)
                    cc["admission_sha256"]=aa["manifest_record_sha256"]
                elif case=="false-science":
                    pp["factory_scientific_input"]="ACCEPTED"
                    repin_price(pp)
                    cc["price_query_sha256"]=pp["price_query_sha256"]
                cc["assessment_sha256"]=_digest({
                    k:v for k,v in cc.items() if k!="assessment_sha256"})
                with self.assertRaises(UnifiedBackboneError):
                    consume_core_warehouse_query(aa,pp,cc)

    def test_lab_trial_missing_duplicate_and_cross_source(self):
        a,p,assessment,source,comparison,trials,port=lab_inputs()
        for action in ("missing","duplicate","source","candidate","duplicate-report"):
            with self.subTest(action=action):
                t=copy.deepcopy(trials)
                source0=copy.deepcopy(source)
                p0=copy.deepcopy(port)
                reports=[p0]
                if action=="missing":t.pop()
                if action=="duplicate":t[1]["attempt_id"]=t[0]["attempt_id"]
                if action=="source":
                    p0["core_price_query_sha256"]="0"*64
                    p0["artifact_sha256"]=_digest({
                        k:v for k,v in p0.items() if k!="artifact_sha256"})
                if action=="candidate":
                    t[0]["candidate_digest"]="f"*64
                if action=="duplicate-report":reports.append(copy.deepcopy(p0))
                with self.assertRaises(UnifiedBackboneError):
                    build_lab_experiment_ledger(source0,comparison,t,reports)

    def test_lab_partial_original_with_reports_rejected(self):
        a,p,assessment,source,comparison,trials,port=lab_inputs()
        s=copy.deepcopy(source)
        s["coverage"]="PARTIAL"
        s["artifact_sha256"]=_digest({
            k:v for k,v in s.items() if k!="artifact_sha256"})
        with self.assertRaises(UnifiedBackboneError):
            build_lab_experiment_ledger(s,comparison,trials,[port])

    def test_paper_actual_main_positionledger_contract_and_replay(self):
        n,d,s=paper_inputs()
        events=simulated_events(s["delivered_ms"])
        out=build_offline_paper_model_trace(n,d,s,events)
        self.assertEqual(out,build_offline_paper_model_trace(n,d,s,events))
        self.assertEqual(out["modeled_positions"][0]["status"],"closed")
        self.assertEqual(out["orders_created"],0)
        self.assertIsNone(out["actual_fills"])
        self.assertEqual(out["paper_intent_nontrading"]["status"],"proposed")
        a,p,c,source,comparison,trials,port=lab_inputs()
        lab=build_lab_experiment_ledger(source,comparison,trials,[port])
        e2e=build_unified_offline_e2e(source,lab,out)
        self.assertEqual(e2e["scanner_secretary_link"],
                         "TEST_ONLY_SAME_SOURCE_NOT_AUTHENTIC")
        self.assertEqual(e2e["actual_original_to_raw_warehouse_to_scanner"],
                         "NOT_CONNECTED_CORE_253_PENDING")

    def test_paper_not_selected_cannot_accept_or_position(self):
        n,d,s=paper_inputs(selected=False)
        with self.assertRaises(UnifiedBackboneError):
            build_offline_paper_model_trace(n,d,s)
        n,d,s=paper_inputs(decision="WAIT")
        with self.assertRaises(UnifiedBackboneError):
            build_offline_paper_model_trace(
                n,d,s,simulated_events(s["delivered_ms"]))
        out=build_offline_paper_model_trace(n,d,s,[])
        self.assertEqual(out["decision"],"WAIT")

    def test_paper_reject_remains_intent_only(self):
        n,d,s=paper_inputs(decision="REJECT")
        out=build_offline_paper_model_trace(n,d,s)
        self.assertEqual(out["paper_intent_nontrading"]["status"],"declined")
        self.assertEqual(out["modeled_positions"],[])

    def test_paper_tamper_routing_policy_and_duplicates(self):
        for fault in ("nomination","false_authority","secretary",
                      "policy","time","conflict","source"):
            with self.subTest(fault=fault):
                n,d,s=paper_inputs()
                n,d,s=copy.deepcopy((n,d,s))
                events=simulated_events(s["delivered_ms"])
                if fault=="nomination":n["payload"]["symbol"]="ETHUSDT"
                if fault=="false_authority":
                    n["payload"]["delivery_authorized"]=True
                    n["sha256"]=research_digest(n["payload"])
                if fault=="secretary":
                    s["source_raw_sha256"]="f"*64
                    s["artifact_sha256"]=_digest({
                        k:v for k,v in s.items() if k!="artifact_sha256"})
                if fault=="policy":
                    d["payload"]["decision_policy_id"]="WRONG"
                    d["sha256"]=research_digest(d["payload"])
                if fault=="time":
                    events[0]["event_ms"]=s["delivered_ms"]-2
                if fault=="conflict":
                    events.append({**events[0],"price":"999"})
                if fault=="source":
                    events[0]["source"]="BROKER_REAL_ORDER"
                with self.assertRaises(UnifiedBackboneError):
                    build_offline_paper_model_trace(n,d,s,events)

    def test_real_original_and_synthetic_scan_never_join_implicitly(self):
        a,p,c,source,comparison,trials,port=lab_inputs()
        lab=build_lab_experiment_ledger(source,comparison,trials,[port])
        n,d,s=paper_inputs()
        n["payload"]["source_raw_sha256"]="f"*64
        n["payload"]["attempt_id"]=research_digest({
            "run":n["payload"]["run_id"],
            "strategy":n["payload"]["config_digest"],
            "symbol":n["payload"]["symbol"]})
        n["sha256"]=research_digest(n["payload"])
        d["payload"]["nomination_sha256"]=n["sha256"]
        d["payload"]["paper_intent_interface"]=None
        d["payload"]["decision"]="WAIT"
        d["sha256"]=research_digest(d["payload"])
        # Route identity must be rederived, not fabricated by changing SHAs.
        with self.assertRaises(UnifiedBackboneError):
            build_offline_paper_model_trace(n,d,s)
        e2e=build_unified_offline_e2e(source,lab)
        self.assertEqual(e2e["paper_receipt_sha256"],None)


if __name__=="__main__":
    unittest.main()
