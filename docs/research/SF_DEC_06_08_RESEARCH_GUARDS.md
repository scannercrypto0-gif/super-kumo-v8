# Strategy Factory research guards — SF-DEC-06/07/08 (provisional v0.1)

> **Status: OWNER PROVISIONAL / NOT G0. Documentation and acceptance-test DESIGN ONLY.** No runtime implementation, new market experiment, OOS/holdout evaluation, PR merge or strategy promotion is authorized here.
>
> Project: ATLAS Quant Lab (`AQL-CRYPTO-RESEARCH-001`). Scope: **Strategy Factory / future research plans only**, not Core, G1, Scanner, Secretariat, realtime feed, production, paper or live trading.

## Authority, continuity and boundaries

Owner confirmed:
- **SF-DEC-06**: choose *hybrid C*, with conservative *B* default for historical inputs without trustworthy receipt/readiness timestamps; no implementation/OOS.
- **SF-DEC-07**: prospective paired per-side **fee 10 bps + slippage 5 bps** base, and **fee 20 bps + slippage 10 bps** stress; no implementation/OOS.
- **SF-DEC-08**: each strategy declares **essential** versus **supporting** inputs when authored. Missing essential inputs prohibit a *new trading decision*; missing supporting inputs do not prohibit that decision, but their absence must be recorded. No post-result relabeling.
- Owner explicitly authorized direct **architectural documentation and acceptance-case design on GitHub only**, not code/CI execution or merge.

G0-GOV-01: most recent owner-sent Work execution handoff visible in the available records was **“Strategy Factory P0 Recovery & First Historical Backtest” (2026-10-26)**, followed by owner-directed REVIEW-02, CLOSEOUT-03, TIMING-REVIEW-04 and INDEPENDENT-GATE-05. Subsequently the owner personally sent an independent-reproduction request in a separate Work chat and confirmed its separation. The [published reviewer receipt](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/117#issuecomment-6410682200) documents bounded development replay, *not* independently timestamped historical data or actual fills. [Owner-authorized PR #117](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/117) **merged into main** at `3780de3943bb02aba8a00b689358af2108eebad9`. Issues #77/#120 remain open/blocked when this document was prepared. Other chats or Work attachments not visible here have not been claimed reviewed. Earlier independent code acceptance concerns *bounded code scope*, not prospective decisions.

Existing `docs/research/SF_STRAT_01.md` distinguishes confirmed custody and a fixed timing declaration; it does **not** yet implement the conservative delayed historical execution contract below. Proposed missing-data classification is a *future contract extension*; don't interpret it as modifying accepted strategy JSON V1 or its custody gates. Unmerged PR #46's research ledger must not be assumed to exist in main. Keep the historical repository distinct from the live feed and its routing.

## SF-DEC-06 — evidence-aware execution eligibility

**Goal:** no future research result may assume a fill at a price known only after its decision could have been made. Separate these four quantities:

| Symbol | Meaning | Evidence |
|---|---|---|
| `A` | LAST required input's actual availability to research consumer (final candle included) | Verified consumer receipt/availability, not mere publisher bar close |
| `R` | Decision computation readiness | Independently observable time, `R >= A`; hypothetical latency is not a measured R |
| `S_eligible` | First policy-permitted **order-submission opportunity** | Fixed causal selection/grid/TTL rule; not an order receipt |
| `F` | Actual fill | Explicit causal order/exchange evidence; an OHLCV open, fixed slippage or ACK alone does not establish F |

Two **mutually explicit**, predeclared simulation modes:

1. `RETROSPECTIVE_UNVERIFIED_TIMING`: historical closed OHLCV without reliable arrival/readiness times. Declare `A_assumed = candle_close_ms + 1` as a *counterfactual convention*, not observed A. Freeze execution grid width `Delta` in the plan and choose default guard `L = Delta` for now. Proposed hypothetical candidate is the **first eligible grid open** `T0 >= A_assumed + L`, subject to full causal coverage. For 1m candles closed 12:00:59.999, `A_assumed=12:01:00`, `L=60,000ms`, so first eligible 12:02:00, **not** the 12:01:00 opening. For 5m: 12:04:59.999 -> 12:05:00 -> 12:10:00. For 1h: 12:59:59.999 -> 13:00:00 -> 14:00:00. Apply identically to entry and crossover exit. `L=Delta` is a conservative *research default*, **not a statement that real compute latency equals an hour**. Any changed L must have a documented, versioned, owner-reviewed basis and be frozen **before** seeing candidate outcomes; no automatic per-asset search for favorable delay.
2. `VERIFIED_TIMESTAMPED`: require trustworthy availability for *all essential inputs* and independently observed readiness on a comparable time base. Submission eligibility follows R; only a causally supportable opportunity strictly **later than R** can be chosen, with the order's actual submission time respected where known. An OHLCV grid-open simulator can choose the next demonstrable grid opening; sub-grid/tick opportunities require their own timestamped evidence. Do not silently fall back to retrospective mode for missing receipt timestamps.

Common rejection rules: missing/ambiguous timestamps or clock-domain mismatch, nonfinal/late essential input, missing expected first eligible bar, gapped input/grid coverage, execution crossing development boundary or into unopened OOS, or unavailable market evidence => **UNKNOWN / UNRESOLVED** as applicable; do not skip ahead to a more convenient price. `NO_FILL` or `EXPIRED` requires a separately frozen order/TTL contract and enough evidence to assert that outcome. Record `A_assumed` separately from real A and preserve all unknowns. Even passing this contract **does not certify PIT custody or actual exchange fills**.

## SF-DEC-07 — fixed paired-cost policy, not optimized costs

- Pre-register **BASE** `fee=10bps`, `slippage=5bps` **on each side**, and **STRESS** `fee=20bps`, `slippage=10bps` on each side.
- Both runs use the **same frozen signals, opportunities, timing eligibility, capital/sizing, sample, split, benchmark and marking method**. Report both, including adverse outcomes, with no favorable after-the-fact scenario selection. These numbers are assumptions, not broker quotes or guaranteed executable costs.
- Reuse the accepted merged #108 accounting primitive in any later authorized code work. For 1 unit with raw entry `P_in`, raw exit `P_out`, fee rate `f`, slippage rate `s`: `cash_debit=P_in*(1+s)*(1+f)`; `cash_credit=P_out*(1-s)*(1-f)`; `net_quote=cash_credit-cash_debit`. Entry and exit fees apply to **their own slipped notional**, not a fixed round-trip haircut. Preserve open terminal exposure separately from closed realized trades; quote/account-capital percentage returns and benchmarks must use like denominators.
- A stress failure must be visible in the evaluation; it is not permission to retune costs. Acceptance threshold or model selection must be a **separate owner decision fixed before any new experiment**. Nothing here proves the strategy should trade.

## SF-DEC-08 — essential vs supporting, per-strategy frozen definitions

Every **new versioned strategy definition** must declare each requested input:
- `ESSENTIAL`: decision cannot be made without a valid, sufficiently fresh, finalized and causally available value, including derived essential indicators and their warmup inputs. Missing/invalid/stale/unverified essential data => `BLOCKED_MISSING_REQUIRED_DATA` (or a more specific recorded reason). **No new entry/trading decision** should be issued from that incomplete observation. Do not treat absent essentials as HOLD (which is a calculated strategy signal) or as zero.
- `SUPPORTING`: may rank, qualify or increase/decrease confidence **only when present** according to predeclared logic. Missing supporting data => a tagged `UNKNOWN` field and explicit `SUPPORTING_DATA_MISSING` audit record; continue evaluating the base decision if every essential input is valid. Never silently assume missing supporting data is zero, neutral, favorable or unfavorable. Freeze the no-support fallback rule and any confidence/position-sizing effect *before* results.

**Crucial qualification:** if a purported supporting input is a **hard veto**, mandatory safety filter, minimum liquidity gate, or is otherwise necessary to calculate a non-optional entry/exit rule, it is **ESSENTIAL for that decision**, regardless of the label. Users can select strategy-specific essentials, but cannot bypass mandatory system-wide risk/security/custody guards by reclassifying them as optional. Missing essentials prevent fresh entries; management of an already-open position follows a separately predefined conservative exit/risk protocol and must not be disabled silently by the entry data-block. Do not invent emergency fills or execution prices.

Example for a strategy explicitly frozen as EMA8/21 base crossover (ESSENTIAL: finalized BTCUSD price candles, EMA warmup and the EMA outputs; SUPPORTING: volume and BTC dominance used only for confidence):
- EMA present, dominance missing: base decision proceeds; dominance `UNKNOWN`, supporting-gap receipt emitted; confidence falls back to frozen no-dominance rule.
- EMA warmup gap or required BTC candle stale: block decision and record why.
- If a future strategy makes dominance a mandatory "never enter below X" veto, dominance must instead be tagged ESSENTIAL.
- If supporting input is present but contradictory, follow frozen strategy-specific conflict/weight logic; missing data is not an automatic favorable vote.

## Acceptance-test cases (SPECIFICATION ONLY — NOT EXECUTED)

| ID | Given | Expected |
|---|---|---|
| T01 | 1m retrospective, close12:00:59.999, open12:01:00 | 12:01 rejected; 12:02 eligible only with coverage |
| T02 | 5m and 1h retrospective examples above | Eligible at 12:10 and14:00 respectively |
| T03 | Candidate exactly `A_assumed+L` on frozen grid | Allowed; candidate 1ms early or off-grid rejected |
| T04 | Verified A12:01:00.120, R12:01:00.250, grid opening12:01 | Reject; next evidenced grid open candidate |
| T05 | Verified candidate time equals R or independent receipt arrives after R | Reject temporal tie/inconsistency; no forged readiness |
| T06 | Missing expected first candidate, later favorable bar exists | UNKNOWN/UNRESOLVED, no opportunistic shift |
| T07 | Candidate crosses frozen development split into OOS | UNRESOLVED, no OOS access |
| T08 | Missing receipt, inconsistent timezone/clock, partial/future candle | No VERIFIED-mode claim; do not auto-fallback |
| T09 | Entry and crossover exit | Identical eligibility policy for both, no same-close fill |
| C01 | Entry100, exit105, f=.001, s=.0005, quantity1 | Debit100.15005, credit104.8425525; net4.6925025 |
| C02 | Same frozen plan base vs stress; flat or losing trade | Both scenarios reported; two-side notional charges, no selection |
| C03 | Unclosed terminal position | Not a realized trade; separately labeled mark and risk |
| D01 | Essentials valid, optional dominance missing | Evaluate base signal; dominance UNKNOWN + audit receipt |
| D02 | Missing essential candle/EMA/warmup or stale data | Block new decision; explicit reason; not HOLD |
| D03 | Optional input present but conflicts with base signal | Apply predeclared weighting/veto semantics; no retune |
| D04 | Input labeled optional but used as hard veto | Definition invalid until classified ESSENTIAL |
| D05 | Required input becomes unavailable while holding position | No fresh entry; invoke separately frozen protective position policy |
| D06 | Strategy declares optional data but no missing-data fallback | Reject definition before replay |
| D07 | Future append, altered labels, availability or cost config after freeze | Pinned version/hash mismatch, cannot rewrite old decisions |
| X01 | Any scenario without observed fills or external PIT custody | Report hypothetical simulation, never CONFIRMED fill/PIT |

Acceptance requires both positive and negative cases, versioned definitions, explicit provenance/unknown fields, deterministic golden results across supported CI matrices, and independent review **only after** owner authorizes a bounded implementation. These are **not passing tests** or a new CI result.

## Implementation boundary and next owner gate

**No change** to P0 frozen original 2024-01-01 historical replay, its hashes, source plan, optimistic zero-latency label, benchmark or exploratory stresses. This documentation does not add a module, test, schema migration or runtime dependency. Existing confirmed-custody SF-STRAT-01 semantics must not be relaxed by prospective retrospective assumptions; if future implementation changes its schema/timing declaration, that requires a separately approved compatibility decision.

Future proposal (not ordered now): implement the smallest compatible policy extension on a new authorized PR, then run specification-driven synthetic/golden tests, CI and bounded independent review **before** any new data experiment. Keep retrospective market store separate from realtime feed routing. OOS, final holdout, ledger COMPLETE, empirical profitability acceptance, G0 final approval, deployment, strategy promotion, and any merge require distinct explicit owner decisions.
