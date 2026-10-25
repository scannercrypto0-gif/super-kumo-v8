"""Deterministic offline INPUTS receipt audit, not a trading evaluator.

This layer never produces fills, PnL, COMPLETE or a custody attestation.
"""
import hashlib
from .strategy_definition import canonical, keys
from .historical_evaluation_bridge import OfflineInputs


def audit_offline_inputs(inputs, *, expected_digest):
    """Fail closed on missing/tampered receipts; return reproducible audit hash."""
    if not isinstance(inputs, OfflineInputs):
        raise ValueError("OfflineInputs required")
    if type(expected_digest) is not str or len(expected_digest) != 64:
        raise ValueError("Separately retained input digest required")
    if inputs.digest != expected_digest:
        raise ValueError("Input commitment mismatch")
    spec = inputs.spec
    keys(spec, "schema_version state strategy protocol protocol_digest binding dataset_manifest bars independent_custody")
    if spec["schema_version"] != "research-input-1" or spec["state"] != "INPUTS_ONLY_NOT_EVALUATED":
        raise ValueError("Only unevaluated input receipts accepted")
    if spec["independent_custody"] != "NOT_VERIFIED":
        raise ValueError("Custody cannot be self-attested")
    from .strategy_definition import digest
    if digest(spec["protocol"]) != spec["protocol_digest"]:
        raise ValueError("Protocol digest mismatch")
    keys(spec["strategy"], "definition digest")
    if digest(spec["strategy"]["definition"]) != spec["strategy"]["digest"]:
        raise ValueError("Strategy digest mismatch")
    keys(spec["binding"], "binding digest")
    binding = spec["binding"]["binding"]
    if digest(binding) != spec["binding"]["digest"]:
        raise ValueError("Binding digest mismatch")
    if binding["strategy_digest"] != spec["strategy"]["digest"]:
        raise ValueError("Strategy/binding mismatch")
    manifest = spec["dataset_manifest"]
    if binding["dataset_id"] != manifest["dataset_id"] or binding["dataset_version"] != manifest["version"]:
        raise ValueError("Dataset identity mismatch")
    if binding["dataset_manifest_hash"] != manifest["manifest_integrity_hash"]:
        raise ValueError("Manifest commitment mismatch")
    bars = spec["bars"]
    if type(bars) is not list or not bars or len(bars) != len(binding["bar_checksums"]):
        raise ValueError("Missing or partial bar receipts")
    for row, checksum in zip(bars, binding["bar_checksums"]):
        if type(row) is not dict or row.get("checksum") != checksum:
            raise ValueError("Bar checksum mismatch")
        if row.get("quality") != "FINAL" or row.get("availability_kind") != "CONFIRMED":
            raise ValueError("Unconfirmed bar")
        if type(row.get("observation_cutoff_ms")) is not int or row["observation_cutoff_ms"] > binding["decision_cutoff_ms"]:
            raise ValueError("Future bar receipt")
        if type(row.get("ingest_time_ms")) is not int or row["ingest_time_ms"] > row["observation_cutoff_ms"]:
            raise ValueError("Missing or inconsistent ingestion")
    return {"status": "INPUTS_AUDITED_NOT_EVALUATED", "inputs_digest": inputs.digest,
            "audit_sha256": hashlib.sha256(canonical({"schema": "sf-input-audit-1",
                                                       "inputs_digest": inputs.digest})).hexdigest(),
            "independent_custody_verified": False}
