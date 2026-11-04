"""Core #253 dual native #245 vs indexed #253 query identity map tests.

Existing native Bridge/Custody/Price query functions and pinned RawVault are
used, not a fabricated receipt. All input prices are TEST_ONLY fixtures.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.raw_vault_offline.vault import RawVault
from research_wp_r0.aql_archive_custody_bridge_v1 import (
    OfflineBridgeStager,digest,
)
from research_wp_r0.aql_authenticated_historical_admission_v1 import admit_original_bytes
from research_wp_r0.aql_core_backbone_local_v1 import (
    BackboneError,query_local,
)
from research_wp_r0.aql_core_authorized_source_transfer_v1 import run_authorized_original_intake
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.aql_core_offline_lab_test_strategy_v1 import calculate_one_original_test_strategy
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.historical_library import HistoricalLibrary
from test_aql_core_authorized_source_transfer_v1 import synthetic_test_only,START,N,WIDTH


class DualQueryIdentity(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"core"
        self.vault=RawVault(Path(self.temp.name)/"vault")
        self.raw,self.cs,self.witness=synthetic_test_only()
        self.cutoff=START+N*WIDTH+10_000
        _,self.warehouse,self.local,_=run_authorized_original_intake(
            self.root,self.raw,self.cs,self.witness,
            vault=self.vault,cutoff_ms=self.cutoff,test_only=True)
        self.lib=HistoricalLibrary()
        pin={
            "schema":"aql.core.external-original-byte-pin.v1",
            "source_kind":"BINANCE_KLINES_ZIP",
            "original_object_id":self.witness["dataset_id"],
            "original_sha256":self.witness["archive_sha256"],
            "provenance_reference":"TEST_ONLY_IN_MEMORY",
            "captured_at_ms":None,"claimed_available_at_ms":None,
            "expected_inventory_sha256":None,"vault_object_metadata":None,
            "universe_manifest_sha256":None,"universe_member_count":None,
            "test_only":True,"archive_name":self.witness["archive_name"],
            "csv_member_name":self.witness["csv_member_name"],
            "csv_member_sha256":self.witness["csv_member_sha256"],
            "checksum_file_sha256":self.witness["checksum_sha256"],
        }
        spec={
            "dataset_id":self.witness["dataset_id"],
            "version":1,"symbol":"BTCUSDT","interval":"15m",
            "exchange":"BINANCE","market":"SPOT",
            "source_label":"RETAINED_NATIVE_RETROSPECTIVE",
            "start_ms":START,"end_exclusive_ms":START+N*WIDTH,
            "as_of_ms":self.cutoff,"parent_source_sha256":None,
            "correction_reason":None,"test_only":True,
        }
        adm=admit_original_bytes(
            self.raw,pin,spec,
            stager=OfflineBridgeStager(self.root/"native-query-independent"),
            library=self.lib,decision_cutoff_ms=self.cutoff,
            checksum_file_bytes=self.cs)
        req={
            "schema":REQUEST_SCHEMA,"dataset_id":self.witness["dataset_id"],
            "version":1,"start_ms":START,
            "end_exclusive_ms":START+N*WIDTH,
            "decision_cutoff_ms":self.cutoff,
            "require_complete":False,"confirmed_only":False,
        }
        self.native=query_price_custody(
            self.lib,req,expected_source_sha256=self.witness["archive_sha256"],
            expected_manifest_integrity_sha256=adm["manifest_integrity_sha256"])
        self.calc=calculate_one_original_test_strategy(
            self.root,self.warehouse,start_ms=START,
            end_exclusive_ms=START+N*WIDTH,cutoff_ms=self.cutoff)

    def mapped(self,native=None,local=None,warehouse=None,calc=None):
        return bind_dual_query_identities(
            native if native is not None else self.native,
            local if local is not None else self.local,
            warehouse if warehouse is not None else self.warehouse,
            strategy_evaluation=calc if calc is not None else self.calc,
        )

    def test_two_distinct_query_hashes_preserved_and_replay(self):
        result=self.mapped()
        self.assertEqual(result,self.mapped())
        self.assertEqual(result["core_245_native_price_query_sha256"],
                         self.native["price_query_sha256"])
        self.assertEqual(result["core_253_query_local_sha256"],
                         self.local["query_sha256"])
        self.assertEqual(result["strategy_evaluation_sha256"],
                         self.calc["evaluation_sha256"])
        self.assertFalse(result["query_shas_are_identical"])
        self.assertEqual(result["bar_count"],N)
        self.assertIsNone(result["historical_known_at_ms"])
        self.assertEqual(result["trading_authority"],"NONE")

    def test_mutated_native_local_source_and_cutoff_denied(self):
        bad=deepcopy(self.native);bad["source_bytes_sha256"]="0"*64
        with self.assertRaises(BackboneError):
            self.mapped(native=bad)
        bad=deepcopy(self.local);bad["decision_cutoff_ms"]=self.cutoff+1
        bad["query_sha256"]=digest({k:v for k,v in bad.items()
                                   if k!="query_sha256"})
        with self.assertRaisesRegex(BackboneError,"SOURCE_VERSION_CUTOFF"):
            self.mapped(local=bad)
        bad=deepcopy(self.warehouse);bad["source_zip_sha256"]="0"*64
        with self.assertRaises(BackboneError):
            self.mapped(warehouse=bad)

    def test_mutated_query_grid_and_strategy_parent_denied(self):
        bad=deepcopy(self.local)
        bad["bars"][0]["bar_checksum"]="0"*64
        bad["query_sha256"]=digest({k:v for k,v in bad.items()
                                   if k!="query_sha256"})
        with self.assertRaisesRegex(BackboneError,"BAR_GRID_OR_CHECKSUM"):
            self.mapped(local=bad)
        bad=deepcopy(self.calc)
        bad["core_price_query_sha256"]=self.native["price_query_sha256"]
        bad["evaluation_sha256"]=digest({k:v for k,v in bad.items()
                                        if k!="evaluation_sha256"})
        with self.assertRaisesRegex(BackboneError,"STRATEGY_PARENT"):
            self.mapped(calc=bad)

    def test_stage_only_vault_is_not_authenticated(self):
        bad=deepcopy(self.warehouse)
        bad["status"]="OFFLINE_LOCAL_STAGE_ONLY"
        bad["receipt_sha256"]=digest({k:v for k,v in bad.items()
                                      if k!="receipt_sha256"})
        with self.assertRaisesRegex(BackboneError,"NOT_COMMITTED"):
            self.mapped(warehouse=bad)


if __name__=="__main__":
    unittest.main()
