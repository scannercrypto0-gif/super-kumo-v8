# CORE-128: D1-C implementation checkpoint — BLOCKED

Project AQL-CRYPTO-RESEARCH-001. Current direct owner instruction authorizes
bounded Core synthetic/local implementation, tests, an independent Draft and
independent review; no merge, real migration, hosted targets, OOS/PAPER/LIVE or G0.

## Continuity and scope

DESIGN-2 was read completely (300 lines, Library libfile_9abeea1b0b908191a80c06d0dc070305).
Its T01–T32 were proposals, not executed evidence. Last actual Core code delivery:
#127 comment6416097799, SHA542578ec8b81a0b933811d878e896d23daac7ac4. Last design
handoff: DESIGN-2 followed by the owner's current execution order. #128 is the
execution ledger; #92/#77 reviewed through6417014554/6417015976. Inaccessible
external Work/chat history is not claimed reviewed. #127 and #126 remain
OPEN/DRAFT/unmerged; #126 is ff817c0581d57424592308336c29962875e8b101. main remains
10924f0f463b28559711f6384c87f308ee67d335. Complete open PR inventory inspected;
G2 and backup Drafts not imported.

This branch is stacked on exact #127 SHA542578ec; parent PR unchanged. Only new
synthetic source fixtures may opt in. Sources are frozen finite inventories;
legacy append, ACK, replay, sandbox delivery and source_row export refuse an
activated source. Legacy sources without core128 metadata retain old behavior.
No MarketBar/legacy checksum or committed_at change. Existing source instance,
full row bytes and explicit local configuration are bound by a caller-retained
anchor. This capsule is NOT a migration of all legacy records to CORE-ARCH-68.

Allowlist used: src/aql/delivery/{__init__,authority}.py; narrow guards/hooks in
g1_integrity.py, journal/durable_journal.py, archive/local.py,
storage/sandbox_store.py; tests/test_core_arch_63_66.py; this doc;
.github/workflows/core-63-66.yml. No Factory paths or remote schemas modified.

## What is implemented, and what is not

The local synthetic adapter stages original payloads privately, fences publishers
using monotonic consumer epochs, records publication and quarantine under the
same source SQLite BEGIN IMMEDIATE transaction, and rechecks quarantine on every
protected read. Read authorization linearizes inside that transaction; previously
returned bytes cannot be revoked. No network I/O or external target publication
occurs. Independent consumers have separate D/W/V/S projections, even though
source restriction is shared. Durable events rebuild the projection. S covers
actual frozen source rows, not all integer IDs and not the legacy delivery cursor.
Stage/private or published-but-unsettled is not a delivered ACK.

A durable denial intent precedes the potentially failing conflict evidence
transaction. An unresolved intent blocks reads/reopen, but is never fabricated
withheld evidence. A process fault latch is set before trying the persistent fault
marker. No claim can persist diagnostics on wholly unwritable media. Reopen
requires a separately retained exact progress head as well as the source anchor;
missing/mismatched progress refuses startup. This is fixture-level reconciliation,
NOT an independently anchored real antirollback service. The supplied checkpoint
must be retained outside the snapshot being tested. Passing an old caller-supplied
checkpoint does not prove latest progress; no deployed trust authority is built.

Operational clients should receive only ProtectedReader, not Authority maintenance
objects or DB/filesystem credentials. Public SQL context managers were removed.
Python introspection/host-admin adversaries are not an isolation boundary this
module can enforce. No real ACL/hostile-client security certification is claimed.

**The mandatory D1 gate remains FAILED.** A separate OperationalStore can detect
and persist a same-key conflict without binding it to this source authority.
Protected journal publication then remains readable. This is independent finding
R2, retained as a real failing acceptance test without skip, xfail, weakened
assertion, or continue-on-error. Binding all configured store/recovery/collector
writers to one source authority and preventing unbound writers is not implemented.
There is no safe inference that equal symbol/interval/time means two arbitrary DBs
share ownership. A source/target binding and activation contract must be made
concrete before enabling this adapter in any pipeline. No existing pipeline is
activated by this Draft.

Accordingly **partial archive v2, Coverage Manifest, backup/restore v2 and real
complete-inventory verification were NOT implemented after this first gate failed.**
D4-C expected-inventory authority is still a proposal in #128. No COMPLETE output
is emitted by this implementation. Existing v1 schemas/verifiers are unchanged;
only v1 API attempts to consume a v2-activated source fail closed. No fallback to
legacy consumers on an activated source is allowed.

## Independent review findings and repair status

Independent reviewer separately inspected commit773c0cc7777f2ec9cab35a95b0ec80fabd7ad9c6
and executed the eight-case suite (8 PASS/1.36s), then reproduced five defects.
The first author run was 8 PASS/1.01s: those green fixtures did NOT establish D1.

| Finding | Independent reproduction | Repair/disposition |
|---|---|---|
| R1 | Audit insert failure before hook, or BLOCK append + fault-file failure, allowed published read | Pre-evidence durable denial intent; process fault latch; pending proof blocks read/reopen; two new adversarial tests. Final independent re-review required. |
| R2 | Independent OperationalStore quarantines, authority still reads the key | **OPEN/BLOCKING**; acceptance test must FAIL; no full G1 integration claim. |
| R3 | Public connection()/transaction() returned SQL access to private stages | Removed public contexts; separate reader-only facade; source/API introspection scope explicit. Final re-review required. |
| R4 | Correctly hashed WITHHELD used B evidence for A and advanced S; invalid INIT/order accepted | Replay now checks genesis, source-seq/key/evidence bindings, stage identity and publication/ACK conflict ordering; forgery tests. Final re-review required. |
| R5 | Restore after epoch1 and reopen using source-only anchor resurrected old fence after epoch2 | Exact separately retained progress checkpoint and source path required; old-snapshot fixture rejects. External current-anchor trust remains **NOT IMPLEMENTED**. |

## Acceptance coverage and unexecuted work

Implemented tests cover T01, T02/T03/T04 local process exits, T05/T06 transaction
rollback/projection replay, T07 failed audit proof, T08/T16 unproven ACK/pending
stage, T10 late batch quarantine, T11 both actual ordering schedules + private
reader denial, T12 late conflict below S, T13 semantic forgery, T14/T15 fences and
rollback, T31 event capacity. E06 has an actual stale-publisher subprocess;
E07 concurrently publishes the same stage and verifies one publication receipt.
These are bounded local subsets of the design cases, not a claim that T01–T32 as
a whole passed. T02–T04 exercise same-DB private staging, not a remote target.

T09 complete external-effect protocol, T17–T30 archive/coverage/backup/full-reader
contract and PIT/Factory cases, T32 correction/restore system behavior, broader
fault/capacity cases and remaining T11 subcases are **NOT EXECUTED/NOT DELIVERED**
where their components do not exist. No dummy tests with those names are added.
The failing R2 case blocks progression and phase acceptance. Exact test-case names,
source SHAs, failures and actual CI results go to #128 and the Draft conversation.

## Consultant E01–E13 ledger

| Item | Current disposition |
|---|---|
| E01 duplicate content | Parent #127 fix; existing 31-case acceptance retained, no final operational acceptance inferred. |
| E02 journal/store disagreement/orphan/ACK | **OPEN**; R2 concretely reproduces missing cross-store propagation. Orphan full reconciliation not delivered. |
| E03 crash/ACK | Synthetic local publication/receipt reconciliation subsets tested; existing store→ACK behavior not declared fully repaired. |
| E04 full record integrity | New frozen-source full-byte capsule detects timestamp tampering with unchanged MarketBar checksum; legacy CORE-ARCH-68 remains DESIGN_ONLY. |
| E05 SQLite churn/contention | Existing timeout observed; no pooling/tuning implemented or SLO claimed. Compatibility suite measured separately, not a new contention benchmark. |
| E06 cross-process fencing | Synthetic stale publisher subprocess tested; other pipeline writers and external rollback anchors remain OPEN. |
| E07 concurrent replay/claim | Same-stage two-writer idempotency tested; consumer/recovery full integration remains OPEN. |
| E08 gaps/clock/REST budget | Existing regressions only; no new clock/gap or REST changes, not closed by this Draft. |
| E09 provenance checksum | Preserved exactly; new capsule is separate, not a replacement semantic identity. |
| E10 PIT | No real temporal eligibility/availability certification; OPEN cross-contract. |
| E11 historical provenance | No live→Factory bridge; source copy/real coverage authority not implemented. |
| E12 synthetic/real boundary | Explicit synthetic-only finite adapter, no deployment/real fixtures. No Factory/OOS code touched. |
| E13 observability/Windows durability | Test artifacts/source IDs only; no physical durability, research health or host-wide isolation acceptance. |

## Remaining gates and migration

R2 must close with an independently reviewed writer/source binding and rejection
of unbound configured writers. A physical OS/remote target ACL policy, independent
progress anchor, expected inventory authority, concrete operational resource
limits/RPO/RTO/retention and real cross-process fault distribution remain separate
requirements. No values are invented. Limits used by tests are explicitly supplied
fixture settings, not production defaults. No data or cursor conversion is offered.
Legacy v1 roots remain distinct; no deployment or mixed-writer authorization.

This Draft is evidence of a first-gate implementation and independent rejection,
NOT delivery/approval of the complete CORE-ARCH-63–66 phase. Keep #128 OPEN.
No merge recommendation, Factory acceptance grant, OOS/PAPER/LIVE or G0.
