"""Acceptance: actual Core253 SQLite admission/query, real Scanner→Factory→Lab,
and genuine OS process death/restart. All bytes are synthetic and disposable.
"""
from __future__ import annotations
from contextlib import closing
from io import BytesIO
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile,ZIP_DEFLATED

from research_wp_r0.aql_core_backbone_local_v1 import (
    admit_local_original, query_local, BackboneError,
)
from research_wp_r0.aql_authenticated_historical_admission_v1 import PIN_SCHEMA
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    migrate_store_v2, digest,
)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
from research_wp_r0.aql_factory_lab_experiment_index_v1 import get_experiment_link
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    read_generic_research_result_route,
)
from tools.scanner_strategy_f import research_strategy_plugin as scanner
from tools.atlas_f_lab_3_lifecycle_v1 import run_synthetic, LifecycleStop
from research_wp_r0.strategy_definition import Frozen

from test_aql_factory_h_generic_signal_adapter_v1 import case_for,reseal

START=1709251200000
STEP=900000
N=64


def synthetic_real_sqlite(root,*,partial=False):
    """Actual Core admission, not a mocked query, using native-format test ZIP."""
    basename="BTCUSDT-15m-2024-03"
    rows=[]
    for i in range(N):
        if partial and i==4:
            continue
        opened=START+i*STEP
        px=98.0+(i%17)*0.3
        rows.append(",".join((
            str(opened),str(px),str(px+1),str(px-1),str(px),
            str(float(i+1)),str(opened+STEP-1),"505",str(2+i),
            "2","202","0"
        )))
    csv=("\n".join(rows)+"\n").encode()
    stream=BytesIO()
    with ZipFile(stream,"w",compression=ZIP_DEFLATED) as archive:
        archive.writestr(basename+".csv",csv)
    raw=stream.getvalue()
    source=hashlib.sha256(raw).hexdigest()
    checksum=(source+"  "+basename+".zip\n").encode()
    end=START+N*STEP
    pin={
        "schema":PIN_SCHEMA,"source_kind":"BINANCE_KLINES_ZIP",
        "original_object_id":"TEST_LAB3_RAW_ZIP",
        "original_sha256":source,
        "provenance_reference":"SYNTHETIC_TEST_ONLY",
        "captured_at_ms":end+10000,"claimed_available_at_ms":None,
        "expected_inventory_sha256":None,
        "vault_object_metadata":None,"universe_manifest_sha256":None,
        "universe_member_count":None,"test_only":True,
        "archive_name":basename+".zip",
        "csv_member_name":basename+".csv",
        "csv_member_sha256":hashlib.sha256(csv).hexdigest(),
        "checksum_file_sha256":hashlib.sha256(checksum).hexdigest(),
    }
    spec={
        "dataset_id":"TEST-ONLY-H-BTC-15M","version":1,
        "symbol":"BTCUSDT","interval":"15m","exchange":"BINANCE",
        "market":"SPOT","source_label":"native-monthly-zip",
        "start_ms":START,"end_exclusive_ms":end,"as_of_ms":end+5000,
        "parent_source_sha256":None,"correction_reason":None,
        "test_only":True,
    }
    receipt=admit_local_original(
        root,raw,checksum,pin,spec,decision_cutoff_ms=end+2000)
    # The real read explicitly opens Core's derived SQLite in immutable mode.
    query=query_local(root,spec["dataset_id"],1,START,end,end+2000,
                      required_source_sha256=source,
                      require_complete=not partial,sqlite_immutable=True)
    assert query["source_bytes_sha256"]==receipt["source_zip_sha256"]
    assert query["query_sha256"]!=receipt["receipt_sha256"]
    assert query["historical_pit"]=="NOT_ATTESTED"
    return query,receipt


def actual_scanner_packet(query,warehouse):
    """Create *new* scanner events with unpatched real query_local readback."""
    packet=case_for(2)
    plugin=packet["strategy_plugin"]
    policy=packet["scanner_signal_policy"]
    # This call invokes real Scanner's internal Core253 query_local against the
    # actual disposable warehouse. No monkeypatch is in scope here.
    batch=scanner.evaluate_strategy_plugin(
        plugin,query,warehouse_root=str(warehouse),policy=policy)
    scanner.verify_factory_signal_batch(batch)
    packet.update({
        "scanner_signal_batch":batch,"core_query":query,
        "source_query_sha256":query["query_sha256"],
        "source_bytes_sha256":query["source_bytes_sha256"],
        "manifest_integrity_sha256":query["manifest_integrity_sha256"],
        "decision_cutoff_ms":query["decision_cutoff_ms"],
    })
    reseal(packet)
    return packet


class RealWarehouseAndKill(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.warehouse=self.root/"real-synthetic-warehouse"
        self.store=self.root/"factory-v2.sqlite"
        self.secretary=self.root/"secretary-durable"
        self.checkpoint=self.root/"checkpoint-durable"
        self.checkpoint.mkdir()
        migrate_store_v2(self.store)

    def packet(self,partial=False):
        query,receipt=synthetic_real_sqlite(self.warehouse,partial=partial)
        return actual_scanner_packet(query,self.warehouse)

    def run_pipeline(self,packet,**kw):
        return run_synthetic(
            packet=packet,store_path=self.store,
            secretary_root=self.secretary,checkpoint_root=self.checkpoint,**kw)

    def test_real_sqlite_core253_to_real_scanner_factory_lab_secretary(self):
        packet=self.packet()
        self.assertEqual(packet["core_query"]["coverage"],"COMPLETE")
        self.assertEqual(len(packet["core_query"]["bars"]),N)
        self.assertNotEqual(packet["core_query"]["query_sha256"],
                            packet["core_query"]["source_bytes_sha256"])
        result=self.run_pipeline(packet)
        self.assertEqual(result["state"],"SECRETARY_WAIT")
        self.assertEqual(self.run_pipeline(packet),result)
        index=get_experiment_link(self.store,packet["experiment_id"],
                                  secretary_root=self.secretary)
        self.assertEqual(index["status"],"VERIFIED_WAIT")
        route=read_generic_research_result_route(
            self.secretary,packet["experiment_id"])
        self.assertEqual(route["state"],"WAIT_RESEARCH_REVIEW")
        for ack in ("source_ack_sha256","strategy_approval_sha256",
                    "factory_consumer_ack_sha256","research_review_ack_sha256"):
            self.assertIsNone(route[ack])

    def test_actual_os_process_kill_twice_and_new_process_resume(self):
        packet=self.packet()
        file=self.root/"test-packet.json"
        file.write_text(json.dumps(packet))
        code=r"""
import json,os,sys
from tools.atlas_f_lab_3_lifecycle_v1 import run_synthetic
from pathlib import Path
p=Path(sys.argv[1])
packet=json.loads(p.read_text())
stage=sys.argv[5]
def after_checkpoint(state,receipt):
    if state==stage:
        os._exit(77)
out=run_synthetic(packet=packet,store_path=sys.argv[2],
                  secretary_root=sys.argv[3],checkpoint_root=sys.argv[4],
                  on_durable_stage=after_checkpoint if stage!="NONE" else None)
print(json.dumps({"state":out["state"],"sha256":out["sha256"]}))
"""
        def child(stage):
            return subprocess.run(
                [sys.executable,"-c",code,str(file),str(self.store),
                 str(self.secretary),str(self.checkpoint),stage],
                cwd=str(Path.cwd()),text=True,capture_output=True,timeout=45)
        first=child("SCANNER_VERIFIED")
        self.assertEqual(first.returncode,77,(first.stdout,first.stderr))
        cp=self.checkpoint/(packet["experiment_id"]+".json")
        self.assertEqual(json.loads(cp.read_text())["state"],
                         "SCANNER_VERIFIED")
        second=child("LAB_EVALUATED")
        self.assertEqual(second.returncode,77,(second.stdout,second.stderr))
        self.assertEqual(json.loads(cp.read_text())["state"],"LAB_EVALUATED")
        third=child("NONE")
        self.assertEqual(third.returncode,0,(third.stdout,third.stderr))
        fourth=child("NONE")
        self.assertEqual(fourth.returncode,0,(fourth.stdout,fourth.stderr))
        a=json.loads(third.stdout.strip().splitlines()[-1])
        b=json.loads(fourth.stdout.strip().splitlines()[-1])
        self.assertEqual(a,b)
        self.assertEqual(a["state"],"SECRETARY_WAIT")
        with closing(sqlite3.connect(self.store)) as con:
            self.assertEqual(con.execute(
                f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0],1)
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM factory_h_experiment_links_v1").fetchone()[0],1)
        self.assertEqual(read_generic_research_result_route(
            self.secretary,packet["experiment_id"])["state"],
            "WAIT_RESEARCH_REVIEW")

    def test_partial_warehouse_query_not_promoted(self):
        packet=self.packet(partial=True)
        self.assertEqual(packet["core_query"]["coverage"],"PARTIAL")
        self.assertEqual(len(packet["core_query"]["missing_bar_opens"]),1)
        self.assertEqual(packet["scanner_signal_batch"]["payload"][
            "signal_counts"]["UNKNOWN"],N)
        done=self.run_pipeline(packet)
        self.assertEqual(done["state"],"SECRETARY_WAIT")
        index=get_experiment_link(self.store,packet["experiment_id"],
                                  secretary_root=self.secretary)["link"]
        self.assertEqual(index["modeled_trades"],0)
        with self.assertRaisesRegex(BackboneError,"WAREHOUSE_INCOMPLETE_OR_FUTURE"):
            query_local(self.warehouse,packet["core_query"]["dataset_id"],1,
                        START,START+N*STEP,START+N*STEP+2000,
                        required_source_sha256=packet["source_bytes_sha256"],
                        require_complete=True,sqlite_immutable=True)

    def test_unsafe_cutoff_rejects_without_authority_upgrade(self):
        packet=self.packet()
        with self.assertRaisesRegex(BackboneError,"WAREHOUSE_INCOMPLETE_OR_FUTURE"):
            query_local(self.warehouse,packet["core_query"]["dataset_id"],1,
                        START,START+N*STEP,START+STEP,
                        required_source_sha256=packet["source_bytes_sha256"],
                        require_complete=True,sqlite_immutable=True)
        self.assertEqual(packet["historical_pit"],"NOT_ATTESTED")

    def test_parent_source_query_sha_conflict_no_result(self):
        packet=self.packet()
        forged=copy.deepcopy(packet)
        forged["source_query_sha256"]="f"*64
        reseal(forged)
        with self.assertRaises(LifecycleStop):
            self.run_pipeline(forged)
        with closing(sqlite3.connect(self.store)) as con:
            self.assertEqual(con.execute(
                f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0],0)


if __name__=="__main__":
    unittest.main()
