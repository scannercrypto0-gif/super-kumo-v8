"""F-LAB-1/2 actual pinned Scanner H -> Factory H -> Core Secretary -> P2 Lab.

Synthetic source only. No owner E: read, no cash/fills, no private source IO.
Existing Scanner H/Frozen Work235 + Core Secretary overlay staged by CI.
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
    ResultsStoreError,digest,migrate_store_v2)
from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import (
    run_factory_h_generic_research)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
from research_wp_r0.aql_factory_lab_experiment_index_v1 import (
    build_link,prepare_experiment_link,finalize_experiment_link,
    get_experiment_link,list_experiment_links,TABLE_INDEX)
from research_wp_r0.aql_factory_lab_generic_paired_v1 import (
    build_generic_paired_lab,HOUR)
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    build_generic_research_result_route,route_generic_research_result,
    read_generic_research_result_route)
import test_aql_factory_h_generic_signal_adapter_v1 as hfixture
from test_aql_factory_h_generic_signal_adapter_v1 import case_for
from tools.scanner_strategy_f.test_research_strategy_plugin import synthetic_query

HORIZONS=(4,24,72)


class LabWiring(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"existing-factory-v2.sqlite"
        self.secretary=Path(temp.name)/"secretary-existing-root"
        migrate_store_v2(self.path)

    def run_one(self,i,*,missing=None,source=None,cost=None):
        if source is None:
            packet=case_for(i,missing=missing,extra_bps="1" if cost is None else cost)
        else:
            # Change source lineage *before* Scanner evaluates the query.
            # Scanner and Factory then independently check the same receipt.
            self.assertEqual(len(source),64)
            query=synthetic_query(n=64,missing_index=missing)
            query["source_bytes_sha256"]=source
            query["manifest_integrity_sha256"]="d"*64
            query["query_sha256"]=digest({
                k:v for k,v in query.items() if k!="query_sha256"})
            with patch.object(hfixture,"synthetic_query",return_value=query):
                packet=case_for(
                    i,missing=missing,extra_bps="1" if cost is None else cost)
        first=run_factory_h_generic_research(packet,self.path)
        again=run_factory_h_generic_research(packet,self.path)
        self.assertEqual(first["package_sha256"],again["package_sha256"])
        self.assertEqual(again["store_status"],"REPLAY_IDENTICAL")
        con=sqlite3.connect(self.path)
        try:
            row=con.execute(
                f"SELECT document FROM {TABLE} WHERE experiment_id=?",
                (packet["experiment_id"],)).fetchone()
        finally:
            con.close()
        package=json.loads(row[0])
        route=build_generic_research_result_route(packet,package,first)
        link=build_link(packet,package,first,route)
        return packet,package,first,route,link

    def windows(self,packet,package,*,missing_horizon=None):
        events=package["trade_event_ledger"]["events"]
        start=packet["core_query"]["start_ms"]
        train_end=packet["core_query"]["end_exclusive_ms"]
        cost=packet["operator_cost_policy"]["sha256"]
        # Test only: this distinct later research observation clock is outside
        # the Scanner decision cutoff but BEFORE the 72h embargo/holdout.
        asof=train_end+HOUR*72-1  # last 15m bar matures before embargo
        observation=[]
        for index,e in enumerate(events):
            for h in HORIZONS:
                unavailable=(missing_horizon is not None and
                             index==len(events)-1 and h==missing_horizon)
                due=e["bar_open_ms"]+HOUR*h
                status="UNKNOWN" if unavailable else "COMPLETE"
                observed=min(asof,due) if unavailable else due
                observation.append({
                    "bar_open_ms":e["bar_open_ms"],
                    "horizon_hours":h,
                    "availability":status,
                    "availability_reason":(
                        "HORIZON_UNAVAILABLE_NO_FUTURE_IMPUTATION"
                        if unavailable else None),
                    "market_metrics":None if unavailable else {
                        "reference_price":100.0,
                        "observed_high":101.0,
                        "observed_low":99.0,
                    },
                    "observed_at_ms":max(
                        observed,packet["decision_cutoff_ms"]),
                    "source_query_sha256":packet["source_query_sha256"],
                    "source_bytes_sha256":packet["source_bytes_sha256"],
                    "experiment_id":packet["experiment_id"],
                    "strategy_definition_sha256":
                        packet["strategy_definition_sha256"],
                    "cost_policy_sha256":cost,
                })
        return observation,asof

    def test_two_distinct_experiments_and_unknown_source_restart_join(self):
        values=[]
        for i,missing in ((0,None),(2,None),(1,4)):
            packet,package,result,route,link=self.run_one(
                i,missing=missing,
                source="c"*64 if i==2 else None,
                cost="2" if i==2 else None)
            values.append((packet,package,result,route,link))
            prepared=prepare_experiment_link(self.path,link)
            self.assertEqual(prepared["status"],"PREPARED")
            self.assertEqual(prepare_experiment_link(self.path,link)["status"],
                             "PREPARED")
            self.assertEqual(get_experiment_link(self.path,packet[
                "experiment_id"])["status"],"PREPARED")
            self.assertEqual(prepare_experiment_link(self.path,link)[
                "link_sha256"],link["sha256"])
            # Process restart boundary: Core Secretary write happens *later*.
            with self.assertRaises(ValueError):
                finalize_experiment_link(self.path,self.secretary,
                                         packet["experiment_id"])
            saved=route_generic_research_result(
                self.secretary,packet,package,result)
            self.assertEqual(saved["receipt_sha256"],route["receipt_sha256"])
            done=finalize_experiment_link(self.path,self.secretary,
                                         packet["experiment_id"])
            self.assertEqual(done["status"],"VERIFIED_WAIT")
            self.assertEqual(finalize_experiment_link(
                self.path,self.secretary,packet["experiment_id"])["sha256"],
                done["sha256"])
            self.assertEqual(read_generic_research_result_route(
                self.secretary,packet["experiment_id"])["state"],
                "WAIT_RESEARCH_REVIEW")
            self.assertTrue(all(saved[k] is None for k in (
                "source_ack_sha256","strategy_approval_sha256",
                "factory_consumer_ack_sha256","research_review_ack_sha256")))
        discovered=list_experiment_links(
            self.path,secretary_root=self.secretary)
        self.assertEqual(len(discovered),3)
        self.assertEqual(len({x["link_sha256"] for x in discovered}),3)
        self.assertEqual(len({x["link"]["run_sha256"]
                              for x in discovered}),3)
        self.assertTrue(all(x["link"]["decision_attempt_count"]==64
                            and x["link"]["attempt_scope"]==
                              "SCANNER_DECISION_SLOTS_NOT_F2_TRIALS"
                            for x in discovered))
        self.assertEqual(values[2][4]["decision_attempt_count"],64)
        self.assertNotEqual(values[0][4]["decision_attempt_census_sha256"],
                            values[1][4]["decision_attempt_census_sha256"])
        self.assertNotEqual(values[0][4]["strategy_definition_sha256"],
                            values[1][4]["strategy_definition_sha256"])
        self.assertNotEqual(values[0][4]["source_bytes_sha256"],
                            values[1][4]["source_bytes_sha256"])
        self.assertNotEqual(values[0][4]["cost_policy_sha256"],
                            values[1][4]["cost_policy_sha256"])
        self.assertEqual(values[2][4]["missing_bars"],1)
        self.assertEqual(values[2][4]["decision_counts"]["UNKNOWN"],64)
        self.assertEqual(values[2][4]["modeled_trades"],0)
        self.assertEqual(values[2][4]["decision_counts"]["NO_SIGNAL"],0)
        self.assertEqual(values[2][4]["coverage"],"PARTIAL")
        self.assertEqual(values[2][4]["expected_bars"],64)

    def test_existing_E_registry_is_untouched_no_fake_attempts(self):
        packet,package,result,route,link=self.run_one(2)
        prepare_experiment_link(self.path,link)
        route_generic_research_result(self.secretary,packet,package,result)
        finalize_experiment_link(self.path,self.secretary,
                                 packet["experiment_id"])
        con=sqlite3.connect(self.path)
        try:
            exp=con.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
            oldindex=con.execute(
                "SELECT COUNT(*) FROM experiment_index_v2").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(exp,0)
        self.assertEqual(oldindex,0)

    def test_conflict_tamper_and_missing_factory_parent(self):
        packet,package,result,route,link=self.run_one(2)
        prepare_experiment_link(self.path,link)
        wrong=copy.deepcopy(link)
        wrong["cost_policy_sha256"]="c"*64
        wrong["sha256"]=digest({k:v for k,v in wrong.items()
                                if k!="sha256"})
        with self.assertRaises(ResultsStoreError):
            prepare_experiment_link(self.path,wrong)
        with self.assertRaises(ResultsStoreError):
            prepare_experiment_link(self.path,{
                **link,"sha256":"f"*64})
        forged=copy.deepcopy(link)
        forged["decision_attempt_census_sha256"]="a"*64
        forged["sha256"]=digest({k:v for k,v in forged.items()
                                 if k!="sha256"})
        with self.assertRaises(ResultsStoreError):
            prepare_experiment_link(self.path,forged)
        con=sqlite3.connect(self.path)
        try:
            con.execute(
                f"UPDATE {TABLE_INDEX} SET link_json='{{}}' "
                "WHERE experiment_id=?",(packet["experiment_id"],))
            con.commit()
        finally:
            con.close()
        with self.assertRaises(ResultsStoreError):
            get_experiment_link(self.path,packet["experiment_id"])

    def test_actual_generic_decisions_into_existing_paired_lab(self):
        for i in (0,2):
            with self.subTest(strategy=i):
                packet,package,result,route,link=self.run_one(i)
                prepare_experiment_link(self.path,link)
                route_generic_research_result(
                    self.secretary,packet,package,result)
                finalize_experiment_link(
                    self.path,self.secretary,packet["experiment_id"])
                windows,asof=self.windows(
                    packet,package,missing_horizon=72)
                kwargs=dict(
                    store_path=self.path,secretary_root=self.secretary,
                    experiment_id=packet["experiment_id"],
                    packet=packet,package=package,base_result=result,
                    observation_windows=windows,
                    comparison_definition_sha256="d"*64,
                    protocol_sha256="e"*64,
                    evaluation_asof_ms=asof,
                )
                report=build_generic_paired_lab(**kwargs)
                replay=build_generic_paired_lab(**kwargs)
                self.assertEqual(report,replay)
                self.assertEqual(report["trading_authority"],"NONE")
                self.assertEqual(report["paired_disposition_counts"].get(
                    "REJECTED",0),0) # EXIT != REJECTED synthetic opportunity
                self.assertEqual(report["decision_counts"][
                    "NO_SIGNAL"],link["decision_counts"]["NO_SIGNAL"])
                self.assertEqual(report["horizon_coverage"]["72"][
                    "UNKNOWN"],1)
                self.assertEqual(report["horizon_coverage"]["4"][
                    "COMPLETE"],64)
                self.assertEqual(report["observed_outcome_scope"],
                                 "TEST_ONLY_DESCRIPTIVE_NO_ALPHA")
                self.assertEqual(report["secretary_wait_sha256"],
                                 route["receipt_sha256"])
                # The Lab is descriptive and never moves Secretary out of WAIT.
                self.assertEqual(read_generic_research_result_route(
                    self.secretary,packet["experiment_id"])["state"],
                    "WAIT_RESEARCH_REVIEW")

    def test_source_gap_produces_unknown_paired_outcomes_not_fake_data(self):
        packet,package,result,route,link=self.run_one(1,missing=4)
        prepare_experiment_link(self.path,link)
        route_generic_research_result(self.secretary,packet,package,result)
        finalize_experiment_link(self.path,self.secretary,packet["experiment_id"])
        windows,asof=self.windows(packet,package)
        # For an incomplete Core253 source the Factory Generic H cohort is
        # fully UNKNOWN; the paired evaluator must never report COMPLETE.
        with self.assertRaisesRegex(
                ResultsStoreError,"INCOMPLETE_SOURCE_NO_POSITIVE_OUTCOME"):
            build_generic_paired_lab(
                store_path=self.path,secretary_root=self.secretary,
                experiment_id=packet["experiment_id"],packet=packet,
                package=package,base_result=result,
                observation_windows=windows,
                comparison_definition_sha256="d"*64,
                protocol_sha256="e"*64,evaluation_asof_ms=asof)
        for w in windows:
            w["availability"]="UNKNOWN"
            w["availability_reason"]="SOURCE_GAP_NO_OUTCOME_ATTESTATION"
            w["market_metrics"]=None
        report=build_generic_paired_lab(
            store_path=self.path,secretary_root=self.secretary,
            experiment_id=packet["experiment_id"],packet=packet,
            package=package,base_result=result,
            observation_windows=windows,
            comparison_definition_sha256="d"*64,
            protocol_sha256="e"*64,evaluation_asof_ms=asof)
        self.assertEqual(report["decision_counts"]["UNKNOWN"],64)
        self.assertEqual(report["horizon_coverage"]["4"]["UNKNOWN"],64)
        self.assertEqual(report["horizon_coverage"]["72"]["UNKNOWN"],64)
        self.assertEqual(report["paired_disposition_counts"].get(
            "TRIGGERED",0),0)
        self.assertEqual(report["trading_authority"],"NONE")

    def test_future_source_cost_identity_and_missing_outcome_refused(self):
        packet,package,result,route,link=self.run_one(2)
        prepare_experiment_link(self.path,link)
        route_generic_research_result(self.secretary,packet,package,result)
        finalize_experiment_link(self.path,self.secretary,
                                 packet["experiment_id"])
        windows,asof=self.windows(packet,package,missing_horizon=72)
        base=dict(store_path=self.path,secretary_root=self.secretary,
                  experiment_id=packet["experiment_id"],
                  packet=packet,package=package,base_result=result,
                  observation_windows=windows,
                  comparison_definition_sha256="d"*64,
                  protocol_sha256="e"*64,
                  evaluation_asof_ms=asof)
        cases=[]
        omitted=copy.deepcopy(windows)[:-1]
        cases.append(("missing",omitted,base))
        badfuture=copy.deepcopy(windows)
        badfuture[0]["observed_at_ms"]=asof+1
        cases.append(("future",badfuture,base))
        badsha=copy.deepcopy(windows)
        badsha[1]["source_query_sha256"]="f"*64
        cases.append(("source",badsha,base))
        badfee=copy.deepcopy(windows)
        badfee[1]["cost_policy_sha256"]="f"*64
        cases.append(("cost",badfee,base))
        badstrat=copy.deepcopy(windows)
        badstrat[1]["strategy_definition_sha256"]="f"*64
        cases.append(("strategy",badstrat,base))
        for label,window,parameters in cases:
            with self.subTest(label=label):
                with self.assertRaises(ResultsStoreError):
                    build_generic_paired_lab(
                        **{**parameters,"observation_windows":window})
        self.assertEqual(read_generic_research_result_route(
            self.secretary,packet["experiment_id"])["state"],
            "WAIT_RESEARCH_REVIEW")


if __name__=="__main__":
    unittest.main()
