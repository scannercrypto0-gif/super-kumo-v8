from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
WATCHDOG_CHECKOUT = ROOT / ".integration" / "watchdog"
sys.path.insert(0, str(WATCHDOG_CHECKOUT / "tools"))

from tools.realtime_market_feed.acceptance_gates import (
    evaluate_24h_report, profile_synthetic_windows, verify_sanitized_live_projection,
)
from tools.realtime_market_feed.test_atlas_integration import feed, START
from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256
from atlas_ops_watchdog import live_view


def _accepted_report():
    return {
        "observation":{
            "schema":"aql.realtime-market-feed.observation-run.v1",
            "producer_code_sha256":"a"*64,"symbols":["btcusdt"],
            "requested_observe_seconds":86400,"started_ms":0,"stopped_ms":86400000,
            "config_sha256":"b"*64,
        },
        "orders":0,"trading_authority":"NONE","integrity_check":"ok",
        "durable_readback_verified":True,"fresh_trade_quote_final_bar":True,
        "short_gaps_recovered":True,"unexplained_message_rejections":0,
        "open_gaps":[],"events":[
            {"kind":"PLANNED_ROTATION","at_ms":80000000},
            {"kind":"CONNECTED","at_ms":80000100},
        ],
        "replay_after_restart_verified":True,"natural_fault":"NOT_OBSERVED",
    }


def test_24h_gate_pending_and_exact_acceptance():
    pending=evaluate_24h_report(None,expected_code_sha256="a"*64,
                                expected_symbols=["btcusdt"])
    assert pending["status"] == "24H_RESULT_PENDING"
    assert pending["natural_fault"] == "NOT_OBSERVED"

    report=_accepted_report()
    result=evaluate_24h_report(report,expected_code_sha256="a"*64,
        expected_symbols=["btcusdt"],expected_config_sha256="b"*64,
        provider_terms_cleared=True,quota_headroom_verified=True)
    assert result["status"] == "24H_ACCEPTANCE_PASS"
    assert result["natural_fault"] == "NOT_OBSERVED"


def test_24h_gate_fails_closed_on_pin_duration_and_missing_proofs():
    report=_accepted_report()
    report["observation"]["producer_code_sha256"]="c"*64
    report["observation"]["stopped_ms"]=1000
    report["open_gaps"]=[[60_000,120_000]]
    report["replay_after_restart_verified"]=False
    result=evaluate_24h_report(report,expected_code_sha256="a"*64,
        expected_symbols=["btcusdt"],expected_config_sha256="b"*64)
    assert result["status"] == "24H_ACCEPTANCE_BLOCKED"
    assert {"PRODUCER_CODE_PIN_MISMATCH","MEASURED_DURATION_SHORT",
            "OPEN_GAPS_PRESENT_OR_UNREPORTED","RESTART_REPLAY_NOT_PROVEN",
            "PROVIDER_TERMS_NOT_CLEARED","SHARED_IP_QUOTA_NOT_VERIFIED"} <= set(result["failures"])


def test_synthetic_window_profile_reports_proxy_and_honest_io_limit(tmp_path):
    path=tmp_path/"feed.sqlite"
    feed(path,count=10)
    result=profile_synthetic_windows(path,symbol="BTCUSDT",start_ms=START,
        counts=[1,10],expected_producer_code_sha256=PRODUCER_CODE_SHA256)
    assert result["status"] == "SYNTHETIC_PROFILE_PASS"
    assert [x["bars"] for x in result["measurements"]] == [1,10]
    assert all(x["decoded_logical_bytes"] > 0 for x in result["measurements"])
    assert all(x["sqlite_file_bytes_proxy"] > 0 for x in result["measurements"])
    assert all(x["physical_bytes_read"] == "NOT_MEASURED_SQLITE_STDLIB_NO_VFS_COUNTER"
               for x in result["measurements"])


def test_existing_watchdog_projection_is_exactly_sanitized():
    report={
        "schema":"atlas.ws.continuous-report.v1","source_class":"LIVE_CAPTURE",
        "trading_authority":"NONE","orders":0,"status":"OBSERVING_CONTINUOUS_ACCEPTANCE",
        "as_of_ms":1000,"verified_receipts":1,"verified_receipt_sha256":["a"*64],
        "last_committed_ms":900,"last_receipt_fresh":True,"missing_open_ranges":[],
        "hold_reason":None,
    }
    projected=live_view(report)
    result=verify_sanitized_live_projection(report,projected)
    assert result["status"] == "SANITIZED_PROJECTION_PASS"
    assert "raw_payload" not in projected and "path" not in projected
    with pytest.raises(ValueError,match="LIVE_PROJECTION_ALLOWLIST_MISMATCH"):
        verify_sanitized_live_projection(report,dict(projected,raw_payload="secret"))
