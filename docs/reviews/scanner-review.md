# Scanner — Architecture & Evidence Review
**Project:** ATLAS Quant Lab / AQL-CRYPTO-RESEARCH-001  
**Review date:** 2026-11-12  
**Status:** PROVISIONAL / PRE-G0 — engineering-ready on isolated synthetic input only  
**Source:** [Codex handoff #277/6804157213](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/277#issuecomment-6804157213)  
**Frozen Scanner HEAD:** `33c3b1c410035077ae5a5296c7703938addc62b4` (OPEN / DRAFT / UNMERGED, stacked on #270).

## Mission and ownership
Scanner reads immutable, time-qualified Core market data directly and evaluates versioned existing strategies. It reuses shared `IndicatorRegistryV2`, distinguishes DECISION indicators (signal-authoritative only under frozen strategy configuration) from Lab-requested MONITOR_ONLY indicators (research-only, cannot mutate decisions), records complete per-slot ENTRY_SIGNAL / EXIT_SIGNAL / NO_SIGNAL / UNKNOWN census, and sends decision research receipts to Secretary and monitoring receipts to Lab. Factory and Discoverer query Core independently, not through Scanner. Scanner does not authorize paper/live orders, fill assumptions, scientific approval, or PIT/OOS promotion.

## Owner provisional decisions (not final G0)
- B: initial bounded configurable symbols/strategies; no untested broad-universe production promise.
- B: historical recovery is `LATE_RESEARCH_ONLY`; no retroactive actionable trading signal.
- Shared versioned indicators; technical ownership migration not ratified.
- Lab MONITOR_ONLY remains separate from DECISION.
- Defer AI-generated indicator/strategy agent, advanced asset intelligence and broad scaling until essential loop works.

## P0–P6 verified evidence as reported by Codex
| Gate | Delivery | Scope |
|---|---|---|
| P0 | PASS_VERIFIED inventory | Reused existing Core253, Scanner H, Factory kernels; checked main/stacked draft dependencies |
| P1 | PASS_SYNTHETIC | Core253 pinned rights/source/manifest/cutoff; 15m native |
| P2 | PASS_SYNTHETIC | IndicatorRegistryV2 and independent Lab monitor receipts; unchanged decision bytes |
| P3 | PASS_SYNTHETIC | Stable slot/strategy/symbol census; fail-closed gaps; late-only recovery |
| P4 | PASS_SYNTHETIC / BLOCKED_EXTERNAL | Fixture Secretary/Lab ACK, durable replay; actual F3 proposal path rejects |
| P5 | PASS_SYNTHETIC / BLOCKED_EXTERNAL | Simulated disconnect/restart/clock/quota; bounded 24-row census, not live six-feed proof |
| P6 | PASS_SYNTHETIC | Two independent processes per OS, four batches/four decisions/eight effects and eight ACKs per replay |

[Windows/Ubuntu CI and proof comparison](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/43078743451): 30 tests + 24 subtests on each OS, no skips/failures reported; canonical proof SHA256 `f26e2e8a4d18f5ae5b0671de1552d18582c766a942d640a32dac38d8ccb46e74`. Fixture-only performance; no provider traffic, witnessed real PIT, sustained runtime or paper/live. [Exact code and reproduction](https://github.com/scannercrypto0-gif/super-kumo-v8/blob/33c3b1c410035077ae5a5296c7703938addc62b4/tools/scanner_strategy_f/P0_READINESS.md).

## S1–S8 evidence and open owners
| Gap | Scanner synthetic status | Remaining external evidence / owner |
|---|---|---|
| S1 Core direct input | PASS | lawful source, first-known-at and real PIT custody — Core/owner |
| S2 Indicators | PASS | existing registry reused, no migration |
| S3 Decisions | PASS | 15m scope; prospective cutoff proof — Core/Integration |
| S4 Lab monitors | PASS | deployed real Lab receiver — Lab/Integration |
| S5 Secretary/ACK | PASS fixture | real Secretary research intake, durable ACK, no F3 bypass — Secretary/Integration |
| S6 Scheduler | PASS bounded | real host clock/schedule — Integration/owner |
| S7 Recovery | PASS synthetic | real host/provider outage and shared egress quota — Integration/#305 |
| S8 Operations | PASS synthetic | sustained operation and capacity measurements — Integration/owner |

**Critical exact seam:** producer `aql.scanner.p0.handoff.v1`; Secretary `aql.scanner.p0.decision.v1`; Lab `aql.scanner.p0.lab-monitor.v1`. Fixture ACK `aql.scanner.p0.fixture-consumer-ack.v1`. Existing F3 proposal rejects with `F3_SOURCE_AND_POLICY_GRAPH_NOT_READY_FOR_PROPOSAL`; retain the scientific/paper policy gate, do not weaken it. Minimal owner-authorized receiver assignment: [Integration #271/6815763697](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6815763697).

## Readiness / closure
- **SCANNER_ENGINEERING_READY:** YES, isolated synthetic scope, as claimed by Codex handoff and linked CI.
- **SCANNER_REAL_OPERATIONS_ATTESTED:** NO.
- **REAL_PIT_OOS:** NOT_RUN.
- **PAPER/LIVE:** NOT_RUN; no permission.
- **G0:** NOT_GRANTED.
- **PR #277:** OPEN / DRAFT / UNMERGED at review; do not treat stacked branch as main.
- **Next review trigger:** Integration provides actual Secretary and Lab consumer-code acceptance receipts; then append exact commit/CI/ACK evidence and independently assess this file. Do not premark the future gate PASS.

## References
- [Scanner owner assignment](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/277#issuecomment-6803536156)
- [Scanner documentation addendum](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/277#issuecomment-6803582655)
- [Scanner Codex handoff](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/277#issuecomment-6804157213)
- [Integration BTC evidence map](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6795169572)
- [PM Operating System / CLOSE-FIRST](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205)
- [Independent architecture audit](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/134#issuecomment-6794166523)
