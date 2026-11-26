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


def _canonical_sha(value):
    import hashlib, json
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def evaluate_24h_report(report, *, expected_code_sha256, expected_symbols,
                        expected_config_sha256=None, provider_terms_cleared=False,
                        quota_headroom_verified=False,
                        expected_verifier_code_sha256=None, database_path=None):
    """Evaluate only complete run-scoped v2 evidence; legacy --report is insufficient."""
    if not isinstance(report, dict):
        return {"status":"24H_RESULT_PENDING","failures":["OWNER_REPORT_MISSING"],
                "natural_fault":"NOT_OBSERVED","orders":0,"trading_authority":"NONE"}
    failures=[]
    top={"schema","natural_fault","run","events","events_complete","events_sha256",
         "clock_validation","coverage","orders","trading_authority","verification"}
    if set(report)!=top:
        failures.append("EVIDENCE_FIELDS_INCOMPLETE_OR_UNKNOWN")
    if report.get("schema")!="atlas.realtime-market-feed.observation-evidence.v2":
        failures.append("COMPLETE_EVIDENCE_ENVELOPE_REQUIRED")
    run=report.get("run")
    run_keys={"schema","run_id","producer_code_sha256","symbols","requested_observe_seconds",
              "started_ms","stopped_ms","config_sha256","source_id",
              "started_monotonic_ms","stopped_monotonic_ms"}
    if not isinstance(run,dict) or set(run)!=run_keys:
        failures.append("RUN_ENVELOPE_MISSING_OR_UNKNOWN_FIELDS")
        run={}
    if run.get("schema")!="aql.realtime-market-feed.observation-run.v2":
        failures.append("RUN_SCHEMA_MISMATCH")
    if type(run.get("run_id")) is not str or not run.get("run_id"):
        failures.append("RUN_ID_MISSING")
    if run.get("producer_code_sha256")!=expected_code_sha256:
        failures.append("PRODUCER_CODE_PIN_MISMATCH")
    symbols=sorted(expected_symbols)
    if run.get("symbols")!=symbols:
        failures.append("SYMBOL_SET_MISMATCH")
    if run.get("requested_observe_seconds")!=86_400:
        failures.append("REQUESTED_DURATION_MISMATCH")
    started,stopped=run.get("started_ms"),run.get("stopped_ms")
    mono_start,mono_stop=run.get("started_monotonic_ms"),run.get("stopped_monotonic_ms")
    elapsed=0
    if any(type(v) is not int or v<0 for v in (started,stopped,mono_start,mono_stop)) or stopped<started or mono_stop<mono_start:
        failures.append("MEASURED_DURATION_OR_CLOCK_INVALID")
    else:
        elapsed=stopped-started
        if elapsed<DAY_MS or mono_stop-mono_start<DAY_MS:
            failures.append("MEASURED_DURATION_SHORT")
    if expected_config_sha256 is not None and run.get("config_sha256")!=expected_config_sha256:
        failures.append("CONFIG_PIN_MISMATCH")
    if run.get("source_id")!="BINANCE_SPOT_PUBLIC_WEBSOCKET":
        failures.append("SOURCE_IDENTITY_MISMATCH")
    if report.get("orders")!=0 or report.get("trading_authority")!="NONE":
        failures.append("SAFETY_BOUNDARY_VIOLATION")

    events=report.get("events")
    if (report.get("events_complete") is not True or type(events) is not list or not events):
        failures.append("COMPLETE_EVENT_SET_REQUIRED")
        events=[]
    event_keys={"id","run_id","at_ms","monotonic_ms","kind","detail"}
    allowed_kinds={"RUN_STARTED","SERVICE_START","SERVICE_STOP","CONNECTING","CONNECTED",
        "SOCKET_ERROR","SOCKET_EXCEPTION","DISCONNECTED","PLANNED_ROTATION","RECONNECT_WAIT",
        "MESSAGE_REJECTED","FINAL_BAR_RECEIVED","FINAL_BAR_CONFLICT","RESTART_REPLAY_VERIFIED","GAP_BACKFILL_LIMIT","GAP_BACKFILL_STARTED",
        "GAP_BACKFILL_COMPLETED","GAP_BACKFILL_FAILED","GAP_BACKFILL_WORKER_ERROR"}
    seen_ids=set()
    prior_id=-1
    prior_mono=-1
    for event in events:
        if not isinstance(event,dict) or set(event)!=event_keys:
            failures.append("EVENT_SCHEMA_OR_UNKNOWN_FIELD")
            continue
        if event["run_id"]!=run.get("run_id"):
            failures.append("EVENT_RUN_ID_MISMATCH")
        if type(event["id"]) is not int or event["id"]<=prior_id or event["id"] in seen_ids:
            failures.append("EVENT_DUPLICATE_OR_REORDERED")
        else:
            seen_ids.add(event["id"]);prior_id=event["id"]
        if event["kind"] not in allowed_kinds:
            failures.append("EVENT_KIND_UNKNOWN")
        if any(type(event[k]) is not int for k in ("at_ms","monotonic_ms")):
            failures.append("EVENT_CLOCK_INVALID")
        elif (type(started) is int and type(stopped) is int and
              not (started<=event["at_ms"]<=stopped)):
            failures.append("EVENT_OUTSIDE_RUN_WINDOW")
        if type(event["monotonic_ms"]) is int:
            if event["monotonic_ms"]<prior_mono:
                failures.append("EVENT_MONOTONIC_ORDER_INVALID")
            prior_mono=event["monotonic_ms"]
            if type(mono_start) is int and type(mono_stop) is int and not (
                mono_start<=event["monotonic_ms"]<=mono_stop):
                failures.append("EVENT_MONOTONIC_OUTSIDE_RUN")
        if type(event["detail"]) is not str:
            failures.append("EVENT_DETAIL_INVALID")
    if not isinstance(report.get("events_sha256"),str) or report["events_sha256"]!=_canonical_sha(events):
        failures.append("EVENT_SET_DIGEST_MISMATCH")
    kinds=[e.get("kind") for e in events if isinstance(e,dict)]
    if "RUN_STARTED" not in kinds or "SERVICE_STOP" not in kinds:
        failures.append("RUN_BOUNDARY_EVENTS_MISSING")
    rotations=[e for e in events if isinstance(e,dict) and e.get("kind")=="PLANNED_ROTATION"]
    reconnects=[e for e in events if isinstance(e,dict) and e.get("kind")=="CONNECTED"]
    if not any(c["id"]>r["id"] and c["at_ms"]>=r["at_ms"] for r in rotations for c in reconnects):
        failures.append("PLANNED_ROTATION_RECONNECT_NOT_PROVEN")

    clock=report.get("clock_validation")
    clock_keys={"method","start_skew_ms","stop_skew_ms","monotonic_elapsed_ms","max_allowed_skew_ms"}
    if not isinstance(clock,dict) or set(clock)!=clock_keys or clock.get("method")!="WALL_MONOTONIC_BRACKET_V1":
        failures.append("CLOCK_VALIDATION_MISSING")
    else:
        limit=clock.get("max_allowed_skew_ms")
        if type(limit) is not int or limit!=2_000 or any(
            type(clock.get(k)) is not int or clock[k]<0 or clock[k]>limit
            for k in ("start_skew_ms","stop_skew_ms")):
            failures.append("CLOCK_SKEW_UNVALIDATED")
        if clock.get("monotonic_elapsed_ms")!= (mono_stop-mono_start if type(mono_stop) is int and type(mono_start) is int else None):
            failures.append("CLOCK_ELAPSED_MISMATCH")

    coverage=report.get("coverage")
    coverage_keys={"expected_closed_bars","observed_closed_bars","per_symbol",
        "missing_open_ranges","open_gaps","conflict_events","duplicate_or_missing_bar_count",
        "all_observed_bars_have_lineage","market_state","short_gaps_recovered",
        "restart_replay_verified","fault_recovery_pairs"}
    if not isinstance(coverage,dict) or set(coverage)!=coverage_keys:
        failures.append("COVERAGE_ENVELOPE_MISSING_OR_UNKNOWN")
        coverage={}
    if type(started) is int and type(stopped) is int:
        expected_n=max(0,(stopped//MINUTE_MS)-(started//MINUTE_MS))*len(symbols)
        if coverage.get("expected_closed_bars")!=expected_n or coverage.get("observed_closed_bars")!=expected_n:
            failures.append("CLOSED_BAR_COVERAGE_INCOMPLETE")
    if coverage.get("missing_open_ranges")!=[] or coverage.get("open_gaps")!=[]:
        failures.append("OPEN_GAPS_PRESENT_OR_UNREPORTED")
    if coverage.get("conflict_events")!=0 or coverage.get("duplicate_or_missing_bar_count")!=0:
        failures.append("DUPLICATE_OR_CONFLICTING_BARS")
    if coverage.get("all_observed_bars_have_lineage") is not True:
        failures.append("BAR_LINEAGE_COVERAGE_INCOMPLETE")
    per=coverage.get("per_symbol")
    if not isinstance(per,dict) or set(per)!=set(symbols):
        failures.append("PER_SYMBOL_COVERAGE_MISSING")
    else:
        for symbol in symbols:
            row=per[symbol]
            if not isinstance(row,dict) or set(row)!={"expected","observed","missing"} or row.get("expected")!=row.get("observed") or row.get("missing")!=[]:
                failures.append("PER_SYMBOL_COVERAGE_INCOMPLETE")
                break
    market=coverage.get("market_state")
    if not isinstance(market,dict) or set(market)!=set(symbols) or any(
        not isinstance(market[s],dict) or set(market[s])!={"trade_received_ms","quote_received_ms","trade_fresh","quote_fresh"}
        or market[s].get("trade_fresh") is not True or market[s].get("quote_fresh") is not True
        for s in symbols if isinstance(market,dict) and s in market):
        failures.append("LATEST_MARKET_STATE_NOT_FRESH")
    if coverage.get("short_gaps_recovered") is not True:
        failures.append("SHORT_GAP_RECOVERY_NOT_PROVEN")
    if coverage.get("restart_replay_verified") is not True:
        failures.append("RESTART_REPLAY_NOT_PROVEN")

    fault_kinds={"SOCKET_ERROR","SOCKET_EXCEPTION","MESSAGE_REJECTED",
                 "GAP_BACKFILL_FAILED","GAP_BACKFILL_WORKER_ERROR"}
    faults=[e for e in events if isinstance(e,dict) and e.get("kind") in fault_kinds]
    natural_fault=report.get("natural_fault")
    pairs=coverage.get("fault_recovery_pairs")
    if natural_fault=="OBSERVED_NOT_RECOVERED":
        failures.append("NATURAL_FAULT_NOT_RECOVERED")
    elif natural_fault=="NOT_OBSERVED":
        if faults or pairs:
            failures.append("NATURAL_FAULT_STATE_MISMATCH")
    elif natural_fault=="OBSERVED_AND_RECOVERED":
        if not faults or not isinstance(pairs,list) or len(pairs)!=len(faults):
            failures.append("FAULT_RECOVERY_PAIRING_INCOMPLETE")
        else:
            by_id={e.get("id"):e for e in events if isinstance(e,dict)}
            for pair in pairs:
                if not isinstance(pair,dict) or set(pair)!={"fault_event_id","recovery_event_id"}:
                    failures.append("FAULT_RECOVERY_PAIR_INVALID");break
                f=by_id.get(pair["fault_event_id"]);r=by_id.get(pair["recovery_event_id"])
                expected=("GAP_BACKFILL_COMPLETED" if f and f.get("kind","").startswith("GAP_")
                    else "FINAL_BAR_RECEIVED" if f and f.get("kind")=="MESSAGE_REJECTED"
                    else "CONNECTED")
                if not f or not r or f not in faults or r.get("kind")!=expected or r["id"]<=f["id"] or r["at_ms"]<f["at_ms"]:
                    failures.append("FAULT_RECOVERY_CAUSALITY_INVALID");break
    else:
        failures.append("NATURAL_FAULT_STATE_INVALID")

    verification=report.get("verification")
    verify_keys={"schema","verifier_id","verifier_code_sha256","method",
        "database_sha256","integrity_check","run_id","verified_at_ms","event_count","events_sha256",
        "evidence_sha256","complete_event_set"}
    if not isinstance(verification,dict) or set(verification)!=verify_keys:
        failures.append("INDEPENDENT_VERIFICATION_MISSING_OR_UNKNOWN")
    else:
        if expected_verifier_code_sha256 is None:
            from tools.realtime_market_feed.observation_evidence import VERIFIER_CODE_SHA256
            expected_verifier_code_sha256=VERIFIER_CODE_SHA256
        if (verification.get("schema")!="atlas.realtime-market-feed.independent-local-verification.v1"
            or verification.get("verifier_id")!="atlas.realtime_market_feed.observation_evidence.build_observation_evidence"
            or verification.get("method")!="READ_ONLY_SQLITE_REOPEN_AND_RECOMPUTE"
            or verification.get("verifier_code_sha256")!=expected_verifier_code_sha256
            or verification.get("integrity_check")!="ok"
            or verification.get("run_id")!=run.get("run_id")
            or type(verification.get("verified_at_ms")) is not int
            or type(stopped) is not int or verification.get("verified_at_ms")<stopped
            or verification.get("event_count")!=len(events)
            or verification.get("events_sha256")!=report.get("events_sha256")
            or verification.get("complete_event_set") is not True
            or type(verification.get("database_sha256")) is not str
            or len(verification.get("database_sha256",""))!=64):
            failures.append("INDEPENDENT_VERIFICATION_INVALID")
        unsigned={k:v for k,v in report.items() if k!="verification"}
        if verification.get("evidence_sha256")!=_canonical_sha(unsigned):
            failures.append("EVIDENCE_DIGEST_MISMATCH")
    if not provider_terms_cleared:
        failures.append("PROVIDER_TERMS_NOT_CLEARED")
    if not quota_headroom_verified:
        failures.append("SHARED_IP_QUOTA_NOT_VERIFIED")
    if database_path is None:
        failures.append("INDEPENDENT_SOURCE_REOPEN_REQUIRED")
    else:
        try:
            from tools.realtime_market_feed.observation_evidence import build_observation_evidence
            independent=build_observation_evidence(database_path,run.get("run_id"))
            if _canonical_sha(independent)!=_canonical_sha(report):
                failures.append("SOURCE_REPORT_RECOMPUTE_MISMATCH")
        except (OSError,ValueError,TypeError,KeyError):
            failures.append("INDEPENDENT_SOURCE_REOPEN_FAILED")
    return {"status":"24H_ACCEPTANCE_PASS" if not failures else "24H_ACCEPTANCE_BLOCKED",
        "failures":sorted(set(failures)),"natural_fault":natural_fault if natural_fault in
        ("OBSERVED_AND_RECOVERED","OBSERVED_NOT_RECOVERED","NOT_OBSERVED") else "UNKNOWN",
        "measured_duration_ms":elapsed,"orders":0,"trading_authority":"NONE"}


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
            allow_synthetic_fixture=True,
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
