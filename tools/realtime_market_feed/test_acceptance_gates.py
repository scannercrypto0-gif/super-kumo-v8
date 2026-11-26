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


def _seal(report):
    from tools.realtime_market_feed.acceptance_gates import _canonical_sha
    report["events_sha256"]=_canonical_sha(report["events"])
    unsigned={k:v for k,v in report.items() if k!="verification"}
    from tools.realtime_market_feed.observation_evidence import VERIFIER_CODE_SHA256
    report["verification"]={
        "schema":"atlas.realtime-market-feed.independent-local-verification.v1",
        "verifier_id":"atlas.realtime_market_feed.observation_evidence.build_observation_evidence",
        "verifier_code_sha256":VERIFIER_CODE_SHA256,
        "method":"READ_ONLY_SQLITE_REOPEN_AND_RECOMPUTE",
        "database_sha256":"d"*64,"integrity_check":"ok",
        "run_id":report["run"]["run_id"],"event_count":len(report["events"]),
        "events_sha256":report["events_sha256"],"evidence_sha256":_canonical_sha(unsigned),
        "complete_event_set":True,
    }
    return report


def _accepted_report():
    started,stopped=1_000,86_401_000
    mono_start,mono_stop=5_000,86_405_000
    run={"schema":"aql.realtime-market-feed.observation-run.v2","run_id":"run-a",
         "producer_code_sha256":"a"*64,"symbols":["btcusdt"],
         "requested_observe_seconds":86_400,"started_ms":started,"stopped_ms":stopped,
         "config_sha256":"b"*64,"source_id":"BINANCE_SPOT_PUBLIC_WEBSOCKET",
         "started_monotonic_ms":mono_start,"stopped_monotonic_ms":mono_stop}
    events=[
        {"id":1,"run_id":"run-a","at_ms":started,"monotonic_ms":mono_start,
         "kind":"RUN_STARTED","detail":"observation-v2"},
        {"id":2,"run_id":"run-a","at_ms":80_000_000,"monotonic_ms":80_004_000,
         "kind":"PLANNED_ROTATION","detail":""},
        {"id":3,"run_id":"run-a","at_ms":80_000_100,"monotonic_ms":80_004_100,
         "kind":"CONNECTED","detail":"symbols=1"},
        {"id":4,"run_id":"run-a","at_ms":stopped,"monotonic_ms":mono_stop,
         "kind":"SERVICE_STOP","detail":""},
    ]
    coverage={"expected_closed_bars":1440,"observed_closed_bars":1440,
        "per_symbol":{"btcusdt":{"expected":1440,"observed":1440,"missing":[]}},
        "missing_open_ranges":[],"open_gaps":[],"conflict_events":0,
        "duplicate_or_missing_bar_count":0,"all_observed_bars_have_lineage":True,
        "market_state":{"btcusdt":{"trade_received_ms":stopped-1000,
             "quote_received_ms":stopped-1000,"trade_fresh":True,"quote_fresh":True}},
        "short_gaps_recovered":True,"restart_replay_verified":True,
        "fault_recovery_pairs":[]}
    report={"schema":"atlas.realtime-market-feed.observation-evidence.v2",
        "natural_fault":"NOT_OBSERVED","run":run,"events":events,
        "events_complete":True,"events_sha256":"",
        "clock_validation":{"method":"WALL_MONOTONIC_BRACKET_V1","start_skew_ms":0,
            "stop_skew_ms":0,"monotonic_elapsed_ms":86_400_000,"max_allowed_skew_ms":2000},
        "coverage":coverage,"orders":0,"trading_authority":"NONE"}
    return _seal(report)


def _evaluate(report, **kwargs):
    options={"expected_code_sha256":"a"*64,"expected_symbols":["btcusdt"],
             "expected_config_sha256":"b"*64,"provider_terms_cleared":True,
             "quota_headroom_verified":True}
    options.update(kwargs)
    return evaluate_24h_report(report,**options)


def test_24h_gate_requires_complete_evidence_and_accepts_exact_healthy_run():
    pending=evaluate_24h_report(None,expected_code_sha256="a"*64,
                                expected_symbols=["btcusdt"])
    assert pending["status"]=="24H_RESULT_PENDING"
    assert pending["natural_fault"]=="NOT_OBSERVED"
    legacy={"observation":{"schema":"aql.realtime-market-feed.observation-run.v1"}}
    assert "COMPLETE_EVIDENCE_ENVELOPE_REQUIRED" in _evaluate(legacy)["failures"]

    result=_evaluate(_accepted_report())
    assert result["status"]=="24H_ACCEPTANCE_PASS"
    assert result["natural_fault"]=="NOT_OBSERVED"


def test_24h_gate_rejects_out_of_window_and_cross_run_rotation_events():
    report=_accepted_report()
    report["events"][1]["at_ms"]=0
    report["events"][1]["monotonic_ms"]=4999
    report["events"][2]["run_id"]="other-run"
    _seal(report)
    result=_evaluate(report)
    assert result["status"]=="24H_ACCEPTANCE_BLOCKED"
    assert {"EVENT_OUTSIDE_RUN_WINDOW","EVENT_MONOTONIC_OUTSIDE_RUN",
            "EVENT_RUN_ID_MISMATCH","PLANNED_ROTATION_RECONNECT_NOT_PROVEN"} <= set(result["failures"])


def test_24h_gate_rejects_duplicate_unknown_truncated_and_forged_evidence():
    report=_accepted_report()
    report["events"][2]["id"]=2
    report["events"][2]["unexpected"]="not allowed"
    report["events_complete"]=False
    _seal(report)
    result=_evaluate(report)
    assert {"EVENT_DUPLICATE_OR_REORDERED","EVENT_SCHEMA_OR_UNKNOWN_FIELD",
            "COMPLETE_EVENT_SET_REQUIRED"} <= set(result["failures"])

    report=_accepted_report()
    report["coverage"]["expected_closed_bars"]=1439
    _seal(report)
    assert "CLOSED_BAR_COVERAGE_INCOMPLETE" in _evaluate(report)["failures"]

    report=_accepted_report()
    report["verification"]["verifier_code_sha256"]="f"*64
    assert "INDEPENDENT_VERIFICATION_INVALID" in _evaluate(report)["failures"]


def test_24h_gate_requires_clock_identity_freshness_recovery_and_complete_grid():
    report=_accepted_report()
    report["run"]["config_sha256"]="c"*64
    report["clock_validation"]["start_skew_ms"]=9000
    report["coverage"]["market_state"]["btcusdt"]["quote_fresh"]=False
    report["coverage"]["restart_replay_verified"]=False
    report["coverage"]["open_gaps"]=[{"symbol":"btcusdt","start_ms":1000,"end_ms":61000}]
    _seal(report)
    result=_evaluate(report)
    assert {"CONFIG_PIN_MISMATCH","CLOCK_SKEW_UNVALIDATED",
            "LATEST_MARKET_STATE_NOT_FRESH","RESTART_REPLAY_NOT_PROVEN",
            "OPEN_GAPS_PRESENT_OR_UNREPORTED"} <= set(result["failures"])


def test_24h_gate_rejects_unrecovered_fault_and_accepts_causal_in_window_recovery():
    report=_accepted_report()
    fault={"id":4,"run_id":"run-a","at_ms":80_001_000,"monotonic_ms":80_005_000,
           "kind":"SOCKET_ERROR","detail":"ConnectionResetError"}
    report["events"].insert(-1,fault)
    report["events"][-1]["id"]=5
    report["natural_fault"]="OBSERVED_NOT_RECOVERED"
    report["coverage"]["fault_recovery_pairs"]=[]
    _seal(report)
    blocked=_evaluate(report)
    assert "NATURAL_FAULT_NOT_RECOVERED" in blocked["failures"]

    report["natural_fault"]="OBSERVED_AND_RECOVERED"
    report["coverage"]["fault_recovery_pairs"]=[{"fault_event_id":4,"recovery_event_id":5}]
    # The prior CONNECTED event remains earlier than the fault, so use a later recovery.
    report["events"][-1]["id"]=6
    report["events"].insert(-1,{"id":5,"run_id":"run-a","at_ms":80_002_000,
        "monotonic_ms":80_006_000,"kind":"CONNECTED","detail":"symbols=1"})
    report["coverage"]["fault_recovery_pairs"]=[{"fault_event_id":4,"recovery_event_id":5}]
    _seal(report)
    accepted=_evaluate(report)
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
