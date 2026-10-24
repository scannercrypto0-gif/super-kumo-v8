# ATLAS Quant Lab — Capacity & Scalability Review
**Version:** 1.1-DRAFT | **Evidence snapshot:** 2026-10-24
**Main source baseline:** `4e4c3537036bdf2b106c1a63ec65b2a9855972a7` | **Documentation:** PR #74, Draft/unmerged.
Reviewed documentation baseline: `e4ce1c8a5d7911f52fb67e52f7e58c2e0ee5b476`; final document HEAD is in PR metadata/correction matrix, not the main-source SHA.
Evidence IDs and scope: [09_EVIDENCE_REGISTER.md](09_EVIDENCE_REGISTER.md). No production authorization or owner decision is created by this map.

## Thirteen scenarios: observations, code assumptions and unknowns

All rates below are arithmetic scenarios, not deployed universe cardinalities.
Provider constants are the inspected code's assumptions, not freshly verified
current Binance plan/endpoint entitlements. No new live/network/load test was
run for this documentation-only correction.

| Scenario | Corrected capacity statement | Evidence / actual status | Remaining work |
|---|---|---|---|
| SC-01 single symbol/interval | BTCUSDT1m=1440 final bars/day,60/hour | Main G1 fixtures and #64 bounded live report accepted | Sustained unattended operation/authorization not proven |
| SC-02 one symbol/multiple intervals | Example1m+5m+15m+1h=77 bars/hour, not four equal-rate streams. Journal/store keys include interval in the same schemas | run_pipeline defaults to one symbol/interval; multi-interval orchestration absent | Subscription planning/shared budgets; no need to invent four separate tables |
| SC-03 four symbols1m |4×1440=5760/day,240/hour | Schemas support symbol keys; no accepted universe orchestrator | Collector/subscription sharing, global limits and load tests; four separate collectors are not a mandated design |
| SC-04 ten symbols×three intervals | Example1m/5m/15m=760 bars/hour;30 streams does not prove a SQLite bottleneck or insufficient recovery budget | No sustained target-scale run | Measure write/latency/recovery budgets before sizing or declaring failure |
| SC-05 eight-hour gap |480 one-minute bars fit one code-sized1000-row request if fully returned; code request cost2, not480 units | Arithmetic from recover_gap; #64 observed one recovered bar, not an eight-hour outage | Exercise actual multi-page/gap/error/weight scenarios before broad acceptance |
| SC-06 recovery/API budget | Code MAX_SESSION_WEIGHT=1200, KLINES_WEIGHT_PER_REQUEST=2; cumulative IP-window header is separate from this job's cost | Bounded source tests/report; no induced live429/exhaustion or global multi-job budget proof | Validate current provider rules when separately authorized and design aggregate concurrency accounting |
| SC-07 concurrent writers | SQLite serializes writes; WritePriority already gates shared DurableJournal commits and ACK writes, recovery background=True | Caller chain and test_core_waiter_precedes_next_background_writer verified; #75 zero-caller premise false | Measure high-load/multi-process fairness; no wiring/removal fix justified here |
| SC-08 disk pressure | Uncommitted failures are not successful durability; later source recovery is conditional, not guaranteed. Source must remain until verified backup/retention approval | Error/lock/disk-fault fixtures; Draft73 archive reserve defaults10GB | No host quota/physical disk-full certification; backups/partials share disk unless isolated and budgeted |
| SC-09 selective cloud storage | Option B already conditionally decided: local bulk authority + later capped rebuildable summaries; no routine cloud candles | #67 measured/modelled design; #65 cloud NOT TESTED | Recheck official plan limits only before actual sandbox/budget decisions; old map's2GB bandwidth/720 candles/day were incorrect |
| SC-10 process termination/replay | Journal-first and idempotent replay/ACK fixtures, real Linux SIGKILL and #73 cross-platform process-exit tests exist | Software recovery evidence; not actual exchange-wide failure or power loss | Independent off-device restoration and operating procedure before activation |
| SC-11 reconnect/backpressure | Bounded background jobs expose rejection/errors; source records remain durable where committed. Rejection does not itself fabricate a recovered gap | #64 forced real reconnect+harness recovery; queue saturation/retry fixtures | Reconnect storms, unattended orchestration and whole-host pressure remain unvalidated |
| SC-12 historical data volume | One symbol1m/year=525600 bars.500B/row would be262.8MB before overhead, only an assumed representation | HistoricalLibrary is in-memory; durable bulk is Draft73 JSONL, not main HistoricalLibrary persistence | Coverage/RAM/storage/query measurements; Parquet/incremental access only if justified |
| SC-13 concurrent research | Instance manifest differences do not prevent parallel comparison; retained-manifest/semantic identity and exact config must be specified | #46 isolated synthetic composition, #78 input contracts/repro tests; no accepted parallel historical runner | Process/CPU/memory budget and deterministic comparison protocol; no unsupported GIL throughput prediction |

## Fresh Phase1 measurement versus extrapolation

Draft73 head **cb7829e3e3c13c6b6433b6625f2df35d1991a65d** is technically reviewed,
Draft/unmerged, not production-authorized. Its versioned final evidence records
4096 synthetic rows/64 sealed segments, JSONL4507946B, manifests141378B,
catalog831488B and journal2560000B. Archive footprint **1338.088867B/row**;
archive13.0065s, verified backup9.2705s/restore9.8016s with exact4096 keys/hashes/
watermark.20 core commits while archive blocked: p95=25.700ms, max33.470ms,
not a latency SLA or a controlled comparison. Older512-row measurements belong
to the prior source, not a second independent production trial (E-84).

Decimal archive-only GB=symbols×1440×days×1338.0888671875/1e9:

| Symbols |30d GB|90d GB|365d GB|
|---|---:|---:|---:|
|10|0.5781|1.7342|7.0330|
|100|5.7805|17.3416|70.3300|
|500|28.9027|86.7082|351.6498|

Exclude journal/hot/PIT/research/WAL/partials and every backup copy. The
separately measured #67 journal+hot high-scenario estimate257.27GB/year plus
this archive implies about608.92GB primary/year before richer evidence, not a
measured annual allocation or approved disk budget. Two full copies total about
1.22TB, three1.83TB across media under those assumptions. No compression claimed.

## Protective limits, not a production backup-service capacity claim

Default8192 inventory files/2GB/60s bounds fail closed. At default64 rows per
segment, two files per segment plus two SQLite files permit at most4095
segments/262080 archived rows before other limits: roughly18.2/1.82/0.364 days
at10/100/500 one-minute symbols. Optional hot snapshot, sparse partitions and
short runs can lower this. Time/byte constraints may bind earlier; no linear
runtime extrapolation is certified. Larger/incremental inventories are a future
scoped task, not an unlimited setting or a reason to impose Parquet now.

Windows directory fsync unsupported→explicit DEGRADED; no hardware power-loss
guarantee. Archive10GB reserve is not a host-protected disk quota. Bounded
sidecar work/queue prevents synchronous callbacks, not competition for all I/O.
Partial/quarantine files accumulate without automatic deletion; owner must
approve cleanup/retention independently. Off-device backup remains NOT_VERIFIED;
same-host drills and retained hashes are not independent media/custody.
RPO/RTO remain proposed targets, not established by4096 rows.

## Cloud design model is not current platform acceptance

#67's historical design worksheet predicts selective projection footprints
under declared row/retention/bloat/egress assumptions. Free-tier fit is conditional
for low/base capped projections; high scenarios and sustained egress/WAL may
exceed it. No cloud quota/role/TLS/RLS measurements were performed. Do not
present old plan numbers or a hypothetical200MB model as a current guarantee.
Owner-approved Option B direction remains; named sandbox, final quotas/budgets,
retention and any paid upgrade need their own authority and fresh official facts.
