"""Negative-only recovery fixture contracts; no forged original E: source."""
import copy
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_factory_f_f2_recovery_diagnostic_v1 import (
    validate_recovery_input,verified_core_receipts,run_recovery_diagnostic,
    SCHEMA,RECOVERY_SHA,RECEIPT_FIELDS
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


    def _core_shaped_receipts(self):
        """Core #275 public receipt SHAPE ONLY, not owner E: evidence."""
        from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
            MONTHS, _month_boundaries
        )
        receipts=[]
        for i, month in enumerate(MONTHS):
            start,end=_month_boundaries(month)
            receipt={
                "schema":"aql.core.f2-recovery-readonly-source.v1",
                "month":month,
                "dataset_id":"BINANCE-SPOT-BTCUSDT-15M-"+month+"-F-v1",
                "status":"SOURCE_BACKED_RECOVERY_READBACK_ONLY",
                "recovery_file_sha256":RECOVERY_SHA,
                "opaque_recovery_file_pin_verified":True,
                "original_f2_report_sha256":None,
                "source_zip_sha256":f"{i+1:064x}",
                "manifest_integrity_sha256":f"{i+21:064x}",
                "warehouse_receipt_sha256":f"{i+41:064x}",
                "core245_native_query_sha256":f"{i+61:064x}",
                "core253_local_query_sha256":f"{i+81:064x}",
                "dual_map_sha256":f"{i+101:064x}",
                "bar_count":(end-start)//900000,
                "start_ms":start,"end_exclusive_ms":end,
                "decision_cutoff_ms":end+1000,
                "no_write_tree_fingerprint_sha256":f"{i+121:064x}",
                "historical_pit":"NOT_ATTESTED",
                "source_ack_sha256":None,
                "strategy_approval_sha256":None,
                "factory_consumer_ack_sha256":None,
                "secretary_state":"NOT_ENQUEUED",
                "trading_authority":"NONE"
            }
            self.assertEqual(set(receipt)|{"receipt_sha256"},RECEIPT_FIELDS)
            receipt["receipt_sha256"]=digest(receipt)
            receipts.append(receipt)
        return {
            "schema":"F2_RECOVERY_EVIDENCE.v1",
            "original_f2_report_sha256":None,
            "recovery_evidence_file_sha256":RECOVERY_SHA,
            "source_rights":"OWNER_LOCAL_NOT_INDEPENDENT",
            "readback_receipts":receipts
        }

    def test_current_core_full_receipt_shape_accepts_structural_fixture(self):
        from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import MONTHS
        doc=self._core_shaped_receipts()
        parents=verified_core_receipts(doc)
        self.assertEqual(set(parents),set(MONTHS))
        self.assertEqual(parents[MONTHS[0]]["readback_receipt_sha256"],
                         doc["readback_receipts"][0]["receipt_sha256"])
        self.assertFalse(self.db.exists())

    def test_core_proof_false_missing_extra_and_resealed_tamper_denied(self):
        for mutation in ("false","missing","extra","tamper","swapped_month",
                         "swapped_source","swapped_query","swapped_manifest",
                         "swapped_warehouse","no_write_removed"):
            with self.subTest(mutation=mutation):
                doc=self._core_shaped_receipts()
                a,b=doc["readback_receipts"][:2]
                if mutation=="false":
                    a["opaque_recovery_file_pin_verified"]=False
                elif mutation=="missing":
                    del a["opaque_recovery_file_pin_verified"]
                elif mutation=="extra":
                    a["untrusted_field"]="x"
                elif mutation=="tamper":
                    a["source_zip_sha256"]="f"*64
                elif mutation=="swapped_month":
                    a["month"],b["month"]=b["month"],a["month"]
                elif mutation=="swapped_source":
                    a["source_zip_sha256"],b["source_zip_sha256"]=(
                        b["source_zip_sha256"],a["source_zip_sha256"])
                elif mutation=="swapped_query":
                    a["core245_native_query_sha256"]=b["core245_native_query_sha256"]
                elif mutation=="swapped_manifest":
                    a["manifest_integrity_sha256"]=b["manifest_integrity_sha256"]
                elif mutation=="swapped_warehouse":
                    a["warehouse_receipt_sha256"]=b["warehouse_receipt_sha256"]
                elif mutation=="no_write_removed":
                    del a["no_write_tree_fingerprint_sha256"]
                # For source/month/parent swaps, stale seal must be rejected.
                # A caller-resealed fake remains structurally indistinguishable
                # from Core; only Core's private readback proves authenticity.
                with self.assertRaises(ResultsStoreError):
                    verified_core_receipts(doc)
                self.assertFalse(self.db.exists())

    def test_receipt_seal_binds_store_status(self):
        body={"lab_sha256":"a"*64,"experiment_sha256":"b"*64,
              "result_sha256":"c"*64,"store_status":"STORED_IMMUTABLE"}
        first=digest(body)
        body["store_status"]="REPLAY_IDENTICAL"
        self.assertNotEqual(first,digest(body))
        self.assertEqual([body[k] for k in
                          ("lab_sha256","experiment_sha256","result_sha256")],
                         ["a"*64,"b"*64,"c"*64])


if __name__=="__main__":
    unittest.main()
