"""Single supported Factory orchestration for the bounded B0 historical DEV study.

This is the only supported production workflow: original input pair -> Core
admission -> one-time start authorization -> all 12 fixed scenarios -> verified
per-scenario result bundles -> verified aggregate index. It does not grant
PIT, OOS, PAPER, LIVE, merge, or G0 authority.

Python cannot make an imported low-level function cryptographically unreachable.
The production contract therefore treats direct engine replay and direct bundle
persistence as unsupported internal/test APIs; production callers must use this
orchestrator. Adversarial tests protect this supported boundary against accidental
alternate Factory paths.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any

from .core_b0_entrypoint import admit_one_study_run
from .core_b0_admission import authorize_factory_execution
from .dev_input_preflight import (
    ENGINE_PIN, POLICY_ID, SCENARIO_CONFIG, START_MS, END_MS, _parse_archive,
)
from .historical_dev_exits_v1 import Config, digest, replay, verify_receipt
from .dev_result_bundle import persist_bundle, verify_bundle

_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\\Z")
EXPECTED_SCENARIOS = tuple(f"S{i:02d}" for i in range(12))


class FactoryStudyDenied(PermissionError):
    """The canonical production orchestration failed closed."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _exclusive_json(path: Path, value: Any) -> str:
    raw = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    readback = path.read_bytes()
    if readback != raw or sha256(readback).hexdigest() != sha256(raw).hexdigest():
        raise FactoryStudyDenied("AGGREGATE_INDEX_READBACK_MISMATCH")
    return sha256(raw).hexdigest()


def _scenario_config(values: tuple[int, int, float, float, float]) -> Config:
    source_lag_ms, execution_latency_ms, spread_bps, slippage_bps, fee_bps = values
    # Source availability lag is modeled separately from execution latency.
    return Config(
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


def run_authorized_b0_study(
    *,
    permit: dict[str, Any],
    archive_path: str | os.PathLike[str],
    issued_receipt_path: str | os.PathLike[str],
    result_store: str | os.PathLike[str],
    experiment_id: str,
) -> dict[str, Any]:
    """Execute exactly one admitted B0 study covering S00-S11.

    The caller supplies a permit record, never a secret. The owner HMAC key and
    out-of-checkout admission directory are provisioned through the documented
    environment variables consumed by Core. Any ambiguous admission/start/write
    state stops the run; never retry with the same permit ID.
    """
    if not isinstance(experiment_id, str) or not _SAFE.fullmatch(experiment_id):
        raise ValueError("INVALID_EXPERIMENT_ID")
    archive = Path(archive_path).resolve(strict=True)
    issued_receipt = Path(issued_receipt_path).resolve(strict=True)
    store = Path(result_store).resolve(strict=True)
    if not archive.is_file() or archive.is_symlink():
        raise FactoryStudyDenied("ORIGINAL_ARCHIVE_NOT_REGULAR_FILE")
    if not issued_receipt.is_file() or issued_receipt.is_symlink():
        raise FactoryStudyDenied("ISSUED_RECEIPT_NOT_REGULAR_FILE")
    if not store.is_dir() or store.is_symlink():
        raise FactoryStudyDenied("RESULT_STORE_NOT_TRUSTED_DIRECTORY")

    archive_bytes = archive.read_bytes()
    receipt_bytes = issued_receipt.read_bytes()
    archive_sha = sha256(archive_bytes).hexdigest()
    issued_receipt_sha = sha256(receipt_bytes).hexdigest()

    # This performs the literal S00-S11 preflight and consumes the signed,
    # exact-pin one-run permit only after all 12 scenarios pass.
    admission = admit_one_study_run(
        permit, archive_bytes=archive_bytes,
        issued_receipt_bytes=receipt_bytes,
    )
    admission_path = admission.get("admission_record_path")
    if not isinstance(admission_path, str) or not admission_path:
        raise FactoryStudyDenied("SIGNED_ADMISSION_RECORD_MISSING")

    # Mandatory one-time start authorization; do not replay or write results
    # until this returns a valid started record.
    started = authorize_factory_execution(admission_path)
    if (not isinstance(started, dict)
            or started.get("schema") != "aql-owner-admission-start-v1"
            or started.get("max_runs") != 1
            or not isinstance(started.get("start_record_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", started["start_record_sha256"])):
        raise FactoryStudyDenied("FACTORY_START_AUTHORIZATION_INVALID")

    normalized, normalized_sha, normalized_size = _parse_archive(archive_bytes)
    if len(normalized) != 1440:
        raise FactoryStudyDenied("PINNED_WINDOW_BAR_COUNT_MISMATCH")
    if normalized[0][0] != START_MS or normalized[-1][1] >= END_MS:
        raise FactoryStudyDenied("PINNED_WINDOW_BOUNDARY_MISMATCH")

    store_summary: list[dict[str, Any]] = []
    for scenario_id in EXPECTED_SCENARIOS:
        values = SCENARIO_CONFIG.get(scenario_id)
        if values is None:
            raise FactoryStudyDenied("FIXED_SCENARIO_MISSING")
        source_lag_ms, execution_latency_ms, spread_bps, slippage_bps, fee_bps = values
        bars = [
            {
                "open_ms": row[0], "close_ms": row[1],
                "open": row[2], "high": row[3], "low": row[4],
                "close": row[5], "volume": row[6],
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
        config = _scenario_config(values)
        result = replay(bars, source=source, config=config)
        if not verify_receipt(result):
            raise FactoryStudyDenied("ENGINE_RECEIPT_VERIFICATION_FAILED")
        if set(result.get("paths", {})) != {"FACTUAL", "TARGET_FIRST", "STOP_FIRST"}:
            raise FactoryStudyDenied("THREE_PATH_CONTRACT_MISSING")

        evidence = {
            "policy_id": POLICY_ID,
            "policy_sha256": digest({"policy_id": POLICY_ID,
                                     "engine_config": result["config"]}),
            "source_zip_sha256": archive_sha,
            "issued_receipt_sha256": issued_receipt_sha,
            "code_sha": ENGINE_PIN,
            "input_prefix_sha256": digest(result.get("input_rows")),
            "scenario_id": scenario_id,
            "warmup_bars": 252,
            "experiment_id": experiment_id,
        }
        run_id = f"{experiment_id}-{scenario_id}"
        manifest = persist_bundle(
            store, run_id=run_id, receipt=result, evidence=evidence
        )
        if not verify_bundle(store, run_id):
            raise FactoryStudyDenied("RESULT_BUNDLE_READBACK_FAILED")
        manifest_bytes = _json_bytes(manifest)
        store_summary.append({
            "scenario_id": scenario_id,
            "run_id": run_id,
            "bundle_manifest_sha256": sha256(manifest_bytes).hexdigest(),
            "bundle_verified": True,
            "source_lag_ms": source_lag_ms,
            "execution_latency_ms": execution_latency_ms,
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "fee_bps": fee_bps,
            "path_status": {
                name: result["paths"][name]["status"]
                for name in ("FACTUAL", "TARGET_FIRST", "STOP_FIRST")
            },
            "scheduled_denominator": {
                name: result["paths"][name]["scheduled_denominator"]
                for name in ("FACTUAL", "TARGET_FIRST", "STOP_FIRST")
            },
        })

    if [item["scenario_id"] for item in store_summary] != list(EXPECTED_SCENARIOS):
        raise FactoryStudyDenied("SCENARIO_SET_OR_ORDER_MISMATCH")

    aggregate = {
        "schema": "aql-factory-b0-single-study-index-v1",
        "study_executed": True,
        "experiment_id": experiment_id,
        "policy_id": POLICY_ID,
        "engine_pin": ENGINE_PIN,
        "source_zip_sha256": archive_sha,
        "issued_receipt_sha256": issued_receipt_sha,
        "normalized_rows_sha256": normalized_sha,
        "normalized_bytes": normalized_size,
        "bar_count": len(normalized),
        "start_ms": START_MS,
        "end_exclusive_ms": END_MS,
        "warmup_bars": 252,
        "admission_record_sha256": admission.get("admission_record_sha256"),
        "start_record_sha256": started.get("start_record_sha256")
            or started.get("started_record_sha256")
            or started.get("record_sha256"),
        "scenarios": store_summary,
        "limits": {
            "retrospective_dev_only": True,
            "point_in_time_provenance_established": False,
            "source_timing_verified": False,
            "fills_are_modeled_not_observed": True,
            "oos_or_profitability_claim": False,
            "paper_live_or_g0_authority": False,
        },
    }
    aggregate_path = store / f"{experiment_id}-aggregate.json"
    aggregate_sha = _exclusive_json(aggregate_path, aggregate)
    return {
        "status": "COMPLETE_LOCAL_VERIFIED_BUNDLE",
        "experiment_id": experiment_id,
        "scenario_count": len(store_summary),
        "aggregate_path": str(aggregate_path),
        "aggregate_sha256": aggregate_sha,
        "study_executed": True,
    }
