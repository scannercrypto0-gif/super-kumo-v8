# WS-RESILIENCE-RECOVERY-20261122

## Continuity and one outcome

Authority: PR321 comment 7074915111, owner-approved Option B engineering only.
PM charter 205/6721828613 and canonical 202 were reconciled with current 205,
134, 271, exact PR321 reviews/commits/CI and the latest owner handoff before
editing. No submitted native review on321. Baseline321 is open/non-draft,
unmerged at495f328396d37019d8c70c37f921ea68497ffddf; 271 remains draft/unmerged
at ed6f0435c84bb14fa508d1cfa07f279b6b4531c7. Historical330 is separate: its
owner-host backfill is active, last supplied progress reaches October2026 and
then daily fallback; this package does not read or interrupt the active E: store.

The latest actual WS owner readback, **22 Nov2026 08:38:59 Riyadh**, supersedes
205/7058707661 (installation/resumption) and205/7060377960 (one completed
segment/rollover): task Ready, fix_present true, HOLD true,
`PILOT_STOP_TimeoutError`, last receipt2026-11-21 14:00:00.116 Riyadh, reported
age1119minutes. Owner reported installed cycle SHA
`26fc53b5152f802cb14da04d163adf41b1b2d24cb2c0e77efb29294a920cd3a7`
and earlier config SHA
`9b36cb50ee6dc0b87d2e04d324d443534e05f3cebbdb1703eb6782d5eb8cba5e`.
Those are prior reported pins, not an assertion that current private bytes or
config still match. The operator verifies actual identities before any change.

Owner-provided supervisor sequence (UTC):

| Event | UTC | Segment open_ms |
| --- | --- | --- |
| COMPLETE | 2026-11-21 08:15:00.568 |1795241700000|
| COMPLETE | 2026-11-21 10:15:00.674 |1795248900000|
| FAILED ConnectionResetError |2026-11-21 11:07:46.917|1795256100000|
| RESET_RECOVERY_PENDING |2026-11-21 11:07:47.077|not supplied|
| RESET_RECOVERY_STARTED |2026-11-21 11:15:58.433|1795259700000|
| FAILED TimeoutError |2026-11-21 11:18:54.234|1795259700000|

Evidence grade OWNER_REPORTED_LOCAL. Actual sanitized health traces, saved
frame-buffer state, exception chains, current taskXML/config and original
receipt files were not independently available in Work. No second host probe
was requested merely to repeat this already established state.

## Diagnosis, minimum corrections and preserved STOP

`ROOT_CAUSE_NOT_PROVEN` for the real second timeout. The supplied summary
cannot identify handshake, no-frame read, partial frame, outer deadline,
PONG/liveness, quota, process or local I/O phase. Do not blame the network.

The baseline supervisor intentionally permits one persisted recovery successor.
Once claimed, a failed successor must HOLD; no automatic budget reset is
justified. Its old 2-attempt transport logic, however, caught broad
TimeoutError/ConnectionError around the stream and processing loop. That
could retry partial/unknown frame faults despite available parser diagnostics.
The narrow transport delta requires explicit eligible stage and frame-boundary
evidence. Unknown, partial, protocol, source-integrity and local failures stay
terminal. It preserves the exact endpoint, two-connection cap, quota admission
and capped delay; no new source/retention mode or elevated limits.

A normal segment now also persists an execution claim before the collector.
An orphan after a killed process cannot silently start another slot: it enters
LIVE_SERVICE_INCOMPLETE_SEGMENT_REVIEW_REQUIRED. A claim is archived only after
a completed segment or a durably recorded pending/HOLD outcome. Independent
process tests replay original frame persistence, journal ACK and applied
consumer boundaries exactly once, and reject corrupted saved frames.

The operator ticket is an explicit owner-authorized **one-segment** escape
from the already correct safety HOLD, not automatic clearing. Under existing
supervisor+collector locks, deployment preserves installed files/config/taskXML
and old HOLD/claims, pins the replacement, and stages a scoped expiring permit.
The supervisor durably claims the permit before archiving original state or
starting its collector. Failed/crashed claims stay blocked; completed one-shot
also enters `LIVE_SERVICE_OPERATOR_RECOVERY_COMPLETE_REVIEW_REQUIRED`. Ongoing
release/rollover after this operator action needs separate authority. The
original automatic recovery logic remains for ordinary, already-authorized
nonoperator lifecycle and is not invoked after a one-shot recovery fails.

## Evidence and data boundaries

- CI stages the **actual installed assembly model**: pinned286 d0725444... plus
  pinned305 0a45cb6d... transport, overlaid only with current candidate modules.
  Offline failure injection uses production frame reader, quota, parsing,
  persistence and existing research consumer code. Existing green baseline
  44874998831 remains prior-scope evidence; changed seams are tested again.
- The current sustained pilot deliberately uses in-memory original market
  stores and persists sanitized service receipts only. The package does not
  convert them into retained native candles, authenticated original Core/Scanner
  receipts, historical known-at, PIT/OOS, Factory/Lab original E2E or orders.
  Native downstream still returns WAIT_AUTHENTICATED_PARENTS/Secretary WAIT.
- Receipt write/fsync/readback and parent hashes can be tested with generated
  data. They are not independent owner-host custody or successful live recovery.
  A rejected partial frame never creates a candle receipt. Same-key different
  payload and unknown/missing source eligibility stay fail closed.
- Read-only gap inventory uses actual sanitized receipt validation and immutable
  original gap history. Retrospective replacement uses only the separately
  pinned native330 warehouse reader against eligible already-retained data,
  in an isolated subprocess, without acquisition or source mutation. Missing,
  unpublished and quarantined candidates are distinguished. Replacement never
  replaces the original live gap or becomes a forward receipt.
- No actual gap-minute count is inferred from the last receipt **commit time**
  alone: exact missing opens require the private receipt observation.slot and
  confirmed capture watermark. Engineering gap fixtures are synthetic.
- No host task is started/stopped/disabled/re-scheduled, no live source acquired,
  no quota raised, no PR merge/closure, no trading, G0 or scientific promotion.
  Source rights, route/clock/custody remain owner-host verification gates.

## One handoff and independent scope

Use the version-pinned unified Windows entry point in the final delivery.
Default Diagnose is bounded read-only and never starts a collector, clears HOLD
or changes task/runtime. Apply additionally requires explicit owner permission
for exact deployment, ConfigSha256-only task action update, clock probe and
one recovery segment, bound to actual preflight hashes. Do not invoke Apply
under engineering authorization alone. Rollback applies only while the staged
ticket is unused and preserves all evidence; after any consumption, HOLD and
review rather than resetting claims.

Highest possible engineering disposition:
`WS_ENGINEERING_READY_HOST_RECOVERY_NOT_ATTESTED`, never a claim of permanent
connection. Host success requires separately approved new original finalized
receipts, reviewed slot rollovers, observed fault recovery or bounded HOLD,
gap/custody checks and appropriate sustained monitoring. Independent scoped
Audit intake is appropriate after exact code/test evidence exists; implementer
cannot issue independent acceptance. Existing unrelated Registry C audit does
not accept this WS delta. orders=0; trading_authority=NONE; REAL_PIT_OOS_BLOCKED.
