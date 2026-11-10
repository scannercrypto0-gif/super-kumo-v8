"""Disposable Supabase only. Pre-provision role and schema; inject DSN privately."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from time import perf_counter, time_ns
from uuid import uuid4

from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.storage.operational_store import OperationalStore
from aql.storage.sandbox_store import PostgresSandboxStore, SandboxReplicator, StoreUnavailable

CANDIDATE = "ee8107d88069c73b13abdffb8c5bd1770e2c961b"
PROJECT_REF = "bolnrcksslkrxnilbdnk"
STATS = """SELECT pg_total_relation_size('aql_sandbox.market_bars'), n_tup_ins,
                  heap_blks_read, heap_blks_hit
           FROM pg_stat_user_tables JOIN pg_statio_user_tables USING (relid)
           WHERE pg_stat_user_tables.schemaname = 'aql_sandbox'
             AND pg_stat_user_tables.relname = 'market_bars'"""

def connection_settings():
    if os.environ.get("ATLAS_DISPOSABLE_SUPABASE_AUTHORIZED") != "1":
        raise SystemExit("BLOCKED: explicit disposable Supabase authorization required")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    dsn = os.environ.get("ATLAS_DISPOSABLE_SUPABASE_DSN")
    if not dsn:
        raise SystemExit("BLOCKED: writer DSN must be injected from secret storage")
    info = conninfo_to_dict(dsn)
    host = info.get("host", "")
    user = info.get("user")
    expected_endpoint = (
        (host == f"db.{PROJECT_REF}.supabase.co" and user == "aql_sandbox_probe")
        or (host.endswith(".pooler.supabase.com") and info.get("port", "5432") == "5432"
            and user == f"aql_sandbox_probe.{PROJECT_REF}")
    )
    if (not expected_endpoint
            or info.get("hostaddr") or info.get("sslmode") != "verify-full"
            or info.get("user", "").split(".")[0] != "aql_sandbox_probe"):
        raise SystemExit("BLOCKED: verified TLS and dedicated aql_sandbox_probe login required")
    return psycopg, dsn, host

def crash_after_commit(root):
    psycopg, dsn, _ = connection_settings()
    remote = PostgresSandboxStore(lambda: psycopg.connect(dsn, connect_timeout=5),
                                 sandbox=True, attempts=1)

    class InterruptAfterCommit:
        def upsert(self, bar):
            if remote.upsert(bar) is not True:
                raise RuntimeError("First remote insert was not new")
            os._exit(73)

    SandboxReplicator(DurableJournal(str(root / "journal.sqlite")),
                      InterruptAfterCommit(), str(root / "cursor.sqlite"),
                      batch_size=1).deliver_once()

def main():
    psycopg, dsn, host = connection_settings()
    counts = {"connections": 0, "fallback_injections": 0}
    timings = {}
    start = datetime.now(timezone.utc).isoformat()
    symbol = "ATLASPROBE" + uuid4().hex[:16].upper()
    close = (time_ns() // 1_000_000 // 900_000) * 900_000 - 1
    bar = MarketBar(symbol, "15m", close-899999, close, 100., 102., 98., 101.,
                    1., True, "synthetic_supabase_probe", close+1).with_checksum()

    def connect():
        counts["connections"] += 1
        return psycopg.connect(dsn, connect_timeout=5)

    def read_metrics():
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute("""SELECT current_user = 'aql_sandbox_probe'
                                      AND session_user = current_user
                                      AND pg_has_role(current_user, 'aql_sandbox_writer', 'MEMBER')
                                      AND NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls)
                                      AND NOT has_table_privilege(current_user, 'aql_sandbox.market_bars', 'DELETE')
                                      AND NOT has_table_privilege(current_user, 'aql_sandbox.market_bars', 'UPDATE')
                               FROM pg_roles WHERE rolname = current_user""")
                if cur.fetchone() != (True,):
                    raise RuntimeError("Writer role exceeds sandbox permissions")
                cur.execute(STATS)
                metrics = cur.fetchone()
                if metrics is None:
                    raise RuntimeError("Sandbox relation metrics unavailable")
                cur.execute("SELECT count(*), min(checksum) FROM aql_sandbox.market_bars "
                            "WHERE symbol=%s AND interval=%s AND bar_open=%s",
                            (symbol, "15m", bar.bar_open))
                return metrics, cur.fetchone()

    def measure(label, operation):
        started = perf_counter()
        try:
            return operation()
        finally:
            timings[label] = round((perf_counter() - started)*1000, 3)

    def unavailable():
        counts["fallback_injections"] += 1
        raise OSError("Controlled connection loss")

    before, absent = measure("before_read_ms", read_metrics)
    if absent != (0, None):
        raise RuntimeError("Fixture key collision")
    with tempfile.TemporaryDirectory(prefix="atlas-supabase-probe-") as tmp:
        root = Path(tmp)
        journal = DurableJournal(str(root / "journal.sqlite"))
        local = OperationalStore(str(root / "market.sqlite"))
        journal.commit(bar)
        local.upsert(bar)
        journal.mark_persisted(bar.stable_key())
        cursor = str(root / "cursor.sqlite")
        remote = PostgresSandboxStore(connect, sandbox=True, attempts=1)
        offline = SandboxReplicator(journal, PostgresSandboxStore(unavailable, sandbox=True, attempts=1),
                                    cursor, batch_size=1)
        try:
            offline.deliver_once()
        except StoreUnavailable:
            pass
        else:
            raise RuntimeError("Expected offline fallback")
        def cursor_seq():
            with closing(sqlite3.connect(Path(cursor).as_uri() + "?mode=ro", uri=True)) as db:
                return db.execute("SELECT seq FROM delivery_cursor").fetchone()[0]

        if cursor_seq() != 0:
            raise RuntimeError("Offline failure advanced the cursor")
        child = measure("commit_then_crash_ms", lambda: subprocess.run(
            [sys.executable, "-B", __file__, "--commit-then-crash", str(root)],
            capture_output=True, timeout=30,
        ))
        if child.returncode != 73 or cursor_seq() != 0:
            raise RuntimeError("Expected process exit after remote COMMIT before local ACK")
        counts["connections"] += 1
        _, committed = measure("before_ack_readback_ms", read_metrics)
        if committed != (1, bar.checksum):
            raise RuntimeError("Committed fixture missing before ACK")
        reopened = DurableJournal(str(root / "journal.sqlite"))
        live = SandboxReplicator(reopened, remote, cursor, batch_size=1)
        if measure("idempotent_recovery_ms", live.deliver_once) != 1 or live.deliver_once() != 0 or cursor_seq() != 1:
            raise RuntimeError("Spool ACK mismatch after restart")
        conflict = replace(bar, close=101.5).with_checksum()
        try:
            measure("conflict_rejected_ms", lambda: remote.upsert(conflict))
        except StoreUnavailable:
            pass
        else:
            raise RuntimeError("Conflicting duplicate accepted")
        prior_connections = counts["connections"]
        try:
            remote.upsert(replace(bar, is_final=False))
        except ValueError:
            pass
        else:
            raise RuntimeError("Nonfinal accepted")
        if counts["connections"] != prior_connections:
            raise RuntimeError("Nonfinal rejection touched remote DB")
        after, row = measure("after_readback_ms", read_metrics)
    if row != (1, bar.checksum):
        raise RuntimeError("Remote checksum/count mismatch")
    print(json.dumps({"candidate": CANDIDATE, "started_utc": start,
                      "ended_utc": datetime.now(timezone.utc).isoformat(),
                      "endpoint_sha256": hashlib.sha256(host.encode()).hexdigest(),
                      "fixture_checksum": bar.checksum, "remote_count": row[0],
                      "counts": counts, "latency_ms": timings,
                      "negative_checks": ["outage_preserved_cursor", "process_exit_before_ack",
                                          "conflict_rejected", "nonfinal_rejected_locally"],
                      "db_columns": ["relation_bytes", "inserts", "heap_reads", "heap_hits"],
                      "db_before": before, "db_after": after,
                      "provider_budget": "ATTACH_SAME_WINDOW_PROJECT_METRICS_AND_QUOTA_SEPARATELY"}))

if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--commit-then-crash":
            crash_after_commit(Path(sys.argv[2]))
        elif len(sys.argv) == 1:
            main()
        else:
            raise SystemExit("Invalid arguments")
    except Exception as exc:
        raise SystemExit(f"Sandbox probe failed ({type(exc).__name__}); no DSN or remote exception logged") from None
