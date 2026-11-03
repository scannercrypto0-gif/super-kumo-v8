# AQL-P2-INTEGRATED-TRADE-001 — Factory frozen Breakout modeled-trade package

**Status:** runnable Factory code and focused TEST_ONLY tests; separate Work-private real modeled-trade execution **NOT YET PERFORMED** at this delivery. Owner Option A #77/6602520077; integrated-build rule AQL-EXEC-01 #205/6602265245. Existing Draft Factory #222 ONLY; no merge/G0/holdout/orders, no strategy edits.

## Reused, not rebuilt

1. Core #221 frozen original Breakout `58e423431cc639958736337a65db8a17bfdbaa85`: REAL source-backed `schedule`, `preregistration`, `cost_model`, `arm_decisions` for each original Work-authenticated source cohort. No Core producer clone.
2. Work's **retained, privately verified** original Feb2024 2784 + Aug2024 2976 BTCUSDT 15m archived bars, private windows delivery #77/6601938646. Never download/reprocess originals, join months or open sealed Nov2025 holdout. Both data cohorts previously exposed: **DEVELOPMENT / NOT unseen OOS; RETROSPECTIVE_NON_PIT**.
3. Factory #222 previously executed real descriptive horizon consumer, Work actual #77/6602388758, with original private receipt ZIP raw SHA `21b20c0f218ba67ff375c891f6765adbb56050101e48cd420b6c3cdc497257e1`. Existing `validate_prereg` and `prepare_real_development` are invoked **directly** by this new modeling consumer; its report includes the descriptive receipt artifact SHA and coverage by 4h/24h/72h. Re-running them inside the new package is deterministic validation/consumption of the *same* already frozen data, not fresh data acquisition or a new backtester.

## Public Factory API

`research_wp_r0.aql_p2_factory_modeled_trades.build_modeled_trade_package(schedule, prereg, cost_model, windows, arm_decisions, *, provenance_verified, prereg_time_verified, source_proof_sha256, prereg_anchor_raw_sha256, windows_delivery_receipt_sha256)`

`windows` are the existing Work 4/24/72h `source_window_sha256` self-pinned records, with original 15m `bars[]`. For each bar, the additional modeled-trade input is **the original source `open` decimal**; this must match the authenticated Work original bar, not be imputed from close/market reference. If the stored windows omit `open`, STOP with the precise missing field; Work may read the existing independently authenticated source record in its private runtime but must not fabricate an open or regenerate the universe. No new source download.

**External attestation is mandatory.** Calling booleans with arbitrary values is NOT sufficient proof. Work must actually inspect and verify preserved private bytes and GitHub timing evidence, and pass these unchanged raw SHA identifiers:
- Independent original source attestation receipt: `c224025885b5186732fa21755c0f3fa7042f03c44d19f1b566be454a31518b44`
- Core GitHub pre-outcome policy anchor receipt: `5a5b7248ddfedf602cb1be840eff834b98edc250f2240b9d83374825b9b16949` ([artifact 13223338562](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/41621283376/artifacts/13223338562))
- Work original full window delivery receipt: `4edd70fa422b690a079386ee831adf66ba1b3f8b65e30e33fba736a30b90bb91`

Anchor 2026-11-03T10:41:03Z and separate downstream checkpoint 10:52:36Z predate controlled Work source-window generation at 10:55:03Z per Work's published receipt. This is bounded proof for **that controlled downstream process**, not an assertion that the historical data were unobserved by everybody or a PIT/OOS guarantee.

Run **separately** for Feb and Aug. Exact original frozen pair denominator: Feb 2763 pairs / 5526 arm decisions / 8289 unique windows; Aug 2955 / 5910 / 8865, total 5718 pairs / 11436 arms / 17154 windows. Same pair identity for BASE/SHADOW, same 4/24/72h underlying market windows; no duplicate windows as two independent observations.

## Frozen modeled trade logic — no new strategy

- BASE: LONG close-confirmed breakout above previous 20 completed-bar highs. SHADOW: same signal, but exclude if prior completed 20-bar range divided by previous close **>3%**; equality accepted. Decisions and dispositions are emitted and self-hashed by Core, never re-inferred by Factory.
- For eligible **TRIGGERED + LONG + COMPLETE modeled-exit** arms, entry price = authenticated `open[i+1]` = bar at Core cutoff; modeled exit = authenticated `open[i+11]` = price after 10 complete 15m holding bars. Date alignment is validated at 900000ms intervals.
- Modeled gross LONG unit return = `exit_open / entry_open - 1`; modeled net unit return = gross minus **30bps round trip**, composed of Core-frozen fee 20bps and slippage 10bps. No compounding, margin, position sizing, funding, modeled slippage execution mechanics, market fills, or portfolio ledger. No actual trade is asserted.
- Holding-period MFE/MAE use the *10 held bars* only, plus exit open. Critically **do not read high/low of exit bar `i+11`**, which would be information after the frozen modeled exit. These are descriptive extrema, not fillable TP/SL orders.
- **NO_SIGNAL / REJECTED / UNKNOWN** remain in exact scheduled pair denominator with **NULL trade results**; not silently excluded and not treated as 0% return or failed fills. Core's signal truth and modeled exit availability are distinct. For triggered tail with absent `i+11`: UNKNOWN, null direction/outcomes, explicit reason. Even when a 4h window is CENSORED near month end, a valid 10-bar modeled exit may still exist after 11 opens: evaluate eligibility from original bars, not the 4h completeness flag.
- The **4/24/72h descriptive cutoff-close-reference returns/MFE/MAE** remain a separate already implemented Factory output and SHA. They do not stand in for the 10-bar modeled trade, and 10-bar trade returns must not overwrite them.
- Both-eligible BASE/SHADOW trades have the same model entry/exit and hence the same modeled return; pair delta is 0 for those pairs. Excluded SHADOW arms are **NULL**, so the report makes **no causal/statistical uplift, alpha, significance or unseen validation claim**. Descriptive per-arm means are explicitly **conditioned on eligible modeled-complete trades**, never treated as equal-denominator portfolio profits.

## Receipt contract and reproduction

Output `aql.p2.factory.breakout-modeled-trades.v1`: frozen source schedule SHA, protocol trial ID, original source SHA, prereg/cost SHA, three independent external receipt SHAs, existing descriptive 4/24/72h artifact SHA and availability coverage, per-pair BASE/SHADOW identity, every arm's decision SHA and original 4h source-window SHA, eligibility/missingness, entry and exit price/time, modeled gross/net returns, modeled MFE/MAE, fixed denominator and per-arm complete/null status counts. Flags: `MODELED_ONLY` in fields, `NOT_OBSERVED` execution, `NOT_ATTESTED` PIT/OOS, `SEALED_UNOPENED` holdout, no alpha/causal claim.

Output has deterministic `artifact_sha256=digest(report excluding artifact_sha256)`. Call `canonical_receipt_bytes(report)` for canonical sorted compact UTF-8 JSON **plus one newline**; `raw_receipt_sha256(report)` returns its raw file SHA (different domain from the report's artifact SHA). Work should write receipts in its PRIVATE source-authorized workspace using write-new-only, verify them twice byte-identically, and publish only counts/hash/evidence (never private windows/prices on public GitHub).

**Concrete isolated invocation in existing Work private environment** (using already present package deserialization from prior `p2_factory_private_execute.py`):

```python
from research_wp_r0.aql_p2_factory_modeled_trades import (
    build_modeled_trade_package, canonical_receipt_bytes, raw_receipt_sha256,
    WORK_SOURCE_PROOF_SHA, CORE_PREOUTCOME_ANCHOR_RAW_SHA,
    WORK_WINDOWS_DELIVERY_RECEIPT_SHA,
)
# schedule, prereg, costs, windows, arms: ORIGINAL private Work objects
# sourced read-only from existing authenticated Feb/Aug ZIP members
report = build_modeled_trade_package(
    schedule, prereg, costs, windows, arms,
    provenance_verified=True, prereg_time_verified=True,
    source_proof_sha256=WORK_SOURCE_PROOF_SHA,
    prereg_anchor_raw_sha256=CORE_PREOUTCOME_ANCHOR_RAW_SHA,
    windows_delivery_receipt_sha256=WORK_WINDOWS_DELIVERY_RECEIPT_SHA,
)
raw = canonical_receipt_bytes(report)
with open("/private/new-output/feb2024-modeled-trades.json", "xb") as f:
    f.write(raw)
print(raw_receipt_sha256(report))
```

The sample path is **illustrative**, not a claim that the file or environment is present in Factory's session. Run twice on independently original inputs, with a new destination for the second receipt, compare raw SHA. Do not change Core/Work/Factory branches during actual private evaluation. If a field error occurs, publish only its exact minimal location/contract mismatch and STOP affected path; no fake outcome/receipt.

Focused CI runs original 11 Factory lab + 9 pinned Core schedule handshake + 10 existing real-development readiness + additional modeled-trade negative/positive tests on exact Draft Factory HEAD. CI is **synthetic-only**, distinct from actual Work-private modeled-trade output; complete integrated checkpoint occurs when verified private receipt is returned.

**Required next gate:** Work private execution *after exact new Factory HEAD CI passes*, then one consolidated technical Factory/Work handoff. Broad scientific Audit only when appropriate, per AQL-EXEC-01; no merge, G0, holdout, paper/live or trading.
