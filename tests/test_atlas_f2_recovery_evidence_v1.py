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

    def test_no_silent_original_f2_fallback(self):
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FILE_REQUIRED"):
            read_recovered_diagnostic("/absent-warehouse","/absent-vault",
                                      "/absent-recovery",{})


if __name__=="__main__":
    unittest.main()
