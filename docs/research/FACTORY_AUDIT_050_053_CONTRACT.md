# Factory indicator numerical compatibility and fixed-window research policy

Scope: scoped owner remediation of AIARC-050/051/052/053; synthetic / offline. No historical PIT, OOS, live or G0 approval.

## AIARC-050 — fixed anchors
MACD and ADX recursive smoothing and cumulative OBV may change if the input prefix changes while target bar remains fixed. Two calculation claims are comparable only when the **same dataset ID, pinned dataset version, input manifest, source bytes, indicator ID, parameters, start_ms, end_ms, decision cutoff, warmup policy and input bar hash** agree. Use the existing indicator_calculation_identity.require_same_calculation gate, not a fresh identity implementation.

For the first empirical study: pre-register a **single fixed UTC anchor and warmup prefix per dataset/indicator before inspecting outcome returns**; calculate scanner/decision/monitoring from the same pinned prefix, at each causal cutoff. Missing prefix, varying start, unpinned vintage or changed seed => NOT_COMPARABLE, never silently pair or overwrite. An independently verified convergence study may justify later explicit scope changes but is not presumed from MACD/ADX mathematical formula. Existing tests for window identity and OBV shifted start are reused; no new OOS study started.

## AIARC-051 — RSI
RSI_v1 has historical zero/zero=100 semantics, preserved for immutable replay. New RSI_v2 has neutral zero/zero=50, gains only=100, losses only=0. New StrategyDNA definitions must **explicitly select RSI_v2**, and cannot silently change prior DNA digest, signals or thresholds. No old archived result is re-labeled or recomputed under the same ID. Mandatory approval before promoting a strategy using the new signal interpretation.

## AIARC-052 — EMA
Existing EMA_v1 valid smoothing values retain their previous output identity. Constructor refuses non-finite or out-of-range smoothing where alpha=smoothing/(period+1) is not strictly positive and <=1; the same invalid parameter was not a usable well-defined convex EMA, so no persisted valid result reinterpretation is authorized.

## AIARC-053 — Manifest verification
Existing V1 manifest bytes/hash scheme is unchanged. verify(results) now checks each result's provenance hash and matches the declared manifest computation identity. This is a verifier strengthening, NOT retroactive cryptographic signer or independently attested custody. Genuine source-supplied recalculated result+manifest still needs independent source recomputation, custody checks and Council review before empirical admission.

## Release bounds
Changes in Draft #143 stacked on unmerged Draft #141/#140/#139/#138; CI plus independent S/R on exact commit is required. Core Binance watcher evidence and issuer first-known verification are separate responsibilities and remain outside these fixes.
