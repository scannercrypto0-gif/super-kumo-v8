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

## Attempt accounting and failure contract — durable receipt slice

Main AttemptRecorder remains unchanged. Factory-owned AttemptLedger now implements
its dictionary persist-or-raise sink using local SQLite, no operational imports.
Malformed definitions persist INVALID; prepare errors persist FAILED after PENDING;
success stays PENDING. prepare_durable_candidate adds an immutable full INPUTS
receipt before returning, retaining dataset/version/manifest/cutoff and bundle digest.
It delegates all input/PIT validation to the existing bridge unchanged. INPUTS is
not evaluation or COMPLETE. A failed INPUTS append raises with PENDING unresolved.
Explicit ABANDONED is supported; no startup silently changes lifecycle state.
COMPLETE is rejected until an actual evaluator/result contract is reconciled.

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

## Factory-owned receipt adapter v1 — consolidated order6384985545

### Typed compatibility and absent semantics

STATE_MAPPING is an in-code frozen dataclass mapping, inspected against PR46
a4c106a02c55ee012eedf4c55c1488d71d850203 trial_holdout.py. Actual legacy enum is
COMPLETE/FAILED/INELIGIBLE (not INVALID/ABANDONED/PENDING). Main INVALID has only
a non-lossless analogy to INELIGIBLE; PENDING/ABANDONED are absent there. Main
dictionary input/strategy/error payload versus typed Attempt+event_id, and frozen
family/metric/alpha/temporal-manifest fields remain explicit incompatibilities.
No legacy backend is imported or old record rewritten. Earlier reports that
described the whole journal integration as blocked are superseded ONLY for this
new narrow local receipt slice, not the full statistical TrialFamilyLedger.

### Commit, replay and input binding

AttemptLedger(existing_private_parent / filename) creates version1 SQLite receipts
table (seq,event_id,payload,chain_hash). WAL + synchronous=FULL + BEGIN IMMEDIATE
serialize appends; ACK returns (sequence,chain hash) only after COMMIT succeeds.
No UPDATE/DELETE API; this is logically append-only, NOT physically immutable
SQLite or an access-control/security boundary. No runtime operational storage import.
sqlite3 is the sole new stdlib allowance in the research static dependency guard;
all operational/third-party import bans remain. No package installation.

Event ID = SHA256(domain AQL:ATTEMPT-ID:1 + NUL + canonical family/candidate/input/
state identity). Same-ID identical bytes replay without adding rows, even after a
terminal event; changed payload rejects. One input+strategy identity per family/
candidate. Legal initial PENDING/INVALID/FAILED; PENDING can transition to FAILED
or ABANDONED, or acquire INPUTS without completing. Conflicting terminal events
reject. Existing accepted definition is PENDING, not an invented separate success.
Full canonical input bundle/digest is saved, including immutable original manifest
and instance hashes; no content_hash_v1/legacy hash contract changes or fabricated
receipt times. Identical durable prepare replays idempotently.

Chain hash = SHA256(previous digest bytes + canonical payload); first predecessor
is32zero bytes. Full chain/schema/state replay on open and each append, contiguous
sequence, bounded10000receipts/16MB payload total/2MB each,1sSQLite lock timeout.
No unbounded job loop; reaching capacity raises, does not ACK/drop/auto-prune.
Bounds are application inventory limits, not file/WAL/host resource quotas or SLAs.
Use dedicated local private directories; SQLite transactions handle cooperating
concurrent writers, no shared operational queue. New ledger file/parent symlink/
Windows reparse components rejected; observed file identity replacement rejected.

### Checkpoints and crash evidence

snapshot returns detached events plus checkpoint; caller may retain checkpoint
separately and supply expected_checkpoint on open. It must match a complete prefix;
extensions are accepted, truncation/rewrite of that prefix rejected. Missing anchored
file is rejected without recreation. SQLite quick_check, canonical payload, chain
and state verification fail closed; no torn-tail repair or automatic truncation.
Real temporary-file tests exercise committed child os._exit and uncommitted child
write os._exit, reopen/replay, physical DB truncation, corrupted payload/hash/sequence,
rollback relative to separately saved digest, duplicate/conflict, concurrent writers,
failed SQLite INSERT and input-receipt failure propagation.

The saved-checkpoint test uses a separate local fixture file: it is an independent
verification path, NOT a trusted off-device anchor service. An attacker controlling
both database and retained checkpoint can rewrite both. SQL FULL requests durability
from actual filesystem/OS; tests prove process-crash recovery on tested environments,
not hardware power-loss/directory-fsync/offsite certification. SQLite corruption may
raise DatabaseError/OSError rather than a normalized custom exception; caller must
treat every exception as no ACK. No credential/error-value dump is persisted, only
bounded error_type where main supplies it. Exact OS path replacement races against
same-account attackers, private-directory ACL provisioning, network filesystems,
hardware caches and independently authenticated anchors remain unproven/out of scope.

### Remaining honest blockers

Received-attempt receipts now have durable local replay; complete preregistered
family accounting (including candidates never submitted), metric/alpha/selection
policy and legacy checkpoint interchange are NOT delivered by this narrow adapter.
No compatible evaluated-result/backend is installed, so COMPLETE remains disabled.
Historical evaluator/real source receipt/coverage and frozen splits remain blocked;
no duplicate engine, empirical result, profit, OOS or shadow-runtime claim. Final
Holdout remains CLOSED; no G1/Scanner/cloud/production or main change.

Final evidence/counts/head/CI and local invocation details are recorded on Issue77
and existing Draft78. Prior393+36identity+32receipt tests =461 distinct final CI
cases. One final PR-triggered Factory matrix; remove duplicate push trigger to avoid
running that same matrix twice on one submitted change. No manual repeated dispatch.
