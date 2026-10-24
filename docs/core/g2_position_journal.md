# G2 Core local durable journal (offline)

This experimental single-writer JSONL journal fsyncs each event, verifies a SHA-256 hash chain on startup, and deterministically reconstructs the existing in-memory PositionLedger. Duplicate event IDs with identical content are idempotent; conflicting events fail closed. A torn trailing record fails closed, requiring explicit recovery handling rather than silently discarding data. SHA-256 is an integrity check, **not** protection against an attacker able to rewrite the whole journal. The journal is not encrypted and does not yet have process-level locks, atomic multi-process coordination, backup, rotation, checkpointing or operational Core Run integration. Use only in offline tests; do not deploy for live position custody or trading.

## Acceptance boundaries and follow-up

- **Offline only:** a hash chain detects accidental edits and many corruptions, but cannot prevent full-file rewrite by an attacker with disk access.
- **No concurrency guarantee:** the pre-append size/hash recheck narrows stale-writer risks but remains subject to a time-of-check/time-of-use race. A real exclusive writer lease/lock with recovery semantics is required before production use.
- **No external durability guarantee:** fsync of the file is not a substitute for atomic creation/rename, directory sync where supported, verified backups, or recovery testing on actual storage.
- **Fail closed:** a torn tail, corrupt record, or unexpected file change requires operator recovery; never truncate or silently discard records.
- **Scalability:** full replay before each append is intentionally conservative and may become expensive as the journal grows. A bounded, verified checkpoint/index is future work.
- **No Core Run activation:** this journal is not connected to quote ingestion, live monitoring, paper orders, portfolio accounting, or Strategy Factory.
