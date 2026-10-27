# CORE-128: R2 source/store binding candidate â€” independent acceptance pending

Project AQL-CRYPTO-RESEARCH-001. Owner repair handoff: PR #129 comment
6417847879, followed by continuation 6417931579 and the current direct repair
instruction. Bounded synthetic/local Core only: no merge, Factory changes,
real migration, hosted services, OOS/PAPER/LIVE, trading or final G0.

## Continuity and exact ancestry

Last delivered Core handoff: #128/6417726650 and #129/6417727096, source
801a82cf6e375fc0c9ceccbe167a06420332b028, independently BLOCKED by R2.
The unchanged parent #127 is 542578ec8b81a0b933811d878e896d23daac7ac4,
OPEN/DRAFT/unmerged. Work continues on the SAME #129 branch, stacked on that
parent. No rebase or import of main/Factory. Main is now
 a4f19c97e77d87f1cd69f4146822394fe3f369d4 after owner-authorized Factory #126
merge by another actor. Subsequent Factory #130 is a separate open Draft;
its delivery and latest #77/#92 design/review records were consulted for scope.
Unavailable originating Work chats/Library DESIGN-2 artifact were not reread or
claimed accessible in this repair. Prior handoff records DESIGN-2 as preparation,
not executed T01â€“T32. Architectural approvals remain provisional until G0.

## Explicit activation contract

Only a fresh finite synthetic source and explicitly supplied fresh EMPTY SQLite
OperationalStore objects can activate. Source anchor v2 adds an immutable source
generation plus versioned store registration: canonical source path/instance,
store path/UUID, adapter identity `operational-store-v2`, initial writer epoch,
and initial full store-state digest. A store-side immutable backlink must match
the journal-side frozen registration. No path search, market-key ownership
inference, global store registry or implicit legacy migration is used.

```python
store = OperationalStore(explicit_disposable_store_path)
authority = Authority(journal, limits=explicit_fixture_limits,
                      synthetic=True, stores=[store])
writer = authority.store_writer(store)
```

The registered adapter captures its writer epoch at enrollment or reopen.
Maintenance can increment the epoch through `fence_store(authority, store)`;
old objects fail, and an explicitly reopened registered adapter obtains the new
epoch. An object made before enrollment is NOT silently upgraded. A configured
unregistered store is refused by `store_writer`; an unrelated ordinary v1 DB
remains independent. Missing binding refuses Authority activation altogether.
Reopen requires the separately retained source anchor and current progress head.
Existing pre-binding v2 sources are not silently migrated; missing registrations
fail closed. No existing pipeline is activated by this repair.

Activation is OFFLINE/FRESH-SOURCE ONLY. Supported legacy Collector (including
run), JournalConsumer, startup reconciliation, gap recovery and sandbox replicator
record a one-way durable source registration before operational work. Activation
refuses a source ever configured to those clients, covering already-prefetched
batches without guessing whether a client has exited. No deregistration/conversion
is supplied. Conversely activation durably reserves the source under the same
BEGIN IMMEDIATE discipline BEFORE cross-file enrollment; later legacy client
registration, raw appends/retries and reads are refused even if enrollment crashes
before core128_meta exists. A failed reservation needs maintenance reconciliation,
not automatic legacy fallback. This is conservative refusal, not in-flight recall.
The Collector/Recovery entry guards perform no network operation in tests.

## Ordering, denial, and restart

All publication, settlement and protected reads use source BEGIN IMMEDIATE.
A bound store write first validates registration/epoch/inventory and commits a
STORE_INTENT in that same authoritative journal. Protected operations refuse an
unresolved intent. Only then may the adapter start the separate store mutation,
while holding the source serialization lock. Conflicting incoming source facts,
retained store divergence, or explicit quarantine also append source BLOCK audit
before completing. A STORE_COMMIT records the resulting full bounded store state;
its source commit releases the read prohibition, while per-key quarantine remains.

These are TWO SQLite transactions, NOT cross-file atomicity. A crash/audit-write
failure after intent or store commit leaves durable denial. Restart, retry, a
current checkpoint, or projection rebuild cannot silently clear it or fabricate
an ACK. No automatic reconciliation/recovery command is delivered: unresolved
operations require a separately reviewed maintenance reconciliation protocol;
availability is sacrificed conservatively. Process-exit tests verify restart
REFUSAL, not successful reconciliation or physical power-loss survival.

The source lock orders cooperating writers with readers. Source verification
checks every frozen store backlink, current full state digest, absence of orphan
rows, semantic agreement with source or source quarantine, and that store audit
quarantine is also denied by source authority. Missing/replaced stores and stale
restored snapshots refuse access. Already-returned bytes are historical deliveries
and cannot be retroactively recalled; D remains historical while V excludes blocks.

## Original R2 preservation and contract migration

The original `test_R2_unbound_operational_store_conflict_must_deny_read` function
is text-identical to baseline801a82cf, SHA256 of its AST source segment:
`ab467cdba1339ae499d5acad4a6097012ec9d1728b0650de2c5030a9e46c7a5d`.
No assertion, skip, xfail or error expectation was weakened. Shared setup now
EXPLICITLY registers store.sqlite at activation. Therefore the old function now
exercises a separately reopened REGISTERED store; unchanged function text alone
does not preserve its original unbound premise. This is an intentional disclosed
activation-contract change, NOT a claim that an arbitrary unbound DB automatically
propagates quarantine. Additional tests preserve the stronger boundary:

- No stores: activation fails, no protected source reader is obtained; v1 intact.
- Unregistered configured writer: refusal before operational effect.
- Unrelated v1 DB: no guessed ownership or contamination of registered source.
- Object created before enrollment and stale epoch: refused.
- Registered store conflict: protected read denied, healthy keys remain readable,
  historical D/S retained; repeat conflict never clears quarantine.
- Missing/replaced/old store snapshot and changed object path: denied.
- Source/store audit failure, post-store-commit failure and completion failure:
  durable unresolved denial survives restart; no inferred completion.
- Both source-lock ordering schedules for publish versus store intent/conflict.
- Real subprocess exit after intent, after store commit and before source commit,
  using portable os._exit on Ubuntu/Windows; no mocks of process termination.
- Bound store v1 coverage reads, source legacy replay/ACK/archive/sandbox bypasses
  and writes outside the frozen inventory: refused.

Baseline independent reproduction remains 1 FAIL (final read did not raise).
First local extended candidate was 49 PASS/2 FAIL: a repeat already-quarantined
write left an unnecessary unresolved intent, and a test leaked a SQLite handle
preventing Windows rename. The implementation now rejects known quarantine before
new intent, and the test closes its backup handle; failures are not hidden.
Final source SHA, exact native CI counts and independent report belong in the
PR/#128/#92 receipts, not inferred from earlier local success.

## Limits and supported API boundary

Finite explicit fixture limits only: no production SLO, RPO/RTO, retention,
trusted time, external latest-checkpoint authority or expected-inventory signer
is invented. Store-state scans are bounded by configured records/bytes/events.
No network operation occurs under the source lock. Source/store IDs and digests
are local integrity/registration metadata, not external authentication or custody.
Cooperating adapters must use the registered API. Python private-member access,
direct SQL, altered source binaries, filesystem/admin adversaries and effective
OS ACL enforcement remain outside this capability discipline. A source lock does
not certify hostile external path replacement/alias races or physical durability.

Legacy v1 sources/stores without activation retain their APIs. Bound store
coverage getters refuse v1 access; operational payload clients get ProtectedReader,
not SQL/maintenance handles. MarketBar fields, legacy checksum/committed_at,
legacy delivery cursor, archive v1 schemas/verifiers and Factory remain unchanged.

## Current phase boundaries and consultant ledger

D1-C/R2 is a CANDIDATE until independent adversarial verification and exact-head
Ubuntu/Windows gate+compatibility pass. Keep #128 OPEN, #129 Draft/unmerged.
D2 full external-effect/receipt protocol, partial archive/coverage/backup/restore v2,
full T01â€“T32 acceptance and real expected-inventory authority are NOT delivered by
this R2 repair. D4-C remains an unconfirmed recommendation; no COMPLETE is emitted.
Only after independently accepted D1 may the remaining staged work resume.

| Item | Bounded current status / remaining work |
|---|---|
| E01 | Parent duplicate fix retained; no service acceptance inferred. |
| E02 | Registered-store R2 repair candidate; independent gate pending. Arbitrary legacy/orphan integration not claimed complete. |
| E03 | Crash windows fail CLOSED; automatic in-doubt reconciliation and complete external ACK integration remain open. |
| E04 | Frozen full-source capsule unchanged; legacy CORE-ARCH-68 remains design-only. |
| E05 | No pooling, timeout tuning or contention SLO claim. |
| E06 | Source publisher and store writer epoch tests; effective OS fencing/external rollback anchors remain open. |
| E07 | Bounded source/store/publisher race tests; no live consumer/recovery rollout. |
| E08 | Existing gap/clock/REST regressions only; no new gap policy. |
| E09 | Existing provenance checksum bytes preserved. |
| E10 | No real PIT/availability certification. |
| E11 | No live-to-Factory historical provenance/coverage bridge. |
| E12 | Synthetic finite opt-in only; Factory/OOS untouched. |
| E13 | Native process tests are not physical power-loss, custody, research health or host-isolation evidence. |

Prior R1/R3/R4/R5/R6 regression tests are retained. Prior independent review at
#129/6417641355 is historical evidence, not approval of this new candidate.
A separate review agent is requested on every revised pinned source; no GitHub APPROVED
review, owner merge consent or phase closure is implied by an author test run.


## Subsequent self-review: configured legacy pipeline edge

Source83cd49d passed native gate56 and compatibility Ubuntu264/2skip,
Windows256/10skip, plus independent adapter review. It was NOT used as final
phase acceptance. Subsequent self-review found a legacy Collector could accept a
matching journal retry then write an unbound store before its legacy ACK failed.
The new offline source-registration/reservation rule and matching-retry refusal
close that admission route. Extra tests cover configured Collector/Consumer/
Recovery/Sandbox rejection, preconfigured-source activation refusal, concurrent
registration versus activation reservation and failed-reservation restart denial.
The latest source requires NEW independent review and exact-head native CI.

Repair-specific Core allowlist includes delivery authority/store_binding,
storage operational_store/sandbox_store, g1_integrity, journal durable_journal,
collector binance_collector, pipeline recovery entry, lanes consumer entry,
the acceptance tests and this document. Those extra entry guards are necessary
source-writer admission checks, not new pipeline activation or Factory work.
No GitHub workflow was weakened or changed in the net repair diff.
