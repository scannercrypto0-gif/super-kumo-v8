# Test and evidence policy
Unit: indicator math, clocks, cutoff, outcomes, state transitions, fill calculations.
Property: same input same output; no future references; idempotent writes; missing data never silently passes.
Integration: Binance fixtures, Supabase test database, retries, local spool and restarts.
Replay: frozen datasets, checksums, exact versions.
Failure: 429, timeout, delisting, missing candles, same-bar TP/SL, offline writes, duplicate jobs.
Load: measured symbol coverage, API weights, CPU/RAM, Supabase rows/egress, backlog.
Research: distinguish forward max return from realized paper PnL; report full denominators; compare against random and simple momentum baselines; purged time splits for overlapping 72h labels; all experiments registered; parent/shadow paired and forward-validated.
Gate evidence: commit + test command/output + fixture hash + failure cases + benchmark + known limitations + reviewer + owner signature.

## Future acceptance/regression scenarios — G0-PAPER-01–08

Specification only; none of these tests is claimed executed by this documentation task. Use focused deterministic fixtures and frozen policy versions; add risk-based integration/recovery coverage when implementation is authorized. Reference: [canonical provisional decisions](03_DECISIONS.md#g0-paper-trading-decisions--owner-selected-provisional-rules).

| Decision | Scenario | Required evidence / expected behavior |
| --- | --- | --- |
| 01 | Entry condition never met | No manufactured fill; NO_FILL/expiry reason retained; rejection distinguishable. |
| 01 | Immediate entry and delayed availability | First eligible price strictly after availability; no earlier price or future-data entry selection. |
| 02 | Same-bar TP/SL with/without finer evidence | Resolve only with legitimate ordering; otherwise factual AMBIGUOUS plus separate best/worst paths and aggregate trader bounds; best case not verified performance. |
| 03 | Fees, missing execution evidence and stressed costs | Gross/baseline-net/stress reported independently; version/source/effective date recorded; no hard-coded 0.01% or perfect missing-data fallback. |
| 04 | Reference and smaller/larger notionals | Provisional 1,000 USDT and feasible sensitivity scenarios reflect available liquidity; insufficient evidence flagged; no portfolio/live-capital interpretation. |
| 05 | Two traders same symbol; duplicate active signal in one trader | Cross-trader independence preserved, within-trader duplicate suppressed per versioned identity; overlap reported, grouped Telegram does not merge records. |
| 06 | Expiry/early invalidation; configuration later changes | Frozen original validity remains; expired opportunities retained; entry validity does not cap filled holding duration. |
| 07 | Early exit then original TP reached | Original trade stays closed; preregistered post-exit research captures target touch independently. |
| 07 | TP1 raised stop hit before later TP2 | Record missed upside on isolated fixed/raised-stop comparison with event ordering/ambiguity; no original-path rewrite. |
| 07 | TP1 raised stop followed by further fall | Record protected downside and aggregate paired risk-adjusted costs/sample-size evidence, not anecdotal superiority. |
| 07 | Adjustment conflicts and future partial exits | Only predeclared timestamped adjustments; conflicting order uses 02; partial mechanics remain unimplemented until separately specified. |
| 08 | Outage spans TP/SL | Chronological missing-interval recovery, event vs ingestion/recovery times, no stale-last-price exit or invented offline strategy decision; unresolved ordering uses 02. |
| 08 | Restart/replay repeated | Same fills/closes/accounting/alerts produced once; durable progress and correction lineage; original decisions unchanged. |
| 08 | Irrecoverable data gap | Explicit unresolved status; exclude from confirmed performance; report unresolved denominator and any transparent scenarios. |
| 02/07/08 | Counterfactual/recovered-data leakage | Same frozen initial conditions and visibility boundaries, separate variants, no mutation/reopening or hindsight decision fabrication. |

Implementation evidence must include fixture/data hashes, source visibility/availability assumptions, policy versions, expected/actual outputs and aggregate reconciliation. No gate completion or promotion follows from documenting these scenarios.
