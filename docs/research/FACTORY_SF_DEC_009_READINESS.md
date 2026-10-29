# Factory SF-DEC-009 — multi-outcome reporting and Binance observation acceptance

2026-10-28 · Owner authorized all four readiness tasks · review-only acceptance policy (no OOS execution).

## Evidence checkpoints
Factory PR #143 at 1240d88258c8c7244e64d6a0fdf48477401416da remains an unmerged draft; comprehensive acceptance 40649718661 and integrity 40649718703 succeeded six jobs each. Council #134 AIARC-055/056/058 independently checked bounded old-source custody, single-long accounting, report/matched opportunity controls; **not** every report/export consumer. No standalone independent S/R final review of PR #143 exact code commit is visible as of this handoff.

Core Binance observer Work PR #142 at 08c140a9eedd21c59510a0e9671b2c45fa25989c is an unmerged draft; 40649587150 succeeded after one Windows job retry, which does not cure underlying throughput variability. New Core observation authority PR #144 has been reported with code/tests but no final independent acceptance seen at this checkpoint. No Core branch merge is assumed.

## AIARC-055/056/058 — bounded inspection and disposition

Existing source contracts inspected:
- `historical_library` / `historical_evaluation_bridge` enforce checksum, manifest, version and complete-bar prefix; they DO NOT independently certify issuer timestamps.
- `synthetic_execution.account_long_prices` prices an explicitly synthetic, single long entry/exit and charges entry/exit fees plus slippage; **not a full multi-asset account**.
- `factory_exam.run_route` carries scheduled opportunity receipts, status, explicit no-fill/unknown/halt, cash and sampled mark-to-market drawdown. `compare_routes` pairs exact event/source identity, preserves the scheduled denominator and returns NULL full-universe mean if any unknown; both-executed metric flagged conditional/selection-sensitive.
- `synthetic_summary.summarize_synthetic_opportunities` requires receipt integrity, separates unresolved/no-fill from resolved trade counts and explicitly writes `profitability_claim=False`. Its `mean_resolved_net_return` is *not* unconditional policy return.
- The B2 report `factory_b2_counterfactual` retains all 18 scheduled events and opportunity-level ALWAYS/REGIME statuses; its net result is authored synthetic, not market alpha.

Disposition:
- AIARC-055 *internal custody and version binding*: EXISTING_BOUNDED_GUARDS, external issuer proof BLOCKED.
- AIARC-056 *single-long accounting*: EXISTING_BOUNDED_GUARDS; multi-position leverage, pathwise max drawdown, portfolio funding and position overlap NOT_IMPLEMENTED_OR_PROVEN. No claim that they are solved.
- AIARC-058 *route comparator and synthetic summary*: EXISTING_GUARDS_REUSED; downstream alternate report/export consumers and any global multi-trade book require separate explicit inventory/authorization. No demonstrated falsifier justifies rewriting already-green comparison.
- Every future exporter must preserve `scheduled, known, unknown, executed, abstain, no-fill, censored, halt, source/version/cutoff, assumptions`; never substitute zero for unknown, rank or gate on resolved-only return, advertise `sampled_mtm_drawdown_fraction` as worst-case path drawdown, or promote synthetic receipts to profitability. A report missing a mandatory denominator must be `INCOMPLETE_NOT_SCORED`.

## Core Work #142/#144 → Factory admissibility
Allowed tier with supplied genuine capture: `FIRST_INDEPENDENT_OBSERVED` for independently recorded watcher receipt, tied to raw bytes SHA, source event E separately from candle close T and observer monotonic/wall clock, version ancestry, and pinned bundle hash. Distinguish an observed watcher receipt from an issuer-published timestamp. Gaps, uncertain clock, reconnect, missing receipts, observed-after-decision revisions and historical pre-watcher time => UNKNOWN/REJECT; no backdated first-known.

The existing `core_proof_bridge.review_core_envelope` handles `LOCAL_ONLY_UNATTESTED` and keeps `empirical_eligible=False` and `real_pit_accepted=False`. It must not simply flip `verified_source_timing=True` on receipt strings. Any separately verified watcher-tier positive admission is a future distinct contract/decision and requires clock bounds + custody verifier and Council independent acceptance. For now use the received genuine data only for read-only integrity/transport verification and negative-cutoff demonstrations, never historical PIT endorsement.

## First historical experiment freeze checklist
Gate `BLOCKED_EXTERNAL_PROVENANCE` until independently time-bounded source/version availability and correction-first-known exists for intended research period, Core→Factory E2E accepted, Council S/R scoped approval and owner separate authorization. Then freeze exact instrument/universe/listing and surviving symbols, verified interval and dataset/vintage SHA, UTC anchored warmup prefix and indicator versions (including explicit RSI_v1 vs RSI_v2), strategy DNA/thresholds, ALWAYS/REGIME scheduled opportunity set, same execution fee/slippage/latency, financing/capital constraints, chronologically separated development and embargo, OOS sealed, metrics including unknown and per-opportunity policies, replay digests and no multiple-testing after freeze.

No calendar dates, market sample size or statistical power fabricated without verified actual source coverage. No OOS, paper, live, PR merge or G0 here.
