# G2 Core local durable journal (offline)

This experimental single-writer JSONL journal fsyncs each event, verifies a SHA-256 hash chain on startup, and deterministically reconstructs the existing in-memory PositionLedger. Duplicate event IDs with identical content are idempotent; conflicting events fail closed. A torn trailing record fails closed, requiring explicit recovery handling rather than silently discarding data. SHA-256 is an integrity check, **not** protection against an attacker able to rewrite the whole journal. The journal is not encrypted and does not yet have process-level locks, atomic multi-process coordination, backup, rotation, checkpointing or operational Core Run integration. Use only in offline tests; do not deploy for live position custody or trading.

## Acceptance boundaries and follow-up

- **Offline only:** a hash chain detects accidental edits and many corruptions, but cannot prevent full-file rewrite by an attacker with disk access.
- **No concurrency guarantee:** the pre-append size/hash recheck narrows stale-writer risks but remains subject to a time-of-check/time-of-use race. A real exclusive writer lease/lock with recovery semantics is required before production use.
- **No external durability guarantee:** fsync of the file is not a substitute for atomic creation/rename, directory sync where supported, verified backups, or recovery testing on actual storage.
- **Fail closed:** a torn tail, corrupt record, or unexpected file change requires operator recovery; never truncate or silently discard records.
- **Scalability:** full replay before each append is intentionally conservative and may become expensive as the journal grows. A bounded, verified checkpoint/index is future work.
- **No Core Run activation:** this journal is not connected to quote ingestion, live monitoring, paper orders, portfolio accounting, or Strategy Factory.

## In-process serialization

A module-wide Python threading mutex now serializes `append` calls made by journal instances **within the same interpreter process**. Together with the pre-append disk verification, this rejects stale second instances rather than allowing sequential interleaving. This is **not** a cross-process file lock and does not prevent another executable from changing the file. Do not interpret it as production multi-process safety.

## Cross-process writer lock (experimental)

Appends now acquire an atomic `O_CREAT | O_EXCL` sidecar `.writer.lock` before checking/replaying/writing the journal. Cooperating processes on a local filesystem cannot simultaneously enter the write critical section. A crash may leave the lock behind: fail closed; **never delete a lock without confirming the owning process is dead and inspecting the journal**. This is not a distributed lock and must not be assumed safe on all network filesystems. There is no automatic orphan-lock recovery, lock ownership fencing, or crash-atomic directory durability guarantee. These are required for production readiness.

## G2-CORE-04 recovery drill: operator-only proposal (not approved for activation)

**Status:** documented recovery proposal for offline drills. No automatic lock removal,
repair, or promotion of a backup is implemented. This section does not grant a
production custody or recovery policy.

1. **Quiesce and fence writers first.** Stop every cooperating writer and any
   service that could restart it. Record host, process identity, journal path,
   lock path, timestamps, filesystem and operator. A PID in the current lock
   file is only a hint: PIDs are reusable and a missing PID is not proof that
   no writer exists. An exclusive lock file by itself provides no durable
   fencing token or restart prevention. If exclusive ownership cannot be
   established, **stop; do not delete the lock**.
2. **Preserve evidence before recovery.** Record byte length and SHA-256 of
   the journal and lock; preserve immutable, access-controlled copies of both
   and the failure logs on a separate offline location. Do not truncate a torn
   tail, replace the primary journal, or copy over an active writer.
3. **Verify the candidate offline.** Reopen a copy using
   `DurablePositionJournal` and independently compare expected position/event
   counts and final hash with the incident inventory. A digest match against
   the same corrupted source does **not** prove the backup is correct.
   If either chain validation or reconciliation fails, keep the incident
   blocked and escalate to the owner.
4. **Obtain explicit operator/owner authorization for a recovery action.**
   The operator must specify which verified version is authoritative, how
   competing writers remain fenced, what evidence is retained, and how the
   original is rolled back. This repository does not currently supply an
   approved mechanism for these guarantees.
5. **Reopen only after the fencing and audit gates are met.** Record the
   authorization, before/after hashes, validation outcome, and a rollback
   reference. Do not equate a successful offline reopen with safe activation.

### Benchmark and Core Run isolation acceptance plan

The current `_append_locked` performs a complete journal replay and rebuilds
a candidate ledger before each append. For `n` events, this makes a sequence
of `n` appends potentially quadratic in total work. Do not introduce an
arbitrary latency threshold or an unverified checkpoint format.

A reproducible benchmark must record OS, Python version, filesystem/storage
type, event count, journal bytes, per-append p50/p95/p99, full-reopen time,
peak memory, and checksum/ledger reconciliation. Compare at several journal
sizes and report raw samples and run-to-run variance. Any checkpoint or
backup-custody design is a **separate owner decision**, not implicit approval.

Core Run isolation is **not yet proven**: the journal has no operational
pipeline integration, and background research must not be scheduled onto the
Core Run execution lane. A future test must show bounded core-loop latency
while replay/backup work runs in a separately bounded worker with shared
resource limits. The current offline unit tests cannot establish this.

### Existing evidence and explicit gaps

- Existing journal tests cover torn tails, tampering, stale instances and
  orphan-lock refusal; avoid duplicating them.
- Draft PR #93 adds actual append-fsync subprocess crash injection and a
  minimal byte-copy verification baseline. CI on both Windows and Ubuntu
  validates those focused tests, **not** backup custody or power-loss safety.
- **Open gates:** independent coherent backup/restore, operator-fenced
  recovery with audit, bounded replay benchmark, Core Run isolation, and
  owner approval of any custody/fencing design. No production activation.
