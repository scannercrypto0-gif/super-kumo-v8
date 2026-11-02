"""R4 nontrading evaluation-time host with immutable predecision schedule.

This is a caller-invoked host: no background runner, market subscription,
independent clock, issuer witness, F3 or broker. It may run on offline input,
which MUST remain RETROSPECTIVE_NON_PIT and never be called original G2 PIT.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .aql_f1_decision_capture_v1 import CaptureError, digest, jcs_bytes
from .aql_r3_breakout_closed_prefix import evaluate_breakout_closed_prefix

ARMS = ("BASE", "SHADOW")
C2_FIELDS = ("trial_id", "opportunity_id", "producer_event_id", "envelope_sha256")
PINS = ("source_id", "source_version", "source_bytes_sha256",
        "correction_generation", "strategy_id", "strategy_version",
        "feature_snapshot_sha256", "regime_snapshot_sha256")
SCHEMA = "aql.r4-nontrading-evaluation-host.v1"
SCHEDULE_SCHEMA = "aql.r4-predecision-schedule.v1"


def _write_once(path: Path, data: bytes) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise CaptureError("R4_UNSAFE_FILE")
    if path.exists():
        if path.read_bytes() != data:
            raise CaptureError("R4_IMMUTABLE_CONFLICT")
        return
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise CaptureError("R4_SHORT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
    if path.read_bytes() != data:
        raise CaptureError("R4_READBACK_MISMATCH")
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _read_same(path: Path, doc: dict) -> None:
    raw = path.read_bytes()
    if raw != jcs_bytes(doc) + b"\n":
        raise CaptureError("R4_SCHEDULE_TAMPER")


def invoke_g2_nontrading(
    *, c2_identity: Mapping[str, Any], experiment_plan_sha256: str,
    decision_cutoff_ms: int, scheduled_at_ms: int,
    availability_mode: str, pins: Mapping[str, str],
    bars_provider: Callable[[], Sequence[Sequence[Any]]],
    directory: Path,
    source_available_at_ms: int | None = None,
    original_f1_records: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict:
    """Schedule+fsync BASE/SHADOW before invoking a callable bar provider.

    Records are local software history, not independent receipt/PIT evidence.
    Never maps ARMED to TRIGGERED. Without authentic F1 records, F1 is blocked.
    """
    if availability_mode not in ("RETROSPECTIVE_NON_PIT", "PROSPECTIVE_CAPTURE"):
        raise CaptureError("R4_MODE_INVALID")
    if set(c2_identity) != set(C2_FIELDS) or not all(
            isinstance(c2_identity[k], str) and c2_identity[k]
            for k in C2_FIELDS):
        raise CaptureError("R4_C2_IDENTITY_INVALID")
    if set(pins) != set(PINS) or any(not isinstance(v, str) or not v for v in pins.values()):
        raise CaptureError("R4_PINS_MISSING")
    if (pins["strategy_id"] != "SF_BREAKOUT_BASE_20_10_DEV_v1" or
            pins["strategy_version"] != "1"):
        raise CaptureError("R4_STRATEGY_VERSION_DRIFT")
    hashes = ("envelope_sha256", "source_bytes_sha256",
              "feature_snapshot_sha256", "regime_snapshot_sha256")
    for field in hashes:
        value = c2_identity[field] if field in c2_identity else pins[field]
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise CaptureError("R4_SHA_FORMAT")
    if (len(experiment_plan_sha256) != 64 or
            any(ch not in "0123456789abcdef" for ch in experiment_plan_sha256)):
        raise CaptureError("R4_PLAN_SHA_INVALID")
    if (type(decision_cutoff_ms) is not int or decision_cutoff_ms <= 0 or
            decision_cutoff_ms % 900000 or
            type(scheduled_at_ms) is not int or scheduled_at_ms < 0 or
            scheduled_at_ms >= decision_cutoff_ms):
        raise CaptureError("R4_SCHEDULE_CLOCK")
    if source_available_at_ms is not None and (
            type(source_available_at_ms) is not int or
            source_available_at_ms < 0 or source_available_at_ms > decision_cutoff_ms):
        raise CaptureError("R4_SOURCE_LATE")
    if not callable(bars_provider):
        raise CaptureError("R4_PROVIDER_REQUIRED")
    if original_f1_records is not None:
        # Caller cannot promote an offline evaluation via unproven F1 fixtures.
        raise CaptureError("R4_ORIGINAL_F1_RUNTIME_AUTHORITY_NOT_ESTABLISHED")

    c2 = dict(c2_identity)
    pair = digest({"experiment_plan_sha256":experiment_plan_sha256,
                   "c2_identity":c2})
    schedule = {
        "schema_version":SCHEDULE_SCHEMA,
        "c2_identity":c2, "pair_id":pair,
        "experiment_plan_sha256":experiment_plan_sha256,
        "decision_cutoff_ms":decision_cutoff_ms,
        "scheduled_at_ms":scheduled_at_ms,
        "availability_mode":availability_mode,
        **dict(pins),
        "arms":[{"arm":arm,"capture_status":"MISSING_CAPTURE"} for arm in ARMS],
        "source_available_at_ms":source_available_at_ms,
        "scheduled_source_proof":"UNVERIFIED_LOCAL_INPUT",
    }
    schedule["schedule_sha256"]=digest(schedule)

    folder=Path(directory)
    folder.mkdir(parents=True,exist_ok=True)
    spath=folder / (pair+".schedule.json")
    rpath=folder / (pair+".result.json")
    if rpath.exists():
        _read_same(spath,schedule)
        raise CaptureError("R4_REPLAY_ALREADY_INVOKED")
    _write_once(spath,jcs_bytes(schedule)+b"\n")

    # The provider is invoked ONLY after the frozen schedule is readable.
    bars=bars_provider()
    if source_available_at_ms is None and availability_mode=="PROSPECTIVE_CAPTURE":
        # A caller-controlled mode string is not evidence that a source arrived.
        raise CaptureError("R4_SOURCE_KNOWN_AT_UNVERIFIED")
    evaluation=evaluate_breakout_closed_prefix(
        bars,decision_cutoff_ms=decision_cutoff_ms,
        availability_mode=availability_mode,
        source_id=pins["source_id"],source_version=pins["source_version"],
        correction_generation=pins["correction_generation"],
        strategy_id=pins["strategy_id"],strategy_version=pins["strategy_version"])
    output={
        "schema_version":SCHEMA,
        "schedule_sha256":schedule["schedule_sha256"],
        "pair_id":pair,"c2_identity":c2,
        "availability_mode":availability_mode,
        "source_available_at_ms":source_available_at_ms,
        "runtime_invocation":"CALLED_NOW_IN_THIS_HOST",
        "runtime_evaluation_status":"COMPLETED_LOCAL_NONTRADING",
        "original_g2_event_status":"NOT_CONNECTED",
        "original_f1_capture_status":"BLOCKED_ON_ORIGINAL_F1_RECORD_AND_INDEPENDENT_EVIDENCE",
        "original_f1_missing_fields":[
            "validated_original_f1_record_BASE", "validated_original_f1_record_SHADOW",
            "original_G2_pre_F3_lifecycle_invocation",
            "independent_source_issuer_known_at_clock_custody_freeze"],
        "proof_status":"BLOCKED_EXTERNAL_EVIDENCE",
        "arm_statuses":{arm:"MISSING_CAPTURE" for arm in ARMS},
        "decision_status_by_arm":{arm:evaluation["breakout_signal_state"] for arm in ARMS},
        "evaluation":evaluation,
        "f3_monitor_status":"NOT_CONNECTED",
        "trade_execution":"DISABLED",
        "historical_replay_is_original_proof":False,
    }
    output["result_sha256"]=digest(output)
    _write_once(rpath,jcs_bytes(output)+b"\n")
    return output
