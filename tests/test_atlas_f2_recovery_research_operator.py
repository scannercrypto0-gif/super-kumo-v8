"""Negative-only recovery orchestrator tests; no fake private PASS."""
import unittest
from tools.atlas_f2_recovery_research_operator import run


class RecoveryRunnerFailClosed(unittest.TestCase):
    def test_missing_owner_manifest(self):
        with self.assertRaisesRegex(ValueError,"AUTHORIZATION"):
            run({})
    def test_reject_original_f2_alias_before_source_io(self):
        with self.assertRaisesRegex(ValueError,"AUTHORIZATION"):
            run({"schema":"aql.integration.f2-recovery-research-operator.v1",
                 "owner_operator_authorized":False})
    def test_cannot_synthesize_private_recovery_with_only_sha(self):
        from tools.atlas_f2_recovery_evidence_v1 import load_recovery_evidence
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FILE_REQUIRED"):
            load_recovery_evidence("/nonexistent/owner/recovery.json",{})


if __name__=="__main__":
    unittest.main()
