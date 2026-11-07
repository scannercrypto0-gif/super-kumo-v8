"""Negative-only tests: never substitute fabricated recovery for original data."""
import tempfile
import unittest
from pathlib import Path

from tools.atlas_f2_recovery_evidence_v1 import (
    load_recovery_evidence, read_recovered_diagnostic,
)


class F2RecoveryEvidenceNegatives(unittest.TestCase):
    def test_missing_private_file_is_wait(self):
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FILE_REQUIRED"):
            load_recovery_evidence("/not/a/real/owner-private-file", {})

    def test_caller_mapping_cannot_bypass_actual_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"claimed-recovery.json"
            p.write_text('{"schema":"aql.integration.f2-recovery-evidence.v1"}')
            with self.assertRaisesRegex(ValueError,"FILE_BYTES_DIGEST_MISMATCH"):
                load_recovery_evidence(p, {"schema":"aql.integration.f2-recovery-evidence.v1"})

    def test_known_owner_internal_sha_is_not_raw_file_sha(self):
        from tools.atlas_f2_recovery_evidence_v1 import (
            EXPECTED_RECOVERY_FILE_SHA256, EXPECTED_RECOVERY_RAW_BYTES_SHA256,
            OWNER_REPORT_SCHEMA,
        )
        self.assertNotEqual(EXPECTED_RECOVERY_FILE_SHA256,
                            EXPECTED_RECOVERY_RAW_BYTES_SHA256)
        self.assertEqual(OWNER_REPORT_SCHEMA,
                         "aql.owner-local.f2-recovery-evidence.v1")

    def test_forged_internal_digest_cannot_bypass_raw_bytes_pin(self):
        import json
        from tools.atlas_f2_recovery_evidence_v1 import (
            EXPECTED_RECOVERY_FILE_SHA256,
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fake-owner-report.json"
            p.write_text(json.dumps({
                "schema": "aql.owner-local.f2-recovery-evidence.v1",
                "recovery_sha256": EXPECTED_RECOVERY_FILE_SHA256,
                "disposition": "OWNER_LOCAL_DUAL_READBACK_PASS",
                "verified_months": [{}] * 10,
            }))
            with self.assertRaisesRegex(ValueError,
                                        "FILE_BYTES_DIGEST_MISMATCH"):
                load_recovery_evidence(p, {})

    def test_real_producer_state_distinct_from_core_mapping_state(self):
        # Pure contract-level synthetic identities; never treated as E: evidence.
        from tools.atlas_f2_recovery_evidence_v1 import (
            _owner_report_matches_reconstructed_mapping as matches,
        )
        month="2024-01"
        parent={
            "month":month, "state":"DUAL_READBACK_VERIFIED",
            "dataset_id":"BINANCE-SPOT-BTCUSDT-15M-"+month+"-F-v1",
            "bars":2976, "source_sha256":"a"*64,
            "core245_native_query_sha256":"b"*64,
            "core253_local_query_sha256":"c"*64,
            "manifest_sha256":"d"*64,
        }
        mapping={
            "month":month, "state":"RAW_AND_DUAL_QUERY_READBACK",
            "bars":2976, "source_sha256":"a"*64,
            "core_245_native_price_query_sha256":"b"*64,
            "core_253_local_query_sha256":"c"*64,
        }
        self.assertTrue(matches(parent,mapping))
        self.assertEqual(parent["state"],"DUAL_READBACK_VERIFIED")
        for field,value in (
            ("state","SELECTED"),
            ("state","RAW_AND_DUAL_QUERY_READBACK"),
            ("dataset_id","UNKNOWN"),
            ("bars",1),
            ("source_sha256","e"*64),
            ("core245_native_query_sha256","e"*64),
            ("core253_local_query_sha256","e"*64),
            ("manifest_sha256","x"*64),
        ):
            with self.subTest(field=field,value=value):
                self.assertFalse(matches({**parent,field:value},mapping))
        for field,value in (
            ("state","F5_APPROVED"),
            ("state","DUAL_READBACK_VERIFIED"),
            ("month","2024-03"),
            ("bars",0),
            ("source_sha256","e"*64),
            ("core_245_native_price_query_sha256","e"*64),
            ("core_253_local_query_sha256","e"*64),
        ):
            with self.subTest(mapping_field=field,value=value):
                self.assertFalse(matches(parent,{**mapping,field:value}))

    def test_no_silent_original_f2_fallback(self):
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FILE_REQUIRED"):
            read_recovered_diagnostic("/absent-warehouse","/absent-vault",
                                      "/absent-recovery",{})


if __name__=="__main__":
    unittest.main()
