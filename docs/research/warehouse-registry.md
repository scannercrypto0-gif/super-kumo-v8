# Warehouse Registry Option C — scoped recovery handoff

## Authority and continuity

ATLAS-WH-REGISTRY-RECOVERY-001; owner approved implementation and focused tests
on existing Draft #330 on 2026-11-21 after the prepared-only brief was reviewed.
PM OS v1 (#205/6721828613), registry proposal #205/7058793440, canonical #202 and
G0-GOV-01 apply. No merge, G0 promotion or scientific acceptance is included.

Reuse baseline `30854a2b30d0b4ae62914b6a58e1c6065a501387`: exact September
correction, guarded Windows operator, immutable August baseline and original-input
Linux diagnostic proof. Baseline warehouse CI run 44877584228 passed 59 tests on
each OS; unchanged source-validator tests and data acquisition are not repeated
as a new diagnostic. The modified import/read path needs incremental regression
CI. Dependencies #271/#321 (Windows/daily), #312/#309 (closed-bar research) remain
separate existing interfaces; no capture, scheduling or strategy replacement.
Independent audit #134/7058424736 accepted only the older bounded engineering
scope, not this registry delta or owner E: execution.

## Commit, read and recovery contract

`catalog/<ZIP SHA>.json` sealed source receipts and retained ZIP/CHECKSUM bytes
remain authoritative. Existing per-day SQLite publication precedes that source
commit. Registry reconciliation verifies the full source lineage and every
physical row before appending anything. A partial archive without its receipt,
missing shard, corrupt source, conflicting row or unapproved derivation closes
the research read gate; it cannot become an eligible snapshot.

`catalog/registry/event-N.json` is a create-only sequence of payload identities,
previous hashes and event hashes. Each event has a create-only checkpoint.
Types cover committed sources, approved corrections, repair/recovery and sealed
rejection/quarantine receipts. Replaying identical accepted evidence does not
append an import event. Rejection hashes identify attempted bytes, and do **not**
attest that rejected original bytes were retained. Successful gap repair and
lost-shard recovery have explicit before/after facts. Observation times come from
receipts; legacy quarantine receipts without times have a null timestamp, never
an invented historical time.

On interruption after source commit, writer-only `rebuild_registry()` resumes
the missing event suffix. An event published before its final checkpoint can
recover that last checkpoint. Readers never reconcile or repair. A deleted
event with a surviving checkpoint, broken chain, duplicate identity, missing
lineage or corrupt existing snapshot rejects. Source replay repairs warehouse
data first when required, then reconciliation can run. Files are never edited
to disguise a hash failure. A coordinated administrator rewrite/deletion of
all evidence and anchors is outside this local hash-chain threat model; there
is no independent origin/custody attestation.

Snapshots are immutable, content-addressed, versioned canonical JSON. Rebuild
uses the existing event ordering, source facts, verified physical coverage,
gap/boundary lists, conflict receipts, data-file sizes and projected availability.
It has an as-of observation and event watermark. Absolute root, wall clock and
registry/operational-receipt sizes are excluded from its identity; otherwise a
snapshot would change its own digest. `report.stored_bytes` still includes **all**
managed bytes under the unchanged 150GB cap / 50GB reserve. Snapshot physical
byte totals cover raw/bar/quarantine files only and are labeled accordingly.
This is one existing file-backed warehouse, without a new database or service.
Verification retains at most two native archives plus a daily comparison map;
source/event metadata grows with the retained warehouse evidence. Rebuilds
verify retained history and may take time on large stores; no continuous task
or automatic source acquisition is introduced.

`report()` returns physical inventory plus `registry`. Under the existing writer
lock it reconciles completed evidence; outside it, pending/corrupt state rejects.
`query(..., include_registry=True)` returns bars, requested window, cutoff and
the exact snapshot/watermark. Existing list-return callers remain compatible,
but also pass the registry eligibility gate. The registry is verified before
and after a query and a changed digest aborts the read. The HistoricalLibrary
adapter binds the snapshot digest and watermark into its existing manifest
source hash. Coverage projections are computed on demand, never represented as
physical higher-timeframe files. Every eligible read remains
RETROSPECTIVE_NON_PIT; FORWARD_UNQUALIFIED, REAL_PIT_OOS_BLOCKED and trading NONE
are explicit. Native Core245/253/Scanner-E receipts are still separate.

## September and one guarded local handoff

Reuse [the exact transform and pins](september-derived-admission.md). The only
change is line 8160 / field 6: `1504713600000` → `1504713599999`, policy
`AQL-2017-09-CLOSE-8160-v1`. No publisher bytes or generic validator are changed.
The 420-minute interval `[1504713600000,1504738800000)` stays OPEN. Expected
September acceptance is 42,780 rows; with August alone the total is 64,140.
August's 21,360 rows and fifteen owner-pinned shard hashes must match before
and after. The registry verifies the original-to-derived lineage again.

After the final exact-SHA delivery and only on the authorized owner host, use
the **existing** `ATLAS-WAREHOUSE-SEPTEMBER-RECOVERY.ps1` in
`ApplyApprovedCorrection` mode with `-ExpectedCommit` equal to that full SHA.
The delivery comment supplies the complete command. It reads already-retained
source files, checks the warehouse policy and all August pins, admits the one
approved derivative, rebuilds the registry and emits the actual receipt. It
does not obtain new data or change the daily task/WS. Do not invoke Diagnose or
full backfill again. Existing checks fail closed if required files, free space,
permissions or pins are absent.

No new E: execution occurred in this implementation package. Host receipt
#330/7058739302 remains **OWNER_REPORTED_LOCAL**: August 21,360; September 0 at
the then-current failure; daily task Ready / result 0; finite action NOT_PROVEN;
original daily-output directory not inspected. This is reused, not re-probed.
Unavailable private E: files and cross-chat conversations are **NOT_ACCESSED**.
The isolated Linux September proof is **ORIGINAL_E2E_RUN** only for that earlier
diagnostic store, never Windows registry operational acceptance.

## Evidence, blockers and rollback

New tests are **SYNTHETIC_TESTED**, not original publisher attestation. They
cover deterministic relocation/rebuild, independent-process read, replay,
source/event/snapshot tampering, missing lineage, orphan shard, interrupted
event/checkpoint/snapshot publication, rejection, gap repair and recovery.
The existing generated September admission test additionally verifies registry
correction lineage, policy, count and the OPEN gap while preserving August.
Cross-platform exact-head CI and the scoped Audit request are in the delivery
comment; only an actual independent Audit response can earn AUDIT_ACCEPTED.

Remaining blockers: no newly evidenced owner E: September+registry receipt;
no independent Audit acceptance of this delta. Deferred: native Scanner-E
original custody, daily-task finite-action verification/activation, live/PIT,
trading and G0 decisions. No claim closes the stage or advances these authorities.

Rollback: leave task and WS unchanged. Before owner execution, pin/retain the
existing checkout and receipts. A failed import can leave committed daily shards
without its final source receipt: reads stay blocked until replay of the exact
retained source completes. Do not delete originals, events, receipts or shards.
For a code regression, stop invoking the candidate, preserve the warehouse and
use an audited follow-up fix; blindly running an older reader would bypass the
new provenance gate. There is no automatic destructive data rollback or source
mutation. Keep #330 Draft; owner closure and any merge require separate decisions.
