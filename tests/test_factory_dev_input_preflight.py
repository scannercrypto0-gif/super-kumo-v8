"""Synthetic-only tests for exact first-run input preflight."""
from hashlib import sha256
from io import BytesIO
import zipfile

import pytest

from research_wp_r0.historical_dev_exits_v1 import Config, digest, replay
from research_wp_r0.dev_result_bundle import persist_bundle, verify_bundle
from research_wp_r0.dev_input_preflight import (
    InputGateRejected, validate_historical_dev_inputs,
)

START = 1704067200000
END = 1704153600000


def archive_bytes():
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("fixture.csv", "synthetic fixture only\n")
    return out.getvalue()


def bars():
    return [
        {"open_ms": START + i*60000, "close_ms": START + (i+1)*60000-1,
         "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
         "volume": 1.0, "available_ms": START + (i+1)*60000+1000,
         "modeled_quote": True}
        for i in range(1440)
    ]


def inputs():
    raw = archive_bytes()
    issued = b'{"synthetic_receipt":"fixture-not-issued"}'
    rows = bars()
    source = {"version": "synthetic-b0", "reference": "fixture:input-preflight",
              "archive_sha256": sha256(raw).hexdigest(),
              "rows_sha256": digest(rows), "availability_evidence": "UNKNOWN",
              "correction_evidence": "PINNED_VERSION_ONLY"}
    commitment = {
        "issued_receipt_sha256": sha256(issued).hexdigest(),
        "symbol": "BTCUSDT", "interval_ms": 60000,
        "start_ms": START, "end_exclusive_ms": END,
        "code_sha": "a"*40, "policy_id": "DEV-B0-v1",
        "scenario_id": "S00", "warmup_bars": 252,
    }
    return raw, issued, rows, source, commitment


def run(args):
    raw, issued, rows, source, commitment = args
    return validate_historical_dev_inputs(
        archive_bytes=raw, issued_receipt_bytes=issued, bars=rows,
        source=source, config=Config(warmup_bars=252), commitment=commitment)


def test_exact_one_day_preflight_returns_non_authorizing_manifest():
    out = run(inputs())
    assert out["status"] == "INPUT_BYTES_AND_NORMALIZED_ROWS_VALID_NOT_STUDY_AUTHORITY"
    assert out["bar_count"] == 1440
    assert out["warmup_bars"] == 252
    assert out["receipt_authenticity"] == "NOT_AUTHENTICATED_BY_THIS_GATE"


@pytest.mark.parametrize("field,value,error", [
    ("symbol", "ETHUSDT", "UNEXPECTED_SYMBOL"),
    ("interval_ms", 300000, "UNEXPECTED_INTERVAL"),
    ("warmup_bars", 22, "EXPLICIT_252_WARMUP_REQUIRED"),
    ("start_ms", START+60000, "UNEXPECTED_WINDOW"),
])
def test_wrong_run_contract_fails_closed(field, value, error):
    args = list(inputs())
    args[4] = dict(args[4])
    args[4][field] = value
    with pytest.raises(InputGateRejected, match=error):
        run(tuple(args))


def test_wrong_archive_or_issued_receipt_digest_fails_closed():
    args = list(inputs())
    args[0] = args[0] + b"tampered"
    with pytest.raises(InputGateRejected, match="ORIGINAL_ARCHIVE_SHA_MISMATCH"):
        run(tuple(args))
    args = list(inputs())
    args[1] = args[1] + b"tampered"
    with pytest.raises(InputGateRejected, match="ISSUED_RECEIPT_SHA_MISMATCH"):
        run(tuple(args))


def test_missing_bar_and_corrupt_archive_fail_closed():
    args = list(inputs())
    args[2] = args[2][:-1]
    with pytest.raises(InputGateRejected, match="1440"):
        run(tuple(args))
    args = list(inputs())
    args[0] = b"not a zip archive"
    with pytest.raises(InputGateRejected, match="ORIGINAL_ARCHIVE_SHA_MISMATCH"):
        run(tuple(args))


def test_row_tampering_fails_closed():
    args = list(inputs())
    args[2] = list(args[2])
    args[2][100] = dict(args[2][100], open_ms=args[2][100]["open_ms"]+1)
    with pytest.raises(InputGateRejected):
        run(tuple(args))


def test_validated_preflight_is_saved_and_reverified_with_result_bundle(tmp_path):
    raw, issued, rows, source, commitment = inputs()
    config = Config(warmup_bars=252)
    preflight = validate_historical_dev_inputs(
        archive_bytes=raw, issued_receipt_bytes=issued, bars=rows,
        source=source, config=config, commitment=commitment)
    receipt = replay(rows, source=source, config=config)
    evidence = {
        "policy_id": "DEV-B0-v1",
        "policy_sha256": digest({"policy_id": "DEV-B0-v1",
                                 "engine_config": receipt["config"]}),
        "source_zip_sha256": source["archive_sha256"],
        "issued_receipt_sha256": commitment["issued_receipt_sha256"],
        "code_sha": commitment["code_sha"],
        "input_prefix_sha256": digest(receipt["input_rows"]),
        "scenario_id": commitment["scenario_id"],
        "warmup_bars": 252,
        "experiment_id": "AQL-DEV-FIRST-01",
    }
    manifest = persist_bundle(str(tmp_path), run_id="preflighted-run",
                              receipt=receipt, evidence=evidence,
                              input_preflight=preflight)
    assert "input_preflight.json" in manifest["files"]
    assert verify_bundle(str(tmp_path), "preflighted-run")
    saved = __import__("json").loads(
        (tmp_path / "preflighted-run" / "input_preflight.json").read_text())
    assert saved["archive_sha256"] == source["archive_sha256"]
    assert saved["bar_count"] == 1440


def test_preflight_cannot_be_attached_to_different_receipt_or_policy(tmp_path):
    raw, issued, rows, source, commitment = inputs()
    config = Config(warmup_bars=252)
    preflight = validate_historical_dev_inputs(
        archive_bytes=raw, issued_receipt_bytes=issued, bars=rows,
        source=source, config=config, commitment=commitment)
    receipt = replay(rows, source=source, config=config)
    evidence = {
        "policy_id": "DEV-B0-v1",
        "policy_sha256": digest({"policy_id": "DEV-B0-v1",
                                 "engine_config": receipt["config"]}),
        "source_zip_sha256": source["archive_sha256"],
        "issued_receipt_sha256": "f"*64,
        "code_sha": commitment["code_sha"],
        "input_prefix_sha256": digest(receipt["input_rows"]),
        "scenario_id": commitment["scenario_id"],
        "warmup_bars": 252,
        "experiment_id": "AQL-DEV-FIRST-02",
    }
    with pytest.raises(ValueError, match="INPUT_PREFLIGHT_RECEIPT_BINDING_MISMATCH"):
        persist_bundle(str(tmp_path), run_id="mismatched-run",
                       receipt=receipt, evidence=evidence,
                       input_preflight=preflight)
    assert not (tmp_path / "mismatched-run").exists()
