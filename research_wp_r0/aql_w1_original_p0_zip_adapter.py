"""P0 original-schema, read-only ZIP custody check. No runtime ACK/PIT claims."""
import hashlib
import json
import zipfile
from collections import Counter

from .aql_w1_opportunity_outcomes import EvidenceError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_p0_zip(path, *, independently_recorded_zip_sha256):
    """External anchor must be recorded independently of the supplied ZIP."""
    with open(path, "rb") as handle:
        archive_bytes = handle.read()
    if not independently_recorded_zip_sha256 or sha(archive_bytes) != independently_recorded_zip_sha256:
        raise EvidenceError("original ZIP independent SHA256 anchor mismatch")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise EvidenceError("duplicate ZIP member names")
        if len(names) != 660:
            raise EvidenceError("unexpected original ZIP member count")
        receipts = [n for n in names if n.replace("\\", "/").startswith("consumer_receipts/") and n.endswith(".json")]
        if len(receipts) != 653 or len(set(receipts)) != 653:
            raise EvidenceError("P0 original receipt denominator mismatch")
        ledger = json.loads(z.read("audit_file_hashes.json"))
        if not isinstance(ledger, list):
            raise EvidenceError("invalid original audit ledger")
        if len(ledger) != 659:
            raise EvidenceError("incomplete audit ledger")
        ledger_paths = set()
        for item in ledger:
            if not isinstance(item, dict):
                raise EvidenceError("invalid ledger item")
            # Original ledger keys are determined from actual artifact, not assumed here.
            filename = item.get("Path")
            expected = item.get("SHA256")
            if filename in ledger_paths:
                raise EvidenceError("duplicate audit ledger path")
            ledger_paths.add(filename)
            if not filename or not expected:
                raise EvidenceError("original ledger schema mismatch")
            if sha(z.read(filename)) != expected:
                raise EvidenceError("audit ledger file hash mismatch")
        if ledger_paths != set(names) - {"audit_file_hashes.json"}:
            raise EvidenceError("audit ledger incomplete member coverage")
        summary = json.loads(z.read("core_run_summary.json"))
        ack_rows = [json.loads(line) for line in z.read("core_c2_journal_ack_copy.jsonl").splitlines() if line.strip()]
        envelope_rows = json.loads(z.read("core_decision_envelopes.json"))
        if not isinstance(envelope_rows, list) or len(envelope_rows) != 653:
            raise EvidenceError("P0 envelope denominator mismatch")
        keys = ("trial_id", "opportunity_id", "producer_event_id", "envelope_sha256")
        if not isinstance(summary, dict):
            raise EvidenceError("invalid original Core summary")
        required_summary = ("source_sha256", "run_manifest_sha256", "policy_id", "strategy_id", "assumptions_digest")
        if any(not isinstance(summary.get(f), str) or not summary[f] for f in required_summary):
            raise EvidenceError("missing original Core summary authority fields")
        envelope_keys = set()
        for envelope in envelope_rows:
            if not isinstance(envelope, dict):
                raise EvidenceError("invalid original envelope object")
            identity = tuple(envelope.get(k) for k in keys)
            if any(not isinstance(v, str) or not v for v in identity) or identity in envelope_keys:
                raise EvidenceError("missing or duplicate original envelope identity")
            if sha(canonical({k: v for k, v in envelope.items() if k != "envelope_sha256"})) != envelope["envelope_sha256"]:
                raise EvidenceError("original envelope canonical digest mismatch")
            if envelope.get("run_manifest_sha256") != summary["run_manifest_sha256"]:
                raise EvidenceError("original envelope manifest mismatch")
            envelope_keys.add(identity)
        grouped = {}
        for row in ack_rows:
            key = tuple(row.get(k) for k in keys)
            if any(not isinstance(v, str) or not v for v in key):
                raise EvidenceError("missing original ACK identity")
            grouped.setdefault(key, []).append(row)
        if len(grouped) != 653:
            raise EvidenceError("P0 ACK identity denominator mismatch")
        counts = Counter()
        for name in receipts:
            raw = z.read(name)
            obj = json.loads(raw)
            embedded = obj.get("receipt_sha256")
            if sha(canonical({k: v for k, v in obj.items() if k != "receipt_sha256"})) != embedded:
                raise EvidenceError("P0 canonical embedded receipt digest mismatch")
            key = tuple(obj.get(k) for k in keys)
            if any(not isinstance(v, str) or not v for v in key):
                raise EvidenceError("missing original receipt identity")
            if key not in envelope_keys:
                raise EvidenceError("orphan original receipt without envelope")
            envelope_keys.remove(key)
            rows = grouped.pop(key, None)
            if not rows or Counter(r.get("state") for r in rows) != Counter({"PENDING": 1, "APPLIED": 1, "ACKED": 1}):
                raise EvidenceError("P0 ACK lifecycle mismatch")
            ack = next(r for r in rows if r["state"] == "ACKED")
            if ack.get("consumer_receipt_hash") != sha(raw):
                raise EvidenceError("P0 ACK full receipt byte hash mismatch")
            for field in ("run_manifest_sha256", "policy_id", "strategy_digest", "assumptions_digest"):
                if not isinstance(obj.get(field), str) or not obj[field]:
                    raise EvidenceError("missing original receipt authority field")
                if any(r.get(field) != obj.get(field) for r in rows):
                    raise EvidenceError("P0 receipt/ACK metadata mismatch")
            if ack.get("source_bytes_sha256") != summary.get("source_sha256"):
                raise EvidenceError("P0 source digest mismatch")
            if obj.get("run_manifest_sha256") != summary.get("run_manifest_sha256"):
                raise EvidenceError("P0 manifest reference mismatch")
            counts[obj.get("effect_disposition")] += 1
        if grouped or envelope_keys:
            raise EvidenceError("P0 orphan ACK records")
        if counts != Counter({"NO_SIGNAL": 616, "REJECTED": 27, "TRIGGERED": 10}):
            raise EvidenceError("P0 F3 disposition mismatch")
        return {"status": "ORIGINAL_ZIP_INTERNALLY_LINKED_ANCHORED",
                "archive_sha256": sha(archive_bytes), "receipt_count": 653,
                "ack_copy_rows": len(ack_rows), "ledger_count": len(ledger),
                "f3_descriptive": dict(sorted(counts.items())),
                "ack_authority": "ISOLATED_ACK_COPY_NOT_RUNTIME_ACK",
                "manifest_authority": "REFERENCE_ONLY_NO_STANDALONE_MANIFEST_BYTES",
                "original_f1": "NOT_RECORDED_IN_P0",
                "research_only": True}
