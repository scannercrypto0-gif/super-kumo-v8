"""Fail-closed B0 input-preflight entrypoint.

This module is intentionally input-only. It prepares a redacted validation
matrix for S00-S11 and never invokes replay, PnL, result persistence, or study
execution. A historical study requires a separately implemented authenticated
single-use owner admission; comments, environment flags, and hashes are not
admission credentials.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from .historical_dev_exits_v1 import Config, digest
from .dev_input_preflight import (
    ENGINE_PIN,
    POLICY_ID,
    SCENARIO_CONFIG,
    START_MS,
    END_MS,
    _parse_archive,
    validate_historical_dev_inputs,
)

class B0AdmissionDenied(PermissionError):
    """Raised whenever study execution has not passed authenticated admission."""

def run_input_preflight(*, archive_bytes: bytes, issued_receipt_bytes: bytes) -> dict[str, Any]:
    """Run the literal pinned input gate for every fixed B0 scenario.

    Returns only redacted hashes/config commitments and gate outcomes. Does not
    run the strategy engine and does not authorize subsequent study execution.
    """
    if not isinstance(archive_bytes, bytes) or not archive_bytes:
        raise ValueError("MISSING_ORIGINAL_ARCHIVE_BYTES")
    if not isinstance(issued_receipt_bytes, bytes) or not issued_receipt_bytes:
        raise ValueError("MISSING_ISSUED_RECEIPT_BYTES")

    normalized, normalized_sha, normalized_size = _parse_archive(archive_bytes)
    archive_sha = sha256(archive_bytes).hexdigest()
    receipt_sha = sha256(issued_receipt_bytes).hexdigest()
    outcomes: list[dict[str, Any]] = []

    for scenario_id, values in SCENARIO_CONFIG.items():
        source_lag_ms, execution_latency_ms, spread_bps, slippage_bps, fee_bps = values
        bars = [
            {
                "open_ms": row[0],
                "close_ms": row[1],
                "open": row[2],
                "high": row[3],
                "low": row[4],
                "close": row[5],
                "volume": row[6],
                "available_ms": row[1] + 1 + source_lag_ms,
                "modeled_quote": True,
            }
            for row in normalized
        ]
        source = {
            "version": "original-local-pair-v1",
            "reference": "AQL-CORE-WORK152-BTCUSDT-20240101-001",
            "archive_sha256": archive_sha,
            "rows_sha256": digest(bars),
            "availability_evidence": "UNKNOWN",
            "correction_evidence": "PINNED_VERSION_ONLY",
        }
        config = Config(
            interval_ms=60000,
            initial_cash=1000,
            quantity=0.001,
            tp_fraction=None,
            sl_fraction=None,
            indicator_exit=True,
            fee_bps=fee_bps,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            latency_ms=execution_latency_ms,
            max_signal_age_ms=120000,
            checkpoint_ms=86400000,
            warmup_bars=252,
        )
        commitment = {
            "issued_receipt_sha256": receipt_sha,
            "symbol": "BTCUSDT",
            "interval_ms": 60000,
            "start_ms": START_MS,
            "end_exclusive_ms": END_MS,
            "code_sha": ENGINE_PIN,
            "policy_id": POLICY_ID,
            "scenario_id": scenario_id,
            "warmup_bars": 252,
            "source_kind": "ORIGINAL_LOCAL_PAIR",
        }
        try:
            result = validate_historical_dev_inputs(
                archive_bytes=archive_bytes,
                issued_receipt_bytes=issued_receipt_bytes,
                bars=bars,
                source=source,
                config=config,
                commitment=commitment,
            )
            outcomes.append({
                "scenario_id": scenario_id,
                "status": "PASS",
                "input_result": result["status"],
                "config_sha256": digest({
                    "policy_id": POLICY_ID,
                    "scenario_id": scenario_id,
                    "source_lag_ms": source_lag_ms,
                    "execution_latency_ms": execution_latency_ms,
                    "spread_bps": spread_bps,
                    "slippage_bps": slippage_bps,
                    "fee_bps": fee_bps,
                    "engine_config": result_config(config),
                }),
                "engine_input_sha256": result["normalized_rows_sha256"],
            })
        except (ValueError, TypeError, KeyError) as exc:
            outcomes.append({
                "scenario_id": scenario_id,
                "status": "FAIL",
                "reason": str(exc)[:160],
            })

    passed = sum(item["status"] == "PASS" for item in outcomes)
    return {
        "schema": "aql-core-b0-input-preflight-matrix-v1",
        "status": "INPUT_PREFLIGHT_PASS_NOT_STUDY_AUTHORITY" if passed == len(outcomes) else "INPUT_PREFLIGHT_FAILED",
        "policy_id": POLICY_ID,
        "engine_pin": ENGINE_PIN,
        "window": {
            "symbol": "BTCUSDT",
            "interval_ms": 60000,
            "start_ms": START_MS,
            "end_exclusive_ms": END_MS,
            "bar_count": len(normalized),
            "warmup_bars": 252,
        },
        "archive_sha256": archive_sha,
        "archive_size_bytes": len(archive_bytes),
        "issued_receipt_sha256": receipt_sha,
        "issued_receipt_size_bytes": len(issued_receipt_bytes),
        "normalized_rows_sha256": normalized_sha,
        "normalized_rows_size_bytes": normalized_size,
        "scenario_count": len(outcomes),
        "passed": passed,
        "failed": len(outcomes) - passed,
        "scenarios": outcomes,
        "study_authority": "NONE",
    }

def result_config(config: Config) -> dict[str, Any]:
    """Serialize only the engine configuration fields relevant to B0."""
    return {
        "interval_ms": config.interval_ms,
        "initial_cash": config.initial_cash,
        "quantity": config.quantity,
        "tp_fraction": config.tp_fraction,
        "sl_fraction": config.sl_fraction,
        "indicator_exit": config.indicator_exit,
        "fee_bps": config.fee_bps,
        "spread_bps": config.spread_bps,
        "slippage_bps": config.slippage_bps,
        "latency_ms": config.latency_ms,
        "max_signal_age_ms": config.max_signal_age_ms,
        "checkpoint_ms": config.checkpoint_ms,
        "warmup_bars": config.warmup_bars,
    }

def run_one_study(*args: Any, **kwargs: Any) -> None:
    """Fail closed until a separately authenticated, single-use owner permit exists.

    Deliberately no boolean/string/file/hash argument can grant permission.
    The admission mechanism must be implemented and independently reviewed
    before this function can ever delegate to the engine.
    """
    raise B0AdmissionDenied("OWNER_AUTHENTICATED_SINGLE_USE_PERMIT_REQUIRED")
