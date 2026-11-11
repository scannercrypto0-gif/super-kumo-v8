"""R2 fail-closed Core capability -> Factory boundary.

A disconnected capability probe is NOT a scheduled opportunity or an F3
observation. This module does not ingest market data or activate any producer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

CORE_R2_SHA = "40039ba29c8a63917f66e22e904eca09f2f5554e"
CORE_ARTIFACT_ID = 13124055354
CORE_MEMBER_SHA256 = "7efbf04f32e4624dc20676be4d0344ba2e62397fe3e48c18c39b1e70799e34a9"
SCHEMA = "aql.r2-original-decision-ingress.v1"
ARMS = {"BASE": "MISSING_CAPTURE", "SHADOW": "MISSING_CAPTURE"}
SENTINEL = "NOT_CONNECTED_NO_REAL_G2_EVENT"


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("R2_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def consume_capability(raw: bytes, *, enforce_core_pin: bool = True) -> dict:
    if enforce_core_pin and hashlib.sha256(raw).hexdigest() != CORE_MEMBER_SHA256:
        raise ValueError("R2_CORE_CAPABILITY_SHA_DRIFT")
    try:
        obj = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("R2_NONFINITE")))
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("R2_INVALID_JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {
        "schema_version", "connection_status", "proof_status",
        "reason_code", "opportunity_id", "arm_statuses",
    }:
        raise ValueError("R2_CAPABILITY_FIELDS_OR_FORGED_EVENT")
    if obj["schema_version"] != SCHEMA or obj["connection_status"] != "NOT_CONNECTED":
        raise ValueError("R2_CAPABILITY_SCHEMA_OR_CONNECTION")
    if (obj["proof_status"] != "BLOCKED_EXTERNAL_EVIDENCE"
            or obj["reason_code"] != "ORIGINAL_G2_PRODUCER_NOT_CONNECTED"):
        raise ValueError("R2_FALSE_PROOF")
    if obj["opportunity_id"] != SENTINEL or obj["arm_statuses"] != ARMS:
        raise ValueError("R2_FAKE_SCHEDULE_OR_ARM")
    return {
        "schema_version": "aql.r2-factory-capability-evaluation.v1",
        "core_head_sha": CORE_R2_SHA,
        "core_capability_sha256": hashlib.sha256(raw).hexdigest(),
        "connection_status": "NOT_CONNECTED",
        "original_g2_event_count": 0,
        "scheduled_opportunity_count": 0,
        "scheduled_denominator_status": "NOT_SUPPLIED",
        "market_observation_count": 0,
        "outcome_rows_4h_24h_72h": {"4h": 0, "24h": 0, "72h": 0},
        "f3_monitor_status": "NOT_CONNECTED",
        "directional_evaluation_status": "NOT_EVALUABLE",
        "proof_status": "BLOCKED_EXTERNAL_EVIDENCE",
        "directional_mfe_mae": None,
        "tp_sl": None,
        "fills_pnl": None,
        "paired_uplift": None,
        "reason_code": "ORIGINAL_G2_PRODUCER_NOT_CONNECTED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-capability", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = consume_capability(args.core_capability.read_bytes())
    encoded = (json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.out, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        if os.write(fd, encoded) != len(encoded):
            raise OSError("R2_SHORT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
    if args.out.read_bytes() != encoded:
        raise OSError("R2_READBACK_MISMATCH")
    print("sha256=" + hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    main()
