# Strategy Factory P0 recovery — review dossier (2026-10-26)

Status at code delivery: engineering evidence ready for exact-HEAD CI and real-data development replay; not an acceptance/merge verdict. The final evidence receipt is supplied separately after running this exact source commit, avoiding a self-referential commit hash.

## Verified handoff and reconciliation

The latest verifiable owner-sent Work instruction is the complete **Strategy Factory P0 Recovery & First Historical Backtest** request in this chat (2026-10-26). It explicitly authorizes bounded Factory repair/development replay, existing Draft #117 only, and forbids OOS/final holdout, merge/main changes and agents. It supersedes broader #120 OOS scope for this delivery.

Accessible original owner messages in `ATLAS Factory Codex Review` include the P0 directive, “ابد التنفيذ”, “كمل ما تستناش نتائج الاختبارات الا لو ضروريه للخطوة التاليه”, and the latest “كمل” preceding `bca213b`. `Strategy Factory Manager` contains the B recommendation followed by owner “تمام كمل”; B remains provisional, not G0 acceptance. Earlier full Work receipts cannot be reconstructed merely from agent summaries. This request is itself the current direct authorization, not a claim that a previously drafted command was sent.

Reviewed accessible text in: Strategy Factory Manager; ATLAS Factory Codex Review (both available conversations); ATLAS Strategy Factory (both available conversations); مراجعة التسليم الفني; WORK; and the current 🏗️ ATLAS | مدير الكور discussion. The last contains separate Core #92 authorization, which does not authorize any Factory use of operational feeds. GitHub #77 body and all 76 returned comments, #120 body/comments, #117 reviews/conversation, open PR inventory, #108 and #46 metadata were retrieved. Original attachments marked “file contents were not included” and content-reference-only messages are **inaccessible**; no review of their missing contents is claimed. Unlisted/archived conversations and external sessions were not reviewed. No new essential authorization is inferred from those gaps.

Reconciled binding decisions: Fast Research, Strict Validation; reuse existing Factory; retrospective data never CONFIRMED; per-opportunity immutable technical/context snapshot; predeclared regimes with separate target/off-target results; missing context explicit; dev/OOS/forward separate; no COMPLETE or independent-custody assertion. All architectural approvals remain provisional until G0.

## Source and dependency status

Verified main: `8ce639915ef0181d2b899b518759dd0f4c9ca9e1`. Incoming #117 HEAD: `bca213b75a2d93eb9ef41cebddfd4bc1a9ab97ec`, newer than the review's `86c0f9f47e7bfa98a5adb997da84a66454f02a0b`. Draft remains open. The latest incoming four CI runs were successful (40275123197 Factory, 40275123188 Contracts, 40275123237 Integrity, 40275123156 G1); these do not validate the recovery commit.

#108 actually merged at `c6851bbaf0664d19490e374d6019687d1c234be7`; #46 open/unmerged, HEAD `a4c106a02c55ee012eedf4c55c1488d71d850203`. No #46 files, durable journal, execution runtime or checkpoint imports are used. No accepted custody/CONFIRMED gate or cross-module content-hash semantics changed. The retrospective path is separately labeled and never calls the confirmed evaluator to fabricate admissibility.

Compared cumulative changed paths against all other 36 open PR file lists and recorded their exact HEADs: zero direct path overlap. This is not architectural approval of those PRs. #46's old research ancestry is excluded; #108 accounting and Indicator V2 are semantic dependencies exercised by focused regressions. No Core/Scanner/Secretariat/G1/feed source files changed.

## Bounded repair

- Extract the exact #108 slipped-price/both-notional fee arithmetic into `account_long_prices`; the accepted synthetic engine and both existing demonstrators share it. No second general stop/target/TTL engine.
- Use Indicator V2 `_ema` (fsum seed); plan pins V2 and fixed 8/21. Exact borderline-prefix comparisons cover the binding.
- Require a separately retained expected frozen-plan digest before intake/replay. Changed split, fee, slippage or source fails. Archive SHA, member identity, interval, complete grid and gap rejection precede replay.
- Crossover replay is narrow one-BTC long glue: 100000 USDT fixed initial capital, no leverage/reinvestment, capital rejection, next open, crossover exit, no stop/target, unresolved terminal positions. Missing next bar is UNKNOWN, never evidence of NO_FILL. TTL=1 market-entry model has no observed no-fill/expired orders; those counts are explicit zero, not imputed wins/losses.
- Decision snapshots contain only past technical/context information plus immutable plan/source binding. Execution status is outside the decision snapshot. News, macro, ETH, dominance, breadth, RSI/MACD and other unavailable contexts remain unknown. Bar volume/range are proxies, not order-book liquidity or a comprehensive regime classifier.
- Mark-to-market equity includes hypothetical terminal liquidation costs, separately from closed-trade results. Drawdown uses minute close marks, not intrabar peaks. Benchmark uses the first possible execution open (bar22) to final development close and same costs, one BTC; its percentage is a trade return, not the portfolio percentage.

## Dataset and pre-registration

See JSON files in this directory. Binance Vision SPOT BTCUSDT, 1m, **2024-01-01 UTC only**; expected 1440 bars, observed 1440, gaps zero. Archive SHA256:
`4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e`.

The source CHECKSUM was separately downloaded before the ZIP and matches; same-publisher integrity is not independent custody or historical publication proof. Download observation/HTTP metadata is retained. Exact historical ingest/publication times are unknown. Assumption: closed candles available at close+1ms, hypothetical zero processing latency; next open is eligible under this declared assumption, with no executable liquidity claim. Source archives can be revised; hash pins this version.

License as observed: Binance Vision Dataset Terms v1.0 / CC BY-NC-SA 4.0, noncommercial personal research. Attribution: Binance Vision. Raw archive is local only and not redistributed. See https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md . Derivative real-data outputs are CC BY-NC-SA 4.0 with this attribution; this does not relicense repository source code.

The date/window, costs, strategy, comparator and regime rule were saved before downloading prices. A further frozen-plan amendment before the first replay fixed 100000 USDT capital and corrected benchmark eligibility. No outcome-driven selection, OOS data download, final holdout opening or optimization. OOS begins 2024-01-02 but remains unacquired/unevaluated; final reserved holdout identity is unknown and untouched. One day is deliberately an engineering sample, insufficient for profitability, regime coverage or statistical inference. No confidence interval/significance/promotion claim.

## Reproduce offline

Use Python 3.10–3.12 (CI), or tested local Python 3.14.3. Download the exact ZIP from the `source_reference` in `plan-arguments.json` plus its `.CHECKSUM`; compare SHA256 before proceeding. Use the recorded final code SHA from the delivery receipt and a clean checkout.

```text
python -B -m scripts.sf_ema_development --archive <local BTCUSDT-1m-2024-01-01.zip> --plan-arguments docs/evidence/sf-p0-20261026/plan-arguments.json --expected-plan-sha256 a804e75d43ca0cd57988e7b44873d4179be198fea3c452ec7b38a9a9b9f8ad1b --output <new output.json>
```

Run twice with different new output paths; compare file and replay digests. The CLI uses exclusive creation and performs no network I/O. Canonical serialized snapshots and report hashes detect changed evidence when the expected commitment is separately retained; they are not an immutable external custody service. No durable/fsync/power-loss or AttemptLedger COMPLETE claim. Original input/attempt ledger boundaries remain gated.

## Verification and remaining gates

Focused workflow retains the existing **31 boundary JUnit cases** (27 methods +4 subtests) and separately asserts **41 P0/accepted execution cases**, zero skips/errors/failures, Ubuntu/Windows × Python 3.10/3.11/3.12. The existing 464 contracts gate is unchanged. Local results and exact final-head CI links/counts belong in the final receipt.

Owner next decision: accept/reject this bounded development evidence and frozen assumptions after independent review; merge remains separate. #120 OOS readiness, representative samples, timestamped independent custody and result-to-durable-ledger acceptance remain unresolved. Keep #77/#120 open and blocked until owner disposition. No new architecture, agents, paid services, secrets, paper/live trading or production activation.
