"""Issue #237: bounded authentic-source admission boundary, TEST_ONLY data.

No private historical source is in this fixture. Hash, temporal and correction
tests verify code behavior only, not provenance or prospective PIT.
"""
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest

from research_wp_r0.aql_authenticated_historical_admission_v1 import (
    ADMISSION_SCHEMA, PIN_SCHEMA, SourceAdmissionError,
    admit_original_bytes, source_not_available,
)
from research_wp_r0.aql_archive_custody_bridge_v1 import (
    BridgeError, OfflineBridgeStager, raw_sha,
)
from research_wp_r0.historical_library import HistoricalLibrary
from test_aql_archive_custody_bridge_v1 import (
    H, START, WIDTH, N, archive_payload, spec,
)


def pin(raw, **updates):
    result = {
        "schema": PIN_SCHEMA, "source_kind": "SEALED_ARCHIVE_QUERY",
        "original_object_id": "TEST_ARCHIVE_0001",
        "original_sha256": raw_sha(raw),
        "provenance_reference": "TEST_ONLY_UNVERIFIED",
        "captured_at_ms": START+N*WIDTH+10000,
        "claimed_available_at_ms": None,
        "expected_inventory_sha256": H,
        "vault_object_metadata": None,
        "universe_manifest_sha256": None,
        "universe_member_count": None,
        "test_only": True,
    }
    result.update(updates)
    return result


class AuthenticHistoricalAdmissionGate(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stager=OfflineBridgeStager(self.tmp.name)
        self.library=HistoricalLibrary()
        self.raw=archive_payload()
        self.spec=spec()

    def admit(self, *, raw=None, source_pin=None, data_spec=None, cutoff=None):
        return admit_original_bytes(
            self.raw if raw is None else raw,
            pin(self.raw) if source_pin is None else source_pin,
            self.spec if data_spec is None else data_spec,
            stager=self.stager,library=self.library,
            decision_cutoff_ms=(START+N*WIDTH+2000 if cutoff is None else cutoff),
        )

    def test_missing_original_source_is_explicitly_not_connected(self):
        response=admit_original_bytes(
            None,None,{"dataset_id":"TEST_ONLY_BTCUSDT"},
            stager=None,library=None,decision_cutoff_ms=START,
        )
        self.assertEqual(response,source_not_available("TEST_ONLY_BTCUSDT"))
        self.assertEqual(response["status"],"SOURCE_NOT_AVAILABLE")
        self.assertIsNone(response["query"])
        self.assertEqual(response["factory_scientific_input"],"BLOCKED")

    def test_actual_bridge_stage_register_query_deterministic_and_no_auth_upgrade(self):
        first=self.admit()
        second=self.admit()
        self.assertEqual(first,second)
        self.assertEqual(first["schema"],ADMISSION_SCHEMA)
        self.assertEqual(first["status"],"TEST_ONLY_INTEGRITY_VERIFIED")
        self.assertEqual(first["source_bytes_sha256"],raw_sha(self.raw))
        self.assertEqual(first["coverage"],"COMPLETE")
        self.assertEqual(first["available_bar_count"],N)
        self.assertEqual(first["query"]["result"]["status"],"COMPLETE")
        self.assertEqual(first["query"]["result"]["available_bar_count"],N)
        self.assertEqual(first["underlying_availability_class"],"SYNTHETIC_TEST")
        self.assertEqual(first["authenticated_source"],"NOT_ATTESTED")
        self.assertEqual(first["confirmed_pit"],"NOT_ATTESTED")
        self.assertEqual(first["complete_market_universe"],"NOT_ATTESTED")
        self.assertEqual(first["work_authentic_e2e"],"NOT_CONNECTED")
        self.assertEqual(first["factory_scientific_input"],"BLOCKED")

    def test_original_bytes_sha_and_forged_source_pin_rejected(self):
        with self.assertRaisesRegex(SourceAdmissionError,"ORIGINAL_BYTE_SHA_MISMATCH"):
            self.admit(raw=self.raw+b"\n")
        with self.assertRaisesRegex(SourceAdmissionError,"ORIGINAL_BYTE_SHA_MISMATCH"):
            self.admit(source_pin=pin(self.raw,original_sha256="0"*64))
        with self.assertRaises(BridgeError):
            altered=archive_payload(mutation=2)
            self.admit(raw=altered,source_pin=pin(altered,expected_inventory_sha256="b"*64))

    def test_future_claim_unsupported_provenance_or_false_test_scope_rejected(self):
        with self.assertRaisesRegex(SourceAdmissionError,"CLAIMED_SOURCE_UNAVAILABLE"):
            self.admit(source_pin=pin(self.raw,claimed_available_at_ms=START+N*WIDTH+9000))
        with self.assertRaisesRegex(SourceAdmissionError,"SOURCE_TEST_CLASS_MISMATCH"):
            self.admit(source_pin=pin(self.raw,test_only=False))
        with self.assertRaisesRegex(SourceAdmissionError,"SOURCE_IDENTITY_REQUIRED"):
            self.admit(source_pin=pin(self.raw,provenance_reference="../private/key"))
        with self.assertRaisesRegex(SourceAdmissionError,"UNIVERSE_COUNT_UNANCHORED"):
            self.admit(source_pin=pin(self.raw,universe_member_count=5))
        with self.assertRaisesRegex(SourceAdmissionError,"INVALID_PIN_FIELDS"):
            self.admit(source_pin={**pin(self.raw),"claimed_pit":True})

    def test_partial_unknown_and_no_cutoff_promotion(self):
        partial=self.admit(cutoff=START+WIDTH+1000)
        self.assertEqual(partial["coverage"],"PARTIAL")
        self.assertEqual(partial["available_bar_count"],1)
        self.assertEqual(len(partial["missing_bar_opens"]),N-1)
        unknown=self.admit(cutoff=START)
        self.assertEqual(unknown["coverage"],"UNKNOWN")
        self.assertEqual(unknown["available_bar_count"],0)
        self.assertEqual(len(unknown["missing_bar_opens"]),N)
        self.assertEqual(unknown["underlying_availability_class"],
                         "RETROSPECTIVE_NOT_PIT")
        self.assertEqual(unknown["confirmed_pit"],"NOT_ATTESTED")
        self.assertEqual(unknown["factory_scientific_input"],"BLOCKED")

    def test_nonfinal_gap_duplicate_and_source_identity_adversarial(self):
        for raw in (archive_payload(gap=True),
                    archive_payload(nonfinal=True)):
            with self.subTest(kind=raw[:36]),self.assertRaises(BridgeError):
                self.admit(raw=raw,source_pin=pin(raw))
        with self.assertRaises(BridgeError):
            mutated=archive_payload(mutation=1)
            self.admit(raw=mutated,source_pin=pin(mutated,expected_inventory_sha256="0"*64))

    def test_corrected_version_source_lineage_replay_preserves_original(self):
        old=self.admit()
        corrected=archive_payload(mutation=4)
        v2=spec(version=2,parent_source_sha256=raw_sha(self.raw),
                correction_reason="TEST_ONLY_CORRECTION")
        result=self.admit(raw=corrected,
                          source_pin=pin(corrected,original_object_id="TEST_ARCHIVE_0002"),
                          data_spec=v2)
        self.assertEqual(result["version"],2)
        self.assertEqual(result["correction_parent_source_sha256"],raw_sha(self.raw))
        self.assertNotEqual(result["source_bytes_sha256"],old["source_bytes_sha256"])
        self.assertEqual(self.library.get_manifest(self.spec["dataset_id"],1).source_hash,
                         raw_sha(self.raw))
        fresh=HistoricalLibrary()
        self.stager.replay_committed(fresh)
        self.assertEqual(fresh.get_manifest(self.spec["dataset_id"],2).source_hash,
                         raw_sha(corrected))
        with self.assertRaises(BridgeError):
            self.admit(raw=archive_payload(mutation=5),
                       source_pin=pin(archive_payload(mutation=5)),
                       data_spec=v2)


if __name__=="__main__":
    unittest.main()
