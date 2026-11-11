"""M18: exact calculation identity for multi-consumer indicator comparison.

A consumer MUST NOT treat matching indicator names or final candle alone as
same feature vector. Does not compute or change immutable indicator formulas.
"""
import hashlib
import json


_FIELDS = ("indicator_id", "version", "parameter_set", "dataset_id",
           "dataset_version", "dataset_manifest_hash", "decision_cutoff_ms",
           "start_ms", "end_ms", "warmup_policy", "input_bar_hash",
           "result_hashes", "output_fields")


def calculation_identity(manifest):
    """Strict digest of the complete frozen VectorManifest metadata."""
    if not isinstance(manifest, dict) or any(k not in manifest for k in _FIELDS):
        raise ValueError("Missing frozen calculation provenance")
    # Include the full known metadata; unknown fields cannot be silently
    # discarded when they could change feature meaning.
    payload = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    if not isinstance(payload["result_hashes"], list) or not payload["result_hashes"]:
        raise ValueError("Missing vector results")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_same_calculation(scanner_manifest, decision_manifest):
    left = calculation_identity(scanner_manifest)
    right = calculation_identity(decision_manifest)
    if left != right:
        raise ValueError("M18 calculation window/seed/vector identity mismatch")
    return left
