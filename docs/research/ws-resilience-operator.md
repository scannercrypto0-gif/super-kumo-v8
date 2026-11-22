# WS resilience: one guarded owner-local package

This is engineering preparation for PR321, not permission to deploy or reconnect
on the owner's Windows machine. Current owner evidence (22 November 2026,
08:38:59 Riyadh) is `Ready`, `HOLD/PILOT_STOP_TimeoutError`, with one automatic
recovery already consumed. The second timeout's underlying origin is
`ROOT_CAUSE_NOT_PROVEN`; a prior reset followed by pending/started recovery is
not evidence of sustained successful recovery.

The existing pilot keeps only sanitized receipts. This package does not turn it
into durable raw candle collection, certify PIT, or fill its gaps. It does not
read or modify the separate active E: warehouse backfill, its locks or task.

## Single version-pinned entry point

After the engineering candidate has passed CI, substitute its exact 40-hex SHA:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\dell\Desktop\ATLAS-Quant-Lab\tools\atlas_ws_resilience_windows.ps1" -ExpectedCommit "<EXACT_REVIEWED_COMMIT>" -Mode Diagnose
```

The working checkout must already be that SHA with tracked, unmodified package
and candidate runtime files. `Diagnose` is read-only: no market calls, clock
probe, state creation, task edits, HOLD archival or collector process. It reads
the existing uniquely identified task, current task action/config pin, all
installed runtime pins and the known HOLD/automatic claims, and emits a
sanitized identity digest. No task arguments, private source references, raw
market payloads or owner file contents are published. Missing or invalid quota
evidence is explicit and blocks deployment; installed hashes can still be
reported. Quota reads use immutable read-only SQLite and refuse WAL/SHM evidence
rather than create sidecars or ignore a potentially active WAL.

## Separate explicit owner authorization

`Apply` is intentionally unusable without a private authorization JSON. This
engineering assignment does not supply or fabricate that authorization. The
owner's later decision must bind the exact diagnostic identity, candidate SHA,
existing task and action-pin update, and one recovery segment. No 24/7 release
or restart loop is authorized by this file. The file has this exact shape
(values below are placeholders, not a valid permit):

```json
{
  "schema": "atlas.ws.operator-authorization.v1",
  "action": "DEPLOY_ONE_RECOVERY",
  "identity_sha256": "<diagnostic.identity_sha256>",
  "candidate_commit": "<EXACT_REVIEWED_COMMIT>",
  "task_name": "ATLAS-Research-Sustained-Spot-WS",
  "issued_ms": 0,
  "expires_ms": 0,
  "max_segments": 1,
  "max_connections": 2,
  "orders": 0,
  "trading_authority": "NONE",
  "allow_task_action_pin_update": true,
  "allow_clock_probe": true,
  "existing_pilot_quota_only": true,
  "owner_decision_ref": "<separate explicit deployment and one-recovery decision>"
}
```

`issued_ms` must be current UTC epoch milliseconds; expiry is after the
invocation and at most 30 minutes after issue. Scope integers are strict JSON
integers, not booleans. Identity changes require a newly reviewed authorization;
there is no automatic authority refresh. Successful authorization is claimed
create-once by the SHA256 of the actual private file bytes.

The **single deployment invocation**, only after that separate decision, is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\dell\Desktop\ATLAS-Quant-Lab\tools\atlas_ws_resilience_windows.ps1" -ExpectedCommit "<EXACT_REVIEWED_COMMIT>" -Mode Apply -AuthorizationFile "<owner-private-permit.json>"
```

The wrapper verifies authorization before the bounded 4-sample clock probe.
Clock uncertainty must be at most 250 ms with a fresh observation. Required
preconditions include task `Ready` and enabled, no competing live collector,
existing exclusive supervisor lock, existing collector SQLite lease, no stop
request, no unresolved normal-segment execution marker, unchanged task XML /
runtime / config / HOLD / claim pins, no existing operator ticket or active
claim, pinned original quota policy, no ban/pending request, elapsed backoff,
no active sockets, scoped connection headroom, source permission references and
128 MiB free space. Shared-IP headroom remains unverified in this legacy local
pilot; a permit cannot reclassify it as a shared production egress authority.

The wrapper holds `supervisor.lock` and a Python gate holds the existing
`segments/service-writer.sqlite` exclusive transaction throughout mutation and
task readback. It creates `operator-deployment.in-progress`; candidate collector
and supervisor guards fail closed on that marker. It stages only the three
reviewed runtime files, updates their existing config manifest pins, and
changes only the task action's `ConfigSha256` argument. It checks that task
Triggers, Principals and Settings have not changed. It does not invoke
Start/Stop/Enable/Disable/Register-ScheduledTask or change schedules, rights or
network limits. Gate responses/exits have 30-second bounds; a stuck clock probe
has a 15-second bound and bounded termination.

Before any replacement it preserves private runtime originals, config,
activation, task XML/action, HOLD and automatic recovery claims in
`ws-recovery-backup-<uuid>`, with a sealed hash manifest. It writes the one-use
`operator-resume.authorized.json` only after the action-pin readback. Original
HOLD/pending/claimed files remain untouched by the installer. On the next
existing scheduled invocation, the supervisor claims the ticket before action,
archives exactly the pinned original evidence, and permits only one recovery
segment with two transport attempts. A second terminal failure remains held;
even successful one-shot completion requires a separate release review. No
host reconnection is attested by successful installation.

## Rollback and interrupted installation

Before `COMMIT`, any task action update failure first restores the original
action, then tells the still-leased gate to restore original runtime/config /
activation bytes. Newly introduced candidate files are archived, not deleted;
HOLD and automatic claims never move. The exact authorization stays consumed.
Tests exercise this rollback with the real file writer and SQLite lease.

A killed process, EOF or uncertain post-COMMIT state deliberately leaves the
deployment marker, original HOLD and private backup available for review.
**Do not delete the marker, clear HOLD, restore an old reader or rerun Apply
blindly.** The package emits a precise sanitized failure, and backup
`manifest.json`, `task-action.json`, `task.xml`, original config and files are
the rollback artifact. A post-crash rollback must be separately authorized,
under the same two locks, after verifying current task/config/runtime and
whether the operator ticket was consumed. If no immutable observation can
establish that state, leave HOLD and report the exact blocker. The engineering
package does not grant an unreviewed post-crash task/XML restoration command.

## Evidence and acceptance

`atlas.ws.operator-diagnostic.v1` contains the sanitized identity and blockers;
`atlas.ws.operator-deployment-receipt.v1` binds candidate, authorization,
previous identity, new config, backup manifest and the no-task-start / no
schedule/principal-change / no-order constraints. Private backup JSON is
content-hashed; those hashes are local integrity evidence, not independent
host or source-origin attestation. Original capture gaps and retrospective
coverage remain distinct.

The offline operator tests use isolated generated files, the actual gate and
SQLite locking. They cover identity/authorization drift and expiry, numeric
scope, banned/unknown quotas, zero-write diagnostics, byte-preserving rollback,
crash-before-ACK, one-use operator claims and competing collector lease. Windows
CI parses the entire PowerShell wrapper. No original owner-host deployment,
source collection, real reconnection, sustained capture or trading is asserted.
