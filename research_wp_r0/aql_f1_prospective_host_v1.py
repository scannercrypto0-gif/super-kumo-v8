"""Prospective F1 research host: serialized pre-F3 capture and immutable handoff.

No synthetic clock, source issuer, freeze authority or external custody is minted.
An injected verifier is not operational authority without independent auditing.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping

from .aql_f1_decision_capture_v1 import (
    ARMS, C2_FIELDS, CaptureError, digest, duplicate_keys_reject,
    jcs_bytes, status_slots, validate_f1,
)
from .aql_f1_parent_witness_v1 import make_parent_bound_provenance_verifier
from .aql_f1_prospective_bridge import capture_prospective_pair

try:
    import fcntl
except ImportError:
    fcntl = None


def _candidates(directory: Path, pair: str, registry: Mapping[str, str]) -> dict:
    result = {}
    for arm in ARMS:
        path = directory / (arm.lower() + ".jsonl")
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CaptureError("JOURNAL_PATH_UNSAFE")
        if not path.exists():
            continue
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            raise CaptureError("JOURNAL_TORN_WRITE")
        for line in data.splitlines():
            try:
                record = json.loads(line, object_pairs_hook=duplicate_keys_reject)
                validate_f1(record, dict(registry))
            except Exception as exc:
                raise CaptureError("JOURNAL_CORRUPT") from exc
            if record["arm"] != arm:
                raise CaptureError("JOURNAL_ARM_MISMATCH")
            if record["pair_id"] == pair:
                result.setdefault((pair, arm), []).append(record)
    return result


def _immutable(path: Path, data: bytes) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise CaptureError("HANDOFF_PATH_UNSAFE")
    if path.exists():
        if path.read_bytes() != data:
            raise CaptureError("IMMUTABLE_HANDOFF_CONFLICT")
        return
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise CaptureError("HANDOFF_SHORT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
    if path.read_bytes() != data:
        raise CaptureError("HANDOFF_READBACK_FAILED")
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run_prospective_host(
    c2: Mapping[str, Any],
    plan_sha: str,
    arm_records: Mapping[str, Mapping[str, Any] | None],
    registry: Mapping[str, str],
    journal_dir: Path,
    *,
    pre_f3_gate: Callable[[Mapping[str, Any]], bool],
    evidence_lookup: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    source_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    freeze_attestor: Callable[[Mapping[str, Any]], bool] | None = None,
    durable_anchor_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    parent_witness: Callable[[Mapping[str, Any]], bool] | None = None,
) -> dict:
    """Capture before invoking F3. pre_f3_gate MUST reflect real host lifecycle.

    POSIX flock protects only cooperating processes sharing the filesystem; no
    distributed exclusivity, independent timestamp or external durability.
    """
    if fcntl is None:
        raise CaptureError("POSIX_HOST_LOCK_REQUIRED")
    if c2.get("availability_mode") != "PROSPECTIVE_CAPTURE":
        raise CaptureError("PROSPECTIVE_ONLY_HISTORICAL_C2_REJECTED")
    if set(arm_records) != set(ARMS):
        raise CaptureError("BASE_SHADOW_SCHEDULE_REQUIRED")
    if not callable(pre_f3_gate):
        raise CaptureError("PRE_F3_GATE_REQUIRED")

    def gate() -> None:
        try:
            result = pre_f3_gate(c2)
        except Exception as exc:
            raise CaptureError("PRE_F3_GATE_UNAVAILABLE") from exc
        if result is not True:
            raise CaptureError("F3_ALREADY_STARTED_OR_GATE_DENIED")

    gate()
    identity = {field: c2.get(field) for field in C2_FIELDS}
    pair = digest({"experiment_plan_sha256": plan_sha, "c2_identity": identity})
    directory = Path(journal_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".host.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise CaptureError("LOCK_PATH_UNSAFE")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        gate()
        prior = _candidates(directory, pair, registry)
        for arm in ARMS:
            previous = prior.get((pair, arm), [])
            current = arm_records[arm]
            if len(previous) > 1:
                raise CaptureError("JOURNAL_SAME_SLOT_CONFLICT")
            if previous and current is None:
                raise CaptureError("RETRY_OMITS_PREVIOUS_CAPTURE")
            if previous and jcs_bytes(previous[0]) != jcs_bytes(dict(current)):
                raise CaptureError("JOURNAL_SAME_SLOT_CONFLICT")

        # Bridge checks exact source-prefix/cutoff/C2 identities before writing.
        capture_prospective_pair(c2, plan_sha, arm_records, registry, directory)
        candidates = _candidates(directory, pair, registry)
        verifier = None
        if evidence_lookup is not None:
            verifier = make_parent_bound_provenance_verifier(
                registry, evidence_lookup,
                source_attestor=source_attestor,
                freeze_attestor=freeze_attestor,
                durable_anchor_verifier=durable_anchor_verifier,
                parent_witness=parent_witness,
            )
        rows = status_slots([identity], plan_sha, candidates, dict(registry), verifier)
        result = {
            "schema_version": "aql.f1-prospective-host-handoff.v1",
            "pair_id": pair,
            "c2_identity": identity,
            "experiment_plan_sha256": plan_sha,
            "slots": rows,
            "original_record_sha256_by_arm": {
                arm: candidates[(pair, arm)][0]["f1_record_sha256"]
                if (pair, arm) in candidates else None for arm in ARMS
            },
            "proof_scope": "RESEARCH_ONLY_HOST_VERIFIER_NOT_TRUST_ROOT",
        }
        result["handoff_sha256"] = digest(result)
        _immutable(directory / (pair + ".handoff.json"), jcs_bytes(result) + b"\n")
        return result
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def capture_then_call_f3(
    *,
    f3_entrypoint: Callable[[dict], Any],
    **host_kwargs: Any,
) -> tuple[dict, Any]:
    """A control-flow seam: F3 receives only the frozen handoff after fsync.

    The actual prospective producer must call this wrapper in its F3 lifecycle.
    This wrapper is not itself evidence that a live producer has done so.
    """
    if not callable(f3_entrypoint):
        raise CaptureError("F3_ENTRYPOINT_REQUIRED")
    handoff = run_prospective_host(**host_kwargs)
    return handoff, f3_entrypoint(handoff)
