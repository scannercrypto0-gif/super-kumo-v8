"""Opt-in commit-memory status hook. Never reads feed SQLite, WAL, prices or logs.

These producer-reported links are not native Core receipts, independent custody,
24-hour acceptance or a retrospective/live gap repair. Consumers pin code/config
externally and preserve unknown pre-existing gap coverage.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


SCHEMA = "aql.realtime.producer-bounded-report.v1"
MAX_BYTES = 8192
MIN_INTERVAL_MS = 300_000
# 288 five-minute observations plus startup and a terminal STOPPED report.
MAX_REPORTS_PER_RUN = 290
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RUN = re.compile(r"[0-9a-f]{32}\Z")


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _safe_path(path):
    # Keep this pure path check independent of the historical aql module cache:
    # accepted pinned consumers may load the older warehouse in this process.
    p = Path(path).absolute()
    for member in (p, *p.parents):
        if member.exists() or member.is_symlink():
            bits = member.lstat()
            _need(not stat.S_ISLNK(bits.st_mode)
                  and not (getattr(bits, "st_file_attributes", 0) & 0x400),
                  "PRODUCER_REPORT_REPARSE_DENIED")
    return p


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


class RealtimeReporter:
    """One explicitly enabled run, bounded monotonic create-only publications."""
    def __init__(self, root, protected_root):
        self.root = _safe_path(root)
        self.protected_root = _safe_path(protected_root)
        _need(self.root.is_dir(), "REALTIME_REPORT_ROOT_MUST_PREEXIST")
        _need(self.root != self.protected_root and
              not self.root.is_relative_to(self.protected_root) and
              not self.protected_root.is_relative_to(self.root),
              "REALTIME_REPORT_ROOT_OVERLAP")
        self.sequence = 0
        self.last_observed_ms = None
        self.run_id = None
        self._last_commit = None
        self._last_gap_count = 0
        self._stopped = False

    def publish(self, state, *, observed_ms, published_ms, force=False):
        _need(type(observed_ms) is int and observed_ms > 0 and
              type(published_ms) is int and published_ms >= observed_ms,
              "REALTIME_REPORT_CLOCK")
        _need(self.last_observed_ms is None or observed_ms >= self.last_observed_ms,
              "REALTIME_REPORT_CLOCK_REGRESSION")
        _need(type(force) is bool, "REALTIME_REPORT_FORCE")
        if not force and self.last_observed_ms is not None and observed_ms-self.last_observed_ms < MIN_INTERVAL_MS:
            return None
        _need(self.sequence < MAX_REPORTS_PER_RUN, "REALTIME_REPORT_LIMIT")
        _need(type(state) is dict, "REALTIME_REPORT_STATE")
        for key in ("code_sha256", "config_sha256"):
            _need(type(state.get(key)) is str and _HEX.fullmatch(state[key]),
                  "REALTIME_REPORT_PIN")
        run_id = state.get("run_id")
        _need(type(run_id) is str and _RUN.fullmatch(run_id), "REALTIME_REPORT_RUN")
        _need(self.run_id in (None, run_id), "REALTIME_REPORT_RUN_CHANGED")
        for key in ("committed_final_bars_this_run", "gaps_detected_this_run"):
            _need(type(state.get(key)) is int and 0 <= state[key] <= 10**12,
                  "REALTIME_REPORT_COUNTER")
        for key in ("last_receipt_sha256", "last_source_event_sha256"):
            value = state.get(key)
            _need(value is None or (type(value) is str and _HEX.fullmatch(value)),
                  "REALTIME_REPORT_DIGEST")
        count = state["committed_final_bars_this_run"]
        last = state.get("last_committed_ms")
        close = state.get("last_final_close_ms")
        if count:
            _need(type(last) is int and type(close) is int and
                  0 < close < last <= observed_ms and
                  state.get("last_receipt_sha256") is not None and
                  state.get("last_source_event_sha256") is not None,
                  "REALTIME_REPORT_COMMIT")
        else:
            _need(last is None and close is None and
                  state.get("last_receipt_sha256") is None and
                  state.get("last_source_event_sha256") is None,
                  "REALTIME_REPORT_EMPTY_COMMIT")
        identity = (count, last, close, state.get("last_receipt_sha256"), state.get("last_source_event_sha256"))
        _need(self._last_commit is None or count >= self._last_commit[0],
              "REALTIME_REPORT_COUNTER_REGRESSION")
        _need(state["gaps_detected_this_run"] >= self._last_gap_count,
              "REALTIME_REPORT_COUNTER_REGRESSION")
        if self._last_commit is not None and count == self._last_commit[0]:
            _need(identity == self._last_commit, "REALTIME_REPORT_COMMIT_CHANGED_WITHOUT_PROGRESS")
        stopped = state.get("run_stopped", False)
        _need(type(stopped) is bool and not (self._stopped and not stopped),
              "REALTIME_REPORT_STOP_REGRESSION")
        hold = state.get("hold_reason")
        _need(hold in (None, "FINAL_BAR_CONFLICT"), "REALTIME_REPORT_HOLD")
        body = dict(schema=SCHEMA, lane="REALTIME", run_id=run_id,
                    producer_id="atlas.realtime_market_feed.service.Store.ingest",
                    code_sha256=state["code_sha256"], config_sha256=state["config_sha256"],
                    source_id="BINANCE_SPOT_PUBLIC_WEBSOCKET", source_class="FORWARD_UNQUALIFIED",
                    sequence=self.sequence, observation_ms=observed_ms, published_ms=published_ms,
                    committed_final_bars_this_run=count, last_committed_ms=last,
                    last_final_close_ms=close,
                    last_receipt_sha256=state.get("last_receipt_sha256"),
                    last_source_event_sha256=state.get("last_source_event_sha256"),
                    gaps_detected_this_run=state["gaps_detected_this_run"],
                    gap_status="UNKNOWN_NOT_RESCANNED", source_finality="FINAL" if count else None,
                    status="HELD" if hold else ("STOPPED" if stopped else ("OBSERVED_SOURCE_PROGRESS" if count else "UNKNOWN")),
                    run_stopped=stopped,
                    hold_reason=hold, full_history_verified=False, operational_24h_accepted=False,
                    pit_oos="NOT_ATTESTED", orders=0, trading_authority="NONE",
                    source_mutations=0, network_calls=0, reporting_scope="COMMITTED_MEMORY_ONLY",
                    evidence_grade="PRODUCER_REPORTED_NOT_INDEPENDENTLY_REVALIDATED")
        body["report_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
        raw = _canonical(body)
        _need(len(raw) <= MAX_BYTES, "REALTIME_REPORT_SIZE")
        # Re-check each path at every publication; a swapped linked directory is
        # not made safe by successful constructor validation.
        root = _safe_path(self.root)
        _need(root.is_dir(), "REALTIME_REPORT_ROOT_MUST_PREEXIST")
        destination = _safe_path(root/f"realtime-{run_id}-{self.sequence:06d}.json")
        _need(destination.parent == root, "REALTIME_REPORT_ROOT_ESCAPE")
        if destination.exists():
            _need(destination.is_file() and destination.stat().st_nlink == 1 and
                  destination.read_bytes() == raw, "REALTIME_REPORT_REPLAY_CONFLICT")
        else:
            fd, name = tempfile.mkstemp(prefix=".realtime-pending-", dir=root)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                try:
                    os.link(name, destination)
                except FileExistsError:
                    _need(destination.is_file() and destination.stat().st_nlink == 1 and
                          destination.read_bytes() == raw, "REALTIME_REPORT_REPLAY_CONFLICT")
            finally:
                Path(name).unlink(missing_ok=True)
        self.sequence += 1
        self.last_observed_ms = observed_ms
        self.run_id = run_id
        self._last_commit = identity
        self._last_gap_count = state["gaps_detected_this_run"]
        self._stopped = stopped
        return dict(name=destination.name, sha256=hashlib.sha256(raw).hexdigest(),
                    sequence=body["sequence"])
