"""Core F research diagnostic: read-only dual-query evidence, fixture-only.

No original private OHLCV, trusted signer, Source ACK or Factory route appears
in this test. The public entrypoint refuses synthetic/unpinned owner F2 reports.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
    SCHEMA, _one_read_only, read_original_diagnostic,
)
from research_wp_r0.historical_library import HistoricalLibrary
from tools.raw_vault_offline.vault import RawVault

START = 1704067200000  # Jan 1, 2024 UTC, TEST-ONLY 4 bars
WIDTH = 900000
N = 4
MONTH = "2024-01"
SHA = lambda x: sha256(x).hexdigest()


class DiagnosticOriginalCausality(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32",
                     "positive synthetic fixture is POSIX chmod only; Windows ACL gate separately tested")
    def test_actual_canonical_read_only_core_raw_native_local_replay(self):
        with TemporaryDirectory(prefix="aql-diagnostic-fixture-") as d:
            root = Path(d)
            warehouse = root / "warehouse"
            warehouse.mkdir()
            warehouse.chmod(0o700)
            vault_root = root / "raw"
            vault = RawVault(vault_root)
            vault_root.chmod(0o700)
            base = f"BTCUSDT-15m-{MONTH}"
            csv = ("\n".join(
                ",".join(str(x) for x in (
                    START + i*WIDTH, 100+i, 102+i, 99+i, 101+i,
                    5+i, START+(i+1)*WIDTH-1, 500+i, 10+i, 2+i, 200+i, 0
                )) for i in range(N)) + "\n").encode()
            out = BytesIO()
            with ZipFile(out, "w", compression=ZIP_DEFLATED) as z:
                z.writestr(base + ".csv", csv)
            original_zip = out.getvalue()
            checksum = (SHA(original_zip)+"  "+base+".zip\n").encode("ascii")
            dataset_id = f"BINANCE-SPOT-BTCUSDT-15M-{MONTH}-F-v1"
            pin = {
                "schema":"aql.core.external-original-byte-pin.v1",
                "source_kind":"BINANCE_KLINES_ZIP",
                "original_object_id":dataset_id,
                "original_sha256":SHA(original_zip),
                "provenance_reference":"TEST_ONLY_IN_MEMORY",
                "captured_at_ms":None,"claimed_available_at_ms":None,
                "expected_inventory_sha256":None,
                "vault_object_metadata":None,
                "universe_manifest_sha256":None,"universe_member_count":None,
                "test_only":True,"archive_name":base+".zip",
                "csv_member_name":base+".csv",
                "csv_member_sha256":SHA(csv),
                "checksum_file_sha256":SHA(checksum),
            }
            end = START + N*WIDTH
            cutoff = end + 1000
            spec = {
                "dataset_id":dataset_id,"version":1,
                "symbol":"BTCUSDT","interval":"15m",
                "exchange":"BINANCE","market":"SPOT",
                "source_label":"TEST_ONLY_IN_MEMORY",
                "start_ms":START,"end_exclusive_ms":end,
                "as_of_ms":cutoff,"parent_source_sha256":None,
                "correction_reason":None,"test_only":True,
            }
            admission = admit_local_original(
                warehouse, original_zip, checksum, pin, spec,
                decision_cutoff_ms=cutoff, vault=vault)
            local = query_local(
                warehouse, dataset_id, 1, START, end, cutoff,
                required_source_sha256=SHA(original_zip))
            library = HistoricalLibrary()
            OfflineBridgeStager(warehouse / "stage").replay_committed(library)
            native = query_price_custody(
                library, {
                    "schema": REQUEST_SCHEMA, "dataset_id": dataset_id,
                    "version":1,"start_ms":START,"end_exclusive_ms":end,
                    "decision_cutoff_ms":cutoff,
                    "require_complete":False,"confirmed_only":False,
                },
                expected_source_sha256=SHA(original_zip),
                expected_manifest_integrity_sha256=admission[
                    "manifest_integrity_sha256"])
            dual = bind_dual_query_identities(native, local, admission)
            entry = {
                "month": MONTH, "state":"RAW_AND_DUAL_QUERY_READBACK",
                "source_sha256":SHA(original_zip),
                "core_245_native_price_query_sha256":native["price_query_sha256"],
                "core_253_local_query_sha256":local["query_sha256"],
                "warehouse_receipt_sha256":admission["receipt_sha256"],
                "dual_query_map_sha256":dual["identity_map_sha256"],
                "bars":N,
            }
            watched = [warehouse/"warehouse.sqlite",vault_root/"manifest.jsonl",
                       vault_root/"index.json"]
            before = {str(p):SHA(p.read_bytes()) for p in watched}
            first = _one_read_only(
                warehouse, vault_root, month=MONTH, source_entry=entry,
                start_ms=START, end_exclusive_ms=end, cutoff_ms=cutoff)
            second = _one_read_only(
                warehouse, vault_root, month=MONTH, source_entry=entry,
                start_ms=START, end_exclusive_ms=end, cutoff_ms=cutoff)
            self.assertEqual(first,second)
            self.assertEqual(first["receipt"]["schema"],SCHEMA)
            self.assertEqual(first["receipt"]["readback_bar_count"],N)
            self.assertEqual(first["receipt"]["core245_native_query_sha256"],
                             native["price_query_sha256"])
            self.assertEqual(first["receipt"]["core253_local_query_sha256"],
                             local["query_sha256"])
            self.assertIsNone(first["receipt"]["source_ack_sha256"])
            self.assertFalse(first["receipt"]["owner_f2_report_pin_verified"])
            self.assertIsNone(first["receipt"]["owner_f2_report_sha256"])
            self.assertEqual(first["receipt"]["secretary_state"],"NOT_ENQUEUED")
            self.assertEqual(first["receipt"]["trading_authority"],"NONE")
            self.assertEqual(len(first["local_bars"]),N)
            self.assertEqual(len(first["native_bars"]),N)
            self.assertEqual(before,{str(p):SHA(p.read_bytes()) for p in watched})
            for field,value in (
                ("source_sha256","0"*64),
                ("core_253_local_query_sha256","0"*64),
                ("core_245_native_price_query_sha256","0"*64),
                ("bars",N+1),
            ):
                corrupt={**entry,field:value}
                with self.subTest(field=field), self.assertRaises(
                        (ValueError,Exception)):
                    _one_read_only(warehouse,vault_root,month=MONTH,
                                   source_entry=corrupt,start_ms=START,
                                   end_exclusive_ms=end,cutoff_ms=cutoff)
            with self.assertRaisesRegex(ValueError,
                                        "DIAGNOSTIC_SOURCE_RANGE_OR_CUTOFF"):
                _one_read_only(
                    warehouse,vault_root,month=MONTH,source_entry=entry,
                    start_ms=START,end_exclusive_ms=end,cutoff_ms=START)
            original_object = (vault_root/"objects"/SHA(original_zip)[:2]/
                               SHA(original_zip)[2:])
            backup = original_object.with_suffix(".fixture-backup")
            original_object.rename(backup)
            try:
                original_object.symlink_to(backup)
                with self.assertRaisesRegex(ValueError,
                                            "DIAGNOSTIC_RAW_OBJECT_LINK_OR_MISSING"):
                    _one_read_only(
                        warehouse,vault_root,month=MONTH,source_entry=entry,
                        start_ms=START,end_exclusive_ms=end,cutoff_ms=cutoff)
            finally:
                original_object.unlink(missing_ok=True)
                backup.rename(original_object)

    def test_public_diagnostic_denies_unpinned_original_source(self):
        with self.assertRaisesRegex(ValueError,
                                    "DIAGNOSTIC_OWNER_F2_PIN_OR_STATE_DRIFT"):
            read_original_diagnostic(
                "/missing/warehouse", "/missing/vault",
                {"schema":"aql.core.f.private-raw-warehouse-dual-query-report.v1",
                 "report_sha256":"0"*64}, month="2024-01")

    def test_diagnostic_receipt_cannot_be_promoted_to_signed_f5(self):
        from research_wp_r0.aql_core_f5_secretary_authority_v1 import (
            SOURCE_ROLE, STRATEGY_ROLE, _signed,
        )
        untrusted_diagnostic = {
            "schema": SCHEMA,
            "kind":"RESEARCH_E2E_DIAGNOSTIC",
            "source_ack_sha256":None,
            "strategy_approval_sha256":None,
            "historical_pit":"NOT_ATTESTED",
            "trading_authority":"NONE",
            "receipt_sha256":"a"*64,
        }
        for authority in (SOURCE_ROLE, STRATEGY_ROLE):
            with self.subTest(authority=authority),self.assertRaisesRegex(
                    ValueError,"CORE_F5_RECEIPT_FIELDS_DRIFT"):
                _signed(authority, untrusted_diagnostic,
                        trusted_registry={},
                        trusted_now_utc="2026-11-07T06:00:00Z")

    def test_public_diagnostic_refuses_inventory_only_feb_and_aug(self):
        # No real original report available; month eligibility remains strict.
        from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import _month_bounds
        for month in ("2024-02","2024-08","2025-01"):
            with self.subTest(month=month), self.assertRaisesRegex(
                    ValueError, "DIAGNOSTIC_MONTH_NOT_ADMITTED"):
                _month_bounds(month)


if __name__ == "__main__":
    unittest.main()
