"""Negative-only recovery fixture contracts; no forged original E: source."""
import copy
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_factory_f_f2_recovery_diagnostic_v1 import (
    validate_recovery_input,verified_core_receipts,run_recovery_diagnostic,
    SCHEMA,RECOVERY_SHA
)
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError,digest
)


class FactoryRecoveryDiagnosticSafety(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db=Path(tmp.name)/"recovery.sqlite"

    def test_missing_private_core_receipts_fail_before_lab(self):
        doc={"schema":SCHEMA,"original_f2_report_sha256":None,
             "recovery_evidence_file_sha256":RECOVERY_SHA,
             "experiment_id":"DIAG-F4-RECOVERY-TEST"}
        doc["sha256"]=digest(doc)
        with self.assertRaises(ResultsStoreError):
            run_recovery_diagnostic(doc,self.db)
        self.assertFalse(self.db.exists())

    def test_original_f2_cannot_be_impersonated_even_with_reseal(self):
        doc={"schema":SCHEMA,"original_f2_report_sha256":"d"*64,
             "recovery_evidence_file_sha256":RECOVERY_SHA,
             "experiment_id":"DIAG-F4-RECOVERY-TEST"}
        doc["sha256"]=digest(doc)
        with self.assertRaises(ResultsStoreError):
            validate_recovery_input(doc)
        self.assertFalse(self.db.exists())

    def test_untrusted_mapping_without_monthly_core_receipts_denied(self):
        with self.assertRaises(ResultsStoreError):
            verified_core_receipts({
                "schema":"F2_RECOVERY_EVIDENCE.v1",
                "original_f2_report_sha256":None,
                "recovery_evidence_file_sha256":RECOVERY_SHA,
                "source_rights":"OWNER_LOCAL_NOT_INDEPENDENT",
                "readback_receipts":[]})

    def test_recovery_sha_alone_cannot_promote_f5_authority(self):
        doc={"schema":"F2_RECOVERY_EVIDENCE.v1",
             "original_f2_report_sha256":None,
             "recovery_evidence_file_sha256":RECOVERY_SHA,
             "source_rights":"OWNER_LOCAL_NOT_INDEPENDENT",
             "readback_receipts":[],
             "factory_consumer_ack_sha256":"a"*64}
        with self.assertRaises(ResultsStoreError):
            verified_core_receipts(doc)
        self.assertFalse(self.db.exists())


if __name__=="__main__":
    unittest.main()
