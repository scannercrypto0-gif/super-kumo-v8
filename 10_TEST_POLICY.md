# Test and evidence policy
Unit: indicator math, clocks, cutoff, outcomes, state transitions, fill calculations.
Property: same input same output; no future references; idempotent writes; missing data never silently passes.
Integration: Binance fixtures, Supabase test database, retries, local spool and restarts.
Replay: frozen datasets, checksums, exact versions.
Failure: 429, timeout, delisting, missing candles, same-bar TP/SL, offline writes, duplicate jobs.
Load: measured symbol coverage, API weights, CPU/RAM, Supabase rows/egress, backlog.
Research: distinguish forward max return from realized paper PnL; report full denominators; compare against random and simple momentum baselines; purged time splits for overlapping 72h labels; all experiments registered; parent/shadow paired and forward-validated.
Gate evidence: commit + test command/output + fixture hash + failure cases + benchmark + known limitations + reviewer + owner signature.

## Future GOV-01 and live-data acceptance scenarios
Specification only; no application tests executed. [Canonical rules](03_DECISIONS.md#g0-live-data-operations-decisions--data-0508).

| Rule | Scenario / required outcome |
| --- | --- |
| GOV-01 | Another-chat handoff is inaccessible: report gap/request reference; do not claim inspection/completeness. |
| GOV-01 | Decision/clarification/correction/exception after last owner-confirmed submitted baseline appears exactly once in delta dispositions with evidence. |
| GOV-01 | Draft unsent prompt is not submitted, tool receipt not external confirmation, PR-open not merged; addenda/covered range and audit recorded durably. |
| DATA-05 | WS interruption: bounded reconnect/REST recovery under joint budgets; preserved event/receipt/availability evidence, no fabricated live-observation time. |
| DATA-05/08 | REST recovers past data: chronological/idempotent facts, no retroactive live signals or fictional paper fills. |
| DATA-06 | Slow core cycle: bounded overlap/backlog/deadlines and logged skipped/coalesced scanning; no invented 30-second SLA. |
| DATA-06 | Safe scanning snapshot coalescing retains all events required for open paper positions, fill ambiguity, replay and audit. |
| DATA-07 | Large-universe scan yields; Position Monitor evaluates frozen exits without waiting, scanner remains bounded/adaptive. |
| DATA-05/07 | Both paths/traders share central WS/REST/context/cache/provider authority: no duplicated Binance requests or multiplied limits. |
| DATA-08 | Degraded BTC context blocks dependent new entries but unrelated traders with independently valid essential inputs continue. |
| DATA-07/08 | Missing required price cannot create paper TP/SL/entry/exit fill; positions stay open with explicit monitoring gap/uncertainty. |
| DATA-08 | Healthy liveness but no recent trades: do not automatically declare feed broken. |
| DATA-06/07 | Historical backfill/news/reports/Research Lab pressure cannot synchronously block or starve monitor/core; shared API/resource controls still apply. |
| DATA-08 | Recovery retains order, unresolved ambiguity, provenance, reproducibility, state transition/outage/residual-gap logs; no guaranteed recovery during provider outage. |

Use future fixtures with source/symbol/stream/type failure domains, clock/availability evidence, idempotency keys, budgets/lag/queue metrics and monitoring-event retention; independent trader state preserved. Pending PR #8 TIME/DATA and PR #7 PAPER cases remain separate proposals and must survive later reconciliation.
