# Work #247 — retained original history → custody → frozen candidates → Factory

Owner provisional B. Isolated continuation of Work Draft #242 after Audit #240 accepted the prior TEST_ONLY delta. No Core/Factory/Discoverer/Claude/Scanner edits; no merge, main, sealed holdout, G0 or trading. The previous #239 result remains immutable and is not retroactively promoted.

## Actual reused contracts

Core #226 `c6797654942ac6c81184fdc63637c9871721ecc2`: native ZIP `admit_original_bytes` → existing immutable Bridge stage/commit → HistoricalLibrary → `query_price_custody`. Original archive/member/CHECKSUM pins stay distinct from derived float prices. Work checks every returned price/timestamp against the pinned native CSV and binds Core source/manifest/version/cutoff/query seals. Private Core receipts retain the full native price-query lineage; immutable receipt objects are saved through the existing Work #228 store. Original bytes remain in the already-retained private source package and are not republished.

Discoverer #230 `f2006c0e431690ccea8b0532095bf4f2a2dc88ba`, Work #235/#242: reuse the exact frozen generation payload `aea0fdc3cc8617b39c1d10f6b8ea7d3b97ae09adea4edeef979726e67a0fb225` from previous result `62cbf63612f6b748de5388bbd1fca9e3e26694dfe5efbc9c48bd5d89854f21cf`. The 53 independent attempts / 53 definitions / seven families are unchanged, with their original `INDEPENDENT_TEST_ONLY_RESEARCH_SEED` label. Focused CI regenerates the candidates via actual pinned family builders and verifies the full generation hash. No Scanner nomination or source-based candidate selection is invented. These definitions are retrospective development probes, not independently accepted scientific hypotheses or unseen OOS trials.

Factory #241 `f3632f54ddeba631cafa1182ff8059b958163361`: actual `from_core_original_price_query` receives Core admission/query seals and a sealed Work plan, then calls `evaluate_historical_rules` with every definition, the entire frozen 53-attempt census and Core price grid, separately for each cohort. Work does not implement indicators/rules/trades. Existing Factory kernels and projection semantics apply: next-open entry/exit, conservative unknown stop/target touches, warmup and end-of-data NULL, no overlapping modeled position per individual definition. Gross/net costs are independently checked as arithmetic against query prices. No old P2 engine or experiment is rerun.

## Execution and limits

Two explicit modes exist. `test-only` creates a clearly marked artificial native ZIP fixture for CI. `retrospective-originals` only reads the owner-retained Feb/Aug development package matching the prior outer SHA; it never downloads or substitutes prices. Missing retained input returns `SOURCE_NOT_AVAILABLE`, without fabricated hashes. Unsupported/tampered/partial native admission blocks the affected dependency. No automatic fallback.

The original-data mode produces **RETROSPECTIVE_ONLY_UNVERIFIED / INSUFFICIENT_EVIDENCE**. Core native row `close+1` is only an observation lower bound, not a historically attested receipt. `historical_known_at_ms=NULL`, independent venue provenance NOT_ATTESTED, correction history UNKNOWN. Candidate timing `CONFIRMED_CLOSE` is a grammar requirement; retrospective projection does not prove actual source confirmation. Source byte integrity, historical PIT, semantic model calculation and independent scientific acceptance are separate states.

Full scoped universe is one declared BTCUSDT symbol in each separate monthly window, unknown nomination state. It is never called the full market universe. Factory's empty supplied opportunity/arm ledger records **zero connected adapter slots**, not zero actual market opportunities. Global opportunity/BASE/SHADOW counts and comparisons remain NULL. Model-generated entries are individual rule events, not authenticated independent BASE/SHADOW opportunities. There is no SHADOW policy fabricated for these generic definitions. Attempts are 53 unique definitions reused across two source windows, not 106 independently discovered hypotheses.

Frozen Work batch plan SHA256: `0f2b6f32c768a616dafc7ca32b21cf0f7a2c4d98cdf1c68e9bfa367f1ce723ab`. The pre-calculation GitHub commitment is [#247/6625971479](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/247#issuecomment-6625971479). This is a current disclosed batch commitment, not historic preregistration or unseen-data proof. No outcome-based retuning. Costs are assumptions only: entry/exit fees 10+10bps; slippage 5+5bps; spread 0; spot funding 0. Thirty bps is subtracted from each scored independent modeled return. No funded capital/equity, alpha, executable fills or market capacity assertion. Stop/target unknown outcomes retain NULL; no lucky intrabar order is inferred.

Training ends 2024-09-01; >=3-day embargo; existing sealed November 2025 holdout untouched. Feb and Aug are queried separately; no cross-month fill or carry. This previously exposed single-symbol development sample cannot establish whole-market robustness, OOS or significance.

## Reproduce

Check out exact dependency SHAs above and Work #228 `607e88d69e9450ae66fd5090317c5c296ade8457`. From this Work head:

```sh
python -m tools.original_history_batch.gate \
  --checkout main=. --checkout work=/path/to/work-228 \
  --checkout core=/path/to/core-245 --checkout factory=/path/to/factory-246 \
  --checkout discoverer=/path/to/discoverer-230 --output /path/to/test-only-gate
```

Authorized private retained-original calculation (private output directory):

```sh
python -m tools.original_history_batch \
  --checkout main=. --checkout work=/path/to/work-228 \
  --checkout core=/path/to/core-245 --checkout factory=/path/to/factory-246 \
  --checkout discoverer=/path/to/discoverer-230 --mode retrospective-originals \
  --package /authorized/private/ATLAS_P2A_PUBLIC_DEV_INTAKE_PRIVATE_20261103.zip \
  --output /authorized/private/batch247
```

Only run where owner authorization and original retained package already exist. Output includes private Core prices and modeled entry/exit details and must not be uploaded to public GitHub. Published evidence contains only hashes, aggregate counters, assumption disclosures and blockers.

Core/Factory canonical JSON preserves float `1.0`; StrategyDefinition canonical normalizes it to `1`. Work verifies owner envelopes using owner JSON rules and preserves the original sealed Core JSON as a string inside the existing canonical receipt store. It never normalizes and silently reseals an owner's evidence.

## Final gates

Focused positive/negative tests cover native source and checksum mutation, resealed forged price/source parents, cutoff and cross-cohort identity, false PIT, duplicate/missing candidates or bars, plan/definition drift, missing arms, forged duplicate parents, future feature availability, holdout access, modeled costs, warmup/censoring, no-source, deterministic receipts and exact existing seven-family regeneration. One consolidated TEST_ONLY gate runs the full 53-candidate native custody/Factory route twice with identical receipt bytes. Original private calculation is a separate truthful evidence class; public CI does not replay original market bytes. Audit must review original evidence independently before scientific acceptance.
