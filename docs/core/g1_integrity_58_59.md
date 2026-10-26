# CORE-G1-INTEGRITY-58-59 — bounded implementation proposal

Project: `AQL-CRYPTO-RESEARCH-001`. Owner implementation instruction in the
current Work conversation; canonical provisional decisions:
[CORE-ARCH-58/59](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/92#issuecomment-6414914835),
[Factory synchronization](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/77#issuecomment-6414917567),
[source audit](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/92#issuecomment-6414673983).
Draft proposal only; no merge, deployment, final G0, OOS, PAPER or live activation.

## Continuity / actual source

The latest verified **Core delivery** before this instruction is the read-only
audit linked above (comment `6414673983`, acknowledged on Factory #77 comment
`6414682823`). The current directly received owner instruction authorizes these
two fixes; earlier design-only comments are not reused as execution authority.
The latest accessible implemented **Factory** receipt is #125 delivery
`6414879502`, later review `6415021583` and owner-authorized merge record
`6415095046`. The global latest external Work prompt/run/receipt and inaccessible
chats remain UNVERIFIED. Review is bounded to the visible instruction and
accessible #92/#77/PR records, including page2 of #77 and its later SF-DEC-22/23
read-only proposals/correction. No exhaustive unseen-history claim.

Initial main was `b2b0490403d68c590b23e57410b8b6daa90e9a85`. It advanced during
execution to `10924f0f463b28559711f6384c87f308ee67d335` through #125. Actual compare
contains four additive Factory files only; Core sources/tests used here are
unchanged. This proposal is based on that newer main. #124 and #125 are now
merged synthetic-only; #93/#115/#118/#119 remain separate, unmerged Drafts.
#119 still depends on #118. None is imported, rebased or modified here.

## 58 — versioned observation of successful data COMMIT

`MarketBar` fields, `to_dict`, checksum, identity and historical `committed_at`
bytes/meaning are unchanged. That legacy marker is captured before the commit
attempt and **must not be called completion or recipient-availability proof**.
The old collector/pipeline latency field remains explicitly legacy. Separate
Core-only collector/pipeline fields report the new observation without changing
the historical metric's meaning.

Three additive metadata tables live in the existing Core SQLite DB; no new
service, broker, storage backend or Factory table is introduced:

1. `g1_record_contracts`: version1 marker written in the **same transaction** as
   a new journal bar. Existing valid old payloads are not rewritten/upgraded.
2. `g1_commit_receipts`: immutable-within-API version1 observation for either
   a data transaction (`BAR`) or audit transaction (`AUDIT`).
3. `g1_integrity_events`: append-only conflict/correction evidence, described below.

Order:

1. Validate canonical comparison material; begin the original SQLite FULL/WAL
   data transaction, insert the unchanged payload and new local version marker.
2. Await successful return of **data COMMIT**.
3. Read local UTC wall clock as `commit_return_observed_at_ms`; if it predates
   the attempt or supplied receipt, fail timing qualification rather than clamp.
4. Persist that observation in a **second** FULL transaction. Normal `commit`
   success returns after both transactions. The timestamp observes the first
   COMMIT's return, not the second transaction's completion.

`DurableJournal.commit_receipt(key)` distinguishes:

| Record contract | Receipt version/status | Interpretation |
|---|---|---|
| absent | 0 / NO_RECORD | No retained bar, no completion evidence |
| 0 (legacy) | 0 / LEGACY_COMPLETION_UNVERIFIED | Original legacy payload/time retained; no invented completion |
| 1 | 0 / V1_COMPLETION_UNCONFIRMED | New data may be durable, but receipt was not established |
| 1 | 1 / SQLITE_COMMIT_RETURN_OBSERVED | Observed successful data-COMMIT return, with matching content digest |

Restart/identical retry does **not** backfill an earlier completion timestamp.
A crash between the transactions can leave data/version marker without a
receipt. Receipt failure raises; no timing-qualified success is fabricated.
A duplicate does not change the original timestamp/provenance. A receipt also
does not override quarantine or imply data quality, strategy freshness or trading
eligibility. Unknown receipt versions/content inconsistencies fail closed.

This is millisecond local **software observation**, not measurement of a device
fsync boundary, independently authenticated time/custody, OS/controller cache
behavior or survival of physical power loss. Wall-clock resolution/steps still
limit latency interpretation. Additional receipt persistence has I/O cost;
no performance/capacity guarantee is made.

## 59 — canonical duplicate comparison and persistent quarantine

Identity remains `symbol:interval:bar_open`. Version1 comparison material contains
identity, close time, OHLCV and finality; numeric candle facts use finite float
normalization (including equal numeric int/float and zero representations).
Transport `source`, receipt time, legacy commit time, checksum and pipeline state
are **separate provenance**, not different candle facts. Therefore identical
WS/REST observations are matching retries while original provenance remains
unchanged. This is a Core-local duplicate comparator, **not** Factory's public
provenance-aware dataset `content_hash_v1` or a claim that their PIT provenance is
interchangeable. Nonfinite new facts fail before insertion; invalid legacy
records are not silently rewritten.

Journal/store use BEGIN IMMEDIATE to serialize compare-and-insert. An identical
non-quarantined duplicate is a no-op. A different canonical payload commits an
audit event **before** raising `ContentConflictError`; no original bar is changed.
The event includes both original/incoming records and canonical facts, source,
incoming receipt, first detection, deterministic conflict ID, reason and
`decision_eligible=false`. API/SQLite triggers prevent UPDATE/DELETE of audit
records/receipts/contract markers; this is logical local immutability, not a
hostile-admin or fully rewritten-DB authentication boundary.

Every key with unresolved integrity evidence is quarantined across restart:

- `require_eligible(key)` raises; no owner-resolution or automatic clear API.
- Default journal replay excludes that key; explicit
  `include_quarantined=True` is **forensic original-record access only**.
  Omitted keys are exposed by `quarantined_keys` and scoped health errors, never
  a claim that the remaining history is complete.
- `mark_persisted` checks quarantine in its ACK transaction. Matching data
  persistence does not authorize ACK of a now-conflicted key.
- Collector, consumer, startup reconcile and gap recovery mirror observed
  conflicts to journal/store, refuse ACK, surface errors and continue unaffected
  keys/streams. Startup validates existing store **content**, not presence alone.
- Gap recovery's additive `include_existing=True` option lets the pipeline
  compare fetched already-stored bars; standalone default/report coverage stays
  compatible. No extra provider request is introduced.
- The sandbox replicator checks eligibility before delivery and again before
  advancing its independent cursor. Archive source reads reject quarantined
  records before new segment adoption/watermark advancement. Neither path's
  external schema/checksum changes; no real cloud or archive export is activated.
- Affected stream health reports UNHEALTHY/integrity failure. Other stream
  snapshots and valid records continue. Previously valid historical ACKs/exports
  are not retroactively rewritten or claimed to certify current eligibility.

`record_correction(original, corrected, reason=...)` retains a **new**
CORRECTION_PROPOSAL audit event referencing the actual preserved original,
requiring new arrival/source evidence and a post-audit-COMMIT availability
observation. It never overwrites a candle, backdates a decision, clears
quarantine or grants the proposed value decision eligibility. Audit availability
is distinct from strategy availability. Selecting/resolving a correction remains
an explicit owner-reviewed future policy, not an invented rule in these fixes.

## Existing paths preserved / no cross-track contract change

G1 WAL/FULL, WritePriority, BackgroundLane, bounded JournalConsumer, REST budget,
gap/finality semantics and stable IDs remain. No Scanner/secretary/trader/Execution
Manager, G2 PR integration, new external provider, main write or Factory edit.
`MarketBar`/archive envelope/Factory plan, AttemptLedger and research evidence
formats remain unchanged; legacy archive `fsync_completed_ms` is still unknown,
not automatically populated from this receipt. A future shared receipt schema
or consumer-policy contract requires separate owner/Core–Factory review.

Strict integrity guarantees require the updated cooperating writers/read APIs;
an old writer/raw SQL reader ignoring these gates is not an approved new decision
path. Before any deployment, exclude old writers and obtain separate operating
authority. If storage prevents persisting conflict evidence, the operation raises
and grants no ACK; it cannot promise a durable diagnostic without writable storage.
No automatic lock deletion, repair, eviction or restart orchestration is added.

## Acceptance and test routing

`tests/test_g1_integrity_58_59.py` has 21 focused cases (including parametrization):
success/failure of each commit phase, real child exits after data/before receipt
and after receipt, legacy migration, clock order/rollback, matching/cross-source
retries, conflicts/concurrent inserts, original/evidence preservation, restart,
quarantine, independent progress, collector/recovery/ACK/health, correction
provenance, remote-cursor and archive guards. No physical power-loss claim.

Existing six-file G1 and 78-case archive workflows retain their regressions.
The new focused Windows/Ubuntu job runs **only** the new 21 cases, on native PR
HEAD; it does not duplicate G1/archive suites. Modified existing test definitions
only clarify the legacy marker assertion, handle earlier invalid-data/timing
rejection, and accept the optional recovery flag in synthetic adapters. No test
is skipped or relaxed to hide a conflict, and no timeout/throughput limit changes.

Local first combined run: **252 passed / 2 skipped / 2 failed, 254.44s**. Failures:
old synthetic REST stub signature and isolated-child missing websocket dependency.
They were corrected without disabling tests: mock accepts the validation option,
and a disposable venv supplies the installed dependency to `python -I` children.
Targeted rerun: **29 passed / 112 deselected / 2.40s**; final focused run after
the version-marker addition: **21 passed / 2.10s**. CI must establish final exact
HEAD regressions; do not infer a full local all-green rerun or physical durability.
Actual published head, CI results, final source checks and measurements are linked
in the Draft PR body and #92 delivery receipt, not predicted here.

Remaining risks: two-transaction crash window is explicit, extra FULL I/O,
legacy/unconfirmed timing, pending manual correction review, local-only audit
immutability, shared-interface adoption and real operating capacity/security
acceptance. All existing provisional governance/activation restrictions remain.
## PR #127 bounded follow-up review (2026-10-26)

Authority: the owner's explicit instruction to review/fix this same Draft PR,
not a new implementation mandate for CORE-ARCH-60/61. Starting delivery is
`19756ad377170e417faed8381815349e282c4339`; observed main is
`10924f0f463b28559711f6384c87f308ee67d335`. Both refs were refreshed before
editing. Main's native G1 run 40316583530 was successful; prior PR runs
40320567813/40320567774/40320567896 were successful. These are baseline
observations, not evidence for the follow-up commit.

Reviewed PR description/comments (no inline review threads), Core #92 decisions
58/59 and 60/61 and delivery 6415859592, and Factory #77 through synchronization
6415886277. Factory #126's later `c3a50819...` correction is separate, unmerged
work. No unavailable Work conversation was reviewed; PR #127 is the latest
confirmed code delivery for this task, not proof that its original Work chat
completed. No AGENTS.md was present in this checkout.

### Existing G1 read/delivery inventory

“Denied” below means known quarantine at the corresponding check. Separate
SQLite files and a remote sink do not form one atomic transaction. Already
returned bytes/previous ACKs are not retroactively revoked; this patch does not
claim linearizable global eligibility, hardware durability or independent custody.

| Existing path | Can inspect isolated data? | Operational delivery / ACK | Unrelated progress / disposition |
|---|---|---|---|
| `DurableJournal.replay` | Default excludes; explicit `include_quarantined=True` retains forensic access | Forensic flag is never permission; checksum verified, no ACK | Other keys/streams returned; pre-delivery gate also needed for a fetched batch |
| `JournalConsumer.drain_once` | Fetched batch may predate quarantine | Added check immediately before store upsert; store compare/check and journal ACK gate retained | Conflict mirrored; next healthy key processed; regression covers quarantine after replay |
| `startup_reconcile` | Same batch window | Added pre-upsert check; matching existing contents still verified before ACK | Re-read quarantine after loop; conflict no longer masks gap boundaries; healthy keys continue |
| `OperationalStore.upsert/bulk_upsert` | Private `_original_bar` intentionally retains original for comparison/audit | Transactional compare and eligibility check deny conflict, no replacement; bulk records error | Other rows continue; no public bar-payload reader found in this G1 store |
| Store `get_stored_keys/get_range`; journal `get_committed_range` | Formerly included retained quarantined rows as coverage | Fixed eligible metadata queries; cannot use isolated bounds as healthy freshness/coverage | Same-stream healthy rows and other streams preserved |
| Store `count`, journal `count_by_state`, `commit_receipt`, conflict evidence/private original reads | Physical/audit metadata and originals remain inspectable | No operational bar delivery or new ACK; counts/receipt are not eligibility proof | Intentionally not filtered; retained evidence and legacy receipt contract unchanged |
| Collector synchronous store route | Commit detects quarantine before store; store compares existing content | Conflict mirrors to both DBs; no conflict ACK; existing focused collector test | Other incoming keys continue; background route uses JournalConsumer |
| `_run_gap_recovery` / `recover_gap` | REST rows are candidates; `include_existing=True` compares even existing keys | Journal commit then store compare then gated ACK; conflict errors are explicit | Per-key continuation; no additional provider requests or new transport |
| `SandboxReplicator.deliver_once` | Materializes batch internally; pre/post-remote quarantine checks | Known conflict denied before sink and before cursor advance; remote side effects cannot be rolled back | **Ordered prefix stops at conflict**; independent local consumer/ingest proceeds. See owner gate below |
| `LocalArchive.source_row`, drain/adopt | Missing row returns None at both probes; known isolated row raises | Added second missing-row guard and whole-batch eligibility/content recheck immediately before watermark update | **Atomic archive batch/prefix stops**; other independent lanes continue; sealed originals unchanged |
| Backup create/verify/restore | Copies source forensic bytes to incomplete temporary generation | Full source/segment validation calls guarded source_row; isolated source cannot become verified backup/restore | Whole-generation rejection is intentional; no partial-success/custody claim |
| Offline archive snapshot | Sealed retrospective bytes only, not current live eligibility | Full backup verification before and after query; guarded source denies known isolated record in that generation | Whole-generation verification rejects even unselected defects; no Core operational ACK |
| `verify_segment` / envelope parsing | Pure hash/schema verification can inspect a sealed old record | No source/quarantine authority or operational ACK; adopt/backup/offline wrappers supply source checks | Do not treat a valid hash or old backup as current eligibility |
| Health snapshot / archive health | Audit counts and conflict inventory visible | Scoped quarantine/read error denies healthy/integrity claim | Healthy unrelated symbol remains independently reportable |

Repository search covered all `journal_entries`/`market_bars` SQL and callers of
replay, range/key readers, source_row and segment verification under `src/aql`.
PositionEvent/G2 journals have different identities and no MarketBar delivery
path; open PRs #93/#115/#118/#119 were neither imported nor modified. Factory
historical library is not a Core operational reader and remains out of scope.

### Owner decision boundary — BLOCKED — OWNER DECISION REQUIRED

The existing Sandbox cursor acknowledges a contiguous sequence prefix; the
archive catalog and backup verifier likewise require complete prefix/segment
reconciliation. A quarantined key therefore stalls subsequent healthy keys in
that **same ordered consumer**, although ingest and independent local consumers
continue. Advancing past it would falsely ACK it, and dropping it or silently
filtering segments would change archive coverage/restore contracts. No such
change was made.

If acceptance requires unrelated records to continue **within these same ordered
consumers**, authorize a separate bounded design for durable per-record withheld
dispositions/independent progress and matching archive/restore semantics. Until
then that requirement is BLOCKED, rather than claimed satisfied by green tests.
This does not authorize the full 60 eligibility gate or 61 shared WebSocket.

Existing provenance, legacy committed_at, MarketBar serialization/checksum,
stable identity, preserve-original policy and Core/Factory evidence separation
are unchanged. Cross-DB quarantine propagation can fail on unavailable storage;
failures do not grant ACK. Old/mixed writers and direct SQL consumers are not
approved operational paths. A sealed snapshot cannot learn about conflicts
detected later in its live source; it remains retrospective, never current
decision permission.

### Focused follow-up acceptance

Local Python 3.12 run: **31 passed**, no failures/skips (4.05s). Ten added cases
(including parameterized scenarios) cover missing/valid/isolated source rows,
row disappearance between probes, eligible metadata with physical retention,
quarantine after replay for consumer/startup, newly isolated gap boundary,
Sandbox preexisting conflict/no sink call/no cursor ACK plus independent local
progress, archive conflict after rename and immediately before ACK, and backup
non-anchor conflict refusal. The original 21 cases remain enabled. Exact final
remote SHA and Ubuntu/Windows CI results are recorded on PR #127 after upload;
this pre-upload document does not predeclare them successful.
