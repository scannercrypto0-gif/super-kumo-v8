# Discoverer D1–D6 bounded rehearsal

Owner scope is [#276/6797230715](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/276#issuecomment-6797230715).
Reuse the existing Discoverer draft, frozen hypothesis/search/validation
contracts, and the durable Package E checkpoint. The earlier D-SCAN-1 and
Factory E candidate-generation registry path retain their accepted scope.
This delta has no collector, private-data reader, trading route or Factory
scientific evaluator.

## Core contract

`aql.core.discoverer-snapshot.fixture.v1` binds a fixed membership hash, venue,
market and scheduled slot. It includes every available member's return,
measurement onset and end, publisher, receipt and known-at clocks and a Core
receipt digest. A missing member is UNKNOWN; a missed snapshot is MISSED.
The caller supplies a separately retained expected digest. A new membership
version gets a new pinned policy and run directory. The provisional fixture
ranks eligible non-stable/non-wrapped alts by return within the declared
horizon. Core supplies rank eligibility and sector taxonomy. BTC and PAXG
are explicit roster members. No provider, exchange listing or cap ranking is
asserted by this policy.

The watch receipt is persisted before querying pre-onset context. The request
schema `aql.core.discoverer-context-query.v1` binds outcome identity, symbol,
venue, market, exact lookback and exclusive cutoff. It asks for price, volume,
liquidity, BTC, sector, PAXG, news, macro and Scanner MONITOR_ONLY context.
Fixture responses bind the request hash. Publication, local receipt and
known-at must be strictly before cutoff. Corrections require a visible prior
version and its hash. Late/unknown clocks are counted as exclusions. No raw
Core source bytes are copied.

## Research, feedback and operations

Each due slot is searched, including quiet slots. UP and DOWN have separate
comparison records with a deterministic symbol/sector/horizon match. Retain
trigger/no-trigger controls, contrary, missing and unmatched observations.
Candidate generation requires an observed trigger and a matched control.
Each direction has at most one proposal per frozen run. A proposal is a
falsifiable precursor study, with a separate native family definition,
SearchPlan and sealed ValidationProtocol. It carries no executable strategy
or signal. The forward fixture can freeze a full-roster trigger census before
onset and settle it later, keeping false positives, false negatives and
UNKNOWN in the denominator. Neither the fixture clocks nor event-conditioned
counts attest PIT, causation, predictive skill or alpha.

The checkpoint stores idempotent ACKs and independently pinned Factory
PASS/FAIL/UNKNOWN feedback. The prior native Factory E registry path is
reused for its accepted D-SCAN-1 inputs. These new context predicates require
a Core/Factory-approved feature/strategy translation and independent
scientific result before that downstream route can run. The feedback
contract records lineage and cannot self-promote or unlock the holdout.

`Loop.poll` is called by a single owner-managed polling worker. At most four
due slots per call, 64 per frozen run, 32 members per slot and 32 records per
context response. The response and stored tick each have a 256,000-byte
limit. Synchronous calls avoid a growing queue and prioritize event requests.
The post-call CPU/wall check is supervisory, not a hard worker kill limit.
Core's production client must enforce its own timeout and verified budget.
The bounded fixture soak, restart and gap handling are engineering evidence.
Actual 24/7 deployment, longitudinal live universe continuity, production
Core and independent Factory acceptance remain external dependencies.

Run the focused tests from repository root:

```text
python -B -m pytest tools/strategy_discoverer_offline/tests/test_continuous_research.py -q
```
