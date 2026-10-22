"""
AQL G1-WP03 — Operational Health Snapshot
==========================================

Produces a structured, machine-readable JSON health report for the G1 ingest
pipeline by comparing the DurableJournal and OperationalStore at a point in
time.

Status levels
-------------
HEALTHY    — journal and store are fully consistent; no unresolved gaps.
DEGRADED   — at least one journal bar is absent from the store (backlog exists)
             OR data lag exceeds the configured threshold; but no mandatory
             recovery has failed.
UNHEALTHY  — mandatory recovery failed, a storage exception was swallowed, OR
             the integrity check detects a key-set divergence that cannot be
             explained by a normal backlog.

Key design decisions
--------------------
* Consistency uses stable bar keys (symbol:interval:bar_open), not row counts.
  Equal counts with different keys → NOT healthy.
* An injectable clock (``now_ms_fn``) keeps time-sensitive tests deterministic.
* Exceptions during snapshot production are caught and surfaced in the report
  (``storage_errors`` list), never silently swallowed.
* The snapshot is read-only: it never writes to the journal or store.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import logging

logger = logging.getLogger("aql.health")

# ---------------------------------------------------------------------------
# Thresholds (all durations in seconds)
# ---------------------------------------------------------------------------
DEFAULT_LAG_WARN_S: float = 90.0   # one missed 1m bar → DEGRADED
DEFAULT_LAG_CRIT_S: float = 300.0  # five missed bars   → UNHEALTHY


@dataclass
class HealthSnapshot:
    """
    Structured health report produced by ``take_snapshot()``.

    All fields are JSON-serialisable primitives or lists thereof.
    """
    # Top-level status
    status: str                        # "HEALTHY" | "DEGRADED" | "UNHEALTHY"

    # Identity
    symbol: str
    interval: str
    timestamp_ms: int                  # wall-clock time snapshot was taken (injectable)
    timestamp_iso: str                 # ISO-8601 representation of timestamp_ms

    # Counts
    journal_final_count: int           # final bars in journal (any state)
    store_final_count: int             # rows in operational store

    # Backlog (journal committed but not yet in store)
    unresolved_backlog: bool           # True when ≥1 journal bar missing from store
    missing_bar_opens: List[int]       # sorted list of bar_open values absent from store

    # Recovery
    recovery_status: str               # last recovery status string or "NONE"
    replay_errors: int                 # bars that failed to replay into store

    # Temporal
    last_final_bar_open: Optional[int] # most recent bar_open in store (ms) or None
    data_lag_seconds: Optional[float]  # now - (last_bar_close_ms) in seconds, or None

    # Integrity
    integrity_ok: bool                 # key-set comparison passed
    journal_keys_not_in_store: int     # extra keys in journal vs store (post-replay)
    store_keys_not_in_journal: int     # extra keys in store vs journal

    # Errors
    storage_errors: List[str]          # non-fatal exceptions caught during snapshot

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "status": self.status,
            "symbol": self.symbol,
            "interval": self.interval,
            "timestamp_ms": self.timestamp_ms,
            "timestamp_iso": self.timestamp_iso,
            "journal_final_count": self.journal_final_count,
            "store_final_count": self.store_final_count,
            "unresolved_backlog": self.unresolved_backlog,
            "missing_bar_opens": self.missing_bar_opens,
            "recovery_status": self.recovery_status,
            "replay_errors": self.replay_errors,
            "last_final_bar_open": self.last_final_bar_open,
            "data_lag_seconds": self.data_lag_seconds,
            "integrity_ok": self.integrity_ok,
            "journal_keys_not_in_store": self.journal_keys_not_in_store,
            "store_keys_not_in_journal": self.store_keys_not_in_journal,
            "storage_errors": self.storage_errors,
        }


def _interval_to_ms(interval: str) -> int:
    """Convert a Binance interval string to milliseconds."""
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if len(interval) < 2:
        raise ValueError(f"Invalid interval: {interval!r}")
    n, unit = int(interval[:-1]), interval[-1]
    if unit not in units:
        raise ValueError(f"Unknown interval unit {unit!r}")
    return n * units[unit]


def take_snapshot(
    journal,
    store,
    symbol: str,
    interval: str,
    *,
    recovery_report=None,
    replay_errors: int = 0,
    now_ms_fn: Optional[Callable[[], int]] = None,
    lag_warn_s: float = DEFAULT_LAG_WARN_S,
    lag_crit_s: float = DEFAULT_LAG_CRIT_S,
) -> HealthSnapshot:
    """
    Produce a health snapshot by comparing *journal* and *store* at this moment.

    Parameters
    ----------
    journal      : DurableJournal instance
    store        : OperationalStore instance
    symbol       : trading pair, e.g. "BTCUSDT"
    interval     : Binance kline interval, e.g. "1m"
    recovery_report : most recent RecoveryReport (or None)
    replay_errors   : bar count that failed replay into store during reconcile
    now_ms_fn    : callable returning current epoch-ms; defaults to wall clock
    lag_warn_s   : seconds of data lag that triggers DEGRADED
    lag_crit_s   : seconds of data lag that triggers UNHEALTHY
    """
    if now_ms_fn is None:
        now_ms_fn = lambda: int(time.time() * 1_000)

    storage_errors: List[str] = []
    now_ms = now_ms_fn()
    timestamp_iso = _ms_to_iso(now_ms)

    # -----------------------------------------------------------------------
    # 1. Collect raw data — catch every individual exception
    # -----------------------------------------------------------------------
    journal_bars = []
    try:
        journal_bars = journal.replay(symbol=symbol, interval=interval, final_only=True)
    except Exception as exc:
        storage_errors.append(f"journal.replay: {exc}")

    journal_keys: set = {b.stable_key() for b in journal_bars}
    journal_final_count = len(journal_bars)

    store_keys: set = set()
    store_final_count = 0
    try:
        store_keys = store.get_stored_keys(symbol, interval)
        store_final_count = len(store_keys)
    except Exception as exc:
        storage_errors.append(f"store.get_stored_keys: {exc}")

    # Convert store keys (bar_open ints) → stable_key strings for comparison
    store_stable_keys: set = {f"{symbol}:{interval}:{k}" for k in store_keys}

    # -----------------------------------------------------------------------
    # 2. Key-set integrity analysis
    # -----------------------------------------------------------------------
    # journal bars missing from store (backlog or data loss)
    journal_not_in_store: set = journal_keys - store_stable_keys
    # store rows not in journal (orphan rows — unusual)
    store_not_in_journal: set = store_stable_keys - journal_keys

    missing_bar_opens: List[int] = sorted(
        int(k.split(":")[-1]) for k in journal_not_in_store
    )
    unresolved_backlog = len(missing_bar_opens) > 0
    integrity_ok = len(store_not_in_journal) == 0  # orphan store rows = integrity breach

    # -----------------------------------------------------------------------
    # 3. Temporal metrics
    # -----------------------------------------------------------------------
    last_final_bar_open: Optional[int] = None
    data_lag_seconds: Optional[float] = None
    try:
        _, max_open = store.get_range(symbol, interval)
        if max_open is not None:
            last_final_bar_open = max_open
            interval_ms = _interval_to_ms(interval)
            bar_close_ms = max_open + interval_ms
            data_lag_seconds = round((now_ms - bar_close_ms) / 1_000, 1)
    except Exception as exc:
        storage_errors.append(f"store.get_range: {exc}")

    # -----------------------------------------------------------------------
    # 4. Recovery status
    # -----------------------------------------------------------------------
    recovery_status = "NONE"
    mandatory_recovery_failed = False
    if recovery_report is not None:
        try:
            recovery_status = str(recovery_report.status)
            if recovery_report.status == "HTTP_ERROR" and recovery_report.unresolved > 0:
                mandatory_recovery_failed = True
        except Exception as exc:
            storage_errors.append(f"recovery_report read: {exc}")

    # -----------------------------------------------------------------------
    # 5. Determine overall status
    # -----------------------------------------------------------------------
    status = _compute_status(
        unresolved_backlog=unresolved_backlog,
        integrity_ok=integrity_ok,
        mandatory_recovery_failed=mandatory_recovery_failed,
        replay_errors=replay_errors,
        storage_errors=storage_errors,
        data_lag_seconds=data_lag_seconds,
        lag_warn_s=lag_warn_s,
        lag_crit_s=lag_crit_s,
        journal_keys_not_in_store=len(journal_not_in_store),
    )

    return HealthSnapshot(
        status=status,
        symbol=symbol,
        interval=interval,
        timestamp_ms=now_ms,
        timestamp_iso=timestamp_iso,
        journal_final_count=journal_final_count,
        store_final_count=store_final_count,
        unresolved_backlog=unresolved_backlog,
        missing_bar_opens=missing_bar_opens,
        recovery_status=recovery_status,
        replay_errors=replay_errors,
        last_final_bar_open=last_final_bar_open,
        data_lag_seconds=data_lag_seconds,
        integrity_ok=integrity_ok,
        journal_keys_not_in_store=len(journal_not_in_store),
        store_keys_not_in_journal=len(store_not_in_journal),
        storage_errors=storage_errors,
    )


def _compute_status(
    *,
    unresolved_backlog: bool,
    integrity_ok: bool,
    mandatory_recovery_failed: bool,
    replay_errors: int,
    storage_errors: List[str],
    data_lag_seconds: Optional[float],
    lag_warn_s: float,
    lag_crit_s: float,
    journal_keys_not_in_store: int,
) -> str:
    # UNHEALTHY conditions (any one is sufficient)
    if mandatory_recovery_failed:
        return "UNHEALTHY"
    if not integrity_ok:
        return "UNHEALTHY"
    if replay_errors > 0:
        return "UNHEALTHY"
    if storage_errors:
        return "UNHEALTHY"
    if data_lag_seconds is not None and data_lag_seconds > lag_crit_s:
        return "UNHEALTHY"

    # DEGRADED conditions
    if unresolved_backlog:
        return "DEGRADED"
    if data_lag_seconds is not None and data_lag_seconds > lag_warn_s:
        return "DEGRADED"

    return "HEALTHY"


def _ms_to_iso(ms: int) -> str:
    """Convert epoch-ms to ISO-8601 UTC string."""
    import datetime
    dt = datetime.datetime.fromtimestamp(ms / 1_000, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
