"""Off-host acceptance gates and bounded synthetic profiling.

These gates never inspect owner-host data. A 24-hour result remains pending until
an independently captured, code-pinned owner report supplies every required field.
"""
from __future__ import annotations

import time
import tracemalloc
from pathlib import Path

MINUTE_MS = 60_000
DAY_MS = 86_400_000
MAX_WINDOW_BARS = 10_080
QUERY_BUDGET_MS = 5_000


def evaluate_24h_report(report, *, expected_code_sha256, expected_symbols,
                        expected_config_sha256=None, provider_terms_cleared=False,
                        quota_headroom_verified=False):
    """Evaluate only an explicitly supplied owner report; absence is PENDING."""
    if not isinstance(report, dict):
        return {"status":"24H_RESULT_PENDING","failures":["OWNER_REPORT_MISSING"],
                "natural_fault":"NOT_OBSERVED","orders":0,"trading_authority":"NONE"}
    failures = []
    run = report.get("observation")
    if not isinstance(run, dict):
        failures.append("RUN_ENVELOPE_MISSING")
        run = {}
    if run.get("schema") != "aql.realtime-market-feed.observation-run.v1":
        failures.append("RUN_SCHEMA_MISMATCH")
    if run.get("producer_code_sha256") != expected_code_sha256:
        failures.append("PRODUCER_CODE_PIN_MISMATCH")
    if run.get("symbols") != sorted(expected_symbols):
        failures.append("SYMBOL_SET_MISMATCH")
    if run.get("requested_observe_seconds") != 86_400:
        failures.append("REQUESTED_DURATION_MISMATCH")
    started, stopped = run.get("started_ms"), run.get("stopped_ms")
    if type(started) is not int or type(stopped) is not int or stopped < started:
        failures.append("MEASURED_DURATION_MISSING")
        elapsed = 0
    else:
        elapsed = stopped - started
        if elapsed < DAY_MS:
            failures.append("MEASURED_DURATION_SHORT")
    if expected_config_sha256 and run.get("config_sha256") != expected_config_sha256:
        failures.append("CONFIG_PIN_MISMATCH")
    if report.get("orders") != 0 or report.get("trading_authority") != "NONE":
        failures.append("SAFETY_BOUNDARY_VIOLATION")
    if report.get("integrity_check") != "ok" or report.get("durable_readback_verified") is not True:
        failures.append("DURABLE_READBACK_NOT_PROVEN")
    if report.get("fresh_trade_quote_final_bar") is not True:
        failures.append("LATEST_MARKET_STATE_NOT_FRESH")
    if report.get("short_gaps_recovered") is not True:
        failures.append("SHORT_GAP_RECOVERY_NOT_PROVEN")
    if report.get("unexplained_message_rejections") != 0:
        failures.append("MESSAGE_REJECTIONS_UNEXPLAINED")
    if report.get("open_gaps") != []:
        failures.append("OPEN_GAPS_PRESENT_OR_UNREPORTED")
    events = report.get("events")
    if not isinstance(events, list):
        failures.append("EVENT_EVIDENCE_MISSING")
        events = []
    rotations = [event.get("at_ms") for event in events
                 if isinstance(event, dict) and event.get("kind") == "PLANNED_ROTATION"
                 and type(event.get("at_ms")) is int]
    reconnects = [event.get("at_ms") for event in events
                  if isinstance(event, dict) and event.get("kind") == "CONNECTED"
                  and type(event.get("at_ms")) is int]
    if not rotations or not any(t > r for r in rotations for t in reconnects):
        failures.append("PLANNED_ROTATION_RECONNECT_NOT_PROVEN")
    if report.get("replay_after_restart_verified") is not True:
        failures.append("RESTART_REPLAY_NOT_PROVEN")
    if not provider_terms_cleared:
        failures.append("PROVIDER_TERMS_NOT_CLEARED")
    if not quota_headroom_verified:
        failures.append("SHARED_IP_QUOTA_NOT_VERIFIED")
    natural_fault = report.get("natural_fault")
    if natural_fault not in ("OBSERVED_AND_RECOVERED", "OBSERVED_NOT_RECOVERED", "NOT_OBSERVED"):
        natural_fault = "NOT_OBSERVED"
    return {
        "status":"24H_ACCEPTANCE_PASS" if not failures else "24H_ACCEPTANCE_BLOCKED",
        "failures":failures,"natural_fault":natural_fault,
        "measured_duration_ms":elapsed,"orders":0,"trading_authority":"NONE",
    }


def profile_synthetic_windows(database, *, symbol, start_ms, counts,
                              expected_producer_code_sha256):
    """Profile generated-only DB windows; no physical-I/O claim is made."""
    from tools.realtime_market_feed.atlas_integration import project_feed_window
    output = []
    for count in counts:
        if type(count) is not int or not 0 < count <= MAX_WINDOW_BARS:
            raise ValueError("PROFILE_WINDOW_BOUND")
        end_ms = start_ms + count * MINUTE_MS
        metrics = {}
        tracemalloc.start()
        started = time.perf_counter()
        bars = project_feed_window(
            database, symbol=symbol, start_ms=start_ms, end_ms=end_ms,
            now_ms=end_ms + 120_001, max_age_ms=86_400_000,
            expected_producer_code_sha256=expected_producer_code_sha256,
            query_budget_ms=QUERY_BUDGET_MS, metrics=metrics)
        elapsed_ms = round((time.perf_counter()-started)*1000, 3)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if len(bars) != count or elapsed_ms > 30_000 or peak > 128*1024*1024:
            raise ValueError("SYNTHETIC_PROFILE_CEILING_EXCEEDED")
        output.append({
            "bars":count,"elapsed_ms":elapsed_ms,"python_peak_bytes":peak,
            "decoded_logical_bytes":metrics["decoded_source_bytes"],
            "sqlite_file_bytes_proxy":Path(database).stat().st_size,
            "read_snapshot_ms":metrics["read_snapshot_ms"],
            "query_budget_ms":QUERY_BUDGET_MS,
            "physical_bytes_read":"NOT_MEASURED_SQLITE_STDLIB_NO_VFS_COUNTER",
        })
    return {"status":"SYNTHETIC_PROFILE_PASS","scope":"GENERATED_TEMP_FIXTURE_ONLY",
            "proposed_ceilings":{"window_bars":MAX_WINDOW_BARS,
                                 "query_budget_ms":QUERY_BUDGET_MS,
                                 "profile_wall_ms_per_window":30_000,
                                 "python_peak_bytes_per_window":128*1024*1024},
            "measurements":output}


def verify_sanitized_live_projection(report, live_view):
    """Require the existing watchdog's allowlisted fields, with no payload/path."""
    if not isinstance(report, dict) or not isinstance(live_view, dict):
        raise ValueError("LIVE_PROJECTION_INVALID")
    allowed = {"status","as_of_ms","verified_receipts","last_committed_ms",
               "last_receipt_fresh","missing_ranges","hold_reason",
               "last_receipt_sha256"}
    if set(live_view) != allowed:
        raise ValueError("LIVE_PROJECTION_ALLOWLIST_MISMATCH")
    if any(k in live_view for k in ("path","raw_payload","quotes","trades","open_gaps")):
        raise ValueError("LIVE_PROJECTION_LEAK")
    return {"status":"SANITIZED_PROJECTION_PASS","fields":sorted(live_view),
            "source_schema":report.get("schema")}
