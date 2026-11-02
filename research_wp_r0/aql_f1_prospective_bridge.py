"""Explicit prospective C2 -> original F1 insertion point, before F3.

The existing P0 C2 producer is RETROSPECTIVE_NON_PIT. This bridge refuses it.
Hosts must freeze each genuine arm decision BEFORE any downstream or post-cutoff
read. The bridge persists candidates; it does not forge source/anchor authority.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .aql_f1_decision_capture_v1 import (
    ARMS, C2_FIELDS, CaptureError, _fields, _fail, _is_hash, digest,
    duplicate_keys_reject, jcs_bytes, status_slots, validate_f1,
)

def capture_prospective_pair(
    c2: Mapping[str,Any],
    plan_sha: str,
    arm_records: Mapping[str,Mapping[str,Any]|None],
    registry: Mapping[str,str],
    journal_dir: Path,
) -> list[dict]:
    """Pre-F3 host seam: preserve BASE/SHADOW even when one arm is missing.

    A caller must supply actual frozen original decision payloads. Without
    independently verifiable publication, clock ordering and an external
    durable anchor, structurally valid candidates remain UNVERIFIED.
    This local JSONL journal is sequential only: concurrency-safe external
    custody and original PIT attestation are NOT implemented here.
    """
    if c2.get("availability_mode")!="PROSPECTIVE_CAPTURE":
        _fail("PROSPECTIVE_ONLY_HISTORICAL_C2_REJECTED")
    if not _is_hash(plan_sha) or set(arm_records)!=set(ARMS):
        _fail("PREREGISTERED_PLAN_OR_ARMS_MISSING")
    original={k:c2.get(k) for k in C2_FIELDS}
    _fields(original,C2_FIELDS,"C2")
    if any(not isinstance(original[k],str) or not original[k] for k in C2_FIELDS):
        _fail("C2_IDENTITY_MISSING")
    pair=digest({"experiment_plan_sha256":plan_sha,"c2_identity":original})
    candidates={}
    directory=Path(journal_dir)
    directory.mkdir(parents=True,exist_ok=True)
    for arm in ARMS:
        record=arm_records[arm]
        if record is None:
            continue
        validate_f1(dict(record),dict(registry))
        if record["arm"]!=arm or record["pair_id"]!=pair or record["c2_identity"]!=original:
            _fail("ARM_C2_PAIR_MISMATCH")
        if record["decision_cutoff_ms"]!=c2.get("decision_cutoff_ms"):
            _fail("C2_CUTOFF_MISMATCH")
        for field in ("run_manifest_sha256","prefix_end_exclusive_ms",
                      "prefix_bar_checksums_sha256","gap_inventory_sha256","correction_lineage_sha256"):
            if record[field]!=c2.get(field):
                _fail("C2_SOURCE_PREFIX_MISMATCH_"+field)
        path=directory/(arm.lower()+".jsonl")
        data=jcs_bytes(dict(record))+b"\n"
        # Sequential retry detection: identical original is idempotent.
        # Conflicting same-slot bytes are rejected, never last-write-wins.
        if path.exists():
            existing=[]
            for line in path.read_bytes().splitlines():
                try:
                    item=json.loads(line,object_pairs_hook=duplicate_keys_reject)
                    if not isinstance(item,dict): _fail("JOURNAL_RECORD_INVALID")
                    existing.append(item)
                except (ValueError,UnicodeError,TypeError) as exc:
                    raise CaptureError("JOURNAL_CORRUPT") from exc
            for prior in existing:
                if prior.get("pair_id")==pair and prior.get("arm")==arm:
                    if jcs_bytes(prior)==data.rstrip(b"\n") and prior["producer_sequence"]==record["producer_sequence"]:
                        candidates[(pair,arm)]=[record]
                        break
                    _fail("JOURNAL_SAME_SLOT_CONFLICT")
            if (pair,arm) in candidates:
                continue
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        try:
            if os.write(fd,data)!=len(data): _fail("JOURNAL_SHORT_WRITE")
            os.fsync(fd)
        finally:
            os.close(fd)
        if data not in path.read_bytes().splitlines(keepends=True):
            _fail("JOURNAL_READBACK_MISSING")
        candidates[(pair,arm)]=[record]
    return status_slots([original],plan_sha,candidates,dict(registry))
