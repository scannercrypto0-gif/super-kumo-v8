# Work #148 — native exits and independent DEV paths

Project AQL-CRYPTO-RESEARCH-001. Implementation for
[AQL-SF-WORK-DEV-EXIT-THREE-PATHS-001](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/148),
2026-10-28 (Asia/Riyadh). Branch-only delivery on existing Draft #143,
starting at a6aa5fdd624d717bb4124869d918fbbc41036eba, stacked on unmerged #141.
Main observed dbc191df72f4b4d1ebb7d490926dcad4325dac12. No merge or gate closure.

## Contract and supported use

`research_wp_r0/historical_dev_exits_v1.py` is data-injected, offline, long-only,
one fixed quantity, no leverage, one position, no external I/O. `replay` uses
existing `ema_first_backtest.ema_crossover_decisions` and V2 `_ema`: SMA seed,
fsum, alpha=2/(period+1), 8/21 cross, first decision after 22 closed candles.
No recalibration, new family, scanner or regime policy. Signals use availability
of the entire required recursive prefix, then explicit latency and first eligible
bar open. Excessively delayed inputs block as stale. No same-close execution.
`replay_contract_fixture` accepts hand-authored signals solely under the distinct
CONTRACT_FIXTURE_ONLY_1 identity. It cannot claim an EMA study.

All rows, source reference/version/archive digest, canonical rows digest,
availability declaration and correction declaration are pinned in the receipt.
Availability timestamps may be retrospective assumptions; UNKNOWN is retained,
and as_known_at_cutoff/real_pit_accepted are always false. PINNED_VERSION_ONLY
means precisely no independent correction lineage certificate. Missing evidence
fields/digest, bad grid/OHLCV, missing opens/availability, invalid costs or
configuration raise diagnosed ValueError before any receipt is returned. Missing
modeled executable quote is UNKNOWN, without invented fill. This is NOT #150's
independent provenance inspector, Core authority, or empirical source admission.

## Execution and uncertainty rules

- Optional explicitly configured TP/SL are fractions of raw modeled entry open.
  None disables that overlay. Entry/exit price impact is half spread + slippage,
  applied adversely each side; fees charged on impacted notional each side.
  Fixed full quantity is a declared liquidity assumption, never observed volume
  participation or an observed fill_fraction. No partial-fill claim.
- TP-only / SL-only use modeled trigger price; opens beyond trigger use the bar
  open (adverse gap stop included). Missing quote cannot authorize even a scenario
  fill. No trustworthy intrabar evidence resolver is implemented in V1.
- Both triggers: FACTUAL retains inventory/cash, latches UNKNOWN_EXIT_ORDER,
  makes aggregate realized PnL/equity/return/DD unknown, and blocks future entries.
  Known realized subtotal before uncertainty remains explicitly separate. Neither
  a zero fill nor a zero scored return is substituted.
- TARGET_FIRST and STOP_FIRST start from initial capital and independently replay
  all events, costs, inventory, cash, marks and subsequent eligibility. They are
  hypothetical modeled paths, not observed trades or guaranteed global bounds.
  Different downstream paths may encounter different later ambiguous events.
- Indicator exit plus overlay touch is UNKNOWN_INDICATOR_OVERLAY_COLLISION in
  **all** paths. No optimistic priority is inferred from OHLC. Multiple delayed
  signals executable at the same timestamp also latch UNKNOWN, rather than using
  an unsupported input-list priority. A future trusted ordering model needs a
  versioned contract/evidence update.
- Missing terminal exit open is UNKNOWN_NO_EXIT_OPEN. Without an exit trigger,
  terminal position is OPEN_UNRESOLVED, right-censored, with no forced liquidation.
  The configurable 24h checkpoint only samples MTM. Intermediate missed checkpoints
  are not filled with interpolated prices.
- MTM is sampled cash + held quantity times raw close; open positions have no
  settled equity. This gross inventory valuation is not a liquidation fill and
  excludes prospective liquidation costs. Drawdown is sampled, never intrabar.
  After factual uncertainty only a conditional frozen-inventory mark is retained,
  excluded from return/DD. Mark times denote candle valuation, not knowledge proof.
- Every scheduled signal (including HOLD, stale, capacity/capital rejection,
  unknown quote, missing next open) stays in scheduled_denominator. Per-opportunity
  scored_return is null: there is no trade ranker, policy average or imputed zero.
  Return is path portfolio sampled equity / initial capital minus one, distinct
  from realized PnL; unknown portfolio returns stay null.
- Each ledger state checks finite nonnegative cash and cash + held cost basis =
  initial cash + known realized PnL. Every event carries prior hash; canonical
  receipt binds rows, signals, source, strategy/config, assumptions and paths.
  `verify_receipt` reruns the complete calculation, not just a self-reported hash.
  Hashes establish reproducibility, not independently authenticated custody.

## Reproduction and targeted evidence

```bash
python -B -m pytest -p no:cacheprovider tests/test_sf_historical_dev_exits_v1.py tests/test_sf_factory_exam.py -q --tb=short
python -B research_wp_r0/_dep_guard.py research_wp_r0/historical_dev_exits_v1.py
python -c "import json; from research_wp_r0.historical_dev_exits_v1 import verify_receipt; r=json.load(open('docs/research/work148/three_path_fixture_receipt.json')); assert verify_receipt(r); print(r['receipt_sha256'])"
```

Local final targeted result: **63 passed** (35 new contract cases + 28 unchanged
fixed-horizon cases), 0 failed/skipped, Python 3.12. Initial runtime lacked pytest;
installed pytest/pytest-timeout. No failing test hidden or legacy fixture changed.
Dependency boundary: no external third-party module dependencies in new core.
Existing configured complete Factory acceptance and integrity workflows are to run
once on final pushed HEAD; exact SHA, counts and URLs will be recorded in #148,
#77 and #134 after observed completion. No unchanged-baseline CI rerun.

Checked-in synthetic fixture receipt canonical SHA256:
`0ed0cdf8132876baf11677dca43f67e18c6dc06c6949df9a5fab2048299b81d5`.

| Path | Cash | Held quantity | Realized PnL | Next entry |
|---|---:|---:|---|---|
| FACTUAL | 0 | 1 | UNKNOWN | BLOCKED_PRIOR_UNKNOWN |
| TARGET_FIRST | 10 | 1 | 10 (scenario) | MODELED_ENTRY |
| STOP_FIRST | 90 | 0 | -10 (scenario) | CAPITAL_REJECTED |

All paths retain scheduled denominator 2. Costs zero ONLY in this arithmetic
falsifier; explicit nonzero fee/spread/slippage accounting is tested separately.
This fixture is fabricated, not the Binance Work146 source or any empirical result.
Per-path chain heads are stored in the JSON and verified by replay/tests.

## Study design and audit handoff

`study_proposal_v2.json` removes forced max holding; adds optional TP/SL,
indicator exits, 24h observation and independent uncertainty paths. Canonical
proposal SHA256 `b420b0458d248589daa836fb1093aba1b89f20896c3abb3e2b9982f36fe77b93`.
It references prior Work146 proposal digest
`dd756b785f3ca27d8591c68f42a570a075a90c8a9f4c7e0c513b7c9d976e484f`
without editing its bytes/digest. No study date/episodes, regime labels, empirical
cost schedule, issuer timing, independent anchor or correction lineage is frozen.

S request: independently accept/reject exact-head code, availability, missingness,
conservation, independent downstream paths, canonical replay and legacy isolation.
R request: separately assess DEV-only inference, modeled-fill/cost limitations,
right-censoring/denominators and non-bound scenarios. Science remains unvalidated.
Real-source multi-episode/PIT comparison is blocked on independent evidence,
predefined study/labels/costs and Council acceptance. No OOS, Paper, Live, orders,
main write, Core bridge change or self-issued final acceptance. Work146 download
and Core Guardian E2E are not repeated. Issue #150 remains separate.

Continuity accessed: current owner instruction; #148; latest #77 and #134 comments;
#143 exact head and ancestry; repository identity/startup/session/register/state.
Last delivered Work per #148 is #146 result 6469407856; approvals/addenda #77
6470243101/6470247381 and execution #148 are included. Other chats inaccessible;
no exhaustive cross-chat coverage claimed. Existing AIARC-084 verdict is not
invented or replaced by this engineering submission. Next exact task is independent
Council S/R on published SHA, not another automated implementation/review task.
