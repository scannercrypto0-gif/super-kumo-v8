"""Factory #254 contract test: actual existing Factory APIs; all upstream
TEST_ONLY/native Core objects are explicitly schema-shaped synthetic fixtures.
"""
import copy
import importlib.util
import tempfile
import os
import sys
from pathlib import Path
import unittest

from research_wp_r0.aql_factory_authentic_research_admission import _digest, seal
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
    consume_core_secretary_route,
)
from research_wp_r0.strategy_definition import StrategyDefinition, digest as research_digest
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
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

    def test_fifty_three_distinct_strategy_definitions_to_one_lab(self):
        # One consolidated TEST_ONLY full candidate-census path. This reuses
        # the actual Factory #246 rule evaluator 53 times only on synthetic
        # bars; no accepted private historical results are rerun.
        a,p,plan=core_fixture()
        source=consume_core_warehouse_query(a,p,core_assessment(a,p))
        definitions=[]
        for i in range(53):
            spec=copy.deepcopy(plan["strategy"]["definition"])
            spec["strategy_id"]="synthetic-lab-%02d" % i
            definitions.append(StrategyDefinition(
                spec, registry=IndicatorRegistryV2()).to_dict())
            plan["trials"][i]["candidate_digest"]=definitions[-1]["digest"]
        comp=comparison_packet()
        comp["source_pins"]={
            "archive_sha256":a["source_bytes_sha256"],
            "member_sha256":a["native_csv_member_sha256"],
            "checksum_sha256":a["native_checksum_file_sha256"],
            "core_price_query_sha256":p["price_query_sha256"],
        }
        comparison=assess_opportunity_comparison(comp)
        ledger=[
            {"attempt_id":t["attempt_id"],"candidate_digest":t["candidate_digest"],
             "family_id":"F%03d" % (i % 7+1),"state":"PROPOSED"}
            for i,t in enumerate(plan["trials"])]
        ports=[]
        for i in range(53):
            owned=copy.deepcopy(plan)
            owned.pop("artifact_sha256", None)
            owned["strategy"]=definitions[i]
            owned["selected_attempt_id"]="attempt-%02d" % i
            ports.append(from_core_original_price_query(a,p,seal(owned)))
        x=build_lab_experiment_ledger(source,comparison,ledger,ports)
        self.assertEqual(x["reported_attempts"],53)
        self.assertEqual(x["not_evaluated_attempts"],0)
        self.assertEqual(len({e["factory_port_sha256"]
                              for e in x["ledger"]}),53)
        self.assertEqual(x["trial_denominator"],53)
        self.assertIsNone(x["base_shadow_results"])
        self.assertEqual(x["scientific_result"],"INSUFFICIENT_EVIDENCE")
        self.assertEqual(x["trial_ledger_sha256"],_digest(ledger))
        self.assertEqual(x,build_lab_experiment_ledger(
            source,comparison,ledger,ports))

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

    def test_actual_core253_warehouse_and_secretary_pinned_offline_flow(self):
        # Core #253 is checked out at exact unmerged SHA by this single CI.
        # All source bytes here are *synthetic*, never Work-private originals.
        root=os.environ.get("AQL_CORE253_PATH")
        if not root:
            self.skipTest("read-only pinned Core #253 checkout unavailable")
        root=Path(root).resolve()
        raw211_root=os.environ.get("AQL_RAW211_PATH")
        if not raw211_root:
            self.skipTest("pinned RAW Vault #211 checkout is not supplied")
        raw211_root=Path(raw211_root).resolve()
        self.assertTrue((raw211_root/"tools/raw_vault_offline/vault.py").is_file())
        sys.path.insert(0,str(raw211_root))
        from tools.raw_vault_offline.vault import RawVault
        self.assertTrue((root/"research_wp_r0/aql_core_backbone_local_v1.py").is_file())
        from datetime import datetime, timezone
        # The pinned Core checkout holds the native ZIP fixture utilities.
        # Add only that checkout to fixture imports; production modules are
        # still owned by the separately checked-out Core SHA.
        sys.path.insert(0, str(root/"tests"))
        import research_wp_r0
        research_wp_r0.__path__.insert(0,str(root/"research_wp_r0"))
        from test_aql_archive_custody_bridge_v1 import START, WIDTH, N, spec
        from test_aql_native_binance_zip_v1 import native_source
        from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
        from research_wp_r0.aql_authenticated_historical_admission_v1 import admit_original_bytes
        from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
        from research_wp_r0.aql_core_chronology_universe_evidence_v1 import assess_chronology_universe
        from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
        from research_wp_r0.historical_library import HistoricalLibrary
        from research_wp_r0.aql_core_backbone_local_v1 import (
            admit_local_original,query_local)
        from research_wp_r0.aql_core_secretary_routing_v1 import (
            enqueue_nomination,poll_nomination,acknowledge_nomination,route_trace)
        import hashlib
        import json
        raw,csv_bytes,checks,pin=native_source()
        scope=spec(source_label="native-monthly-zip")
        cutoff=START+N*WIDTH+2000
        with tempfile.TemporaryDirectory(prefix="factory254-core253-") as tmp:
            warehouse_root=Path(tmp)/"warehouse"
            raw_vault=RawVault(Path(tmp)/"raw-original-vault")
            warehouse=admit_local_original(
                warehouse_root,raw,checks,pin,scope,
                decision_cutoff_ms=cutoff,vault=raw_vault)
            self.assertEqual(warehouse["status"],
                             "OFFLINE_LOCAL_WAREHOUSE_COMMITTED")
            self.assertEqual(warehouse["vault"]["vault"],
                             "EXISTING_PINNED_RAW_VAULT")
            self.assertEqual(raw_vault.read(warehouse["source_zip_sha256"]),raw)
            self.assertEqual(raw_vault.recovery_scan()["status"],"CLEAN")
            self.assertEqual(len(raw_vault.manifest_entries()),1)
            query=query_local(
                warehouse_root,scope["dataset_id"],scope["version"],
                scope["start_ms"],scope["end_exclusive_ms"],cutoff,
                required_source_sha256=warehouse["source_zip_sha256"],
                require_complete=True)
            # Reuse exact Core #245 admitted source envelopes; do not
            # invent a source or reinterpret native ZIP as scanner JSON.
            lib=HistoricalLibrary()
            stager=OfflineBridgeStager(Path(tmp)/"other-core-stage")
            admission=admit_original_bytes(
                raw,pin,scope,stager=stager,library=lib,
                decision_cutoff_ms=cutoff,checksum_file_bytes=checks)
            prices=query_price_custody(
                lib,{
                    "schema":REQUEST_SCHEMA,"dataset_id":scope["dataset_id"],
                    "version":scope["version"],
                    "start_ms":scope["start_ms"],
                    "end_exclusive_ms":scope["end_exclusive_ms"],
                    "decision_cutoff_ms":cutoff,"require_complete":False,
                    "confirmed_only":False,
                },expected_source_sha256=admission["source_bytes_sha256"],
                expected_manifest_integrity_sha256=admission["manifest_integrity_sha256"])
            assessment=assess_chronology_universe(
                admission,prices,chronology_evidence=None,universe_evidence=None)
            source=consume_core_warehouse_query(
                admission,prices,assessment,warehouse,query)
            self.assertEqual(source["raw_warehouse_query"],
                             "CONNECTED_PINNED_CORE_253_RAW_WAREHOUSE")
            self.assertEqual(source["core_253_raw_vault"],
                             "EXISTING_PINNED_RAW_VAULT")
            self.assertEqual(source["core_253_warehouse_receipt_sha256"],
                             warehouse["receipt_sha256"])
            self.assertFalse(source["source_eligible_for_historical_pit"])
            self.assertEqual(source["bar_count_available"],N)
            self.assertEqual(source,consume_core_warehouse_query(
                admission,prices,assessment,warehouse,query))
            # The genuine original mode has a different Core classification
            # from the synthetic fixture mode. Shape-only mock in this CI:
            # NOT an authenticated original source or genuine E2E.
            original_contract_mock=copy.deepcopy(warehouse)
            original_contract_mock["test_only"]=False
            original_contract_mock["source_evidence_class"]="RETROSPECTIVE_NOT_PIT"
            original_contract_mock["receipt_sha256"]=_digest({
                k:v for k,v in original_contract_mock.items()
                if k!="receipt_sha256"})
            original_contract_result=consume_core_warehouse_query(
                admission,prices,assessment,original_contract_mock,query)
            self.assertEqual(original_contract_result["historical_pit"],
                             "NOT_ATTESTED") if "historical_pit" in original_contract_result else self.assertFalse(
                                 original_contract_result["source_eligible_for_historical_pit"])
            original_contract_mock["test_only"]=True
            original_contract_mock["receipt_sha256"]=_digest({
                k:v for k,v in original_contract_mock.items()
                if k!="receipt_sha256"})
            with self.assertRaises(UnifiedBackboneError):
                consume_core_warehouse_query(
                    admission,prices,assessment,original_contract_mock,query)
            self.assertEqual(raw_vault.read(warehouse["source_zip_sha256"]),raw)
            self.assertEqual(warehouse,admit_local_original(
                warehouse_root,raw,checks,pin,scope,
                decision_cutoff_ms=cutoff,vault=raw_vault))
            self.assertEqual(len(raw_vault.manifest_entries()),1)
            # Exercise Core's *actual* persistent off-line queue/ACK APIs.
            scan_cutoff=datetime.fromtimestamp(cutoff/1000,timezone.utc).isoformat()
            native={
                "schema_version":"AQL-SCANNER-V1",
                "scanner_id":"FACTORY254_TEST_SCANNER",
                "candidate_id":"BTCUSDT:TEST_ONLY:254",
                "profile_id":"FACTORY254_TEST_PROFILE",
                "market":"BINANCE:SPOT:USDT",
                "cutoff_at":scan_cutoff,
                "availability_class":"RETROSPECTIVE_NON_PIT",
                "stage":"UNKNOWN",
                "source_manifest":{
                    "dataset_id":warehouse["dataset_id"],
                    "dataset_sha":warehouse["source_zip_sha256"],
                    "schema_version":"AQL-SCANNER-V1",
                    "cutoff_at":scan_cutoff,
                    "created_at":scan_cutoff,
                },
                "feature_snapshot":{},
                "reasons":["TEST_ONLY_NO_AUTHENTIC_PIT"],
                "coverage":{"historical_pit":"NOT_ATTESTED"},
                "score":None,"score_status":"NOT_SCORED",
                "publishable":False,"delivery_authorized":False,
            }
            native["digest"]=hashlib.sha256(json.dumps(
                native,sort_keys=True,separators=(",",":"),
                ensure_ascii=False).encode()).hexdigest()
            mid="FACTORY254_TEST_EVENT"
            queued=enqueue_nomination(
                warehouse_root,native,strategy_id="RESEARCH_254",
                strategy_version="v1",warehouse_receipt=warehouse,
                lane="FAST",idempotency_key=mid)
            self.assertEqual(queued,enqueue_nomination(
                warehouse_root,native,strategy_id="RESEARCH_254",
                strategy_version="v1",warehouse_receipt=warehouse,
                lane="FAST",idempotency_key=mid))
            item=poll_nomination(warehouse_root,now_ms=0,lane="FAST")
            self.assertEqual(item["message_id"],mid)
            delivered_hash=research_digest({
                "test_only_consumer":"FACTORY_254",
                "message_id":mid,
                "source_sha256":warehouse["source_zip_sha256"]})
            ack=acknowledge_nomination(
                warehouse_root,message_id=mid,
                payload_sha256=queued["payload_sha256"],
                acknowledgement_sha256=delivered_hash)
            trace=route_trace(warehouse_root,mid)
            route_report=consume_core_secretary_route(
                warehouse,item["envelope"],queued,ack,trace)
            self.assertEqual(route_report["scanner_strategy_decision"],
                             "NOT_PERFORMED")
            self.assertEqual(route_report["paper_orders"],0)
            self.assertEqual(route_report,consume_core_secretary_route(
                warehouse,item["envelope"],queued,ack,trace))
            self.assertIsNone(poll_nomination(warehouse_root,now_ms=10**15))
            # New delta negative suite: source, version, query gap,
            # corrected lineage, ACK and event chain; all resealed before
            # adversarial reconsumption, no false trusted external witness.
            for fault in ("warehouse","query_source","version","missing",
                          "future","ack","trace","strategy","source_domain"):
                with self.subTest(fault=fault):
                    w,q,a,e=copy.deepcopy((warehouse,query,ack,item["envelope"]))
                    t=copy.deepcopy(trace)
                    if fault=="warehouse":
                        w["source_zip_sha256"]="0"*64
                        w["receipt_sha256"]=_digest({
                            k:v for k,v in w.items() if k!="receipt_sha256"})
                    elif fault=="query_source":
                        q["source_bytes_sha256"]="f"*64
                        q["query_sha256"]=_digest({
                            k:v for k,v in q.items() if k!="query_sha256"})
                    elif fault=="version":
                        w["version"]=2
                        w["receipt_sha256"]=_digest({
                            k:v for k,v in w.items() if k!="receipt_sha256"})
                    elif fault=="missing":
                        q["missing_bar_opens"].append(q["bars"][0]["bar_open_ms"])
                        q["query_sha256"]=_digest({
                            k:v for k,v in q.items() if k!="query_sha256"})
                    elif fault=="future":
                        q["bars"][0]["observation_lower_bound_ms"]=cutoff+1
                        q["query_sha256"]=_digest({
                            k:v for k,v in q.items() if k!="query_sha256"})
                    elif fault=="ack":
                        a["acknowledgement_sha256"]="f"*64
                        a["receipt_sha256"]=_digest({
                            k:v for k,v in a.items() if k!="receipt_sha256"})
                    elif fault=="trace":
                        t[-1]["previous_event_sha256"]="f"*64
                    elif fault=="strategy":
                        e["strategy_id"]="OTHER_POLICY"
                        e["payload_sha256"]=_digest({
                            k:v for k,v in e.items() if k!="payload_sha256"})
                    elif fault=="source_domain":
                        e["source_zip_sha256"]="f"*64
                        e["payload_sha256"]=_digest({
                            k:v for k,v in e.items() if k!="payload_sha256"})
                    with self.assertRaises(UnifiedBackboneError):
                        if fault in ("warehouse","query_source","version",
                                     "missing","future"):
                            consume_core_warehouse_query(
                                admission,prices,assessment,w,q)
                        else:
                            consume_core_secretary_route(
                                warehouse,e,queued,a,t)
            self.assertEqual(route_report["source_zip_sha256"],
                             source["source_bytes_sha256"])
            self.assertEqual(route_report["source_manifest_sha256"],
                             source["manifest_integrity_sha256"])
            self.assertEqual(route_report["trading_authority"],"NONE")
            self.assertEqual(route_report["historical_pit"],"NOT_ATTESTED")
            # The isolated Lab remains descriptive; no old 106-report repeat.
            self.assertEqual(source["scanner_secretary_real_distribution"],
                             "NOT_CONNECTED_CORE_253_PENDING")
            # RAW commit is actually tested here; Scanner-to-Work Paper
            # remains separate and has NOT acquired authority from the ACK.
            self.assertEqual(warehouse["status"],"OFFLINE_LOCAL_WAREHOUSE_COMMITTED")

    def test_actual_core253_authorized_intake_unknown_wait_factory_ack(self):
        # Public CI: actual immutable Core/RAW/Scanner code on SYNTHETIC
        # source-format ZIP. This is NOT the private Feb/Aug original bytes.
        core_root=os.environ.get("AQL_CORE253_PATH")
        raw_root=os.environ.get("AQL_RAW211_PATH")
        scanner_root=os.environ.get("AQL_SCANNER227_PATH")
        if not all((core_root,raw_root,scanner_root)):
            self.skipTest("pinned owner source-intake checkouts unavailable")
        import io, zipfile, hashlib, json
        from datetime import datetime,timezone
        import research_wp_r0
        import tools
        research_wp_r0.__path__.insert(
            0,str(Path(core_root).resolve()/"research_wp_r0"))
        tools.__path__ = [str(Path(raw_root).resolve()/"tools"),
                          str(Path(scanner_root).resolve()/"tools"),
                          str(Path(os.environ.get("AQL_WORK235_PATH")).resolve()/"tools"),
                          *list(tools.__path__)]
        from tools.raw_vault_offline.vault import RawVault
        from research_wp_r0.aql_core_authorized_source_transfer_v1 import (
            run_authorized_original_intake)
        from research_wp_r0.aql_core_secretary_routing_v1 import (
            enqueue_nomination,acknowledge_nomination,route_trace)
        start=1706745600000
        width=900000
        member=(f"{start},100,102,99,101,5,{start+width-1},505,10,2,202,0\n").encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("BTCUSDT-15m-2024-02.csv",member)
        raw=out.getvalue()
        zh=hashlib.sha256(raw).hexdigest()
        checks=(zh+"  BTCUSDT-15m-2024-02.zip\n").encode()
        month_id="BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1"
        witness={
            "dataset_id":month_id,"version":1,
            "symbol":"BTCUSDT","interval":"15m",
            "exchange":"BINANCE","market":"SPOT",
            "archive_name":"BTCUSDT-15m-2024-02.zip",
            "csv_member_name":"BTCUSDT-15m-2024-02.csv",
            "archive_sha256":zh,
            "checksum_sha256":hashlib.sha256(checks).hexdigest(),
            "csv_member_sha256":hashlib.sha256(member).hexdigest(),
            "archive_bytes":len(raw),"checksum_bytes":len(checks),
            "start_ms":start,"end_exclusive_ms":start+width,
            "observed_bars":1,
            "capture_observed_at_ms":start+width+10000,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"core"
            vault=RawVault(Path(tmp)/"raw")
            result,warehouse,prices,queued=run_authorized_original_intake(
                root,raw,checks,witness,vault=vault,
                cutoff_ms=start+width+1000,
                strategy_id="RESEARCH_WAIT_ONLY",strategy_version="v1",
                message_id="FACTORY254_OWNER_A_SYNTHETIC_TEST",test_only=True,
            )
            self.assertEqual(result["warehouse_status"],
                             "OFFLINE_LOCAL_WAREHOUSE_COMMITTED")
            self.assertEqual(result["scanner_stage"],"UNKNOWN")
            self.assertEqual(result["secretary_status"],
                             "PENDING_FACTORY_CONSUMER_ACK")
            self.assertEqual(result["factory_lab_paper"],
                             "NOT_CONNECTED_UNTIL_OWNER_FACTORY_RUN")
            self.assertEqual(vault.read(zh),raw)
            self.assertEqual(prices["available_bar_count"],1)
            self.assertEqual(queued["envelope"]["source_zip_sha256"],zh)
            self.assertEqual(queued["envelope"]["strategy_id"],
                             "RESEARCH_WAIT_ONLY")
            queue=enqueue_nomination(
                root,queued["envelope"]["scanner_nomination"],
                strategy_id="RESEARCH_WAIT_ONLY",
                strategy_version="v1",warehouse_receipt=warehouse,
                lane="SLOW",idempotency_key=queued["message_id"])
            self.assertEqual(queue["payload_sha256"],
                             result["secretary_payload_sha256"])
            acknowledgement=_digest({
                "schema":"aql.factory.source-locked-consumer-ack.v1",
                "source_sha256":zh,"payload_sha256":queue["payload_sha256"],
                "message_id":queued["message_id"],
                "authority":"OFFLINE_TEST_ONLY_CONSUMER",
            })
            ack=acknowledge_nomination(
                root,message_id=queued["message_id"],
                payload_sha256=queue["payload_sha256"],
                acknowledgement_sha256=acknowledgement)
            traced=consume_core_secretary_route(
                warehouse,queued["envelope"],queue,ack,
                route_trace(root,queued["message_id"]))
            self.assertEqual(traced["scanner_strategy_decision"],
                             "NOT_PERFORMED")
            self.assertEqual(traced["paper_orders"],0)
            self.assertEqual(traced["source_zip_sha256"],zh)
            self.assertEqual(traced["dataset_id"],month_id)
            self.assertEqual(traced["delivery"],
                             "CORE_253_OFFLINE_OUTBOX_ACKED_CALLER_EVIDENCE")
            altered=copy.deepcopy(queue)
            altered["payload_sha256"]="f"*64
            with self.assertRaises(UnifiedBackboneError):
                consume_core_secretary_route(warehouse,queued["envelope"],
                                            altered,ack,route_trace(
                                                root,queued["message_id"]))

    def test_actual_work228_receipt_store_replay_and_tamper(self):
        # Reuse the existing Work #228 create-only ReceiptStore, not a second
        # Factory journal/persistence implementation.
        source_root=os.environ.get("AQL_WORK228_PATH")
        if not source_root:
            self.skipTest("pinned Work #228 receipt store checkout not provided")
        src=Path(source_root).resolve()/"tools/research_integration_harness/harness.py"
        self.assertTrue(src.is_file())
        spec=importlib.util.spec_from_file_location(
            "_pinned_work228_receipt_store_factory254",src)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        a,p,c,source,comparison,trials,port=lab_inputs()
        lab=build_lab_experiment_ledger(source,comparison,trials,[port])
        with tempfile.TemporaryDirectory(prefix="factory254-receipts-") as temp:
            root=Path(temp)/"objects"
            store=module.ReceiptStore(root)
            first=store.put(lab)
            self.assertEqual(first,store.put(copy.deepcopy(lab)))
            self.assertEqual(module.strict_json((root/(first+".json")).read_bytes()),lab)
            restart=module.ReceiptStore(root)
            self.assertEqual(restart.put(lab),first)
            (root/(first+".json")).write_bytes(b'{"tamper":"yes"}')
            with self.assertRaises(module.BoundaryError):
                restart.put(lab)

    def test_actual_work235_strategy_route_to_main_paper_ledger(self):
        # A secondary checkout is pinned at the exact existing Work #235
        # SHA; the test imports its genuine route and StrategyScreeningSpec
        # without editing that Work-owned code or its accepted test suite.
        root=os.environ.get("AQL_WORK235_PATH")
        if not root:
            self.skipTest("isolated Work #235 checkout not provided")
        root=Path(root).resolve()
        self.assertTrue((root/"tools/strategy_service_offline/routing.py").is_file())
        sys.path.insert(0,str(root))
        try:
            from tools.strategy_service_offline.common import Frozen
            from tools.strategy_service_offline.screening import StrategyScreeningSpec
            from tools.strategy_service_offline.routing import route, TestOnlyStrategySink
            import json
            data=json.loads((root/"tools/strategy_service_offline/fixtures/strategies.json").read_text())
            class TestOnlyJournal:
                def __init__(self):self.data={}
                def get(self,kind,key):return self.data.get((kind,key))
                def put(self,kind,key,obj):
                    old=self.data.get((kind,key))
                    if old is not None and old!=obj:
                        raise ValueError("CONFLICTING_TEST_ONLY_REPLAY")
                    self.data[(kind,key)]=obj
                    return obj
            reports=[]
            for i,raw in enumerate(data):
                spec=StrategyScreeningSpec.restore_spec(raw)
                n,_,_=paper_inputs()
                row=n["payload"]
                row.update(strategy_id=spec.data["strategy_id"],
                           strategy_version=spec.data["strategy_version"],
                           config_digest=spec.data["config_digest"],
                           strategy_definition_digest=spec.data["definition"]["digest"])
                row["attempt_id"]=research_digest({
                    "run":row["run_id"],"strategy":row["config_digest"],
                    "symbol":row["symbol"]})
                nomination=Frozen.build(row).receipt()
                journal=TestOnlyJournal()
                sink=TestOnlyStrategySink(spec,TestOnlyJournal(),lambda _: "ACCEPT",
                                          decision_policy_id="fixture_policy_%d" % i)
                receipt=route(nomination,spec,journal,test_sink=sink).receipt()
                self.assertEqual(
                    receipt,route(nomination,spec,journal,test_sink=sink).receipt())
                sec=freeze({
                    "schema":"aql.factory.secretary-offline-delivery.v1",
                    "mode":"TEST_ONLY","delivery_state":"ACK_TEST_ONLY_ONLY",
                    "delivery_id":receipt["payload"]["delivery_id"],
                    "nomination_sha256":nomination["sha256"],
                    "attempt_id":row["attempt_id"],
                    "strategy_id":row["strategy_id"],
                    "strategy_version":row["strategy_version"],
                    "config_digest":row["config_digest"],
                    "source_raw_sha256":row["source_raw_sha256"],
                    "cutoff_ms":row["cutoff_ms"],
                    "delivered_ms":row["cutoff_ms"]+1000,
                    "real_secretary_ack":None,"trading_authority":"NONE",
                })
                out=build_offline_paper_model_trace(
                    nomination,receipt,sec,simulated_events(sec["delivered_ms"]))
                self.assertEqual(out["strategy_id"],spec.data["strategy_id"])
                self.assertEqual(out["orders_created"],0)
                self.assertEqual(out["modeled_positions"][0]["status"],"closed")
                reports.append(out)
            self.assertEqual(len(reports),2)
            self.assertEqual(len({x["config_digest"] for x in reports}),2)
            self.assertEqual(len({x["artifact_sha256"] for x in reports}),2)
        finally:
            sys.path.remove(str(root))

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
