# SF-RESEARCH-INT-01: historical evaluation integration boundary

Issue #77; research only. This delivers the accepted-main **input adapter and
contracts**, not a reconciled backtest engine, durable ledger, empirical study or
promotion decision. Main baseline: `4e4c3537036bdf2b106c1a63ec65b2a9855972a7`.

## Capability and ancestry inventory

| Capability | Accepted main evidence | Gap / disposition |
|---|---|---|
| HistoricalLibrary, immutable manifests, CustodyAccessor | `historical_library.py`; #47/#50 closed after #57 merged at cf4339e83d8ce2fe30cc727b6c470f1fb0bf63bb | In-memory store; importer labels retrospective availability honestly. No independently verified real-market dataset identified in inspected repository fixtures. |
| Indicator V1/V2 | `indicator_library.py`, `indicator_library_v2.py`; #68 merged | Reuse native registry; no foreign checkout/import injection. |
| Strategy JSON, bounded candidate grid | `strategy_definition.py`; #69 merged | Definition/binding only, no AST signal execution in main. |
| Input protocol / bridge | This additive module | One complete prefix and cutoff per call, immutable envelope; no signal or return calculation. |
| Backtest / evaluation / temporal manifests | PR #46 head a4c106a02c55ee012eedf4c55c1488d71d850203, `strategy_factory.py`, `evaluation.py` | OPEN, UNMERGED, API draft=false when inspected. Reference only. |
| Family ledger, journal, fsync, replay | PR #46 inherited `durable_journal.py` and trial-family code | Not present in accepted main. Existing main AttemptRecorder is a caller-owned sink port, not that ledger. |
| Baselines, block bootstrap, multiplicity | PR #46 research ancestry | Unmerged reference; no calibrated statistical claims imported. |
| OOS / holdout / shadow | No accepted-main custody/evaluation runtime | No OOS evidence, final holdout access, shadow deployment or trading in this work. |
| Operational archive | Draft #73, Issue #71 | Outside scope; never used as research runtime/feed. |
| Architecture map | Draft #74 | Documentation proposal, not merged runtime authority. #76/OD-01 remains owner-gated. |

GitHub compare main...PR46 reports **diverged, 115 ahead / 55 behind**, common
ancestor `ed188f1902d397fe74613dd966c5a3e88b32f8c0`. PR46 base is the old #43
research line, not accepted current main. Its journal accepts typed `Attempt`
plus an `event_id`; the accepted AttemptRecorder sends event dictionaries.
These are not interchangeable interfaces. No cherry-pick, rebase, merge or
duplicate incompatible engine is performed. Proposed next reconciliation:
review the old temporal/family contracts first, specify a typed dictionary-to-
ledger adapter with idempotency and state transitions, then separately authorize
the smallest compatible engine/journal import with regression evidence.

Latest available completed delivery: #66 comment 6383116930 (post-merge native
216-test six-job acceptance). Current owner instruction: #77. Unavailable chats
and owner handoffs are not claimed reviewed. Open #73/#74/#46 were checked for
overlap; none is a merged implementation of this accepted-main adapter.

## Input boundary

`prepare_inputs` invokes accepted `bind_evaluation` and V2's V1-compatible
registry. It preserves the entire strategy, protocol, manifest, per-bar records,
bar checksums and binding receipts. The range is complete, final and confirmed;
the adapter additionally rejects **unknown recorded receipts**, receipt before
finality, stale inputs, timezone/symbol/source-label mismatch, changed reads and
synthetic data relabelled as historical. Existing historical/indicator hashes
and files are unchanged. UTC/24X7 are the only supported session semantics.

Units, listing/delisting treatment, adjustments and evidence references must be
explicit caller assertions. They are retained, **not independently verified**.
The historical-recorded path requires a source-bytes hash and non-synthetic bars;
that does not establish independent custody or prove receipt timestamps. No
network acquisition, operational queue, G1 store or cloud is consulted.

An adapter call is **one decision prefix**, not permission to use an end-of-study
cutoff for earlier trades. A future engine must bind each earlier decision to
its own observable prefix. `OfflineInputs.restore` checks bytes against a
separately retained commitment; this same-trust test is not an external anchor.
Retain interpreter/package versions alongside source SHA in the execution
evidence. Byte-identical output across platforms is not promised for arbitrary
floating-point computations; the CI matrix checks golden vectors and contracts.

## #76 reproduction and owner decision (no hash change)

Two actual imports of identical bars at different wall-clock times have equal
existing `manifest_hash` (ordered **full bar checksums**) and different
`created_at_ms` / `manifest_integrity_hash`. Both verify correctly. Replaying
the **retained original manifest** in two new processes yields identical bridge
bytes/digests. Independent re-imports intentionally do not yield the same
instance-scoped bridge receipt. These are different reproducibility questions.

The existing bar-content commitment already includes observation, ingest,
availability, source, symbol, interval and OHLCV. It is not an OHLCV-only hash,
nor does it bind all dataset metadata or attest external origin. Removing
timestamps indiscriminately would hide market chronology/PIT distinctions.

Owner options (OD-01):

* A: preserve current contracts; replay retained manifests and compare existing
  full-bar commitments diagnostically. This delivery uses A, without claiming
  an approved cross-import public identity.
* B (owner-approved additive implementation): add a versioned content identity
  binding ordered full bar checksums plus semantic dataset metadata, excluding
  only manifest creation time and self-hash; keep instance identity, temporal
  provenance and independently retained anchor as separate commitments.
* C: OHLCV-only analytical fingerprint, explicitly unsuitable for custody/PIT.

The new public `content_hash`, field list/versioning and downstream receipt
migration are **AUTHORIZED by #76 comment6383377178 / #77 comment6383377744**. Existing hashes are not redefined.

## Simulator requirements: specified, not implemented

Protocol freezes next eligible open strictly after the decision; entry TTL,
holding bounds, stop and target fractions remain in Strategy JSON. Both-side
notional fees and slippage must be explicit. Future engine must reject or retain
unresolved same-bar stop/target ambiguity, gaps, delisting and unknown execution;
never invent a fill or score unknown loss as zero. Expiry is NO_FILL, no signal
retains a zero-exposure opportunity. Costs change the input commitment, not an
invented P&L. Stops/targets across gaps require an explicit engine review.

No timing/stop/TTL/P&L engine tests are claimed: engine integration is blocked by
unreconciled PR46 ancestry. Full-population paired comparisons, regimes, sample
thresholds, bootstrap dependence, multiplicity and purged/embargoed OOS require
real admissible data and frozen split provenance first. No final holdout opens.

## Attempt accounting and failure contract

`prepare_candidate` reuses main's AttemptRecorder: malformed definitions record
INVALID; input/binding errors record FAILED after PENDING; sink errors propagate.
Successful preparation remains PENDING, never COMPLETE. Caller must explicitly
mark ABANDONED if it stops. Fatal process interruption can leave PENDING and
requires future ledger reconciliation, never inferred success.

The memory test sink deliberately permits duplicate attempts. The tests expose
this limitation rather than invent exactly-once persistence. Immutable input
receipts and persist-or-raise port behavior are tested; durable crash recovery,
checkpoint replay, uniqueness, trial-family reconciliation, journal fsync and
Windows power-loss safety are **NOT IMPLEMENTED/NOT VERIFIED** here. Actual
process-crash/restart journal testing is gated on that separately reconciled
durable implementation. No in-memory sink is offered as fsync evidence.

## Local/CI validation

From the dedicated branch worktree with a verified Python interpreter:

```text
python -B research_wp_r0/_dep_guard.py research_wp_r0/indicator_library.py research_wp_r0/indicator_library_v2.py research_wp_r0/strategy_definition.py research_wp_r0/historical_evaluation_bridge.py
python -B -m pytest -p no:cacheprovider tests/test_sf_data_01.py tests/test_sf_ind_01.py tests/test_sf_dep_guard.py tests/test_sf_ind_02.py tests/test_sf_strat_01.py integration_tests/test_sf_strat_ind02.py tests/test_sf_research_int_01.py -v --tb=short --junitxml=sf-research-int-01.xml
```

The workflow runs that exact native checkout on Ubuntu/Windows Python 3.10/3.11/
3.12 and retains JUnit plus environment/source evidence. All fixtures remain
synthetic software tests. There is no independently verified market performance,
profitability, forward result or accepted durable research runtime. Issue #77
remains open for owner review and gated follow-up; this PR must not auto-close it.

Initial local expanded run (before the final cross-process re-import test):
Python 3.14.3, pytest 9.1.1, pytest-timeout 2.4.0: **390 passed, 2 failed / 392**
in 6.77s. The two existing `test_sf_data_01.py` failures are
`TestImportConfinement::test_symlink_rejected` and
`TestFix01AcceptanceGate::test_fix01_all_gates`, both WinError 1314 while creating
a symlink before importer assertions. The account lacks symlink privilege.
No system settings or legacy tests were changed; failures are not hidden as
skips. Final workflow expects **393** tests: 141 historical + 216 accepted core
+ 36 new contracts, with zero failures/errors/skips on each CI job. Local final
evidence and exact tested head are recorded in the Issue #77 RESULT.

## OD-01B continuation: implemented additive content identity

`research_wp_r0.content_identity.content_hash_v1(manifest, bars, *, price_unit,
volume_unit, session, normalization, adjustment)` accepts a complete strictly
ordered, unique, manifest-bound dataset. It verifies stored manifest provenance,
manifest integrity, every bar checksum, count/range and the ordered legacy hash.
It rejects partial prefixes; the existing one-cutoff bridge may legitimately use
a partial prefix and is therefore not silently assigned a whole-dataset identity.
Callers retain this new sidecar commitment separately alongside the immutable
original manifest. Old manifests are not rewritten or given unverifiable hashes.

Domain is ASCII `AQL:CONTENT_HASH_V1` followed by NUL, then canonical ASCII JSON.
Scalar encoding is tagged: null, bool, int decimal string, float64 Python hex,
string; arrays ordered, object keys Unicode-codepoint sorted, ensure_ascii=True,
compact separators. Nonfinite floats/unsupported values fail. Int/float and signed
zero remain distinct. Existing bar checksums are retained too, preserving legacy
numeric representation distinctions; there is no rounding or Unicode normalization.
Version changes require a new hash contract, never silent reinterpretation.

All HistoricalBar fields including finality, source/source_label, receipt (null
when unknown), availability_kind, observation cutoff and checksum are committed.
All persisted manifest fields except dataset_id/version/created_at_ms,
parent_version/lineage_reason/manifest_integrity_hash are committed: exchange,
market, symbol/interval/timezone/source, raw-file hash or null, coverage/gaps,
quality counts and existing full-bar hash remain included. Caller units/session/
normalization/adjustment are required, retained assertions, not authenticated facts.
Different raw source bytes are intentionally distinct even if decoded OHLCV agrees.
Unknown receipt is hashable as UNKNOWN, never promoted to confirmed eligibility.
The function computes on demand once per dataset adoption; no per-bar runtime or
automatic recomputation/caching/migration is introduced. Existing input-1 schema,
strategy bindings, legacy hash algorithms and stored records remain unchanged.

## Concrete staged Research Ledger reconciliation (BLOCKED durable acceptance)

Read-only comparison: main AttemptRecorder sends dictionaries with family_id,
candidate_id, input_digest/strategy_digest, PENDING/INVALID/FAILED/ABANDONED/COMPLETE;
unmerged PR46 a4c106a's DurableResearchJournal accepts typed Attempt plus keyword
event_id, and replays FrozenSearchFamily/TrialFamilyLedger with protocol_digest,
temporal_manifest_digest, dataset_version, metric/direction, alpha, declared_at.
That journal imports unmerged trial_holdout. Its on-disk family/attempt schema is
not main's port. A dictionary cast would lose family/temporal/error semantics.
No safe durable adapter or new journal is claimed by this PR.

Executable next stage, before empirical work:
1. Inventory and freeze legacy family/attempt/checkpoint formats at PR46 SHA;
   use golden retained journals in disposable directories only, never old records.
2. Reconcile a versioned research-only family declaration (complete candidate
   universe, metric, alpha, protocol/split/data commitments) with accepted main.
   Review schema/reader dependencies before selecting the smallest legacy modules.
3. Map deterministic event ID = domain + family + candidate + input commitment +
   lifecycle transition + result/error commitment. Same ID+same bytes is replay;
   same ID+different bytes is corruption. Require unique family/candidate attempt
   identity, legal PENDING→terminal transitions; rejected definitions still count.
4. Persist or raise before acknowledgement; preserve INVALID and failure details.
   COMPLETE requires actual evaluated result and binding, not prepared inputs.
   Restart leaves PENDING unresolved until explicit ABANDONED/reconciliation;
   never infer COMPLETE or silently lose the trial-family denominator.
5. Test process kill at each write/fsync/ACK/checkpoint boundary, torn-tail reject,
   full-chain/state replay, family mismatch, duplicate/conflicting IDs and restored
   checkpoints relative to a separately retained trusted commitment. Real Windows
   locking/path-replacement tests are required; file fsync is not power-loss or
   independently trusted external-anchor certification.

Historical engine remains BLOCKED on that reconciliation plus credible real
source/receipt/coverage and frozen splits. No compatible accepted-main simulator
exists; implementing another independent engine here would duplicate unmerged46.
The explicit execution contract above remains the safe boundary. Final Holdout
stays CLOSED, shadow future-only, no cloud or operational data path is touched.
