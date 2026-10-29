"""Bounded synthetic end-to-end contract: preflight -> replay -> persisted bundle.
Never reads private source files and never authorizes run_study.
"""
from hashlib import sha256
from io import BytesIO, StringIO
import csv
import json
import math
import zipfile

import pytest

from research_wp_r0.historical_dev_exits_v1 import Config, digest, replay
from research_wp_r0.dev_input_preflight import validate_historical_dev_inputs
from research_wp_r0.dev_result_bundle import persist_bundle, verify_bundle
from research_wp_r0.realdev_research_data import (
    accept_prefix, ResearchPermit, CONSUMER, OWNER, EXPERIMENT, SCOPE,
)


START = 1704067200000
END = 1704153600000
CODE = "20928693f30b1730f0693a293bbf4a1f8ab21c88"
POLICY = "DEV-B0-v1"


def synthetic_inputs(n=1440):
    bars = []
    for i in range(n):
        close = 100.0 + 5.0 * math.sin(i * 0.15)
        opening = 100.0 + 5.0 * math.sin((i - 0.5) * 0.15)
        open_ms = START + i * 60000
        close_ms = open_ms + 59999
        bars.append({
            "open_ms": open_ms, "close_ms": close_ms,
            "open": opening, "high": max(opening, close) + 1.0,
            "low": min(opening, close) - 1.0, "close": close,
            "volume": 1.0, "available_ms": close_ms + 1001,
            "modeled_quote": True,
        })
    csv_text = StringIO()
    writer = csv.writer(csv_text, lineterminator="\n")
    for b in bars:
        writer.writerow([b["open_ms"], b["open"], b["high"], b["low"],
                         b["close"], b["volume"], b["close_ms"],
                         "0", 1, "0", "0", 0])
    archive_io = BytesIO()
    with zipfile.ZipFile(archive_io, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("BTCUSDT-1m-2024-01-01.csv", csv_text.getvalue())
    raw = archive_io.getvalue()
    normalized = [[b[k] for k in ("open_ms", "close_ms", "open", "high", "low", "close", "volume")] for b in bars]
    normalized_bytes = json.dumps(normalized, separators=(",", ":"), allow_nan=False).encode()
    archive_sha = sha256(raw).hexdigest()
    issued = {
        "schema": "aql-work152-artifact-handoff-receipt-1",
        "scope": "SYNTHETIC_TEST_ONLY", "status": "SYNTHETIC_FIXTURE_NOT_ISSUED",
        "source_id": "fixture:synthetic-integration", "receipt_id": "fixture-receipt",
        "strategy_execution": "NOT_PERFORMED", "real_pit_accepted": False,
        "verified_source_timing": False,
        "acquisition": {"archive": {"sha256": archive_sha, "size_bytes": len(raw)}},
        "normalization": {
            "bars": 1440, "normalization": "binance12-to-7-tuple-python-float-json-v1",
            "normalized_sha256": sha256(normalized_bytes).hexdigest(),
            "normalized_size_bytes": len(normalized_bytes),
        },
    }
    issued_bytes = json.dumps(issued, sort_keys=True, separators=(",", ":")).encode()
    source = {
        "version": "synthetic-b0", "reference": "fixture:integrated-source-to-result",
        "archive_sha256": archive_sha, "rows_sha256": digest(bars),
        "availability_evidence": "UNKNOWN", "correction_evidence": "PINNED_VERSION_ONLY",
    }
    commitment = {
        "issued_receipt_sha256": sha256(issued_bytes).hexdigest(),
        "symbol": "BTCUSDT", "interval_ms": 60000, "start_ms": START,
        "end_exclusive_ms": END, "code_sha": CODE, "policy_id": POLICY,
        "scenario_id": "S00", "warmup_bars": 252,
        "source_kind": "SYNTHETIC_TEST_FIXTURE",
    }
    return raw, issued_bytes, bars, source, commitment


def test_synthetic_preflight_replay_and_bundle_are_cross_bound(tmp_path):
    raw, issued, bars, source, commitment = synthetic_inputs()
    # Exercise the actual Core174 -> Factory data-only object contract. This is a
    # synthetic fixture; the 1,000 ms availability and modeled quote below are
    # explicit hypothetical execution inputs, not claimed source-timing evidence.
    normalized7 = [[b[k] for k in ("open_ms", "close_ms", "open", "high", "low", "close", "volume")]
                   for b in bars]
    handoff_code = "c" * 40
    runtime = {"host": "synthetic-ci", "account": "fixture", "python": "CPython",
               "python_version": "3.12", "checkout": "fixture", "head": handoff_code}
    raw_sha = sha256(raw).hexdigest()
    issued_sha = sha256(issued).hexdigest()
    inspection_sha = "d" * 64
    rows_sha = digest(normalized7)
    metadata = {
        "schema": "core-factory-research-prefix-1", "experiment_id": EXPERIMENT,
        "consumer_id": CONSUMER, "source_kind": "SYNTHETIC_CONTRACT_FIXTURE",
        "runtime": runtime, "code_sha": handoff_code,
        "base_core_sha": "22d03f4d3434fbce149c4d66349b33149789613a",
        "factory_sha": "eacb5e50150c6e6c64c8a41a8eaa410aebd71532",
        "mapping_schema": "core-factory-dev-map-2",
        "compatibility_profile": "factory148-u160-whole-policy-null-1",
        "symbol": "BTCUSDT", "interval_ms": 60000, "timezone": "UTC",
        "source_start_ms": START, "source_end_ms_exclusive": END,
        "prefix_start_ms": START, "prefix_end_ms_exclusive": END,
        "decision_cutoff_ms": END, "warmup_input_count": 252,
        "raw_archive_sha256": raw_sha, "raw_archive_size": len(raw),
        "issued_receipt_sha256": issued_sha, "issued_receipt_size": len(issued),
        "retained_archive_version": 0, "inspection_report_sha256": inspection_sha,
        "full_normalized7_sha256": rows_sha,
        "source_id": "fixture:synthetic-integration",
        "issued_receipt_id": "fixture-receipt",
    }
    expected = {
        "code_sha": handoff_code, "runtime_sha256": digest(runtime),
        "raw_archive_sha256": raw_sha, "issued_receipt_sha256": issued_sha,
        "inspection_report_sha256": inspection_sha,
        "full_normalized7_sha256": rows_sha, "prefix_normalized7_sha256": rows_sha,
    }
    permit = ResearchPermit(EXPERIMENT, OWNER, CONSUMER, handoff_code, digest(runtime))
    research_data = accept_prefix(
        normalized7, metadata=metadata, expected=expected, permit=permit, request=SCOPE,
    )
    bars = [{
        "open_ms": row[0], "close_ms": row[1], "open": row[2], "high": row[3],
        "low": row[4], "close": row[5], "volume": row[6],
        "available_ms": row[1] + 1 + 1000, "modeled_quote": True,
    } for row in research_data.rows]
    source["rows_sha256"] = digest(bars)
    config = Config(initial_cash=1000, quantity=0.001, warmup_bars=252,
                    latency_ms=1000, spread_bps=2, slippage_bps=5,
                    fee_bps=10, tp_fraction=None, sl_fraction=None,
                    indicator_exit=True)
    preflight = validate_historical_dev_inputs(
        archive_bytes=raw, issued_receipt_bytes=issued, bars=bars,
        source=source, config=config, commitment=commitment,
    )
    receipt = replay(bars, source=source, config=config)
    evidence = {
        "policy_id": POLICY,
        "policy_sha256": digest({"policy_id": POLICY, "engine_config": receipt["config"]}),
        "source_zip_sha256": sha256(raw).hexdigest(),
        "issued_receipt_sha256": sha256(issued).hexdigest(),
        "code_sha": CODE, "input_prefix_sha256": digest(receipt["input_rows"]),
        "scenario_id": "S00", "warmup_bars": 252,
        "experiment_id": "AQL-DEV-FIRST-01",
    }
    manifest = persist_bundle(
        tmp_path, run_id="integrated-synthetic-001", receipt=receipt,
        evidence=evidence, input_preflight=preflight,
    )
    assert manifest["state"] == "COMPLETE_LOCAL_COPY_NOT_IMMUTABLE_CUSTODY"
    assert verify_bundle(tmp_path, "integrated-synthetic-001")
    assert preflight["bar_count"] == len(receipt["input_rows"]) == 1440
    assert preflight["warmup_bars"] == receipt["config"]["warmup_bars"] == 252
    assert preflight["archive_sha256"] == receipt["source"]["archive_sha256"]
    assert preflight["normalized_rows_sha256"] == digest(receipt["input_rows"])
    assert set(receipt["paths"]) == {"FACTUAL", "TARGET_FIRST", "STOP_FIRST"}
    for path in receipt["paths"].values():
        assert path["scheduled_denominator"] == len(path["opportunities"])
    # Strategy replay may remain policy-UNKNOWN due a terminal opportunity, but must
    # still retain any resolved modeled entry/exit events without fabricating totals.
    assert any(
        any(event["kind"] == "MODELED_ENTRY" for event in path["ledger"])
        and any(event["kind"] == "MODELED_INDICATOR_EXIT" for event in path["ledger"])
        for path in receipt["paths"].values()
    )
    saved = json.loads((tmp_path / "integrated-synthetic-001" / "input_preflight.json").read_text())
    assert saved["issued_receipt_sha256"] == evidence["issued_receipt_sha256"]


def test_terminal_unknown_keeps_null_policy_totals_and_full_denominator():
    bars = synthetic_inputs(260)[2]
    source = {
        "version": "synthetic-b0", "reference": "fixture:terminal-unknown",
        "archive_sha256": "a" * 64, "rows_sha256": digest(bars),
        "availability_evidence": "UNKNOWN", "correction_evidence": "PINNED_VERSION_ONLY",
    }
    from research_wp_r0.historical_dev_exits_v1 import replay_contract_fixture
    signal_bar = bars[-2]
    signal = {"bar_open_ms": signal_bar["open_ms"], "action": "ENTER_LONG",
              "available_ms": signal_bar["available_ms"]}
    receipt = replay_contract_fixture(
        bars, source=source, signals=[signal],
        config=Config(initial_cash=1000, quantity=0.001, warmup_bars=252, latency_ms=1000),
    )
    for path in receipt["paths"].values():
        assert path["scheduled_denominator"] == len(path["opportunities"]) == 1
        assert path["status"] == "UNKNOWN_UNRESOLVED"
        assert path["realized_pnl"] is None
        assert path["modeled_equity_return"] is None
        assert path["opportunities"][0]["scored_return"] is None


def test_resolvable_synthetic_execution_fixture_scores_trade_and_costs():
    from research_wp_r0.historical_dev_exits_v1 import replay_contract_fixture
    bars = synthetic_inputs(40)[2]
    source = {
        "version": "synthetic-b0", "reference": "fixture:resolved-contract-trade",
        "archive_sha256": "b" * 64, "rows_sha256": digest(bars),
        "availability_evidence": "UNKNOWN", "correction_evidence": "PINNED_VERSION_ONLY",
    }
    signals = [
        {"bar_open_ms": bars[5]["open_ms"], "action": "ENTER_LONG", "available_ms": bars[5]["available_ms"]},
        {"bar_open_ms": bars[10]["open_ms"], "action": "EXIT_LONG", "available_ms": bars[10]["available_ms"]},
    ]
    receipt = replay_contract_fixture(
        bars, source=source, signals=signals,
        config=Config(initial_cash=1000, quantity=0.001, warmup_bars=22,
                      latency_ms=1000, spread_bps=2, slippage_bps=5,
                      fee_bps=10, indicator_exit=True, tp_fraction=None, sl_fraction=None),
    )
    assert receipt["config"]["spread_bps"] == 2
    assert receipt["config"]["slippage_bps"] == 5
    assert receipt["config"]["fee_bps"] == 10
    for path in receipt["paths"].values():
        assert path["status"] == "SETTLED_MODELED"
        assert path["scheduled_denominator"] == len(path["opportunities"]) == 2
        assert path["realized_pnl"] is not None
        assert path["modeled_equity_return"] is not None
        assert path["fees_paid"] > 0
        assert any(event["kind"] == "MODELED_ENTRY" for event in path["ledger"])
        assert any(event["kind"] == "MODELED_INDICATOR_EXIT" for event in path["ledger"])
