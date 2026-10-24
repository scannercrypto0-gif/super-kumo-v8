# SF-IND-02 additive research indicators (Issue #66)

Base: main 72a183c445fbfc2de20311870e34f861dd85535f. V1 library, its 50 tests and published results are unchanged. No G1/Holdout/execution engine.

## Compatibility and units

| Contract | Accepted main | Additive V2 boundary |
|---|---|---|
| Registry | IndicatorLibrary with SMA/EMA/RSI/ATR v1 | IndicatorRegistryV2 delegates every V1 ID; six explicit *_v2 IDs |
| Results | scalar IndicatorResult.value, existing hashes | frozen VectorResult.value tuple of (field, finite float); no mutable output dictionary |
| Manifests | existing IndicatorManifest | canonical immutable VectorManifest with version, fields, params, dataset hash, cutoff and ordered result commitments |
| Custody | CustodyAccessor confirmed availability | same adapter required; complete contiguous coverage only, no partial opt-out |
| Strategy contract | separate Draft from same main | injectable registry.get; output_fields and version; no strategy import/dependency |
| Ledger | earlier research PR chain unmerged | no journal/ledger implementation or upstream imports here |

Every result binds exact requested start/seed history via its ordered dataset provenance and warmup policy. Computation is prefix-only. Same inputs **including manifest creation metadata** yield identical hashes. Re-importing identical candles into a different custody manifest intentionally changes provenance. Hashes detect change against a retained receipt; replaceable hashes alone do not authenticate external custody.

Parameters are explicit, period/smoothing counts integer2..10000 (no bool), deviation multiplier finite (0,10]. fast<slow for MACD. Constructor configuration is caller-owned; emitted results/manifests are immutable. No live data calls or cross-asset alignment implied.

| ID | Fields | Definition / first output index (0-based) |
|---|---|---|
| MACD_v2 | macd, signal, histogram | Independent fast/slow EMA seeded with each period SMA; alpha2/(p+1). MACD fast-slow, signal SMA-seeded EMA of MACD, histogram difference. slow+signal-2 |
| BBANDS_v2 | middle, upper, lower | rolling SMA ± deviations × population SD (ddof0); period-1 |
| ADX_v2 | adx, plus_di, minus_di | Wilder TR/DM sums seeded from changes1..period, strict directional tie gives zero DM; first ADX mean of period DX values, then Wilder averaging. 2*period-1 |
| STOCH_v2 | k, d | fast %K rolling high/low; D=SMA(smooth K values), **not slow stochastic K**. First jointly valid vector period+smooth-2 |
| ROC_v2 | roc | percentage100*(close/close[-period]-1), period. Zero denominator raises |
| OBV_v2 | obv | zero at first requested bar; cumulative signed **provided base-volume units**, equal close adds0, no session reset. index0 |

Zero TR/DM gives DI=ADX=0; flat stochastic high==low gives neutral K=50. Zero volumes are valid and OBV stays0. Overflow/nonfinite output rejects the computation, never publishes NaN/Inf.

## Reference evidence and parity

Tests compare every output on a nonmonotonic OHLCV vector against independent 50-digit Decimal calculations. EMA and Wilder reference use closed-form decaying weighted sums, not production recurrences. Bollinger reference uses second moment variance; ROC/OBV use direct sums. Six fixed result/manifest commitments pin cross-platform behavior for an explicitly fixed fixture custody timestamp. No TA-Lib dependency or claim of identical vendor seeding.

Formula context: [TA-Lib function definitions](https://ta-lib.org/functions/), [Wilder ADX reference](https://github.com/TA-Lib/ta-lib/blob/main/ta_codegen/input/adx/adx.md). This implementation explicitly versions its chosen initialization; it does not claim bitwise TA-Lib compatibility.

Run:
`python -B -m pytest tests/test_sf_ind_01.py tests/test_sf_dep_guard.py tests/test_sf_ind_02.py -q`
Actual dependency guard checks this new library; CI installs pytest and pytest-timeout, preserving the repository timeout rather than suppressing its warning. Final CI evidence belongs in PR/#66 report.

## Explicitly deferred
VWAP: existing OHLCV lacks an approved session calendar/anchor/reset and volume-unit custody contract. OBV only uses signed raw base-volume under a fixed-start seed; it makes no notional/session claim.
Cross-asset relative strength/volume normalization needs aligned confirmed availability and units. Funding/OI/order book/sentiment require new data contracts. None added.
No profitability, promotion, production, paper or live execution claim. Draft only; owner merge decision separate.

## Final acceptance hardening
V2 verifies the custody manifest on every compute and rejects bool/float dataset versions. Computation manifests additionally bind exact requested start/end and ordered input-bar checksum digest, including seed history; individual result hashes alone are not a complete requested-range receipt. Manifest verification checks result identity, parameters, warmup, fields and ordering against metadata, not only the list of hashes. Original V1 bytes/commitments remain unchanged.

FINAL quality and internally consistent receipt/availability times are checked at the new consumer boundary. Recorded ingestion cannot be later than declared availability, even if both hashes are self-consistent. A CONFIRMED label with unknown receipt time remains only the accepted custody assertion; synthetic fixtures do not prove real-world receipt evidence. No G1 or accepted V1 code changes.
