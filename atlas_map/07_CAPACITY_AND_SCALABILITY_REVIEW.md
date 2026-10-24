# ATLAS Quant Lab — Capacity & Scalability Review
**Version:** 1.0-DRAFT | **Date:** 2026-10-24 | **HEAD:** `4e4c353`

---

## Scalability Scenarios (13)

### SC-01: Single Symbol, Single Interval (Current Baseline)
- **Config:** BTCUSDT 1m
- **Throughput:** 1 final bar/minute = ~60 bars/hour
- **SQLite journal:** Trivially low load
- **SQLite store:** Trivially low load
- **Status:** VERIFIED SYNTHETIC — G1 WP01–WP04 tests pass (CI run #40085463732 @ `453a14d`); Binance bounded acceptance PASS for REST + WS + reconnect + gap recovery (Issue #64 ACCEPTED WITH FOLLOW-UPS)
- **Gap:** Not production-certified; multi-symbol, Supabase cloud, and sustained uptime not validated

---

### SC-02: Single Symbol, Multiple Intervals
- **Config:** BTCUSDT × [1m, 5m, 15m, 1h] = 4 streams
- **Throughput:** ~70+ bars/hour
- **Journal:** 4 separate tables or multiplexed — design unclear
- **Store:** UNIQUE key includes `interval` — supports multi-interval
- **Gap:** Pipeline parameterized for single interval only; multi-interval NOT designed
- **Risk:** Journal schema supports it by design (symbol+interval keys); pipeline does not

---

### SC-03: Multiple Symbols, Single Interval
- **Config:** [BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT] × 1m = 4 streams
- **Throughput:** ~240 bars/hour
- **Issue:** No multi-symbol orchestration; `run_pipeline()` is single-symbol
- **Gap:** Requires: 4 BinanceCollector instances, 4 JournalConsumer instances, shared store
- **Status:** NOT DESIGNED — multi-symbol production scale explicitly flagged as gap in `04_STATE.md`

---

### SC-04: Multi-Symbol, Multi-Interval (Production Target)
- **Config:** 10 symbols × 3 intervals = 30 streams
- **Throughput:** ~1,800 bars/hour
- **SQLite write contention:** High — WAL mode helps but serial writes are bottleneck
- **Recovery weight budget:** `MAX_SESSION_WEIGHT=1200` — insufficient for 30-stream gap recovery
- **Gap:** Significant architectural work needed; no design for this scale

---

### SC-05: Overnight Gap Recovery (Process Restart after 8 hours)
- **Config:** BTCUSDT 1m × 480 missing bars
- **Recovery:** REST `/api/v3/klines` max 1000 bars/call
- **Weight cost:** ~480 weight units (1 per kline request + pagination)
- **Constraint:** `MAX_SESSION_WEIGHT=1200` → sufficient for single symbol
- **Gap:** Multi-symbol restart would exhaust weight budget
- **Evidence:** `GapRecovery` design; `RecoveryReport.weight_cost` tracked

---

### SC-06: Binance Rate Limit Under Load
- **Config:** Sustained recovery + live ingestion simultaneously
- **Risk:** Recovery uses 1200 weight units; spot rate limit is 6000/min
- **Design:** `MAX_SESSION_WEIGHT=1200` is conservative; `last_seen_window_weight` tracked
- **Gap:** No weight coordination between multiple recovery jobs
- **Status:** Designed but not live-tested

---

### SC-07: SQLite WAL Under Concurrent Writers
- **Config:** JournalConsumer (writes) + GapRecovery (background writes) + health reads
- **SQLite WAL:** Supports one writer, multiple readers — not full concurrency
- **Risk:** BackgroundLane recovery job + JournalConsumer could contend on journal SQLite
- **`WritePriority`:** Cooperative priority designed in `lanes.py` — core commits yield over background
- **Gap:** `WritePriority` is NOT connected in current pipeline; not tested under high concurrency
- **Evidence:** `lanes.py` `WritePriority` class exists but is unused in `pipeline.py`

---

### SC-08: Disk Full During Collection
- **Config:** Continuous collection fills disk
- **Risk:** SQLite WAL journal write fails → bar lost before store write
- **Current behavior:** Exception propagated to pipeline → unhandled at high level
- **Gap:** No disk-space monitoring, no graceful degradation, no alert
- **Status:** NOT DESIGNED — G1-PLAN-02 (Durable Inbox capacity and disk-full policy) deferred

---

### SC-09: Supabase Free Tier Capacity
- **Config:** Continuous collection → Supabase sync
- **Supabase Free:** 500MB storage, 2GB bandwidth/month
- **Risk:** BTCUSDT 1m generates ~720 bars/day; with OHLCV+timestamps ~500 bytes/bar = ~360KB/day
- **At 10 symbols:** ~3.6MB/day → Free tier exhausted in ~4.2 months
- **Gap:** Decision on Supabase tier not made (Issue #67)
- **Status:** `SUPABASE_STATUS = "NOT_TESTED"`

---

### SC-10: SIGKILL During Gap Recovery
- **Config:** Process killed during REST batch recovery
- **Mechanism:** Bars committed to journal before store write → `LOCAL_COMMITTED` state
- **Recovery:** On next startup, `startup_reconcile()` finds unacknowledged bars and replays
- **Risk:** `mark_persisted` not called for killed recovery bars → duplicate recovery attempt on next start
- **Idempotency:** `INSERT OR IGNORE` handles duplicates → safe
- **Status:** DESIGNED — synthetic crash tests pass; not live-tested

---

### SC-11: WebSocket Reconnect Loop (Binance Unstable)
- **Config:** Rapid connect/disconnect cycle (e.g. network instability)
- **Mechanism:** Exponential backoff, `MAX_RECONNECT_ATTEMPTS=10`
- **Risk:** Multiple gap windows accumulate; recovery queue fills up
- **BackgroundLane:** `capacity=16` — after 16 jobs, rejections counted
- **Gap:** If 17+ gap windows accumulate, later gaps are rejected from recovery queue → `UNRESOLVED_DATA_GAP`
- **Status:** DESIGNED — rejection counted and surfaced in health; not tested

---

### SC-12: Historical Library at Scale (1 Year of Data)
- **Config:** BTCUSDT 1m × 1 year = 525,600 bars
- **Storage:** ~262MB (500 bytes/bar) in SQLite
- **CustodyAccessor:** In-memory range queries on loaded dataset → RAM limited
- **Gap:** No Parquet or chunked storage designed; no large-scale benchmark
- **Status:** NOT DESIGNED — deferred

---

### SC-13: Concurrent Strategy Evaluation
- **Config:** 10 strategies backtesting simultaneously against same dataset
- **Risk:** `computation_hash` is per-instance → cannot parallelize and compare results
- **CPU:** Python GIL — thread-based parallelism limited
- **Gap:** No parallel backtest runner designed; single-threaded assumed
- **Status:** NOT DESIGNED

---

## Capacity Summary

| Scenario | Risk Level | Status | Mitigation |
|---------|-----------|--------|-----------|
| SC-01: Single symbol baseline | LOW | Verified (synthetic) | Live test needed |
| SC-02: Multi-interval | MEDIUM | Not designed | Future work |
| SC-03: Multi-symbol | HIGH | Not designed | G2+ work |
| SC-04: Production scale | VERY HIGH | Not designed | G5+ work |
| SC-05: 8-hour gap recovery | MEDIUM | Bounded acceptance PASS (Issue #64) | Issue #64 follow-ups |
| SC-06: Rate limit under load | MEDIUM | Bounded acceptance PASS (Issue #64) | Issue #64 follow-ups |
| SC-07: Concurrent writers | MEDIUM | WritePriority unused | Connect WritePriority |
| SC-08: Disk full | HIGH | Not designed | G1-PLAN-02 |
| SC-09: Supabase capacity | HIGH | Architecture decided Option B; cloud NOT_TESTED | Issue #71 Phase 1 |
| SC-10: SIGKILL during recovery | LOW | Bounded acceptance PASS (Issue #64) | Issue #64 follow-ups |
| SC-11: Reconnect loop | MEDIUM | Bounded acceptance PASS (Issue #64) | Issue #64 follow-ups |
| SC-12: Historical Library at scale | MEDIUM | Not designed | Deferred |
| SC-13: Concurrent backtest | MEDIUM | Not designed | Deferred |

**Bottom line:** SC-01 has a bounded tested baseline (synthetic acceptance + bounded Binance PASS for Issue #64 REST/WS/reconnect/recovery) — it is **not production-authorized**. Production authorization requires resolution of Issue #64 follow-ups (clock sync, Supabase cloud, multi-symbol), R09 credential revocation, and explicit owner sign-off. Everything from SC-02 onward requires design and/or implementation work before production authorization.
