# ATLAS Scanner Bundle B — distinct native 15m TEST_ONLY compatibility

**Status:** New Scanner-owned integration source, Draft only. No merge, G0,
broker, operational Paper, holdout, scientific PIT, or private original bytes.

## Upstream exact code pins (read-only)

| Owner | Draft | Exact frozen code SHA for this branch |
| --- | --- | --- |
| Scanner Engine V1 | #227 | `b9c9ff8602e79c534402f44bce83c56ec2fa6bb9` |
| Work strategy service | #235 | `6acbcc7fc243b132f58170df4c6469bbf7f4eff8` |
| Core warehouse / Secretary | #226, Issue #253 | `1b165f85ab0dc21e14d9150764125d92a3b0b568` |
| Factory research source consumer | #255, Issue #254 | `e66ac39a6443853c60463f7bd5bfaf590bb125a6` |
| Discoverer | #230 | Only interface review, never required in Scanner→Secretary→Paper |

All four referenced PR branches remain **independent and unmerged**. The
workflow checks out exact commits and overlays runtime modules into an
**ephemeral CI checkout**, not GitHub source branches. No dependency is copied
or modified by this Scanner PR.

## Authority and important distinction

`native15m.native_15m_policy` requires a valid existing Work #235
strategy/version/DNA/config. It declares `timeframe=15m` **explicitly as
a new TEST_ONLY policy with a new config_digest**, retaining the Work policy
SHA and original timeframe field. It never changes or resamples source bars.

`native15m.scan_native15m` accepts only sealed source bytes of
`aql.strategy-service.synthetic-bars.v1`, `evidence_class=TEST_ONLY`
and an exact native 900,000 ms bar grid. It computes reference indicators
using the **existing** `IndicatorRegistryV2` and decisions via the
**existing** `StrategyDNAV2` rule functions. Every strategy and every
universe symbol gets a SHA-sealed row and explicit status:
SELECTED/REJECTED/UNKNOWN/UNSCANNED/INELIGIBLE (plus defined FAILED
denominator field), even when source/feature data are missing.

No part of the historical operational Scanner #227 UNKNOWN gets upgraded.
With original-retrospective source and missing original-time historical PIT
information, **all eligible historical screening remains UNKNOWN**.
A synthetic SELECTED means only a rule passed a test fixture; it is not a
genuine trading nomination. `safe_wait_for_paper` returns **WAIT even for
synthetic SELECTED**. Work #235 operational native 15m remains
`NOT_CONNECTED_15M_UNSUPPORTED`, which this Scanner-only code does not
misrepresent as closed.

`core_secretary.prepare_source_only_route` validates the original Core
#245 native `price_query_sha256` and Core #253 `query_local.query_sha256`
through Core's own independently sealed dual-query map. These are separate
SHA domains and are never equated, overwritten, or aliased. It accepts
**only** sealed native Scanner V1 UNKNOWN source envelopes, validates source
SHA/version/cutoff/symbol, and asks Core to enqueue one offline SLOW or FAST
source-only message. The Work strategy/version/config are pinned into the
new Scanner route receipt and deterministic Core idempotency key; Core still
owns its immutable route schema/outbox.

`verify_offline_consumer_ack` checks Core event history. Missing or
quarantined ACK yields WAIT; supplied Core ACK requires an actual persisted
ACKED event chain and Factory's read-only contract verifier. It never
creates ACK, never impersonates Secretary or Factory, and never makes
`strategy_decision=SELECTED` or `paper_execution=ACTIVE` from a source ACK.

## Focused regression / replay scope

`python -m unittest -v tools.scanner_strategy_b.test_integration tools.scanner_strategy_b.test_portfolio` after
pinned upstream runtime composition, as in workflow. Checks include:

- Two opposite strategy preferences, independent per-symbol 15m census
  (including incomplete, budget-excluded and universe-ineligible symbols).
- Exact native timeframe, SHA mismatch, duplicate and out-of-order bar,
  incomplete window, future or unknown availability, wrong source/TF,
  missing finality, malformed OHLCV, policy/config mismatch.
- Historical non-PIT never SELECTED and zero activation even from synthetic
  SELECTED.
- Core #245/#253 independent SHA domains, source/manifest/version/coverage
  mismatch, native Scanner UNKNOWN-only envelope.
- Core Secretary deterministic PENDING replay, absence-of-ACK WAIT,
  legitimate explicit synthetic caller ACK followed by verification,
  idempotent duplicate ACK, quarantined nomination unable to ACK.
- No existing Feb/Aug source bytes, no 106-result historical rerun,
  no original private evidence re-evaluation.

## Consolidated E2E boundary

This branch participates in **one future NEW-source combined E2E** alongside
Core and Factory, once an authenticated NEW original native-15m cohort and
a permitted shared runner are available. Core still owns real ZIP verification,
custody/query and Secretary; Factory owns Lab and isolated Paper policy.
The new source-only route cannot establish a same-source strategy rule
decision for retrospective original data. Final independent Audit #256
new-delta gate should evaluate this focused Scanner change together with
Core/Factory deltas only, preserving the prior ACCEPT_IN_SCOPE evidence
verdict and original known-at/PIT/holdout limitations.

**No platform/scientific claim:** This is native15m adapter compatibility in
Scanner's separate TEST_ONLY lane; it is **not** actual Work #235 operational
15m integration, independent original opportunity-universe verification, or
Paper approval.

## Mixed-timeframe portfolio entry point

`portfolio.scan_strategy_groups` runs independent per-timeframe and per-market
groups with exact distinct source bytes/universe/cutoff/strategy config. For
pre-existing 5m/30m/1h/4h/1d groups it invokes **Work #235's own scan**
and existing Worker→Scanner #227 bar-admission adapter without editing their
code. Explicit 15m groups invoke this branch's synthetic TEST_ONLY native
adapter. It returns immutable per-group receipts and a total attempts
denominator; a source/group/strategy/timeframe collision fails closed.

This supports **different screening preferences and declared timeframes** in
the same research portfolio without relabelling candles, cross-strategy
caches, or silently dropping whole groups. Its grouped-output schema is
Scanner-owned, not a change to the existing Work contract. It does not
claim that Work #235 can route native 15m operationally.

The focused CI gate also exercises mixed 5m/15m synthetic portfolios,
independent census/replay, duplicate group refusal, wrong timeframe and
cross-source unknown. The whole batch remains no-network and TEST_ONLY.

## Factory B ONE new-delta combined gate — Scanner handoff V1

Scanner owner: `tools/scanner_strategy_b/factory_handoff.py::prepare_factory_handoff`.
Input: a SHA-sealed Scanner `aql.scanner.strategy-native15m-test-only.v1`
run receipt; a separately sealed Core/Secretary `aql.scanner-b.core-secretary-source-route.v1`
receipt obtained using `prepare_source_only_route`; the independently
verified `aql.scanner-b.secretary-ack-check.v1` receipt from
`verify_offline_consumer_ack`; and **three independently pinned exact SHA
arguments** for source ZIP, Core245 native price query, and Core253 local query.

Result: immutable `aql.scanner-b.factory-handoff.v1` containing the test-only
per-strategy total denominator and census, every strategy ID/version/config,
every symbol/status/attempt/nomination SHA, the synthetic source SHA/manifest,
separate exact Core historical source ZIP/native245/local253 SHA parents and
Secretary ACK verification status. Every nested receipt is independently
SHA-verified before it becomes eligible for the combined harness. The
synthetic screening source and historical source-only route are **separate
lanes**. Historical PIT stays NOT_ATTESTED and operational Scanner UNKNOWN;
no synthetic SELECTED state is carried into the historical source route or
Factory's Lab/Paper authority.

Factory executor calls the existing Core Secretary `acknowledge_nomination`
only for a **real explicit test consumer acknowledgement**, then Scanner's
read-only `verify_offline_consumer_ack` validates the persisted Core outbox
payload, signed event trace and existing Factory source consumer. Missing or
quarantined ACK produces WAIT and no false success. Scanner's
`prepare_factory_handoff` does not call `acknowledge_nomination` itself.
Synthetic tests may provide a deterministic fake consumer SHA, but the result
must remain labelled synthetic, source-only, offline and NOT PAPER ACTIVATED.

For reproducible focused tests (CI composes exact pinned Draft owner modules
in an ephemeral checkout, never changes the owner's PR):

```sh
python -m unittest -v tools.scanner_strategy_b.test_integration tools.scanner_strategy_b.test_portfolio
```

The included CI deliberately does not run accepted original Feb/Aug cohorts,
106 historical reports, private data, operational Work235 Paper or an authentic
new-original source. The **new-source E2E status remains SOURCE_UNAVAILABLE**
until a new independently authenticated 15m cohort is delivered by Core, and
Factory's integrated software gate remains separately owned/assessed.
