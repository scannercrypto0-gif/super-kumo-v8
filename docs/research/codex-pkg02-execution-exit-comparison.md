# CODEX-PKG-02 — synthetic execution and A/B/C exit comparison

Dispatch: [Integration #271/6768334518](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6768334518).
Standing owner decision: [#205/6760348084](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6760348084).
Base: Factory #267 `04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf`.

## Precise material gap and reuse

The base already has strict seven-value Decimal cost inputs, gross/net returns,
next-open causality, same-bar ambiguity rejection, sealed H ledger/Lab reports
and SQLite immutable first/write plus replay. Its cost sensitivity does not
evaluate staged exits or maker entry nonfill/partial/UNKNOWN. Those are the
material additions here. No signal engine, candidate optimizer, new warehouse,
source downloader or replacement Factory store is introduced.

The comparison is an opt-in function of the existing H scientific Lab:
`evaluate_execution_exit_comparison(packet)`. It calls the established
`aql_factory_historical_rule_projection._modeled_trade` for each fractional
accounting leg and `_costs` for strict cost validation. It reuses Factory E's
attempt validator and H's `_store_package`. The reused cost kernel and H store
at this base are byte-identical to the accepted synthetic Factory pin
`52504ad59d75976ce45fb8f75c1b278c3d1b0975`. Existing H evaluation and original
F2 24/20+4 paths are unchanged; no Scanner/Discoverer contract is edited.

## Executable scoped contract

Only `SYNTHETIC_FIXTURE_ONLY`, SPOT/LONG, `trading_authority=NONE` and
`holdout=SEALED_UNOPENED` are accepted. A SHA-sealed fixture freezes entries,
strategy/baseline references, initial risk, all variants, explicit costs,
selection policy and an independently generated seeded null entry cohort.
The entry-batch reference is synthetic metadata, not a claim that an external
Scanner receipt or real source provenance was independently attested.
Training and evaluation must respect a minimum 72h embargo; freeze precedes
the first evaluation sample. Signal time strictly precedes entry at the next
supplied eligible open. OHLC and entry sequences are chronological and entries
within each comparison cohort cannot overlap. This adds no OOS reader and
rejects opened holdouts and winner-selection modes. A caller-controlled seal
is integrity evidence, not an external witness of a genuine prospective freeze.

The three policies use identical entries and initial risk:

| Policy | Supported model |
| --- | --- |
| A | Full exit at the final target, fixed initial stop |
| B | Three predeclared allocations/targets, fixed initial stop |
| C | The same three targets; move stop to entry **from the next bar** after target 1 |

Stop and target touched in one OHLC bar means UNKNOWN before booking favorable
legs in that bar. A previously realized fraction followed by an unresolved
remainder retains its trace but has no full-trade gross/net/cost aggregate.
Stops crossing an opening gap use the worse opening price, not a fictional
exact stop fill. Target market orders crossing an opening gap use that opening
price as an explicit synthetic model. Accounting marks at bar close+1 are
return-kernel reference times, not observed order/fill timestamps.

Each policy has TAKER, PASSIVE_ENTRY_MARKET_EXIT and STRESS_TAKER assumptions.
Passive entry state must explicitly be UNKNOWN, NONFILL, PARTIAL or FILLED;
a bar touch never establishes a passive fill. Nonfills remain in the denominator
and have no charged fee. Partial fills scale exposure and all variable costs
against initial notional. Market exits are explicit even in the passive-entry
scenario; passive target fills are not claimed. Stop-limit triggers remain
UNKNOWN_FILL. No broker orders or Paper positions are created.

Fees, spread and slippage are separate disclosed bps components. The exact
convention is half-spread per leg, with slippage **excluding** that spread;
overlapping conventions are rejected. Entry costs are allocated by exit fraction,
so three exits do not triple-charge entry fees. Spot funding is explicitly zero.
Stress costs cannot be lower than taker costs. These numbers are synthetic
assumptions, not verified venue fee schedules or realized economics.

Attempt/generated/failed/failed-to-generate/unscanned census is explicit and
preserved alongside all nine variant outcomes per entry, including UNKNOWN and
missed fills. The seeded placebo is generated separately without using candidate
outcomes; this is an engineering null fixture, not scientific independence proof.
Unknown outcomes suppress aggregate promotion. Reports include descriptive
gross/net, expected R per attempted entry, trade-close drawdown/tail and order
counts where complete. There is no selected winner or alpha claim.

## One command, no network or private data

From this checkout, using Python 3.11+:

```text
python -B tools/atlas_factory_pkg02_execution_smoke.py --output-dir artifacts/pkg02
```

It creates one disposable v2 SQLite store and JSON input/report, first/replay
receipts and nine deterministic negative rejections. Existing identical input
replays; same experiment with changed costs/input/report fails immutable custody.
Tests also replay from an independent Python process. Published artifacts contain
synthetic JSON and logs only, not the SQLite DB or any source/private bytes.
The report seals the input, policy, code manifest (UTF-8/LF-normalized source
hashes), all outcomes and coverage. CI pins the PR head SHA explicitly and runs
the material delta plus adjacent Factory regressions on Windows/Linux.

## Honest unsupported coverage

No real fills, queue reconstruction, adverse selection, passive exit fills,
cancellation/repricing/fallback, fixed ticket fees, short/perpetual funding,
continuous trailing stop, calibrated latency/liquidity/impact, intrabar path,
portfolio intratrade drawdown or final OOS/multiple-testing robustness is claimed.
Policy C supports exactly next-bar breakeven, not arbitrary trailing variants.
G4 scientific admission, original sources, owner external rights and G0 remain
outside this engineering change. No real acquisition, original March/April
execution, new external probe, Work edit, G2 observer reset, merge or trading.

Exit: `PASS_SYNTHETIC_ENGINEERING_ONLY` when tests and deterministic replay pass;
not a real OOS scientific result, economically attested execution or stage signoff.
