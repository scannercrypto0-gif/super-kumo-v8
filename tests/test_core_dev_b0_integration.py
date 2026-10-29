"""Synthetic end-to-end contract across Core handoff, preflight, replay and bundle."""
from hashlib import sha256
from io import BytesIO, StringIO
import csv, json, zipfile
import pytest
from research_wp_r0.realdev_research_data import accept_prefix, ResearchPermit, CONSUMER, SCOPE, OWNER, digest
from research_wp_r0.dev_input_preflight import SCENARIO_CONFIG
from research_wp_r0.core_dev_b0_integration import prepare_scenario_from_research_data, prepare_all_scenarios, run_study, IntegrationPreflightDenied
from research_wp_r0.core_dev_b0_adapter import ExecutionDenied
from research_wp_r0.historical_dev_exits_v1 import replay, verify_receipt
from research_wp_r0.dev_result_bundle import persist_bundle, verify_bundle

START = 1704067200000
END = 1704153600000
ENGINE_PIN = "20928693f30b1730f0693a293bbf4a1f8ab21c88"

def synthetic_inputs():
    rows = []
    for i in range(1440):
        if i < 300: px = 100.0
        elif i < 600: px = 100.0 + (i - 300) * 0.1
        elif i < 900: px = 130.0 - (i - 600) * 0.1
        elif i < 1200: px = 100.0 + (i - 900) * 0.1
        else: px = 130.0 - (i - 1200) * 0.1
        rows.append([START+i*60000, START+(i+1)*60000-1, float(px), float(px+0.2),
                     float(px-0.2), float(px), 1.0])
    csv_text = StringIO()
    writer = csv.writer(csv_text, lineterminator="\\n")
    for row in rows:
        writer.writerow([row[0], row[2], row[3], row[4], row[5], row[6], row[1], "0", 1, "0", "0", 0])
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("BTCUSDT-1m-2024-01-01.csv", csv_text.getvalue())
    archive = out.getvalue()
    normalized = json.dumps(rows, separators=(",", ":"), allow_nan=False).encode()
    archive_sha = sha256(archive).hexdigest()
    receipt = {
        "schema": "aql-work152-artifact-handoff-receipt-1", "scope": "SYNTHETIC_TEST_ONLY",
        "status": "SYNTHETIC_FIXTURE_NOT_ISSUED", "source_id": "synthetic:BTCUSDT:1m:2024-01-01",
        "receipt_id": "synthetic-receipt-not-issued", "strategy_execution": "NOT_PERFORMED",
        "real_pit_accepted": False, "verified_source_timing": False,
        "acquisition": {"archive": {"sha256": archive_sha, "size_bytes": len(archive)}},
        "normalization": {"bars": 1440, "normalization": "binance12-to-7-tuple-python-float-json-v1",
            "normalized_sha256": sha256(normalized).hexdigest(), "normalized_size_bytes": len(normalized)},
    }
    issued = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    runtime = {"host":"synthetic", "account":"fixture", "python":"CPython",
               "python_version":"3.12", "checkout":"fixture", "head":"c"*40}
    meta = {
        "schema":"core-factory-research-prefix-1", "experiment_id":"AQL-CORE-REALDEV-001",
        "consumer_id":CONSUMER, "source_kind":"SYNTHETIC_CONTRACT_FIXTURE", "runtime":runtime,
        "code_sha":runtime["head"], "base_core_sha":"22d03f4d3434fbce149c4d66349b33149789613a",
        "factory_sha":"eacb5e50150c6e6c64c8a41b8eaa410aebd71532",
        "mapping_schema":"core-factory-dev-map-2", "compatibility_profile":"factory148-u160-whole-policy-null-1",
        "symbol":"BTCUSDT", "interval_ms":60000, "timezone":"UTC",
        "source_start_ms":START, "source_end_ms_exclusive":END, "prefix_start_ms":START,
        "prefix_end_ms_exclusive":END, "decision_cutoff_ms":END, "warmup_input_count":252,
        "raw_archive_sha256":archive_sha, "raw_archive_size":len(archive),
        "issued_receipt_sha256":sha256(issued).hexdigest(), "issued_receipt_size":len(issued),
        "retained_archive_version":0, "inspection_report_sha256":"d"*64,
        "full_normalized7_sha256":digest(rows), "source_id":receipt["source_id"],
        "issued_receipt_id":receipt["receipt_id"],
    }
    expected = {"code_sha":runtime["head"], "runtime_sha256":digest(runtime),
        "raw_archive_sha256":archive_sha, "issued_receipt_sha256":sha256(issued).hexdigest(),
        "inspection_report_sha256":"d"*64, "full_normalized7_sha256":digest(rows),
        "prefix_normalized7_sha256":digest(rows)}
    permit = ResearchPermit("AQL-CORE-REALDEV-001", OWNER, CONSUMER, runtime["head"], digest(runtime))
    research_data = accept_prefix(rows, metadata=meta, expected=expected, permit=permit, request=SCOPE)
    return research_data, archive, issued

def test_full_synthetic_handoff_preflight_replay_and_persist(tmp_path):
    research_data, archive, issued = synthetic_inputs()
    prepared = prepare_scenario_from_research_data(research_data, archive_bytes=archive,
        issued_receipt_bytes=issued, scenario_id="S00")
    assert prepared["study_status"] == "PREPARED_NOT_RUN" and prepared["execution_authorized"] is False
    assert prepared["preflight"]["bar_count"] == 1440 and prepared["preflight"]["warmup_bars"] == 252
    receipt = replay(prepared["bars"], source=prepared["source"], config=prepared["config"])
    assert verify_receipt(receipt)
    assert set(receipt["paths"]) == {"FACTUAL", "TARGET_FIRST", "STOP_FIRST"}
    assert all(p["scheduled_denominator"] == len(p["opportunities"]) for p in receipt["paths"].values())
    assert receipt["config"]["spread_bps"] == SCENARIO_CONFIG["S00"][2]
    assert receipt["config"]["slippage_bps"] == SCENARIO_CONFIG["S00"][3]
    assert receipt["config"]["fee_bps"] == SCENARIO_CONFIG["S00"][4]
    evidence = {"policy_id":"DEV-B0-v1",
        "policy_sha256":digest({"policy_id":"DEV-B0-v1","engine_config":receipt["config"]}),
        "source_zip_sha256":prepared["source"]["archive_sha256"],
        "issued_receipt_sha256":prepared["commitment"]["issued_receipt_sha256"],
        "code_sha":ENGINE_PIN, "input_prefix_sha256":digest(receipt["input_rows"]),
        "scenario_id":"S00", "warmup_bars":252, "experiment_id":"AQL-DEV-FIRST-01"}
    manifest = persist_bundle(str(tmp_path), run_id="integrated-synthetic-run", receipt=receipt,
        evidence=evidence, input_preflight=prepared["preflight"])
    assert verify_bundle(str(tmp_path), "integrated-synthetic-run")
    assert "input_preflight.json" in manifest["files"]
    saved = json.loads((tmp_path/"integrated-synthetic-run"/"receipt.json").read_text())
    assert saved["paths"]["FACTUAL"]["scheduled_denominator"] == len(saved["paths"]["FACTUAL"]["opportunities"])
    assert saved["paths"]["FACTUAL"]["realized_pnl"] is not None
    assert saved["paths"]["FACTUAL"]["realized_pnl"] > 0

def test_all_twelve_scenarios_preflight_without_running_study():
    research_data, archive, issued = synthetic_inputs()
    prepared = prepare_all_scenarios(research_data, archive_bytes=archive, issued_receipt_bytes=issued)
    assert set(prepared) == set(SCENARIO_CONFIG)
    assert all(item["preflight"]["warmup_bars"] == 252 for item in prepared.values())
    assert all(item["execution_authorized"] is False for item in prepared.values())

def test_archive_or_receipt_bytes_cannot_drift_from_handoff():
    research_data, archive, issued = synthetic_inputs()
    with pytest.raises(IntegrationPreflightDenied, match="HANDOFF_ARCHIVE_BYTES_MISMATCH"):
        prepare_scenario_from_research_data(research_data, archive_bytes=archive+b"x",
            issued_receipt_bytes=issued, scenario_id="S00")
    with pytest.raises(IntegrationPreflightDenied, match="HANDOFF_ISSUED_RECEIPT_BYTES_MISMATCH"):
        prepare_scenario_from_research_data(research_data, archive_bytes=archive,
            issued_receipt_bytes=issued+b"x", scenario_id="S00")

def test_study_invocation_remains_denied_without_separate_admission():
    with pytest.raises(ExecutionDenied, match="SEPARATE_AUTHENTICATED_ADMISSION"):
        run_study(approved=True)
