from pathlib import Path
import sys
import json
import hashlib

import pytest

ROOT = Path(__file__).resolve().parents[2]
WATCHDOG_CHECKOUT = ROOT / ".integration" / "watchdog"
sys.path.insert(0, str(WATCHDOG_CHECKOUT / "tools"))

from tools.realtime_market_feed.acceptance_gates import (
    evaluate_24h_report, profile_synthetic_windows, verify_sanitized_live_projection,
)
from tools.realtime_market_feed.test_atlas_integration import feed, START
from tools.realtime_market_feed.service import PRODUCER_CODE_SHA256, Store
from atlas_ops_watchdog import live_view


def _accepted_report(tmp_path, *, fault=False, recover=True):
    path=tmp_path/("accepted-fault.sqlite" if fault else "accepted-healthy.sqlite")
    store=Store(path)
    run_id=store.begin_run(["btcusdt"],86_400)
    run=store.db.execute("SELECT started_ms,started_monotonic_ms FROM service_run WHERE run_id=?",
                         (run_id,)).fetchone()
    started,mono_start=run
    stopped=started+86_400_000
    mono_stop=mono_start+86_400_000
    store.event("PLANNED_ROTATION")
    store.event("CONNECTED","symbols=1")
    store.event("RESTART_REPLAY_VERIFIED","prior_run=fixture:database_reopened:bars=1")
    if fault:
        store.event("SOCKET_ERROR","ConnectionResetError")
        if recover:
            store.event("CONNECTED","symbols=1")
    store.event("SERVICE_STOP")
    lo=started//60_000*60_000
    with store.db:
        store.db.execute("UPDATE service_run SET stopped_ms=?,stopped_monotonic_ms=? WHERE run_id=?",
                         (stopped,mono_stop,run_id))
        for i in range(1440):
            opened=lo+i*60_000
            received=started+i*60_000
            payload_sha="a"*64
            store.db.execute("INSERT INTO final_bar VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("BTCUSDT","1m",opened,opened+59_999,"1","2","1","1.5","3",1,received,payload_sha))
            receipt=json.dumps({"fixture":"complete-local-evidence","open_ms":opened},
                               sort_keys=True,separators=(",",":"))
            store.db.execute("INSERT INTO final_bar_lineage VALUES(?,?,?,?,?)",
                ("BTCUSDT","1m",opened,receipt,hashlib.sha256(receipt.encode()).hexdigest()))
        store.db.execute("INSERT INTO latest_trade VALUES(?,?,?,?,?,?,?)",
            ("BTCUSDT",1,"1.5","1",stopped-1000,stopped-1000,0))
        store.db.execute("INSERT INTO latest_quote VALUES(?,?,?,?,?,?,?)",
            ("BTCUSDT","1.4","1","1.6","1",1,stopped-1000))
    store.db.close()
    from tools.realtime_market_feed.observation_evidence import build_observation_evidence
    return build_observation_evidence(path,run_id),path


def _evaluate(report, database_path, **kwargs):
    options={"expected_code_sha256":PRODUCER_CODE_SHA256,
             "expected_symbols":["btcusdt"],
             "expected_config_sha256":report.get("run",{}).get("config_sha256"),
             "provider_terms_cleared":True,"quota_headroom_verified":True,
             "database_path":database_path}
    options.update(kwargs)
    return evaluate_24h_report(report,**options)


def test_24h_gate_requires_complete_evidence_and_accepts_exact_healthy_run(tmp_path):
    pending=evaluate_24h_report(None,expected_code_sha256=PRODUCER_CODE_SHA256,
                                expected_symbols=["btcusdt"])
    assert pending["status"]=="24H_RESULT_PENDING"
    assert pending["natural_fault"]=="NOT_OBSERVED"
    report,path=_accepted_report(tmp_path)
    result=_evaluate(report,path)
    assert result["status"]=="24H_ACCEPTANCE_PASS"
    assert result["natural_fault"]=="NOT_OBSERVED"
    legacy={"observation":{"schema":"aql.realtime-market-feed.observation-run.v1"}}
    result=_evaluate(legacy,path)
    assert "COMPLETE_EVIDENCE_ENVELOPE_REQUIRED" in result["failures"]
    assert "INDEPENDENT_SOURCE_REOPEN_REQUIRED" not in result["failures"]


def test_24h_gate_rejects_out_of_window_and_cross_run_rotation_events(tmp_path):
    report,path=_accepted_report(tmp_path)
    report["events"][1]["at_ms"]=0
    report["events"][1]["monotonic_ms"]=report["run"]["started_monotonic_ms"]-1
    report["events"][2]["run_id"]="other-run"
    result=_evaluate(report,path)
    assert result["status"]=="24H_ACCEPTANCE_BLOCKED"
    assert {"EVENT_OUTSIDE_RUN_WINDOW","EVENT_MONOTONIC_OUTSIDE_RUN",
            "EVENT_RUN_ID_MISMATCH","PLANNED_ROTATION_RECONNECT_NOT_PROVEN",
            "SOURCE_REPORT_RECOMPUTE_MISMATCH"} <= set(result["failures"])


def test_24h_gate_rejects_duplicate_unknown_truncated_and_forged_evidence(tmp_path):
    report,path=_accepted_report(tmp_path)
    report["events"][2]["id"]=report["events"][1]["id"]
    report["events"][2]["unexpected"]="not allowed"
    report["events_complete"]=False
    result=_evaluate(report,path)
    assert {"EVENT_DUPLICATE_OR_REORDERED","EVENT_SCHEMA_OR_UNKNOWN_FIELD",
            "COMPLETE_EVENT_SET_REQUIRED"} <= set(result["failures"])

    report,path=_accepted_report(tmp_path)
    report["coverage"]["expected_closed_bars"]=1439
    assert "CLOSED_BAR_COVERAGE_INCOMPLETE" in _evaluate(report,path)["failures"]

    report,path=_accepted_report(tmp_path)
    report["verification"]["verifier_code_sha256"]="f"*64
    assert "INDEPENDENT_VERIFICATION_INVALID" in _evaluate(report,path)["failures"]


def test_24h_gate_requires_clock_identity_freshness_recovery_and_complete_grid(tmp_path):
    report,path=_accepted_report(tmp_path)
    report["run"]["config_sha256"]="c"*64
    report["clock_validation"]["start_skew_ms"]=9000
    report["coverage"]["market_state"]["btcusdt"]["quote_fresh"]=False
    report["coverage"]["restart_replay_verified"]=False
    report["coverage"]["open_gaps"]=[{"symbol":"BTCUSDT","start_ms":1000,"end_ms":61000}]
    result=_evaluate(report,path)
    assert {"CONFIG_PIN_MISMATCH","CLOCK_SKEW_UNVALIDATED",
            "LATEST_MARKET_STATE_NOT_FRESH","RESTART_REPLAY_NOT_PROVEN",
            "OPEN_GAPS_PRESENT_OR_UNREPORTED","SOURCE_REPORT_RECOMPUTE_MISMATCH"} <= set(result["failures"])


def test_24h_gate_rejects_unrecovered_fault_and_accepts_causal_in_window_recovery(tmp_path):
    report,path=_accepted_report(tmp_path,fault=True,recover=False)
    assert report["natural_fault"]=="OBSERVED_NOT_RECOVERED"
    blocked=_evaluate(report,path)
    assert "NATURAL_FAULT_NOT_RECOVERED" in blocked["failures"]

    report,path=_accepted_report(tmp_path,fault=True,recover=True)
    accepted=_evaluate(report,path)
    assert accepted["status"]=="24H_ACCEPTANCE_PASS"
    assert accepted["natural_fault"]=="OBSERVED_AND_RECOVERED"


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
    assert result["status"]=="SANITIZED_PROJECTION_PASS"
    assert "raw_payload" not in projected and "path" not in projected
    with pytest.raises(ValueError,match="LIVE_PROJECTION_ALLOWLIST_MISMATCH"):
        verify_sanitized_live_projection(report,dict(projected,raw_payload="secret"))

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
