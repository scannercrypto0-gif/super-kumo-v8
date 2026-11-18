"""Focused synthetic tests of original-byte adapter; not original P0 evidence."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_w1_original_p0_readonly_link import verify_original_linkage
from research_wp_r0.aql_w1_opportunity_outcomes import EvidenceError


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class OriginalLinkAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = dict(trial_id="trial", opportunity_id="opp",
                             producer_event_id="producer", envelope_sha256="envelope")
        self.receipt = dict(self.identity, pointer="r-1", source="s1",
                            policy="p1", generation="original")
        self.ack = dict(self.identity, receipt_pointer="r-1", source="s1")
        self.manifest = dict(source="s1", policy="p1", generation="original")
        self.fields = {
            **{"receipt_" + k: k for k in self.identity},
            **{"ack_" + k: k for k in self.identity},
            "receipt_pointer": "pointer",
            "receipt_source_version": "source",
            "receipt_policy_version": "policy",
            "receipt_correction_generation": "generation",
            "ack_receipt_pointer": "receipt_pointer",
            "ack_source_version": "source",
            "manifest_source_version": "source",
            "manifest_policy_version": "policy",
            "manifest_correction_generation": "generation",
        }

    def run_adapter(self, *, receipt=None, ack=None, manifest=None,
                    bad_anchor=False, fields=None):
        receipt = self.receipt if receipt is None else receipt
        ack = self.ack if ack is None else ack
        manifest = self.manifest if manifest is None else manifest
        blobs = {
            "receipt": json.dumps(receipt).encode(),
            "ack_copy": (json.dumps(ack) + "\n").encode(),
            "manifest": json.dumps(manifest).encode(),
        }
        paths = {}
        for name, raw in blobs.items():
            p = self.root / (name + ".json")
            p.write_bytes(raw)
            paths[name] = p
        anchors = {name + "_sha256": digest(raw) for name, raw in blobs.items()}
        if bad_anchor:
            anchors["receipt_sha256"] = "0" * 64
        return verify_original_linkage(
            receipt_path=paths["receipt"], ack_copy_path=paths["ack_copy"],
            manifest_path=paths["manifest"], anchors=anchors,
            fields=self.fields if fields is None else fields,
            expected_identity=self.identity)

    def test_structural_link_only(self):
        result = self.run_adapter()
        self.assertEqual(result["ack_authority"], "ISOLATED_COPY_ONLY_NOT_RUNTIME_ACK")
        self.assertEqual(result["f1_original"], "NOT_RECORDED_IN_P0")

    def test_independent_anchor_mismatch(self):
        with self.assertRaises(EvidenceError):
            self.run_adapter(bad_anchor=True)

    def test_wrong_ack_pointer(self):
        with self.assertRaises(EvidenceError):
            self.run_adapter(ack={**self.ack, "receipt_pointer": "other"})

    def test_wrong_ack_identity(self):
        with self.assertRaises(EvidenceError):
            self.run_adapter(ack={**self.ack, "opportunity_id": "other"})

    def test_wrong_manifest_policy(self):
        with self.assertRaises(EvidenceError):
            self.run_adapter(manifest={**self.manifest, "policy": "other"})

    def test_missing_original_schema_mapping(self):
        fields = dict(self.fields)
        del fields["receipt_pointer"]
        with self.assertRaises(EvidenceError):
            self.run_adapter(fields=fields)


if __name__ == "__main__":
    unittest.main()
