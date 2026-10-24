# ADR proposal G1-STORAGE-02 v1 — local authoritative archive and recovery

Status: **PROPOSAL FOR REVIEW**, implements only owner-conditionally-authorized Phase1 (#71, #67 owner comment6382338071). No final G0 approval or production migration. Prior register entry004 (Supabase central/local spool) remains unchanged; this proposal would explicitly supersede its storage authority direction upon approval. No other governance decisions are replaced.

One decision: where authoritative bulk evidence resides.

| Option | Result |
|---|---|
| A Supabase central including candles | Rejected for bulk: #67 estimates500 1m symbols at10.8 GB/month at500 B/row versus Free500 MB database allowance |
| B durable local original journal + sealed bulk archive + independent backup; cloud later rebuildable summaries | **Recommended / conditionally approved for Phase1 implementation only** |
| C B with paid cloud projections | Budget/availability alternative, separate owner approval; still no routine cloud bulk candles |

## Current versus implemented

Unchanged: MarketBar, journal WAL/FULL, local-store ACK/recovery, independent sandbox cursor, collector, pipeline and background primitives. The old research ArchiveCopyInterface remains a no-op-by-default optional callback; it is not reused as an authoritative archive or altered by this work. New `aql.archive` is an opt-in sidecar reading an existing journal in SQLite read-only mode, independent of operational ACK. Existing pipeline behavior stays unchanged. Nothing enables it automatically.

Physical format: canonical ASCII-safe UTF-8 JSONL sealed segments and JSON manifests, a SQLite WAL/FULL index and intent/checkpoint. No Parquet dependency is available in the verified Windows environment. This is an explicit durable format fallback, not a claim of Parquet/compression performance. Parquet conversion must be separately versioned, keep exact envelopes/commitments and be justified by real measured storage/query performance. No runtime package installation/networking is used. CI installs only declared existing dev/runtime requirements.

## Commit/recovery and immutability

Bounded batch default64/max128 records, ≤256 KiB segment payload, source row≤16 KiB before materialization; one interprocess writer. Partition market/interval/UTCdate, not per-symbol files. Small finite runs may produce small segments; there is no destructive compaction. Per-batch CPU/memory work is bounded; blocking filesystem fsync cannot be preempted. ArchiveService reuses the bounded BackgroundLane for wake-up jobs only (queue1); rejected wake-ups lose no journal record. Retry/replay is explicit via the next scheduled request or finite CLI invocation, not a newly claimed always-running daemon.

1. Bind source path+journal UUID and build/policy to a new archive root. Existing root with other identity/config fails closed.
2. Persist one intent in independent FULL/WAL catalog. Write new partial directory/data/manifest; flush/fsync files, directory sync where supported; atomically rename sealed directory without overwriting an existing sealed segment.
3. Verify retained manifest hash, file hash, record/key/sequence hashes and each envelope against the original journal. Only then transactionally insert unique index/coverage and advance archive watermark. Never alter local or remote ACKs.
4. Restart adopts verified renamed pending segment; otherwise preserves partial attempts in quarantine and rebuilds from retained journal. No authoritative data or sealed segments are overwritten/deleted. Conflicts/corruption stop progress, pending intent remains. Failures cannot become success by clearing RAM.

Manifests include count, exact sequence IDs, completion watermark, UTC min/max, full key/envelope/file digests, build/policy/source identity, missingness, per-symbol gap and out-of-order inventory including previous archived symbol-open boundary. Coverage means observed journal-prefix coverage, **not full Binance/provider completeness**. Later recovered old bars are labeled out-of-order; earlier gap evidence is not rewritten away.

Full envelope hashes bind all recorded temporal/state/provenance fields in addition to the older market-content checksum. `ingested_at` is the existing model's receipt/ingest field. Source event time, actual independently observed availability, and fsync completion instant are unavailable and remain null. `availability_lower_bound_ms=max(close+1,receipt)` is explicitly DERIVED_LOWER_BOUND_NOT_CONFIRMED, never promoted into actual availability. Existing recorded commit timestamp was captured before COMMIT and is labeled accordingly. The archive does not manufacture earlier final observations or promote research eligibility.

PIT decision/outcome contract includes shared context identity, ACCEPTED/REJECTED/EXPIRED/NO_FILL, immutable canonical snapshot/digest, strategy/policy versions and BTC/ETH regime, breadth, liquidity, volatility, relative-strength feature inventories, source/event/receipt/availability/freshness/version/missingness. **Only validation/serialization plumbing is implemented**: runtime capture, durable decision-event journal and complete paper lifecycle are future work. Unavailable feature fields are null; later outcomes must reference rather than mutate the original decision snapshot. No Strategy Factory/trader/execution code is modified.

## Backup, restore and trust

Opt-in separate local destination, bounded file/byte/time inventory. Coherent SQLite backup API includes committed WAL pages. Archive writer is locked for capture; ingestion may continue. Journal, catalog and optional hot-store backups are individually coherent; they are not a distributed/global point-in-time transaction. Hot store is rebuildable and may lag journal. Every indexed archive envelope/key/hash is reconciled with the backed-up journal; the unarchived source backlog is checksum/geometry/time validated too.

Sealed snapshots are verified using SQLite immutable read-only mode only after backup API completion; live WAL sources never use immutable mode. SHA256 inventory plus caller-retained expected digest detects modification. Keep that commitment independently; an attacker rewriting all files and the caller's trust anchor is outside the hash-only guarantee. No signing service or trusted offsite anchor is provisioned.

Restore requires a new non-overlapping disposable target, verifies before and after bounded copy, and publishes by rename only after reconciliation. No overwrite or automatic production cutover. For restart in another location, keep the restored old catalog forensic and create a new archive root bound to the restored journal, then explicitly replay; never silently rebind a live cursor path. No data is deleted.

Same-directory/device copy is **not independent backup**. Off-device destination, encryption/keys, provider, credentials and budget remain owner decisions; no transfer occurs. Proposed targets: hourly journal RPO≤1h, nightly bulk/manifests RPO≤24h, RTO≤4h after verified independent copy. Local measurements are drill timings, not certified RPO/RTO. Three copies/two media/one encrypted off-device copy are a proposal, not implemented service coverage.

## Operating envelope and failure modes

Default archive reserve10 GB plus two batch payloads; tune only against an approved disk budget. No auto-pruning. Backup defaults:8192 files,2 GB total/individual ceiling,60s per operation (SQLite page copies also have a deadline). Large archives intentionally fail rather than grow memory/unbounded copy; larger scopes need explicit parameters and measured time/disk budgets, with future incremental inventories/Parquet as follow-up. Interrupted copies remain `.partial`/`.restore-partial`; quarantine/partials accumulate and require separately approved cleanup. They are never reported as verified backups.

Health distinguishes backlog, observed errors, disk telemetry, backup age and directory-sync capability. Missing/stale/error telemetry never returns HEALTHY. `last_backup_ms` means last verified local copy in this instance, not independent/offsite protection; restart leaves it unknown until verified again. Last archive check is bounded checkpoint/anchor validation, not a full historical media scrub on every heartbeat. Full archive/source reconciliation happens in backup verification/restore drill. Queue admission and worker status remain available from the reused lane.

Windows supports file fsync and writer lock/rename tests here; portable directory fsync is unavailable and explicitly reported UNSUPPORTED, hence local health remains DEGRADED even with fresh backup. POSIX directory fsync errors abort ACK. Neither platform is power-loss certified. Symlink/reparse paths, ordinary root/journal replacement and cursor rollback are rejected. The archive root needs private owner-controlled filesystem ACLs: path checks/locks do not sandbox a hostile privileged actor racing path replacement or rewriting every trusted catalog/hash. No host-wide CPU/I/O quota or hard real-time guarantee.

Separate archive disk/process I/O budget is recommended; current sidecar avoids synchronous core calls but shares the host/storage. Actual disk-full may stop primary durable ingestion: no false healthy state or fabricated success. Remote/cloud outages do not participate in this phase. R09 stays CRITICAL/UNRESOLVED; no credential access/rotation evidence claimed.

## Acceptance and retention gate

Tests cover restart at each intent/write/rename/ACK boundary, real process termination, exact duplicates/conflicts, timestamps/finality/corruption, disk-full/permission injection, real SQLite locks, real writer lock, bounded RAM queue and core commits while archive is blocked, gap/order inventory, coherent WAL backup, tamper/retained digest rejection, out-of-place exact restore/replay and path safety. Simulated failures are distinguished from real host exhaustion/ACL/power tests in evidence.

No deletion is authorized. A later retention proposal requires complete declared-scope manifest, unresolved gaps/missingness disposition, all required consumer/remote cursor progress, independently verified backup and tested restore, legal/research/OOS evidence retention and separate owner approval. Mutable SQLite state is not a physically immutable audit ledger. #67/#71 stay open until independent review/owner acceptance; Draft PR alone closes no gate.

Phase2: separately reviewed capped generic projection publisher/quota controller/read-only dashboard. Reuse #65 for actual named-Sandbox TLS/RLS acceptance only after separate owner authorization; this issue authorizes no cloud access, schema changes, paid service or deployment.

Trust boundary: sealing is append-only through this API plus retained integrity commitments, not filesystem WORM or protection from a privileged attacker. Envelope hashes start protecting temporal fields at archival capture; they cannot retroactively authenticate earlier journal timestamp edits that the original market checksum did not cover. Real provider availability remains unknown unless separately evidenced.
