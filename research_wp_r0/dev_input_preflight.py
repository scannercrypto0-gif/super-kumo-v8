"""Fail-closed preflight for a single historical DEV input handoff.

This validates bytes, normalized bars, and declared run window before any replay.
It does NOT authenticate an issuer, prove point-in-time availability, or run a study.
The caller/parser must preserve the exact original archive and issued receipt bytes.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import re
import zipfile

from .historical_dev_exits_v1 import Config, digest, _validate as validate_engine_inputs

_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_REQUIRED = frozenset({
    "issued_receipt_sha256", "symbol", "interval_ms", "start_ms",
    "end_exclusive_ms", "code_sha", "policy_id", "scenario_id",
    "warmup_bars",
})


class InputGateRejected(ValueError):
    pass


def sha256_hex(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def validate_historical_dev_inputs(*, archive_bytes: bytes,
                                   issued_receipt_bytes: bytes,
                                   bars: list[dict], source: dict,
                                   config: Config, commitment: dict) -> dict:
    """Return a compact validated input manifest, never a trading result.

    For the first B0 engineering run, the frozen window is 2024-01-01 UTC,
    1m BTCUSDT bars, [00:00, next-day 00:00), exactly 1,440 bars, scoring
    warmup 252. Receipt authenticity/issuer signature and PIT are separate gates.
    """
    if not isinstance(archive_bytes, bytes) or not archive_bytes:
        raise InputGateRejected("MISSING_ORIGINAL_ARCHIVE_BYTES")
    if not isinstance(issued_receipt_bytes, bytes) or not issued_receipt_bytes:
        raise InputGateRejected("MISSING_ISSUED_RECEIPT_BYTES")
    archive_sha = sha256_hex(archive_bytes)
    receipt_sha = sha256_hex(issued_receipt_bytes)
    if not isinstance(commitment, dict) or set(commitment) != _REQUIRED:
        raise InputGateRejected("MISSING_OR_EXTRA_INPUT_COMMITMENT")
    for name in ("code_sha", "policy_id", "scenario_id"):
        if not isinstance(commitment[name], str) or not _SAFE.fullmatch(commitment[name]):
            raise InputGateRejected("INVALID_" + name.upper())
    if commitment["issued_receipt_sha256"] != receipt_sha:
        raise InputGateRejected("ISSUED_RECEIPT_SHA_MISMATCH")
    if source.get("archive_sha256") != archive_sha:
        raise InputGateRejected("ORIGINAL_ARCHIVE_SHA_MISMATCH")
    if commitment["symbol"] != "BTCUSDT":
        raise InputGateRejected("UNEXPECTED_SYMBOL")
    if commitment["interval_ms"] != 60000 or config.interval_ms != 60000:
        raise InputGateRejected("UNEXPECTED_INTERVAL")
    # Unix milliseconds: 2024-01-01T00:00:00Z to 2024-01-02T00:00:00Z.
    start_ms, end_ms = 1704067200000, 1704153600000
    if (commitment["start_ms"], commitment["end_exclusive_ms"]) != (start_ms, end_ms):
        raise InputGateRejected("UNEXPECTED_WINDOW")
    if commitment["warmup_bars"] != 252 or config.warmup_bars != 252:
        raise InputGateRejected("EXPLICIT_252_WARMUP_REQUIRED")
    if len(bars) != 1440:
        raise InputGateRejected("EXPECTED_EXACTLY_1440_ONE_MINUTE_BARS")
    if bars[0].get("open_ms") != start_ms or bars[-1].get("open_ms") != end_ms - 60000:
        raise InputGateRejected("WINDOW_BOUNDARY_MISMATCH")
    try:
        validate_engine_inputs(bars, source, config)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise InputGateRejected("ENGINE_INPUT_VALIDATION:" + str(exc)) from exc
    if source.get("archive_sha256") != archive_sha:
        raise InputGateRejected("SOURCE_ARCHIVE_BINDING_MISMATCH")
    if source.get("rows_sha256") != digest(bars):
        raise InputGateRejected("NORMALIZED_ROWS_DIGEST_MISMATCH")
    # Verify archive structure and CRC; do not extract or execute member paths.
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            names = archive.namelist()
            if not names or archive.testzip() is not None:
                raise InputGateRejected("INVALID_OR_CORRUPT_ARCHIVE")
            if any(name.startswith(("/", "\\")) or ".." in name.split("/") for name in names):
                raise InputGateRejected("UNSAFE_ARCHIVE_MEMBER_PATH")
    except zipfile.BadZipFile as exc:
        raise InputGateRejected("ORIGINAL_ARCHIVE_NOT_VALID_ZIP") from exc
    return {
        "schema": "sf-dev-input-preflight-v1",
        "status": "INPUT_BYTES_AND_NORMALIZED_ROWS_VALID_NOT_STUDY_AUTHORITY",
        "symbol": commitment["symbol"],
        "interval_ms": commitment["interval_ms"],
        "start_ms": start_ms,
        "end_exclusive_ms": end_ms,
        "bar_count": len(bars),
        "warmup_bars": config.warmup_bars,
        "archive_sha256": archive_sha,
        "issued_receipt_sha256": receipt_sha,
        "normalized_rows_sha256": digest(bars),
        "code_sha": commitment["code_sha"],
        "policy_id": commitment["policy_id"],
        "scenario_id": commitment["scenario_id"],
        "receipt_authenticity": "NOT_AUTHENTICATED_BY_THIS_GATE",
        "point_in_time_provenance": "NOT_ESTABLISHED_BY_THIS_GATE",
    }
