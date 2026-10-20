# Test and evidence policy
Unit: indicator math, clocks, cutoff, outcomes, state transitions, fill calculations.
Property: same input same output; no future references; idempotent writes; missing data never silently passes.
Integration: Binance fixtures, Supabase test database, retries, local spool and restarts.
Replay: frozen datasets, checksums, exact versions.
Failure: 429, timeout, delisting, missing candles, same-bar TP/SL, offline writes, duplicate jobs.
Load: measured symbol coverage, API weights, CPU/RAM, Supabase rows/egress, backlog.
Research: distinguish forward max return from realized paper PnL; report full denominators; compare against random and simple momentum baselines; purged time splits for overlapping 72h labels; all experiments registered; parent/shadow paired and forward-validated.
Gate evidence: commit + test command/output + fixture hash + failure cases + benchmark + known limitations + reviewer + owner signature.
