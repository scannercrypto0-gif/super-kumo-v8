# Factory B1 — original market-data execution, partial research delivery

Authority: #77/6557846835; ATLAS Quant Lab / AQL-CRYPTO-RESEARCH-001.
Existing Factory Draft #209 only. Historical market data independent slice is
executed. Strategy outcome research remains BLOCKED_ORIGINAL_CORE_SIGNALS_NOT_SUPPLIED.
No merge, G0, operational PIT or Shadow/Paper/Live readiness claim.

## Actual acquisition and identity

Direct `git ls-remote origin HEAD refs/heads/main` succeeded: main
`dbc191df72f4b4d1ebb7d490926dcad4325dac12`. Full Git objects for Factory #209
`e52a9fb9d091ce439278988bdb0c7ef4ffaeab99` and Core #216
`3ed2954c007d8a2cf9bb111ddc17d6f95d8be7ec` were fetched successfully; separate
detached Factory worktree used. No accepted branch was merged or Core code edited.
All twelve Binance monthly ZIPs and their twelve `.CHECKSUM` companions returned
HTTP 200. Prior DNS/access failure is no longer the current blocker.

Fixed research period selected before calculating outputs: 2024-01-01T00:00:00Z
through 2025-01-01T00:00:00Z exclusive, Binance Vision Spot BTCUSDT 15m. Full
leap year, 366 days / 35,136 bars / 1,940,641 original compressed ZIP bytes.
This is descriptive in-sample research, not preregistered confirmatory OOS.
No prior 2024-01-01 **1m** ZIP was reused or resampled.

Source URL template:
`https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2024-MM.zip`
and the identical URL plus `.CHECKSUM`. Each precise URL, original byte length,
SHA256, same-publisher checksum bytes SHA256, original CSV-member SHA256,
expected month count/start is committed in `originals-lock.json`. The acquisition
observation file retains response metadata. Its request-start times and HTTP
Date/Last-Modified/ETag are diagnostic observations, not historical availability
or independent publication/correction clock evidence.

Parser validates exact single CSV member and CRC, all 12 columns, canonical
integer timestamps/trade counts, finite positive ordered OHLC, nonnegative volumes,
taker-volume bounds, every 15m open and close, month and whole-year counts and
cross-month continuity. No interpolation, resampling, deduplication or dropped rows.
Normalization keeps original text values in 12 named canonical sorted ASCII
JSONL fields; it does not create availability/publication/finalization timestamps.
ZIP -> CSV-member -> normalized JSONL -> market-window CSV -> report hashes are
separate. Correction generation/history is UNKNOWN: these are current vendor
download snapshots with exact retained-byte identity. A future changed download
fails against the committed lock rather than silently accepting a new vintage.
Same-publisher checksums and this local hash lock do not establish independent
issuer custody. CI retains original bytes and outputs for 90 days; artifact
retention is not external historical custody or a permanent availability promise.

## Measured results (market only)

35,136 / 35,136 bars; missing=0; duplicates=0. Each closed bar is a descriptive
market anchor. For each anchor, reference is the **next** bar OPEN; the future
window comprises the next 16/96/288 bars; endpoint is its last CLOSE. No strategy
is created and there is no fill claim. All anchors remain in denominators,
including those without enough following data at the period end.

| Horizon | Market anchors | Complete | Censored | Price up / down / flat | Mean gross price change, bp | Mean unsigned high-low range, bp |
|---|---:|---:|---:|---|---:|---:|
| 4h | 35,136 | 35,120 | 16 | 18,330 / 16,787 / 3 | 4.21362272 | 158.40609602 |
| 24h | 35,136 | 35,040 | 96 | 18,812 / 16,226 / 2 | 25.09533211 | 413.69462282 |
| 72h | 35,136 | 34,848 | 288 | 18,903 / 15,944 / 1 | 73.86934532 | 740.03471129 |

105,408 descriptive horizon rows, 105,008 complete and 400 censored. Price up/down
are NOT wins/losses. Raw price change = (endpoint close / next open - 1)*10,000.
Unsigned range = (future high maximum - future low minimum)/next open*10,000,
NOT signed directional MFE/MAE. Means exclude censored values, whose counts stay
visible. Overlapping observations are dependent; no p-values or independent-trial
interpretation. Passive period context: first OPEN 42,283.58, last CLOSE 93,576,
gross price change 12,130.57645545 bp. This is not strategy profit, investment
advice or a matched strategy-baseline comparison.

Fees, slippage and spread are NOT applied to raw market statistics; actual
execution costs, fills and PnL are NOT_CONFIGURED/absent. Illustrative 32bp
round-trip = 2bp full spread + 2*5bp slippage + 2*10bp fees, not measured account
charges, not run approval. No adjusted strategy result is inferred.

## Original Core signals: exact missing input

Read live #180/6558027071 and #77/6558035673, current #216 projector, example,
full 283-path Git tree, plus #134 and Claude #215 latest handoffs. Inventory
and exact-source grep are retained in `core-tree-inventory.txt` and
`core-source-findings.txt` at pinned Core SHA above. No original historical
2024 BTCUSDT 15m strategy signal/schedule bytes were delivered in those inspected
trees or handoffs. This is a scoped finding, not a claim that none exists on an
unseen operator disk. Core B1 explicitly emits a CONTROLLED_ONLY two-opportunity
sample; its `directional_outcomes_allowed=False`. It must not be joined to these
real archives as historical decisions. Old P0 producer is RETROSPECTIVE_NON_PIT
and its reported one-day 1m source is distinct. No P0 production rerun/backfill.

Core/owner must supply retrievable original, hash-bound historical records:

1. Complete eligible/scheduled C2 opportunity list for this source/period, stable
   opportunity/pair identity, decision cutoffs, strategy/version/parameter pins,
   explicit HOLD/NO_SIGNAL/rejected cases and BASE/SHADOW arm schedule.
2. Original BASE/SHADOW decision records and byte hashes with direction, entry
   reference and timestamp/units, TP/SL levels and activation/expiry, missing or
   unknown arm status; retained source/prefix/version/correction lineage tied
   to actual archive/transform provenance. Do not reconstruct nonexistent F1.
3. Original monitoring-indicator snapshots, registry/version/warmup and decision
   availability assumptions, so associations can be evaluated without lookahead.
4. Explicit research provenance and permission to analyze those records; an
   honest retrospective record need not be relabeled prospective PIT to support
   descriptive research. Independent prospective clock/custody/freeze proof is
   a **separate** operational acceptance boundary, not manufactured here.

Therefore strategy N, 2*N arms, 6*N horizon rows, wins/losses/UNKNOWN counts,
target/stop ordering, indicator association and paired baseline remain **null /
NOT_COMPUTABLE**, not zero and not substituted by 35,136 market anchors. Once
real schedule/records arrive, retain every 2*N slot/6*N row; missing evidence
stays UNKNOWN, same-bar TP/SL ordering stays unknown without finer original
evidence, and no candle touch proves a fill. Full strategy research is not complete.

## Replay and verification

From this exact delivered Factory commit, Python 3.11+ standard library only:

```bash
python -m research_wp_r0.aql_b1_market_research \
  --lock docs/evidence/factory-b1-20261101/originals-lock.json \
  --data-dir /absolute/path/to/b1-originals \
  --out /absolute/path/to/new-b1-replay --download
cmp /absolute/path/to/new-b1-replay/report.json docs/evidence/factory-b1-20261101/market-report.json
AQL_B1_DATA_DIR=/absolute/path/to/b1-originals python -m unittest -v tests.test_aql_b1_market_research
sha256sum /absolute/path/to/new-b1-replay/*
```

Output directory must not exist; omitting `--download` makes an offline replay
from retained originals. Network failure, missing files, corrected vendor bytes,
hash mismatch or malformed coverage fail rather than substituting fixtures.
Replay observations are nondeterministic diagnostic metadata; report, normalized
JSONL and window CSV are deterministic and do not include retrieval clocks.
No signal-file acceptance interface is exposed, so arbitrary JSON cannot silently
become original Core decisions.

Two separate local Python 3.12.14 processes reproduced identical report bytes.
Eight new focused tests run against downloaded actual originals: whole-year,
changed ZIP/checksum/member hashes, duplicate grid, malformed OHLC, nonfinite
volume, and exact next-open/horizon-censor boundary. Adversarial derivatives of
actual rows are test inputs only, never reported as market observations. No old
accepted controlled 288-bar, P0/W1-B or integration harness suite rerun.
The existing Factory focused workflow now downloads/rechecks the locked real
originals, compares exact report bytes, runs only this eight-test module and
uploads originals/replay. CI SHA/run/log/artifact results are recorded in the
Issue #77 delivery after actual completion, not predicted in this document.

| Artifact | SHA256 |
|---|---|
| originals-lock.json | 267964c81772b1a118cd740c8d8a6bc6a757e615a98d80769a68e5a12df34679 |
| market-report.json | 1791109fcbc7a8370ca234fbd24d27bc37db1fc078a142c3b7c54ea9d55cdb11 |
| normalized15m.jsonl | 3858f72148e1f59c90b7ebb21c9979fc91f58540b61d2db89aef678a1020c76d |
| market-windows.csv | d0ab94bf1b12cb20f078472957426fee9a0548defea311b8637f9dbff39d5d27 |

Audit request: delta-only independent byte/hash/coverage/parser/window/count
replay and source-provenance boundaries. Existing accepted controlled overlay
and earlier component verdicts remain separate. Operational issuer publication/
correction clock, external immutable custody, real producer pre-F3 hook and
externally anchored original F1 remain BLOCKED_EXTERNAL_EVIDENCE.
