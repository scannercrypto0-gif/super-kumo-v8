"""Focused synthetic P0 ZIP schema hardening tests; no historical strategy replay."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from research_wp_r0.aql_w1_original_p0_zip_adapter import verify_p0_zip, canonical, sha
from research_wp_r0.aql_w1_opportunity_outcomes import EvidenceError


class P0ZipHardeningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "p0.zip"
        self.summary = dict(source_sha256="source", run_manifest_sha256="manifest",
                            policy_id="policy", strategy_id="strategy",
                            assumptions_digest="assumptions")
        self.envelopes = []
        self.acks = []
        self.receipts = {}
        for i in range(653):
            identity = dict(trial_id="trial", opportunity_id="opp-%03d" % i,
                            producer_event_id="producer-%03d" % i,
                            envelope_sha256="")
            env = {**identity, "run_manifest_sha256": "manifest"}
            env["envelope_sha256"] = sha(canonical({k: v for k, v in env.items() if k != "envelope_sha256"}))
            self.envelopes.append(env)
            identity["envelope_sha256"] = env["envelope_sha256"]
            disposition = "NO_SIGNAL" if i < 616 else ("REJECTED" if i < 643 else "TRIGGERED")
            receipt = {**identity, "run_manifest_sha256": "manifest",
                       "policy_id": "policy", "strategy_digest": "strategy-digest",
                       "assumptions_digest": "assumptions", "effect_disposition": disposition}
            receipt["receipt_sha256"] = sha(canonical(receipt))
            raw = canonical(receipt)
            self.receipts["consumer_receipts\\%s.json" % identity["producer_event_id"]] = raw
            for state in ("PENDING", "APPLIED", "ACKED"):
                row = {**identity, "state": state, "source_bytes_sha256": "source",
                       "run_manifest_sha256": "manifest", "policy_id": "policy",
                       "strategy_digest": "strategy-digest", "assumptions_digest": "assumptions"}
                if state == "ACKED":
                    row["consumer_receipt_hash"] = sha(raw)
                self.acks.append(row)

    def make_zip(self, *, mutate=None, duplicate_zip=False):
        files = dict(self.receipts)
        files.update({
            "core_decision_envelopes.json": canonical(self.envelopes),
            "core_run_summary.json": canonical(self.summary),
            "core_c2_journal_ack_copy.jsonl": b"".join(canonical(row) + b"\n" for row in self.acks),
            "core_c2_journal.jsonl": b"original",
            "factory_report.json": b"{}",
            "consumer_receipts\\financial_receipts.jsonl": b"",
        })
        if mutate:
            mutate(files)
        ledger = [{"Path": name, "SHA256": sha(raw)} for name, raw in sorted(files.items())]
        files["audit_file_hashes.json"] = canonical(ledger)
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, raw in files.items():
                z.writestr(name, raw)
            if duplicate_zip:
                z.writestr("factory_report.json", b"{}")
        return sha(self.path.read_bytes())

    def check(self, **kwargs):
        anchor = self.make_zip(**kwargs)
        return verify_p0_zip(self.path, independently_recorded_zip_sha256=anchor)

    def test_valid_synthetic_complete_link(self):
        result = self.check()
        self.assertEqual(result["receipt_count"], 653)
        self.assertEqual(result["manifest_authority"], "REFERENCE_ONLY_NO_STANDALONE_MANIFEST_BYTES")

    def test_duplicate_zip_member_rejected(self):
        with self.assertRaises(EvidenceError):
            self.check(duplicate_zip=True)

    def test_missing_envelope_identity_rejected(self):
        self.envelopes[0]["opportunity_id"] = ""
        with self.assertRaises(EvidenceError):
            self.check()

    def test_missing_ack_identity_rejected(self):
        self.acks[0]["trial_id"] = None
        with self.assertRaises(EvidenceError):
            self.check()

    def test_missing_receipt_policy_rejected(self):
        name = next(iter(self.receipts))
        obj = json.loads(self.receipts[name])
        obj["policy_id"] = None
        obj["receipt_sha256"] = sha(canonical({k: v for k, v in obj.items() if k != "receipt_sha256"}))
        self.receipts[name] = canonical(obj)
        with self.assertRaises(EvidenceError):
            self.check()

    def test_missing_ledger_member_rejected(self):
        def remove(files):
            files.pop("factory_report.json")
        with self.assertRaises(EvidenceError):
            self.check(mutate=remove)

    def test_wrong_external_anchor_rejected(self):
        self.make_zip()
        with self.assertRaises(EvidenceError):
            verify_p0_zip(self.path, independently_recorded_zip_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
