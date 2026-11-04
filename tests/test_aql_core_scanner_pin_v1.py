"""Core #253: exact pinned Scanner PR #227 engine→Core Secretary seam.

Test intentionally supplies no bars to avoid inventing quote volume/MTF
features or asserting prospective PIT. The actual Scanner engine must return
a complete UNKNOWN/SCREENED attempt, which Core durably routes OFFLINE.
"""
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.scanner_engine_offline.engine import OfflineScannerEngine, ScanRunConfig
from tools.scanner_engine_offline.contracts import SourceManifest
from tools.scanner_engine_offline.adapters import make_synthetic_universe

from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original
from research_wp_r0.aql_core_secretary_routing_v1 import (
    enqueue_nomination,route_trace,poll_nomination,
)
from test_aql_archive_custody_bridge_v1 import START,WIDTH,N,spec
from test_aql_native_binance_zip_v1 import native_source


class ActualScannerPinnedContract(unittest.TestCase):
    def test_actual_engine_sealed_unknown_scanner_result_routes_without_trade(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/"history"
            zip_bytes,member,check,pin=native_source()
            s=spec(source_label="native-monthly-zip")
            cutoff_ms=START+N*WIDTH+2000
            original=admit_local_original(
                root,zip_bytes,check,pin,s,decision_cutoff_ms=cutoff_ms,
            )
            cutoff=datetime.fromtimestamp(cutoff_ms/1000,timezone.utc)
            manifest=SourceManifest(
                dataset_id=original["dataset_id"],
                dataset_sha=original["source_zip_sha256"],
                schema_version="AQL-SCANNER-V1",
                cutoff_at=cutoff,created_at=cutoff,
            )
            scanner=OfflineScannerEngine(
                ScanRunConfig(
                    scanner_id="PINNED_SCANNER_227",
                    profiles=("INTRADAY",),
                    candidate_limit=1,
                    market="BINANCE:SPOT:USDT",
                ),
                manifest,
            )
            universe=make_synthetic_universe(["BTCUSDT"],cutoff)
            result=scanner.scan(universe,{"BTCUSDT":{}},cutoff_at=cutoff)
            self.assertEqual(result.census["attempted"],1)
            self.assertEqual(len(result.envelopes),1)
            n=result.envelopes[0].as_dict()
            self.assertIn(n["stage"],("SCREENED","UNKNOWN","QUALIFIED"))
            self.assertFalse(n["publishable"])
            self.assertFalse(n["delivery_authorized"])
            self.assertEqual(n["source_manifest"]["dataset_sha"],
                             original["source_zip_sha256"])
            q=enqueue_nomination(
                root,n,strategy_id="RESEARCH_ONLY_STRATEGY",
                strategy_version="v1",warehouse_receipt=original,
                lane="SLOW",idempotency_key="SCANNER_227_RESEARCH",
            )
            item=poll_nomination(root,now_ms=0)
            self.assertEqual(item["envelope"]["scanner_nomination"],n)
            self.assertEqual(
                item["envelope"]["scanner_strategy_decision"],"NOT_PERFORMED")
            self.assertEqual(
                item["envelope"]["secretary_trading_authority"],"NONE")
            self.assertEqual(route_trace(root,"SCANNER_227_RESEARCH")[0]["state"],
                             "PENDING")


if __name__=="__main__":
    unittest.main()
