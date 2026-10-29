"""Authenticated, single-use owner admission for one bounded DEV study.

The permit HMAC key must be provisioned out-of-band by the owner in the
authorized runtime. No GitHub issue, environment boolean, CLI flag, or hash
alone grants admission. Consuming a permit writes an exclusive durable record
before the caller may begin any study work.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from .dev_input_preflight import END_MS, POLICY_ID, SCENARIOS, START_MS

_REQUIRED = frozenset({
    "schema", "permit_id", "issued_at", "expires_at", "max_runs",
    "head_sha", "policy_id", "symbol", "interval_ms", "start_ms",
    "end_exclusive_ms", "scenario_ids", "signature",
})
_HEX40 = re.compile(r"[0-9a-f]{40}")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,95}")
_SCHEMA = "aql-owner-single-run-permit-v1"


class AdmissionDenied(PermissionError):
    """The owner-signed one-run admission is missing, invalid, or consumed."""


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise AdmissionDenied("INVALID_PERMIT_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdmissionDenied("INVALID_PERMIT_TIME") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdmissionDenied("PERMIT_TIME_MUST_INCLUDE_TIMEZONE")
    return parsed.astimezone(timezone.utc)


def _validate_shape(permit: Any) -> dict[str, Any]:
    if not isinstance(permit, dict) or set(permit) != _REQUIRED:
        raise AdmissionDenied("INVALID_PERMIT_FIELDS")
    if permit["schema"] != _SCHEMA:
        raise AdmissionDenied("INVALID_PERMIT_SCHEMA")
    if not isinstance(permit["permit_id"], str) or not _SAFE_ID.fullmatch(permit["permit_id"]):
        raise AdmissionDenied("INVALID_PERMIT_ID")
    if permit["max_runs"] != 1 or type(permit["max_runs"]) is not int:
        raise AdmissionDenied("PERMIT_MUST_ALLOW_EXACTLY_ONE_RUN")
    if not isinstance(permit["head_sha"], str) or not _HEX40.fullmatch(permit["head_sha"]):
        raise AdmissionDenied("INVALID_PERMIT_HEAD")
    if permit["policy_id"] != POLICY_ID:
        raise AdmissionDenied("PERMIT_POLICY_MISMATCH")
    if permit["symbol"] != "BTCUSDT" or permit["interval_ms"] != 60000:
        raise AdmissionDenied("PERMIT_MARKET_MISMATCH")
    if (permit["start_ms"], permit["end_exclusive_ms"]) != (START_MS, END_MS):
        raise AdmissionDenied("PERMIT_WINDOW_MISMATCH")
    scenarios = permit["scenario_ids"]
    if not isinstance(scenarios, list) or not scenarios or len(scenarios) != len(set(scenarios)):
        raise AdmissionDenied("INVALID_PERMIT_SCENARIOS")
    if set(scenarios) != set(SCENARIOS):
        raise AdmissionDenied("PERMIT_SCENARIO_SET_MISMATCH")
    issued, expires = _parse_time(permit["issued_at"]), _parse_time(permit["expires_at"])
    if expires <= issued:
        raise AdmissionDenied("INVALID_PERMIT_EXPIRY")
    signature = permit["signature"]
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise AdmissionDenied("INVALID_PERMIT_SIGNATURE_FORMAT")
    return {"issued": issued, "expires": expires}


def _verify_signature(permit: dict[str, Any], secret: bytes) -> None:
    unsigned = {key: value for key, value in permit.items() if key != "signature"}
    expected = hmac.new(secret, _canonical(unsigned), sha256).hexdigest()
    if not hmac.compare_digest(expected, permit["signature"]):
        raise AdmissionDenied("OWNER_SIGNATURE_INVALID")


def _runtime_identity(expected_head: str) -> dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], check=True, capture_output=True, text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdmissionDenied("GIT_RUNTIME_IDENTITY_UNAVAILABLE") from exc
    if head != expected_head:
        raise AdmissionDenied("CHECKOUT_HEAD_MISMATCH")
    if status.strip():
        raise AdmissionDenied("WORKTREE_NOT_CLEAN")
    return {"head_sha": head, "worktree_clean": True}


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o400)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        # Do not remove the exclusive marker: failure after consumption must
        # fail closed rather than make the permit reusable.
        raise


def consume_owner_one_run_permit(
    permit: dict[str, Any],
    *,
    admission_dir: str | os.PathLike[str],
    secret: bytes,
    runtime_head: str,
    worktree_clean: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify and atomically consume one signed permit; no strategy work occurs here."""
    timing = _validate_shape(permit)
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise AdmissionDenied("OWNER_HMAC_KEY_NOT_PROVISIONED")
    _verify_signature(permit, secret)
    if permit["head_sha"] != runtime_head:
        raise AdmissionDenied("CHECKOUT_HEAD_MISMATCH")
    if worktree_clean is not True:
        raise AdmissionDenied("WORKTREE_NOT_CLEAN")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if current < timing["issued"] or current >= timing["expires"]:
        raise AdmissionDenied("PERMIT_NOT_CURRENT")
    root = Path(admission_dir)
    if not root.is_absolute():
        raise AdmissionDenied("ADMISSION_DIRECTORY_MUST_BE_ABSOLUTE")
    root.mkdir(parents=True, exist_ok=True)
    permit_hash = sha256(_canonical(permit)).hexdigest()
    marker = root / (permit["permit_id"] + ".consumed.json")
    record = {
        "schema": "aql-owner-admission-record-v1",
        "state": "ADMITTED_NOT_STARTED",
        "permit_id": permit["permit_id"],
        "permit_sha256": permit_hash,
        "head_sha": runtime_head,
        "policy_id": permit["policy_id"],
        "symbol": permit["symbol"],
        "interval_ms": permit["interval_ms"],
        "start_ms": permit["start_ms"],
        "end_exclusive_ms": permit["end_exclusive_ms"],
        "scenario_ids": permit["scenario_ids"],
        "consumed_at": current.isoformat(),
        "max_runs": 1,
    }
    try:
        _write_exclusive(marker, _canonical(record))
    except FileExistsError as exc:
        raise AdmissionDenied("PERMIT_ALREADY_CONSUMED") from exc
    return {**record, "admission_record_path": str(marker), "admission_record_sha256": sha256(_canonical(record)).hexdigest()}


def admit_current_checkout_one_run(permit: dict[str, Any]) -> dict[str, Any]:
    """Production boundary: read owner-provisioned key, attest actual Git checkout, consume once."""
    secret_text = os.environ.get("AQL_B0_PERMIT_HMAC_KEY", "")
    if not secret_text:
        raise AdmissionDenied("OWNER_HMAC_KEY_NOT_PROVISIONED")
    secret = secret_text.encode("utf-8")
    if len(secret) < 32:
        raise AdmissionDenied("OWNER_HMAC_KEY_TOO_SHORT")
    if not os.environ.get("AQL_B0_ADMISSION_DIR"):
        raise AdmissionDenied("ADMISSION_DIRECTORY_NOT_CONFIGURED")
    head = permit.get("head_sha") if isinstance(permit, dict) else ""
    if not isinstance(head, str):
        raise AdmissionDenied("INVALID_PERMIT_HEAD")
    runtime = _runtime_identity(head)
    return consume_owner_one_run_permit(
        permit,
        admission_dir=os.environ["AQL_B0_ADMISSION_DIR"],
        secret=secret,
        runtime_head=runtime["head_sha"],
        worktree_clean=runtime["worktree_clean"],
    )
