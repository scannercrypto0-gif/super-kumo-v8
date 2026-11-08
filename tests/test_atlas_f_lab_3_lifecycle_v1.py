"""F-LAB-3 unmocked Factory H/Scanner/Scientific Lab/Secretary lifecycle.

The only patching is Factory's *existing* synthetic source-query fixture,
never Factory, Lab, index or Secretary production APIs.
"""
from __future__ import annotations
import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest,migrate_store_v2)
from research_wp_r0.aql_factory_lab_experiment_index_v1 import (
    get_experiment_link,list_experiment_links)
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    read_generic_research_result_route)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
from tools.atlas_f_lab_3_lifecycle_v1 import (
    LifecycleStop,run_synthetic,run_paired,verified,identity)
import test_aql_factory_lab_generic_wiring_v1 as factory_fixture

class Lifecycle(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.store=self.root/"factory-existing-v2.sqlite"
        self.secretary=self.root/"secretary-existing"
        self.checkpoint=self.root/"integration-checkpoints"
        self.checkpoint.mkdir()
        migrate_store_v2(self.store)
        self.factory=factory_fixture.LabWiring("runTest")
        # Reuse real Factory test's actual Scanner H case generator and source
        # query. Its helper has its own store, so rebind to our same store.
        self.factory.path=self.store
        self.factory.secretary=self.secretary

    def packet(self,i,*,missing=None,source=None,cost=None):
        # Actual Scanner & Work235 unmocked; only synthetic query data.
        return self.factory.run_one(i,missing=missing,source=source,cost=cost)[0]

    def drive(self,packet,**kwargs):
        return run_synthetic(
            packet=packet,store_path=self.store,
            secretary_root=self.secretary,checkpoint_root=self.checkpoint,
            **kwargs)

    def test_two_distinct_real_module_replay_and_restart(self):
        done=[]
        for index,source,cost in ((0,None,None),(2,"c"*64,"2")):
            packet=self.packet(index,source=source,cost=cost)
            with self.assertRaisesRegex(LifecycleStop,"SIMULATED_CRASH_AT_SCANNER_VERIFIED"):
                self.drive(packet,stop_after="SCANNER_VERIFIED")
            with self.assertRaisesRegex(LifecycleStop,"SIMULATED_CRASH_AT_LAB_EVALUATED"):
                self.drive(packet,stop_after="LAB_EVALUATED")
            receipt=self.drive(packet)
            self.assertEqual(receipt["state"],"SECRETARY_WAIT")
            self.assertEqual(receipt,self.drive(packet))
            self.assertEqual(verified(receipt)["sha256"],receipt["sha256"])
            ref=get_experiment_link(
                self.store,packet["experiment_id"],
                secretary_root=self.secretary)
            self.assertEqual(ref["status"],"VERIFIED_WAIT")
            self.assertEqual(ref["link"]["sha256"],
                             receipt["receipts"]["factory_index_sha256"])
            secretary=read_generic_research_result_route(
                self.secretary,packet["experiment_id"])
            self.assertEqual(secretary["state"],"WAIT_RESEARCH_REVIEW")
            self.assertEqual(secretary["receipt_sha256"],
                             receipt["receipts"]["secretary_sha256"])
            for ack in ("source_ack_sha256","strategy_approval_sha256",
                        "factory_consumer_ack_sha256","research_review_ack_sha256"):
                self.assertIsNone(secretary[ack])
            done.append((packet,receipt))
        self.assertNotEqual(done[0][1]["run_sha256"],done[1][1]["run_sha256"])
        self.assertEqual(len(list_experiment_links(
            self.store,secretary_root=self.secretary)),2)
        with closing(sqlite3.connect(self.store)) as con:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM experiments").fetchone()[0],0)

    def test_source_partial_unknown_and_missing_outcome_not_promoted(self):
        packet=self.packet(1,missing=4)
        receipt=self.drive(packet)
        self.assertEqual(receipt["state"],"SECRETARY_WAIT")
        link=get_experiment_link(self.store,packet["experiment_id"],
                                 secretary_root=self.secretary)["link"]
        self.assertEqual(link["coverage"],"PARTIAL")
        self.assertEqual(link["decision_counts"]["UNKNOWN"],64)
        self.assertEqual(link["modeled_trades"],0)
        with sqlite3.connect(self.store) as con:
            row=con.execute(f"SELECT document FROM {TABLE} WHERE experiment_id=?",
                            (packet["experiment_id"],)).fetchone()
        package=json.loads(row[0])
        windows,asof=self.factory.windows(packet,package,missing_horizon=72)
        # Source partial gates remain the responsibility of Factory F-LAB-2.
        with self.assertRaisesRegex(Exception,
                                   "INCOMPLETE_SOURCE_NO_POSITIVE_OUTCOME"):
            self.run_paired(packet,package,windows,asof)

    def run_paired(self,packet,package,windows,asof):
        # A real immutable Factory result on disk is used in the paired seam.
        from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import (
            run_factory_h_generic_research)
        result=run_factory_h_generic_research(packet,self.store)
        return run_paired(
            packet=packet,package=package,result=result,
            store_path=self.store,secretary_root=self.secretary,
            checkpoint_root=self.checkpoint,observation_windows=windows,
            comparison_definition_sha256="d"*64,protocol_sha256="e"*64,
            evaluation_asof_ms=asof)

    def test_existing_paired_bridge_real_unmodified_and_missing_72h(self):
        packet=self.packet(2)
        self.drive(packet)
        with sqlite3.connect(self.store) as con:
            package=json.loads(con.execute(
                f"SELECT document FROM {TABLE} WHERE experiment_id=?",
                (packet["experiment_id"],)).fetchone()[0])
        windows,asof=self.factory.windows(packet,package,missing_horizon=72)
        paired=self.run_paired(packet,package,windows,asof)
        self.assertEqual(paired,self.run_paired(packet,package,windows,asof))
        self.assertEqual(paired["horizon_coverage"]["72"]["UNKNOWN"],1)
        self.assertEqual(paired["horizon_coverage"]["4"]["COMPLETE"],64)
        self.assertEqual(paired["trading_authority"],"NONE")
        self.assertEqual(read_generic_research_result_route(
            self.secretary,packet["experiment_id"])["state"],
            "WAIT_RESEARCH_REVIEW")

    def test_same_id_different_strategy_or_source_refused(self):
        packet=self.packet(0)
        self.drive(packet)
        other=dict(packet)
        other["strategy_definition_sha256"]="f"*64
        other["sha256"]=digest({k:v for k,v in other.items() if k!="sha256"})
        with self.assertRaises(LifecycleStop):
            self.drive(other)
        self.assertEqual(self.drive(packet)["state"],"SECRETARY_WAIT")

    def test_checkpoint_bytes_tamper_refused_and_no_hidden_rerun(self):
        packet=self.packet(0)
        self.drive(packet)
        checkpoint=self.checkpoint/(packet["experiment_id"]+".json")
        original=json.loads(checkpoint.read_text())
        forged=dict(original)
        forged["state"]="PLANNED"
        checkpoint.write_text(json.dumps(forged))
        with self.assertRaisesRegex(LifecycleStop,"CHECKPOINT_TAMPER"):
            self.drive(packet)

    def test_checkpoint_original_source_overlap_refused(self):
        packet=self.packet(0)
        with self.assertRaisesRegex(LifecycleStop,"CHECKPOINT_OUTPUT_OVERLAP"):
            run_synthetic(packet=packet,store_path=self.store,
                          secretary_root=self.secretary,
                          checkpoint_root=self.root)

    def test_crash_pending_conflict_is_fail_closed(self):
        packet=self.packet(0)
        pending=self.checkpoint/(packet["experiment_id"]+".pending")
        pending.write_text('{"forged": true}')
        with self.assertRaisesRegex(LifecycleStop,"CHECKPOINT_TAMPER"):
            self.drive(packet)
        self.assertFalse((self.checkpoint/(packet["experiment_id"]+".json")).exists())

    def test_unsealed_query_or_pit_claim_refused(self):
        packet=self.packet(0)
        forged=dict(packet)
        forged["historical_pit"]="ATTESTED"
        forged["sha256"]=digest({k:v for k,v in forged.items() if k!="sha256"})
        with self.assertRaisesRegex(LifecycleStop,"RESEARCH_ONLY_SCOPE"):
            self.drive(forged)
        tamper=dict(packet)
        tamper["source_query_sha256"]="c"*64
        tamper["sha256"]=digest({k:v for k,v in tamper.items() if k!="sha256"})
        with self.assertRaisesRegex(LifecycleStop,"CORE_QUERY_LINEAGE"):
            self.drive(tamper)

if __name__=="__main__":
    unittest.main()
