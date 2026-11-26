"""Read-only complete, run-scoped evidence for the 24-hour feed gate.

This verifier reopens the exact SQLite database in read-only mode. It binds
complete run events, UTC and monotonic clocks, closed-bar coverage, current
market freshness, gaps and conflicts to one run id and configuration. Its local
attestation is not a provider signature or protection against a hostile owner
of the same filesystem.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import time

EVIDENCE_SCHEMA = "atlas.realtime-market-feed.observation-evidence.v2"
VERIFIER_ID = "atlas.realtime_market_feed.observation_evidence.build_observation_evidence"
VERIFIER_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
MINUTE_MS = 60_000
MAX_CLOCK_SKEW_MS = 2_000
FRESHNESS_MS = 120_000


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _file_set_sha(path: Path):
    digest = hashlib.sha256()
    files = [path]
    wal = Path(str(path)+"-wal")
    if wal.exists():
        files.append(wal)
    for item in files:
        digest.update(item.name.encode("utf-8"))
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024*1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def build_observation_evidence(database, run_id):
    """Build a full envelope from one run, never from --report's recent events."""
    path = Path(database).resolve()
    if not path.is_file() or type(run_id) is not str or not run_id:
        raise ValueError("OBSERVATION_SOURCE_OR_RUN_MISSING")
    db = sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("OBSERVATION_DATABASE_INTEGRITY_FAILED")
        run_row = db.execute("""SELECT run_id,producer_code_sha256,symbols_json,
            requested_observe_seconds,started_ms,stopped_ms,config_sha256,source_id,
            started_monotonic_ms,stopped_monotonic_ms
            FROM service_run WHERE run_id=?""",(run_id,)).fetchone()
        if not run_row:
            raise ValueError("OBSERVATION_RUN_NOT_FOUND")
        run = dict(run_row)
        symbols = json.loads(run["symbols_json"])
        events = [dict(row) for row in db.execute("""SELECT id,run_id,at_ms,monotonic_ms,kind,detail
            FROM service_event WHERE run_id=? ORDER BY id""",(run_id,)).fetchall()]
        started, stopped = run["started_ms"], run["stopped_ms"]
        if type(started) is not int or type(stopped) is not int:
            raise ValueError("OBSERVATION_RUN_INCOMPLETE")
        lo, hi = started//MINUTE_MS, stopped//MINUTE_MS
        per_symbol = {}
        missing = []
        observed = expected = 0
        for symbol in symbols:
            expected_opens = list(range(lo*MINUTE_MS,hi*MINUTE_MS,MINUTE_MS))
            rows = db.execute("""SELECT open_ms,received_ms FROM final_bar
                WHERE symbol=? AND interval='1m' AND open_ms>=? AND open_ms<?
                  AND received_ms>=? AND received_ms<=? ORDER BY open_ms""",
                (symbol,lo*MINUTE_MS,hi*MINUTE_MS,started,stopped)).fetchall()
            by_open = {}
            for row in rows:
                by_open.setdefault(row["open_ms"],[]).append(row)
            absent = [opened for opened in expected_opens
                      if opened not in by_open or len(by_open[opened]) != 1]
            expected += len(expected_opens)
            observed += len(expected_opens)-len(absent)
            missing.extend([symbol,opened,opened+MINUTE_MS] for opened in absent)
            per_symbol[symbol] = {"expected":len(expected_opens),
                                  "observed":len(expected_opens)-len(absent),
                                  "missing":[[x,x+MINUTE_MS] for x in absent]}
        open_gaps = [dict(row) for row in db.execute("""SELECT symbol,interval,start_ms,end_ms,reason
            FROM open_gap WHERE status='OPEN' AND interval='1m'
              AND start_ms<? AND end_ms>? ORDER BY symbol,start_ms""",
            (hi*MINUTE_MS,lo*MINUTE_MS)).fetchall()]
        conflicts = sum(1 for e in events if e["kind"]=="FINAL_BAR_CONFLICT")
        duplicate_count = max(0,expected-observed)
        market = {}
        for symbol in symbols:
            trade = db.execute("SELECT received_ms FROM latest_trade WHERE symbol=?",(symbol,)).fetchone()
            quote = db.execute("SELECT received_ms FROM latest_quote WHERE symbol=?",(symbol,)).fetchone()
            market[symbol] = {
                "trade_received_ms":trade[0] if trade else None,
                "quote_received_ms":quote[0] if quote else None,
                "trade_fresh":bool(trade and type(stopped) is int and 0 <= stopped-trade[0] <= FRESHNESS_MS),
                "quote_fresh":bool(quote and type(stopped) is int and 0 <= stopped-quote[0] <= FRESHNESS_MS),
            }
        replay = db.execute("""SELECT COUNT(*) FROM final_bar_lineage l JOIN final_bar f
            ON f.symbol=l.symbol AND f.interval=l.interval AND f.open_ms=l.open_ms
            WHERE f.symbol IN (%s) AND f.interval='1m' AND f.open_ms>=? AND f.open_ms<?
              AND f.received_ms>=? AND f.received_ms<=?""" %
            ",".join("?" for _ in symbols),
            tuple(symbols)+(lo*MINUTE_MS,hi*MINUTE_MS,started,stopped)).fetchone()[0] if symbols else 0
        complete_bars_have_receipts = replay == observed
        # Events retain row ids; this digest covers the complete ordered event set.
        event_digest = _sha(_canonical(events))
        before = _file_set_sha(path)
        fault_kinds = {"SOCKET_ERROR","SOCKET_EXCEPTION","MESSAGE_REJECTED",
                       "GAP_BACKFILL_FAILED","GAP_BACKFILL_WORKER_ERROR"}
        recoveries = []
        for event in events:
            if event["kind"] not in fault_kinds:
                continue
            recovery_kind = "GAP_BACKFILL_COMPLETED" if event["kind"].startswith("GAP_") else "CONNECTED"
            recovery = next((candidate for candidate in events
                if candidate["id"] > event["id"] and candidate["kind"] == recovery_kind
                and candidate["at_ms"] >= event["at_ms"]),None)
            if recovery:
                recoveries.append({"fault_event_id":event["id"],
                                   "recovery_event_id":recovery["id"]})
        fault_count = sum(1 for event in events if event["kind"] in fault_kinds)
        natural_fault = ("NOT_OBSERVED" if fault_count == 0 else
                         "OBSERVED_AND_RECOVERED" if len(recoveries) == fault_count else
                         "OBSERVED_NOT_RECOVERED")
        start_event = next((event for event in events if event["kind"]=="RUN_STARTED"),None)
        stop_event = next((event for event in reversed(events) if event["kind"]=="SERVICE_STOP"),None)
        def skew(wall_delta, mono_delta):
            return None if wall_delta is None or mono_delta is None else abs(wall_delta-mono_delta)
        start_skew = None if (not start_event or run["started_monotonic_ms"] is None
                              or type(start_event["monotonic_ms"]) is not int) else skew(
            start_event["at_ms"]-started,start_event["monotonic_ms"]-run["started_monotonic_ms"])
        stop_skew = None if (not stop_event or run["stopped_monotonic_ms"] is None
                             or type(stop_event["monotonic_ms"]) is not int) else skew(
            stopped-stop_event["at_ms"],run["stopped_monotonic_ms"]-stop_event["monotonic_ms"])
        clock = {
            "method":"WALL_MONOTONIC_BRACKET_V1",
            "start_skew_ms":start_skew,"stop_skew_ms":stop_skew,
            "monotonic_elapsed_ms":None if run["started_monotonic_ms"] is None or
                run["stopped_monotonic_ms"] is None else run["stopped_monotonic_ms"]-run["started_monotonic_ms"],
            "max_allowed_skew_ms":MAX_CLOCK_SKEW_MS,
        }
        coverage = {
            "expected_closed_bars":expected,"observed_closed_bars":observed,
            "per_symbol":per_symbol,"missing_open_ranges":missing,
            "open_gaps":open_gaps,"conflict_events":conflicts,
            "duplicate_or_missing_bar_count":duplicate_count,
            "all_observed_bars_have_lineage":complete_bars_have_receipts,
            "market_state":market,
            "short_gaps_recovered":not open_gaps and not missing,
            "restart_replay_verified":False,
            "fault_recovery_pairs":recoveries,
        }
        body = {
            "schema":EVIDENCE_SCHEMA,
            "natural_fault":natural_fault,
            "run":{
                "schema":"aql.realtime-market-feed.observation-run.v2",
                "run_id":run["run_id"],"producer_code_sha256":run["producer_code_sha256"],
                "symbols":symbols,"requested_observe_seconds":run["requested_observe_seconds"],
                "started_ms":started,"stopped_ms":stopped,
                "config_sha256":run["config_sha256"],"source_id":run["source_id"],
                "started_monotonic_ms":run["started_monotonic_ms"],
                "stopped_monotonic_ms":run["stopped_monotonic_ms"],
            },
            "events":events,"events_complete":True,"events_sha256":event_digest,
            "clock_validation":clock,"coverage":coverage,
            "orders":0,"trading_authority":"NONE",
        }
        report_sha = _sha(_canonical(body))
        verification = {
            "schema":"atlas.realtime-market-feed.independent-local-verification.v1",
            "verifier_id":VERIFIER_ID,"verifier_code_sha256":VERIFIER_CODE_SHA256,
            "method":"READ_ONLY_SQLITE_REOPEN_AND_RECOMPUTE",
            "database_sha256":before,"integrity_check":integrity,
            "run_id":run_id,"event_count":len(events),"events_sha256":event_digest,
            "evidence_sha256":report_sha,"complete_event_set":True,
        }
        # Ensure the input files did not change while this independent snapshot
        # was read; a changed WAL/database invalidates the envelope.
        after = _file_set_sha(path)
        if before != after:
            raise ValueError("OBSERVATION_DATABASE_CHANGED_DURING_VERIFY")
        return {**body,"verification":verification}
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--database",required=True)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    result=build_observation_evidence(args.database,args.run_id)
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+"\\n",encoding="utf-8")
    print(json.dumps({"schema":result["schema"],"run_id":args.run_id,
        "events":len(result["events"]),"evidence_sha256":result["verification"]["evidence_sha256"],
        "output":"WRITTEN","trading_authority":"NONE"},sort_keys=True))


if __name__ == "__main__":
    main()
