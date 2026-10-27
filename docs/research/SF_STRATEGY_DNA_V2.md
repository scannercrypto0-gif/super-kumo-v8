# StrategyDNA V2 — bounded synthetic role slice

Project: **ATLAS Quant Lab**, `AQL-CRYPTO-RESEARCH-001`.
Canonical repository: https://github.com/scannercrypto0-gif/super-kumo-v8

This additive implementation is explicitly opted into and synthetic only.
It is not a running market Scanner, strategy acceptance, paper execution, OOS,
a full Shadow engine, Research Lab, independent custody or final G0 approval.

## Continuity and scope

Verified starting main: `a4f19c97e77d87f1cd69f4146822394fe3f369d4`,
the owner-authorized Factory PR #126 merge. This is the latest executed Factory
delivery evidenced in accessible #77 records, not a claim to know the latest
global Work execution across inaccessible conversations. Historical handoff
register entries are preserved unchanged. The current explicit owner instruction
authorizes this slice after the provisional design approvals.

Reviewed accessible #77 decisions and Core/Factory continuity. PR #46 and Core
#127/#129 are open and unmerged at implementation start. Core #129's last reported
R2 failure is not repaired or accepted here. This branch starts from actual main,
imports none of their unmerged code, and does not duplicate accepted V1/registry.
Originating chats and external Work receipts are unavailable and not claimed audited.

## Contract and ownership

`StrategyDNAV2` freezes canonical bytes and links an actual accepted
`StrategyDefinition` V1 digest. V1 code, AST, schema, canonical bytes, timing,
hashes and behavior remain unchanged. The binding is a reference, **not** a V1
boolean-expression to weighted-score translation. No adapter exists. All typed
indicator references reuse the accepted registry and require explicit roles.

The envelope separately versions ScannerProfile, DecisionProfile and
MonitoringProfile. Its own strategy version must change for revisions through
`revise`; it is not a persistent global version registry. Explicit calls to the
constructor are not owner approval. `from_json` checks a separately retained
digest, not an attacker-supplied replacement trust anchor.

- ScannerProfile: explicit allowed symbol/venue lists, mandatory numeric filters,
  ranked eligible inputs, cap and deterministic symbol/venue tie break. Each
  exclusion records its reason, including missing/stale/invalid data or cap.
- DecisionProfile: separate entry and exit numeric channels. For each term,
  clamp (value - lower)/(upper - lower) into [0,1], invert for LOW, multiply by
  positive weight/sum(weights), then sum contributions. Thresholds, input
  freshness and mandatory predicates are explicit. No missing-term
  renormalization. Invalid mandatory evidence cannot pass. Reports expose every
  reading, normalized value/weight, contribution and failed mandatory condition.
  Simultaneously satisfied entry/exit is AMBIGUOUS_REJECTED; channel eligibility
  means a satisfied research condition, not permission to trade.
- MonitoringProfile: OBSERVE_ONLY. Expected features receive a value or explicit
  MISSING/STALE/LATE/DROPPED/UNVERIFIED/NOT_APPLICABLE status, even for
  scanner-excluded supplied opportunities. Monitoring is evaluated after the
  pure research decision and never contributes to ranking or score.
  In-process fixture evaluation is not a production scheduling/failure-isolation
  implementation or a claim of nonblocking operational fan-out.

Changing monitor observations under the same DNA leaves the entire core report
and its digest unchanged. Changing monitor policy requires a new full DNA
version/digest, hence new DNA-linked synthetic opportunity IDs; it preserves
the decision-policy digest and scanner/decision mathematics. A feature explicitly
used in multiple roles retains its declared decision authority in those roles:
changing that shared observation is not a monitor-only intervention.

## SF-DEC-48 B — additive comparison lineage (synthetic only)

Owner-provisionally approved 2026-10-27; implemented only for the supplied
synthetic research fixture. Existing `opportunity_id` is unchanged: it binds
the **full** `dna_digest` and is unique to the V2 strategy version. In addition,
decision and monitoring rows both expose `opportunity_family_id` calculated
from versioned `synthetic-opportunity-family-1` schema, the
`decision_policy_digest`, frozen synthetic `source_generation_id`,
`plan_id`, symbol, venue, and decision cutoff. The family ID deliberately
does not include monitoring-only policy. Changing monitoring alone preserves
the family ID if the compared decision policy and source context are unchanged,
although the per-version opportunity ID changes.

Different Scanner/Decision policies, source generations, plans, assets, venues
or decision cutoffs cannot be silently joined under a common family ID.
Unselected/scanner-excluded opportunities retain both identifiers and a monitor
row. The ID is **a comparison candidate**, not proof that all input observations
were identical, that two portfolio paths can be paired without separate
simulation, or that missing/rejected populations are interchangeable. Consumers
must verify explicit experiment/source/eligibility compatibility and preserve
unmatched observations; no arbitrary joins, synthetic-to-real normalization,
retrospective backfill or deduplication of a live event stream are authorized.
This pure function evaluates at most one supplied event per symbol+venue per
cutoff and rejects duplicate symbols within that call. The family digest is
not a trusted attestation, Core-issued operational identifier, Research Ledger
receipt, independent custodian certificate, or OOS result.

Focused regressions check cross-revision monitor-only invariance, full-version
identity change, source/policy/cutoff/asset isolation, replay determinism,
monitor join alignment and scanner-excluded denominator. All prior V1 contracts,
Core-owned authority, PAPER/OOS gates and StrategyDNA runtime prohibition
remain unchanged. Final CI/reviewer acceptance is a separate gate.

## Temporal and evidence boundary

The supplied receipt must match registered computation identity, synthetic source,
generation, finality and finite output type. Require
as_of <= observed <= available <= decision cutoff, and bounded per-input as-of
age. Future observations never expose their scalar in reports. Recent arrival
does not refresh old content. This slice intentionally accepts only completed,
supplied synthetic values; it does not implement general intrabar trading policy.

These are structural checks over fixture timestamps, **not proof** of real
point-in-time availability. No market acquisition, operational journal, receipt
ACK, historical correction, durable intent, independent anchor, holdout or
Factory EVALUATED completion is implemented. Canonical report hashes catch
changes relative to a retained digest; they are not signatures or an independent
append-only ledger. Replay here is deterministic pure fixture reevaluation,
not crash recovery or operational durability acceptance.

## Decision traceability

All source links are comments on
[Factory #77](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77).

| Decision / owner evidence | Slice disposition |
|---|---|
| [39-R](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6420531979) | Explicit three roles; no broader activation |
| [40 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6420706268) | Additive immutable V2, retained V1 hash, typed role manifests; regime policy deferred |
| [41 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6420780166) | Scanner before weighted decision; monitor has zero authority; paper A/B deferred |
| [42 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6420982423) | No alternate Core journal; durable intents/asynchronous enrichments deferred to authorized Core integration |
| [43 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6421361696) | Frozen expected monitor universe and explicit missingness for supplied opportunities; population bias/statistical analysis deferred |
| [44 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6421434911) | No promotion or holdout access; hypothesis evaluation and prospective shadow deferred |
| [45 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6421540407) | No invented PnL/portfolio; paired and full-path analyses deferred |
| [46 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6421697870) | Factory builder responsibility retained; independent Lab analysis not built |
| [47 B](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6421959597) | Owner-requested practical slice; complete Lab request/child/evidence/assessment exchange deferred |

Deferred here means outside this explicitly bounded coding task, not waived or
claimed complete. Original owner role sources #77 comments 6386117407 and
6386362811 retain their force.

## Reproduction and acceptance

```bash
python -m unittest discover -s tests -p test_sf_strategy_dna_v2.py -v
python -m research_wp_r0.strategy_dna_v2_example
```

The example reuses unchanged `examples/strategy_definition_v1.json` and supplies
three entirely synthetic assets. Expected: AAA meets entry conditions, BBB waits,
CCC is scanner-excluded but still has a monitor row. No fill or profitability.

The new exact-head workflow runs 30 focused tests and this example on Ubuntu
and Windows with Python 3.11. The existing unmodified SF-RESEARCH-INT-01 workflow
runs its 464 accepted contract regressions on both OSes with Python 3.10–3.12.
Actual CI run links, counts, durations and limitations belong in the delivery
receipt/PR; this document makes no prediction that a run passed.

Tests cover typed contracts, invalid versions/weights/fields, immutable revisions,
retained-hash tampering, V1 golden digest, deterministic replay, missing and future
data, stale content with recent arrival, mandatory predicates, ambiguity,
ranking/ties/exclusion, monitor observation/config noninterference and explicit
multiple roles. Real-market, runtime durability, Core recovery, performance,
historical, prospective, PAPER and OOS validation: **NOT TESTED**.

## Remaining gates

Independent source custody/PIT evidence, protected research anchors, authorized
historical evaluation, complete Lab interfaces, regime specialist reports,
statistical adequacy and separately approved shadow/forward/operational gates
remain future work. No changes to Core or current safety guarantees are implied.
No PR merge or Factory completion is authorized by this implementation.
