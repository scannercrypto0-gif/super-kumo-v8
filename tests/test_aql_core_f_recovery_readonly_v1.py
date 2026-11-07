"""Core F2 recovery: SOURCE-BACKED no-write verifier tests.

Only disposable synthetic source ZIPs in CI. No owner originals, signed
authority, source rights, G0, or genuine F2 recovery report are included.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import os
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from research_wp_r0.aql_core_f_recovery_readonly_v1 import (
    SCHEMA, EXPECTED_RECOVERY_BYTES_SHA256,
    EXPECTED_RECOVERY_INTERNAL_SHA256, OWNER_REPORT_SCHEMA,
    _owner_report_pins, _month_bounds,
    _verify_mapping, _read_existing_month, read_recovery_diagnostic,
)
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.historical_library import HistoricalLibrary
from tools.raw_vault_offline.vault import RawVault

SHA=lambda b:sha256(b).hexdigest()
MONTH="2024-01"
STEP=900000
START,END=_month_bounds(MONTH)
N=(END-START)//STEP


def build_mapping(entries):
    return {
        "schema":"aql.integration.f2-recovery-evidence.v1",
        "source_class":"OWNER_LOCAL_RECOVERY_NOT_ORIGINAL_F2",
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
        "owner_f2_report_sha256":None,
        "entries":entries,
    }


class RecoveryNoWriteContract(unittest.TestCase):
    def test_opaque_bytes_pin_and_non_impersonation(self):
        with TemporaryDirectory() as temp:
            p=Path(temp)/"not-original-recovery.json"
            p.write_bytes(b"FAKE-OWNER-RECOVERY-FIXTURE")
            with self.assertRaisesRegex(ValueError,"OPAQUE_RECOVERY_FILE_SHA_MISMATCH"):
                read_recovery_diagnostic(temp,temp,p,build_mapping([]))
        self.assertEqual(len(EXPECTED_RECOVERY_BYTES_SHA256),64)

    @staticmethod
    def _genuine_structure_fixture():
        # This is ONLY a synthetic structure: it is not the owner's file and
        # cannot pass the genuine immutable FILE BYTES SHA without a test patch.
        import calendar
        from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
            ADMITTED_MONTHS,
        )
        entries = []
        for month in ADMITTED_MONTHS:
            y, m = map(int, month.split("-"))
            bars = calendar.monthrange(y, m)[1] * 96
            entries.append({
                "bars": bars,
                "core245_native_query_sha256": "b" * 64,
                "core253_local_query_sha256": "c" * 64,
                "dataset_id": f"BINANCE-SPOT-BTCUSDT-15M-{month}-F-v1",
                "manifest_sha256": "d" * 64,
                "month": month,
                "source_sha256": "e" * 64,
                "state": "RAW_AND_DUAL_QUERY_READBACK",
            })
        return {
            "schema": OWNER_REPORT_SCHEMA,
            "recovery_sha256": EXPECTED_RECOVERY_INTERNAL_SHA256,
            "disposition": "OWNER_LOCAL_DUAL_READBACK_PASS",
            "verified_months": 10,
            "verified_bars": 29376,
            "entries": entries,
            "historical_pit": "NOT_ATTESTED",
            "trading_authority": "NONE",
            "signed_f5_approval": False,
            "original_f2_report_restored": False,
        }

    def _structure_checked(self, report):
        """Isolate schema checks; production still requires fixed actual bytes."""
        import json
        raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        with patch(
            "research_wp_r0.aql_core_f_recovery_readonly_v1.EXPECTED_RECOVERY_BYTES_SHA256",
            SHA(raw),
        ):
            return _owner_report_pins(raw)

    def test_real_owner_schema_two_hash_contract(self):
        import json
        self.assertNotEqual(EXPECTED_RECOVERY_INTERNAL_SHA256,
                            EXPECTED_RECOVERY_BYTES_SHA256)
        self.assertEqual(OWNER_REPORT_SCHEMA,
                         "aql.owner-local.f2-recovery-evidence.v1")
        fixture = self._genuine_structure_fixture()
        self.assertEqual(self._structure_checked(fixture), fixture)
        raw = json.dumps(fixture, sort_keys=True).encode()
        # No test-only file bypass is ever permitted on the public route.
        with self.assertRaisesRegex(ValueError,
                                    "OPAQUE_RECOVERY_FILE_SHA_MISMATCH"):
            _owner_report_pins(raw)

    def test_report_rejects_count_rows_month_census_and_sha_tampering(self):
        cases = [
            ("months_list", ("verified_months", [{}] * 10),
             "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT"),
            ("months_bool", ("verified_months", True),
             "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT"),
            ("months_nine", ("verified_months", 9),
             "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT"),
            ("bars_wrong", ("verified_bars", 29375),
             "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT"),
            ("bars_bool", ("verified_bars", True),
             "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT"),
            ("report_internal", ("recovery_sha256", "f"*64),
             "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT"),
            ("pit_promote", ("historical_pit", "ATTESTED"),
             "OWNER_REPORT_AUTHORITY_PROMOTION_DENIED"),
            ("f5_promote", ("signed_f5_approval", True),
             "OWNER_REPORT_AUTHORITY_PROMOTION_DENIED"),
            ("restored_original", ("original_f2_report_restored", True),
             "OWNER_REPORT_AUTHORITY_PROMOTION_DENIED"),
            ("trade_promote", ("trading_authority", "LIVE"),
             "OWNER_REPORT_AUTHORITY_PROMOTION_DENIED"),
        ]
        for name, (field, value), reason in cases:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, reason):
                self._structure_checked({
                    **self._genuine_structure_fixture(), field:value})
        for name, mutate in [
            ("duplicate_month",lambda rows:rows.__setitem__(
                1, {**rows[1],"month":rows[0]["month"]})),
            ("missing_month",lambda rows:rows.pop()),
            ("extra_month",lambda rows:rows.append(dict(rows[-1]))),
            ("bar_count",lambda rows:rows[0].__setitem__("bars", 1)),
            ("wrong_dataset",lambda rows:rows[0].__setitem__(
                "dataset_id","INVENTORY_ONLY")),
            ("wrong_query_sha",lambda rows:rows[0].__setitem__(
                "core253_local_query_sha256","not-sha")),
            ("extra_entry_key",lambda rows:rows[0].__setitem__(
                "warehouse_receipt_sha256","a"*64)),
        ]:
            fixture = self._genuine_structure_fixture()
            mutate(fixture["entries"])
            with self.subTest(name=name),self.assertRaisesRegex(
                ValueError,"OWNER_REPORT_ENTRY_FIELDS_DRIFT|OWNER_REPORT_MONTH_CENSUS_OR_IDENTITY_DRIFT"
            ):
                self._structure_checked(fixture)

    def test_real_schema_parser_rejects_duplicate_or_nonfinite_after_byte_pin(self):
        import json
        cases = [
            (b'{"schema":"a","schema":"b"}', "REPORT_DUPLICATE_KEY"),
            (b'{"a":NaN}', "REPORT_NONFINITE"),
            (json.dumps({"schema":OWNER_REPORT_SCHEMA,
                         "recovery_sha256":"f"*64,
                         "disposition":"OWNER_LOCAL_DUAL_READBACK_PASS",
                         "verified_months":10,
                         "verified_bars":29376,
                         "entries":self._genuine_structure_fixture()["entries"]
                         }).encode(),
             "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT"),
        ]
        for raw, reason in cases:
            with self.subTest(reason=reason):
                with patch(
                    "research_wp_r0.aql_core_f_recovery_readonly_v1.EXPECTED_RECOVERY_BYTES_SHA256",
                    SHA(raw),
                ):
                    with self.assertRaisesRegex(ValueError, reason):
                        _owner_report_pins(raw)

    def test_untrusted_mapping_is_only_shape_preflight(self):
        with self.assertRaisesRegex(ValueError,"EXACT_TEN_ADMITTED_MONTHS_REQUIRED"):
            _verify_mapping(build_mapping([]))
        with self.assertRaisesRegex(ValueError,"MAPPING_SCOPE_OR_F2_IMPERSONATION"):
            _verify_mapping({
                **build_mapping([]),
                "owner_f2_report_sha256":"daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40",
            })

    @unittest.skipIf(sys.platform=="win32",
                     "Positive file fixture requires POSIX chmod; Windows negative gates elsewhere")
    def test_real_core_pinned_full_month_recovery_no_mutation_and_tamper(self):
        with TemporaryDirectory(prefix="aql-f2-recovery-fixture-") as temp:
            parent=Path(temp)
            warehouse=parent/"warehouse"
            warehouse.mkdir()
            warehouse.chmod(0o700)
            vault_root=parent/"vault"
            vault=RawVault(vault_root)
            vault_root.chmod(0o700)
            basename=f"BTCUSDT-15m-{MONTH}"
            csv=("\n".join(
                ",".join(str(x) for x in (
                    START+i*STEP, 101+i, 103+i, 100+i, 102+i,
                    5+i, START+(i+1)*STEP-1, 500+i, 10+i, 2+i, 200+i, 0,
                )) for i in range(N)
            )+"\n").encode("ascii")
            sink=BytesIO()
            with ZipFile(sink,"w",compression=ZIP_DEFLATED) as z:
                z.writestr(basename+".csv",csv)
            raw=sink.getvalue()
            checksum=(SHA(raw)+"  "+basename+".zip\n").encode()
            dataset=f"BINANCE-SPOT-BTCUSDT-15M-{MONTH}-F-v1"
            pin={
                "schema":"aql.core.external-original-byte-pin.v1",
                "source_kind":"BINANCE_KLINES_ZIP",
                "original_object_id":dataset,
                "original_sha256":SHA(raw),
                "provenance_reference":"TEST_ONLY_NO_REAL_SOURCE",
                "captured_at_ms":None,"claimed_available_at_ms":None,
                "expected_inventory_sha256":None,
                "vault_object_metadata":None,
                "universe_manifest_sha256":None,
                "universe_member_count":None,
                "test_only":False,"archive_name":basename+".zip",
                "csv_member_name":basename+".csv",
                "csv_member_sha256":SHA(csv),
                "checksum_file_sha256":SHA(checksum),
            }
            cutoff=END+1000
            spec={
                "dataset_id":dataset,"version":1,"symbol":"BTCUSDT",
                "interval":"15m","exchange":"BINANCE","market":"SPOT",
                "source_label":"OWNER_PRIVATE_RETROSPECTIVE",
                "start_ms":START,"end_exclusive_ms":END,"as_of_ms":cutoff,
                "parent_source_sha256":None,
                "correction_reason":None,"test_only":False,
            }
            warehouse_receipt=admit_local_original(
                warehouse,raw,checksum,pin,spec,
                decision_cutoff_ms=cutoff,vault=vault)
            local=query_local(
                warehouse,dataset,1,START,END,cutoff,
                required_source_sha256=SHA(raw))
            lib=HistoricalLibrary()
            OfflineBridgeStager(warehouse/"stage").replay_committed(lib)
            native=query_price_custody(lib,{
                "schema":REQUEST_SCHEMA,"dataset_id":dataset,"version":1,
                "start_ms":START,"end_exclusive_ms":END,
                "decision_cutoff_ms":cutoff,
                "require_complete":False,"confirmed_only":False,
            }, expected_source_sha256=SHA(raw),
               expected_manifest_integrity_sha256=
                warehouse_receipt["manifest_integrity_sha256"])
            dual=bind_dual_query_identities(native,local,warehouse_receipt)
            entry={
                "month":MONTH,"state":"RAW_AND_DUAL_QUERY_READBACK",
                "bars":N,"source_sha256":SHA(raw),
                "warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
                "core_245_native_price_query_sha256":native["price_query_sha256"],
                "core_253_local_query_sha256":local["query_sha256"],
                "dual_query_map_sha256":dual["identity_map_sha256"],
            }
            from research_wp_r0.aql_core_f_recovery_readonly_v1 import (
                _tree_fingerprint,
            )
            baseline=_tree_fingerprint((warehouse,vault_root))
            # Guarantee no incidental mkdir even for a pre-existing stage root.
            with patch.object(Path,"mkdir",side_effect=AssertionError(
                "Recovery attempted a mkdir")):
                first=_read_existing_month(warehouse,vault_root,MONTH,entry)
            second=_read_existing_month(warehouse,vault_root,MONTH,entry)
            self.assertEqual(first,second)
            self.assertEqual(first["receipt"]["schema"],SCHEMA)
            self.assertEqual(first["receipt"]["status"],
                             "SOURCE_BACKED_RECOVERY_READBACK_ONLY")
            self.assertEqual(first["receipt"]["warehouse_receipt_sha256"],
                             warehouse_receipt["receipt_sha256"])
            self.assertEqual(first["receipt"]["dual_map_sha256"],
                             dual["identity_map_sha256"])
            self.assertEqual(first["receipt"]["bar_count"],N)
            self.assertIsNone(first["receipt"]["original_f2_report_sha256"])
            self.assertIsNone(first["receipt"]["recovery_file_sha256"])
            self.assertFalse(first["receipt"]["opaque_recovery_file_pin_verified"])
            self.assertIsNone(first["receipt"]["source_ack_sha256"])
            self.assertEqual(first["receipt"]["trading_authority"],"NONE")
            self.assertEqual(_tree_fingerprint((warehouse,vault_root)),baseline)
            for field,value in (
                ("source_sha256","0"*64),
                ("warehouse_receipt_sha256","1"*64),
                ("core_245_native_price_query_sha256","2"*64),
                ("core_253_local_query_sha256","3"*64),
                ("dual_query_map_sha256","4"*64),
                ("bars",N-1),
            ):
                damaged={**entry,field:value}
                with self.subTest(field=field),self.assertRaises(ValueError):
                    _read_existing_month(warehouse,vault_root,MONTH,damaged)
            self.assertEqual(_tree_fingerprint((warehouse,vault_root)),baseline)
            obj=vault_root/"objects"/SHA(raw)[:2]/SHA(raw)[2:]
            backup=obj.with_suffix(".fixture-bak")
            obj.rename(backup)
            try:
                obj.symlink_to(backup)
                with self.assertRaisesRegex(ValueError,"SYMLINK_(TREE|PATH)_DENIED"):
                    _read_existing_month(warehouse,vault_root,MONTH,entry)
            finally:
                obj.unlink(missing_ok=True)
                backup.rename(obj)
            original_manifest=(vault_root/"manifest.jsonl").read_bytes()
            try:
                (vault_root/"manifest.jsonl").write_bytes(
                    original_manifest + b'{"content_sha256":"0"}\\n')
                with self.assertRaises(ValueError):
                    _read_existing_month(warehouse,vault_root,MONTH,entry)
            finally:
                (vault_root/"manifest.jsonl").write_bytes(original_manifest)
            # Deliberate corruption and restoration of disposable files may
            # change directory/file mtimes. The no-write baseline was already
            # asserted before these adversarial filesystem mutations.

    def test_recovery_receipt_cannot_become_signed_f5_authority(self):
        from research_wp_r0.aql_core_f5_secretary_authority_v1 import (
            SOURCE_ROLE,STRATEGY_ROLE,_signed,
        )
        diagnostic={
            "schema":SCHEMA,"recovery_file_sha256":None,
            "original_f2_report_sha256":None,
            "opaque_recovery_file_pin_verified":False,
            "source_ack_sha256":None,
            "strategy_approval_sha256":None,
            "trading_authority":"NONE",
        }
        for role in (SOURCE_ROLE,STRATEGY_ROLE):
            with self.subTest(role=role),self.assertRaisesRegex(
                    ValueError,"CORE_F5_RECEIPT_FIELDS_DRIFT"):
                _signed(role,diagnostic,trusted_registry={},
                        trusted_now_utc="2026-11-07T07:00:00Z")


if __name__=="__main__":
    unittest.main()
