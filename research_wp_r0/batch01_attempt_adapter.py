"""Synthetic Batch 01 -> frozen AttemptLedger PENDING admission, no execution.

A candidate inventory check is not a trusted custody receipt. This adapter
only admits explicit synthetic attempts into the existing sealed plan ledger.
"""
from .batch01_admission_bridge import check_synthetic_batch_manifest
from .frozen_attempt_writer import FrozenAttemptWriter
from .strategy_definition import canonical, digest, identifier


def register_synthetic_batch_attempt(ledger, raw_plan, expected_plan_digest,
                                     manifest, *, candidate_id, input_commitment):
    """Append a PENDING attempt or raise; never fabricate COMPLETE results.

    input_commitment is a caller-owned immutable input description, not a
    custody attestation. Replays of the same identity are ledger-idempotent.
    """
    gate = check_synthetic_batch_manifest(raw_plan, expected_plan_digest, manifest)
    identifier(candidate_id)
    if type(input_commitment) is not dict or set(input_commitment) != {
        "data_class", "dataset_digest", "split_digest", "protocol_digest",
        "candidate_id", "input_version",
    }:
        raise ValueError("Explicit bounded input commitment required")
    if input_commitment["data_class"] != "SYNTHETIC_TEST":
        raise ValueError("Historical inputs not supported")
    if input_commitment["candidate_id"] != candidate_id:
        raise ValueError("Input candidate identity mismatch")
    identifier(input_commitment["input_version"])
    for key in ("dataset_digest", "split_digest", "protocol_digest"):
        if input_commitment[key] != manifest[key]:
            raise ValueError("Input provenance differs from frozen plan")
    # Validate/canonicalize before any durable ledger enrollment.
    canonical(input_commitment)
    matches = [row for row in manifest["candidates"]
               if row["candidate_id"] == candidate_id]
    if len(matches) != 1:
        raise ValueError("Candidate not in frozen synthetic inventory")
    input_digest = digest({"schema_version": "batch01-input-1",
                           "plan_digest": gate["plan_digest"],
                           "manifest_digest": gate["manifest_digest"],
                           "input": input_commitment})
    writer = FrozenAttemptWriter(ledger, raw_plan, expected_plan_digest)
    checkpoint = writer.record_attempt({
        "state": "PENDING",
        "family_id": manifest["family_id"],
        "candidate_id": candidate_id,
        "input_digest": input_digest,
        "strategy_digest": matches[0]["strategy_digest"],
    })
    return {"checkpoint": checkpoint, "input_digest": input_digest,
            "candidate_id": candidate_id, "state": "PENDING",
            "data_class": "SYNTHETIC_TEST",
            "evaluated": False, "external_custody_verified": False,
            "holdout_opened": False}
