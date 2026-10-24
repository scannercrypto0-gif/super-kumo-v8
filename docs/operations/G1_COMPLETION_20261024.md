# G1 operational completion - 2026-10-24

Project: AQL-CRYPTO-RESEARCH-001. Owner-authorized direct execution; Draft PR only.
Base inspected: `8e8690e58451e4fdd38f3e5e5f3cc89817e59c26`.
No Strategy Factory/research code, trading, production DB, credentials or main changes.

## Verified baseline and continuity

GitHub metadata independently verifies G0 Issue #1 CLOSED/approved and merged PRs
#32/#40/#42/#45/#56. Issue #61 is closed preflight, not implementation evidence.
Its baseline post-merge CI is run 40062092633 at 782c62e69bc326efbe1e25b7b66d631a3c842605.
Current main includes later research commits; those do not extend G1 validation.
The owner's attached Final Execution Mission is the current direct execution
authorization. No new ChatGPT Work submission or exhaustive inaccessible-chat
audit is claimed. Historical handoff-register statements remain historical.

## What the code actually did, and what changes here

The old pipeline ran startup journal reconciliation and REST gap recovery before
starting WebSocket collection, and called operational storage in the WS callback.
It did not provide running-pipeline Fast/Slow isolation, despite earlier design
descriptions. This change introduces:

- Core callback: validate stream/finality/time, then commit to SQLite FULL/WAL.
  The pipeline opts into a separate consumer; direct collector usage retains the
  existing synchronous API for compatibility.
- Independent single background lane for startup reconciliation and backfills.
  Queue admission is bounded at 16 jobs, errors retained in bounded telemetry,
  jobs never terminate collection. Shutdown waits at most one second per lane
  and exposes pending work/worker state rather than reporting success.
- Journal-to-store consumer: batches of 64 unacknowledged records; store success
  or confirmed duplicate precedes ACK. Failed delivery stays in the durable
  journal. Startup replay and steady-state consumption have separate ordering
  so replay metrics and ACKs do not race.
- Cooperative core-first journal write priority. A current SQLite fsync is not
  preempted. SQLite lock waits are bounded at 250ms. This is not an OS CPU quota,
  hard real-time guarantee or protection against a hostile process/disk failure.
- REST jobs: 8 pages / 8000 expected bars maximum, five-second request timeout,
  process-shared admission/cooldown and reserved core capacity. Large ranges are
  explicitly unresolved; missing timestamps are bounded, not silently discarded.
  Subsequent restart reconciliation rediscovers unfinished coverage.
- Observed missing candles without a disconnect are detected; out-of-order bars
  cannot move the latest-open watermark backward. Reconnect waits are interruptible.
- Local store uses FULL/WAL before ACK, strengthening ordinary crash recovery.
  Existing Linux SIGKILL tests are retained unchanged.

No research workload is started or modified. Host-wide quotas, multi-process/IP-wide
provider arbitration, full multi-consumer Inbox/archive reclaim and independent
off-device backup remain outside this narrow execution. Do not widen workloads
or enable trading on the strength of the cooperative thread scheduler alone.

## Binance evidence

One bounded public check was actually executed, with no retries, authentication,
orders, account calls or production persistence.
See [raw non-secret evidence](../../evidence/g1_completion_public_smoke.json).

- REST HTTP 200, 100 unique/contiguous BTCUSDT 1m candles, observed weight 2,
  measured latency 517.76ms.
- WebSocket received 3 non-final kline observations in 5411.68ms.
- Source Date was ahead of the recorded host clock by approximately 635 seconds.
  This is PASS for transport only and BLOCKED for trustworthy temporal integration.
  No clock adjustment or backdating was performed.
- Closed-candle live/reconnect acceptance was NOT established in the short check.
  Deterministic fixtures cover gaps, finality and retries. The collector rejects
  source events more than its configurable 5000ms tolerance ahead of local time;
  the pipeline surfaces CLOCK_UNCERTAIN as unhealthy, not a valid market state.

The evidence tool is `tools/g1_public_smoke.py`. Do not repeatedly run it while
the clock problem remains unchanged. The five-second tolerance is a fail-closed
non-production default, not a measured latency SLA or final source policy.

## Persistence and Supabase sandbox

SQLite stays the operational core. `BarStore` defines the narrow upsert contract.
`PostgresSandboxStore` requires explicit sandbox opt-in and a caller-supplied
connection factory. It imports/reads no credentials, checks finality/checksum,
uses parameterized inserts and the candle unique key, commits transactionally,
rolls back failure and retries transient faults at most three times. Exceptions
are redacted. Caller must configure bounded connection establishment (e.g.
psycopg `connect_timeout=3`); statement timeout is five seconds.

`SandboxReplicator` is separate from local persistence ACK. It reads bounded pages
from the journal and stores a FULL/WAL cursor scoped to the journal path and
consumer. Remote commit precedes local cursor commit, so crash/retry repeats an
idempotent write. It is opt-in; the core pipeline does not start remote access.

Sandbox setup, owner-controlled:
1. Provision a separate disposable Supabase project/database, never production.
2. Apply `migrations/sandbox/001_market_bars.sql`, then `002_writer_role.sql`.
   These create no login/password: RLS, revoked PUBLIC grants and a NOLOGIN
   INSERT/SELECT writer role only. Grant membership to a dedicated sandbox login
   through secure owner administration, never commit a DSN.
3. Install optional psycopg in the sandbox environment; supply a bounded connection
   factory, explicit sandbox=True, and a distinct local durable cursor file.
4. Verify duplicate writes, provenance/timestamps, rollback, outage/restart replay,
   TLS, privileges and RLS on that exact sandbox. Keep evidence without secrets.
5. Do not delete/recreate an existing journal under an old replication cursor;
   retain the immutable journal identity or explicitly use a fresh consumer/cursor.
   Multi-process replication/compaction/replacement is not supported here.

Deterministic mocks and SQLite-backed remote fixtures test retry, rollback,
redaction, independent ACK, restart and remote-commit/local-cursor crash windows.
CI adds disposable PostgreSQL 16 with the actual migrations and restricted writer
role. This is PostgreSQL evidence only, never Supabase-cloud integration PASS.
No local Docker/psql or real Supabase sandbox was available during preparation.

## R09 - owner execution checklist (UNRESOLVED / CRITICAL)

Non-secret docs identify an exposed legacy V7 token. Current tracked paths and
fetched-history assignment-pattern metadata contain no matching legacy credential
implementation/reference in operational src. No V7 imports or key dependencies
were found in G1. This limited scan does not prove absence from every historical
branch, deleted remote, external V7 copy, artifact or log. Credential values were
not printed/retrieved for verification; no revocation/rotation was attempted.

Owner-only actions:
1. In the original V7 deployment's trusted inventory, identify each issuer and
   credential type without sharing values in chat/issues. The available evidence
   does not establish a complete credential-type inventory; do not guess it.
2. Revoke the exposed credential at its issuer and invalidate all derived sessions
   or tokens where applicable. Review issuer access/audit logs for misuse.
3. Rotate only if the service remains needed; provision least-privilege replacement
   into environment/secret manager, independently of V8 market data (public/no key).
4. Remove old values from active V7 configs, CI secrets, scripts and logs using
   owner-approved incident handling. History cleanup alone never revokes a token.
5. Record non-secret issuer confirmation, revoked credential identifier/fingerprint,
   timestamp, affected deployments and verification that old authorization fails.
   Do not paste old/new secrets or run legacy code as a shortcut.
6. R09 may be closed only after this actual verification; G0 approval and this PR
   do not close it. No legacy code/key reuse before closure evidence.

## Windows coverage and verification

- Affected orchestration + new acceptance tests: 25 passed / 5 skipped, then the
  additional clock test passed (new test file: 19 passed / 1 skipped).
- Earlier local G1 regression during development: 121 passed / 9 skipped.
  Final regression and final-head CI are recorded in PR evidence; do not treat
  earlier runs as testing later code.
- Existing Windows skips are POSIX SIGKILL variants and heavy fsync/stress coverage,
  plus opt-in live REST. They were not weakened or removed. New pipeline isolation,
  bounded wait, replay, priority, schema adapter, rollback and clock fixtures run
  on Windows too. Cloud PostgreSQL test is separate from the OS matrix.
- Performance floors remain benchmark/test conditions, not production guarantees.
  Process termination, power loss, networked filesystems and off-device backup
  need environment-specific acceptance beyond passing synthetic fixtures.

## PR #16 disposition

Verified OPEN/unmerged at 828ed10b7c775dcb56627426789057d73e8c5342.
SUPERSEDED as the active minimal-MVP execution plan by merged WP01-WP04.
Its explicitly deferred full Inbox, archive ACK/reclaim and backup/restore/RPO/RTO
requirements are NOT cancelled or proven implemented by this work.
Owner-ready recommendation: close #16 as superseded only while retaining those
requirements in the roadmap/decisions. It was not closed: current authorization
does not explicitly settle disposition of every deferred requirement.

## Acceptance boundary

Implemented/offline-tested engineering can proceed to controlled synthetic
integration after review of the Draft PR. Real temporal integration remains
BLOCKED by clock divergence; real Supabase integration remains NOT TESTED;
R09 remains UNRESOLVED. No production/trading readiness or gate closure is claimed.
