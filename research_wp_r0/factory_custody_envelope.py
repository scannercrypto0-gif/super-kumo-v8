"""Independent-custody checkpoint envelope for Factory research integrity.

This module prepares/verifies portable custody evidence. It does not upload,
secure, or independently retain it: the owner must store the envelope outside
the writer's permissions (for example on separately controlled backup media).
"""
import hashlib
import json

from .strategy_definition import canonical


def custody_envelope(*, plan_digest, ledger_checkpoint):
    if not isinstance(plan_digest, str) or len(plan_digest) != 64:
        raise ValueError("Expected 64-character frozen plan digest")
    try:
        bytes.fromhex(plan_digest)
    except ValueError as exc:
        raise ValueError("Invalid plan digest") from exc
    if not isinstance(ledger_checkpoint, (tuple, list)) or len(ledger_checkpoint) != 2:
        raise ValueError("Expected sequence/hash ledger checkpoint")
    seq, chain = ledger_checkpoint
    if type(seq) is not int or seq < 0 or not isinstance(chain, str) or len(chain) != 64:
        raise ValueError("Invalid ledger checkpoint")
    try:
        bytes.fromhex(chain)
    except ValueError as exc:
        raise ValueError("Invalid checkpoint digest") from exc
    body = {"schema_version": "1", "plan_digest": plan_digest,
            "ledger_sequence": seq, "ledger_chain_hash": chain}
    body_digest = hashlib.sha256(b"AQL:FACTORY-CUSTODY:1\0" + canonical(body)).hexdigest()
    return canonical({**body, "envelope_digest": body_digest})


def verify_custody_envelope(raw, *, plan_digest, ledger_checkpoint):
    if not isinstance(raw, bytes) or len(raw) > 4096:
        raise ValueError("Canonical custody envelope bytes required")
    expected = custody_envelope(plan_digest=plan_digest, ledger_checkpoint=ledger_checkpoint)
    if raw != expected:
        raise ValueError("Custody evidence mismatch")
    return json.loads(raw)
