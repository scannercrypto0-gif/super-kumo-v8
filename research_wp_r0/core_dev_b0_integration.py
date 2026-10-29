"""Integration seam: verified research rows -> scenario preflight.
This module prepares inputs only. It never invokes replay or authorizes a study.
Actual execution remains behind Core's separate authenticated one-run gate.
"""
from hashlib import sha256
from .core_dev_b0_adapter import ENGINE_PIN, ExecutionDenied
from .historical_dev_exits_v1 import Config, digest
from .dev_input_preflight import SCENARIO_CONFIG, validate_historical_dev_inputs

START_MS = 1704067200000
END_MS = 1704153600000
POLICY_ID = "DEV-B0-v1"

class IntegrationPreflightDenied(PermissionError):
    pass

def _require(ok, reason):
    if not ok:
        raise IntegrationPreflightDenied(reason)

def prepare_scenario_from_research_data(research_data, *, archive_bytes, issued_receipt_bytes,
                                        scenario_id, engine_code_sha=ENGINE_PIN, policy_id=POLICY_ID):
    """Bind the Core→Factory data-only handoff to the engine input preflight."""
    from .realdev_research_data import ResearchData
    _require(type(research_data) is ResearchData, "RESEARCH_DATA_OBJECT_REQUIRED")
    spec = research_data.spec
    _require(spec.get("schema") == "factory-research-data-only-1"
             and spec.get("scope") == "DEV_RESEARCH_DATA_ONLY", "RESEARCH_DATA_SCOPE_MISMATCH")
    metadata = spec.get("metadata", {})
    _require(metadata.get("symbol") == "BTCUSDT" and metadata.get("interval_ms") == 60000
             and metadata.get("timezone") == "UTC" and metadata.get("prefix_start_ms") == START_MS
             and metadata.get("prefix_end_ms_exclusive") == END_MS and len(research_data.rows) == 1440,
             "B0_FULL_DAY_SOURCE_WINDOW_REQUIRED")
    archive_sha = sha256(archive_bytes).hexdigest()
    receipt_sha = sha256(issued_receipt_bytes).hexdigest()
    _require(archive_sha == metadata.get("raw_archive_sha256"), "HANDOFF_ARCHIVE_BYTES_MISMATCH")
    _require(receipt_sha == metadata.get("issued_receipt_sha256"), "HANDOFF_ISSUED_RECEIPT_BYTES_MISMATCH")
    _require(scenario_id in SCENARIO_CONFIG, "UNAPPROVED_SCENARIO")
    _require(engine_code_sha == ENGINE_PIN, "UNPINNED_ENGINE")
    _require(policy_id == POLICY_ID, "UNAPPROVED_POLICY")
    source_lag, latency, spread, slip, fee = SCENARIO_CONFIG[scenario_id]
    bars = [{
        "open_ms": row[0], "close_ms": row[1], "open": row[2], "high": row[3],
        "low": row[4], "close": row[5], "volume": row[6],
        "available_ms": row[1] + 1 + source_lag, "modeled_quote": True,
    } for row in research_data.rows]
    source = {
        "version": "aql-dev-b0-research-handoff-v1",
        "reference": metadata.get("source_id", "synthetic:research-data"),
        "archive_sha256": archive_sha, "rows_sha256": digest(bars),
        "availability_evidence": "UNKNOWN", "correction_evidence": "PINNED_VERSION_ONLY",
    }
    config = Config(initial_cash=1000, quantity=0.001, warmup_bars=252,
        latency_ms=latency, spread_bps=spread, slippage_bps=slip, fee_bps=fee,
        max_signal_age_ms=120000, indicator_exit=True, tp_fraction=None, sl_fraction=None,
        checkpoint_ms=86400000)
    source_kind = ("ORIGINAL_LOCAL_PAIR" if metadata.get("source_kind") == "ORIGINAL_LOCAL_PAIR"
                   else "SYNTHETIC_TEST_FIXTURE")
    commitment = {
        "issued_receipt_sha256": receipt_sha, "symbol": "BTCUSDT", "interval_ms": 60000,
        "start_ms": START_MS, "end_exclusive_ms": END_MS, "code_sha": engine_code_sha,
        "policy_id": policy_id, "scenario_id": scenario_id, "warmup_bars": 252,
        "source_kind": source_kind,
    }
    preflight = validate_historical_dev_inputs(archive_bytes=archive_bytes,
        issued_receipt_bytes=issued_receipt_bytes, bars=bars, source=source,
        config=config, commitment=commitment)
    _require(preflight.get("archive_sha256") == archive_sha
             and preflight.get("issued_receipt_sha256") == receipt_sha
             and preflight.get("normalized_rows_sha256") == digest(bars)
             and preflight.get("warmup_bars") == 252
             and preflight.get("scenario_id") == scenario_id, "PREFLIGHT_RESULT_BINDING_MISMATCH")
    return {"bars": bars, "source": source, "config": config, "commitment": commitment,
            "preflight": preflight, "execution_authorized": False, "study_status": "PREPARED_NOT_RUN"}

def prepare_all_scenarios(research_data, *, archive_bytes, issued_receipt_bytes):
    """Preflight all 12 declared scenarios; does not run the engine."""
    return {sid: prepare_scenario_from_research_data(research_data,
        archive_bytes=archive_bytes, issued_receipt_bytes=issued_receipt_bytes, scenario_id=sid)
        for sid in sorted(SCENARIO_CONFIG)}

def run_study(*args, **kwargs):
    """No implicit execution: owner/audit one-run admission is a separate gate."""
    raise ExecutionDenied("STUDY_RUN_REQUIRES_SEPARATE_AUTHENTICATED_ADMISSION")
