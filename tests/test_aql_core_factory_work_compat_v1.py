"""Core-only compatibility tests for Factory #229 and Work #228 schemas.

No import of Factory/Work PR code: those branches have separate owners and
are not connected at runtime. Fixtures exercise *real* Core archive/Bridge/
HistoricalLibrary/query code paths and stable mapping, not fake end-user reports.
"""
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest

from research_wp_r0.historical_library import HistoricalLibrary
from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager, raw_sha
from research_wp_r0.aql_core_factory_work_compat_v1 import (
    compatibility_evidence, FACTORY_SCHEMA, SCHEMA_COMPAT,
)
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from test_aql_archive_custody_bridge_v1 import (
    exported, START, WIDTH, N, spec, archive_payload,
)


def request(*, version=1, cutoff=START+N*WIDTH+2000, **updates):
    x = {
        "schema": REQUEST_SCHEMA, "dataset_id": spec()["dataset_id"],
        "version": version, "start_ms": START,
        "end_exclusive_ms": START + N*WIDTH,
        "decision_cutoff_ms": cutoff,
        "require_complete": False, "confirmed_only": False,
    }
    x.update(updates)
    return x


class CoreToFactoryWorkCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stager = OfflineBridgeStager(self.tmp.name)
        self.lib = HistoricalLibrary()
        self.packet, self.raw = exported()
        key = self.stager.stage(self.packet, self.raw)
        self.stager.advance(key, batch_size=N)
        self.receipt = self.stager.commit(key, self.lib)

    def evidence(self, req=None, packet=None, raw=None, receipt=None):
        return compatibility_evidence(
            self.lib, self.packet if packet is None else packet,
            self.raw if raw is None else raw,
            self.receipt if receipt is None else receipt,
            request() if req is None else req,
        )

    def test_real_core_chain_complete_and_deterministic_mapping(self):
        a = self.evidence()
        b = self.evidence()
        self.assertEqual(a, b)
        self.assertEqual(a["schema"], SCHEMA_COMPAT)
        self.assertEqual(a["coverage"], "COMPLETE")
        self.assertEqual(a["available_bar_count"], N)
        self.assertEqual(a["source_bytes_sha256"], raw_sha(self.raw))
        self.assertEqual(a["source_receipt_sha256"], self.receipt["receipt_sha256"])
        self.assertEqual(a["manifest_integrity_sha256"],
                         self.receipt["manifest_integrity_sha256"])
        factory = a["factory_work_contract"]["factory"]
        work = a["factory_work_contract"]["work"]
        self.assertEqual(factory["target_schema"], FACTORY_SCHEMA)
        self.assertEqual(factory["status"], "NOT_CONNECTED")
        self.assertEqual(work["status"], "NOT_CONNECTED")
        self.assertEqual(factory["feature_availability_class"], "RETROSPECTIVE_NON_PIT")
        self.assertEqual(a["trading_authority"], "NONE")
        self.assertEqual(a["authentic_source"], "NOT_CONNECTED")

    def test_real_core_partial_and_unknown_cutoff_remain_unpromoted(self):
        part = self.evidence(request(cutoff=START+WIDTH+1000))
        self.assertEqual(part["coverage"], "PARTIAL")
        self.assertEqual(part["available_bar_count"], 1)
        self.assertEqual(len(part["missing_bar_opens"]), N-1)
        # Underlying HistoricalLibrary snapshots only bars available at cutoff.
        # With zero eligible bars it raises HistoricalDataError; the Bridge
        # explicitly maps this to UNKNOWN with all opens missing.
        unknown = self.evidence(request(cutoff=START))
        self.assertEqual(unknown["coverage"], "UNKNOWN")
        self.assertEqual(unknown["available_bar_count"], 0)
        self.assertEqual(len(unknown["missing_bar_opens"]), N)
        for item in (part,unknown):
            self.assertEqual(item["pit_status"], "NOT_ATTESTED")
            self.assertEqual(item["factory_work_contract"]["factory"]["status"], "NOT_CONNECTED")

    def test_corrupted_source_forged_manifest_and_receipt_rejected(self):
        with self.assertRaises(ValueError):
            self.evidence(raw=self.raw+b"X")
        bad = deepcopy(self.receipt)
        bad["manifest_integrity_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"RECEIPT_TAMPER"):
            self.evidence(receipt=bad)
        bad = deepcopy(self.packet)
        bad["source_bytes_sha256"]="0"*64
        with self.assertRaises(ValueError):
            self.evidence(packet=bad)

    def test_cross_version_or_cutoff_mismatch_and_pit_upgrade_rejected(self):
        with self.assertRaisesRegex(ValueError,"REQUEST_SOURCE_OR_SCOPE"):
            self.evidence(request(version=2))
        with self.assertRaisesRegex(ValueError,"READ_ONLY_FLAGS"):
            self.evidence(request(confirmed_only=True))
        with self.assertRaisesRegex(ValueError,"READ_ONLY_FLAGS"):
            self.evidence(request(require_complete=True))
        with self.assertRaisesRegex(ValueError,"EXPLICIT_VERSION_REQUIRED"):
            self.evidence(request(version=None))
        with self.assertRaisesRegex(ValueError,"REQUEST_SOURCE_OR_SCOPE"):
            self.evidence(request(end_exclusive_ms=START+2*WIDTH))

    def test_correction_lineage_is_source_bound(self):
        corrected_raw = archive_payload(mutation=3)
        corrected_spec = spec(
            version=2, parent_source_sha256=raw_sha(self.raw),
            correction_reason="TEST_ONLY_CORRECTION",
        )
        corrected, raw = exported(corrected_raw, corrected_spec)
        key = self.stager.stage(corrected,raw)
        self.stager.advance(key,batch_size=N)
        receipt = self.stager.commit(key,self.lib)
        actual = self.evidence(req=request(version=2),packet=corrected,
                               raw=raw,receipt=receipt)
        self.assertEqual(actual["correction_lineage"]["version"],2)
        self.assertEqual(actual["correction_lineage"]["parent_source_sha256"],
                         raw_sha(self.raw))
        self.assertEqual(actual["source_bytes_sha256"],raw_sha(raw))
        self.assertNotEqual(actual["source_bytes_sha256"],
                            self.evidence()["source_bytes_sha256"])

    def test_resume_and_replay_idempotence_produce_same_mapping(self):
        initial = self.evidence()
        self.assertEqual(self.stager.replay_committed(self.lib),[self.receipt])
        fresh = HistoricalLibrary()
        self.stager.replay_committed(fresh)
        rebound = compatibility_evidence(fresh,self.packet,self.raw,
                                         self.receipt,request())
        self.assertEqual(initial,rebound)
        self.assertEqual(initial["artifact_sha256"],rebound["artifact_sha256"])

    def test_no_unsourced_factory_report_or_work_readiness(self):
        item=self.evidence()
        factory=item["factory_work_contract"]["factory"]
        self.assertNotIn("attempt_id",factory)
        self.assertNotIn("feature_snapshot_sha256",factory)
        self.assertNotIn("scheduled_pairs",factory)
        self.assertIn("PINNED_PAIRED_SCHEDULE_AND_PAIR_ARM_CENSUS",factory["requires"])
        self.assertIn("INDEPENDENT_MANIFEST_AND_CHECKOUT_PIN",
                      item["factory_work_contract"]["work"]["requires"])


if __name__=="__main__":
    unittest.main()
