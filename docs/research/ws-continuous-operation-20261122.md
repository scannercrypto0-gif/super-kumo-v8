# Continuous research recovery, 22 November 2026

This extends existing PR321, not a new collector or historical warehouse.
The latest original owner run used both permitted connections: timeout on
attempt1, successful reconnect and two committed 15m bars, reset on attempt2.
The terminal HOLD was correct under the old ONE-segment approval. Root cause
of the external reset/timeout origin remains unproved; do not claim an ISP,
Binance, Windows firewall, NAT or TLS diagnosis without evidence.

## Changed behavior and authority

Continuous operation is **off by default**. The existing guarded operator
requires an explicit continuous-research permit, exact policy digest and
explicit permission to leave missing research intervals visible. The new
owner request to address continuity is the scope extension; installation is
still performed only by the owner-local version-pinned command. The initial
one-use resume ticket remains one segment. A separate config-bound continuous
permit governs later segments until stop/HOLD, without changing task schedule,
principal, settings, endpoint, REST authority or Binance quota Limits.

The exact previously consumed operator claim is backed up and archived after
COMMIT, never silently cleared. Original HOLD, claims, receipts, task XML,
config and runtime backups remain. Existing fail-closed deployment marker and
both locks are reused. Interrupted/incomplete execution claims still require
review; no automatic replay of an ephemeral in-memory segment.

Policy v1 digest:
`7cf6b4ff865fe5fef43ff59fe3f23d7a0cfb555dd76d8b0eb715e8a43f658915`.

- At most **two connections per segment**, unchanged. Additionally at most
  **two charged attempts in every rolling five-minute window across segments**,
  persisted before connect in one local SQLite admission owner. Crash consumes
  admission; no refund, split by segment, or reset on process restart.
- Proven empty frame-boundary receive timeouts can poll the SAME socket for
  less than90seconds since the last complete frame. Polls consume no new
  connection. At90seconds normal fault classification/retry applies. Partial
  headers, length or payload, unknown state, outer deadlines and protocol/data
  failures never resume mid-frame. The original production parser is retained.
- After both attempts fail with demonstrated eligible transport faults, persist
  the failed segment disposition and cooldown before a later eligible scheduled
  segment. Do not continue a consumed segment or invent missing bars. Healthy
  segments use the existing normal rollover. Explicit finalized-source gaps may
  continue only with their outage retained and consumer eligibility blocked.
- Cooldown is exponential30–240seconds, capped by policy300seconds. Existing
  within-segment pinned jitter remains. Four failed segments in a rolling hour
  open a durable HOLD circuit. Success does not erase recent failures. Terminal
  integrity, partial-frame, ban/quota, clock, custody, route or unknown faults
  HOLD immediately. No automatic HOLD clearance or permit renewal.
- Admission history is bounded to100000 events /128MiB; connect history older
  than an hour can be pruned, segment outcomes and immutable source receipts
  remain. Storage exhaustion/corruption/lock conflicts fail closed.

Exception diagnostics add bounded numeric errno/winerror, attempt and committed
counts; exception messages, hosts, credentials and raw payloads are excluded.
These distinguish fault location and budget state, not external network cause.

## Evidence and one local handoff

`tools/ATLAS-WS-CONTINUOUS-RECOVERY.ps1` validates exact candidate and previously
observed installed config, failed slot and consumed authorization, performs
fresh full diagnostic, creates the explicitly scoped short-lived deployment
permit, and invokes the existing tested Apply gate. It NEVER starts a task or
collector manually. Any baseline drift stops rather than rebinding silently.

The same script observes the existing task and verifies real sealed service
receipts, plan/summary integrity, chain, times, gaps, config and runtime hashes.
It requires at least three completed eight-bar production segments, **two
actual normal two-hour rollovers**,24verified receipts, fresh progress, and a
new real fault followed by a later receipt. A Ready task or exit0 is not proof.
Generated offline inputs never count as owner-original operation.

The observer has a24-hour deadline (6–48configurable hours), not a mandatory
72-hour simulation. Completion normally needs at least six hours of original
capture. On HOLD it writes a blocked report immediately; on timeout it writes
NOT_ATTESTED and does not restart or stop the separately authorized service.
If no real fault happens naturally, fault recovery remains unobserved; do not
inject a live fault merely to make a green report. Closing the observer console
also does not create a new task or change the existing service permission.

One JSON report is written under the isolated WS checkout's `owner-results`.
Use `-Mode Observe` to resume observation WITHOUT another Apply/authorization.
A report may explicitly disclose historical/live missing ranges; operational
capture does not mean complete/PIT coverage. Missing forward intervals remain
in service receipt chain `missing_slots` and the existing gap inventory. No
archive/source acquisition or retrospective promotion is added.

Owner Windows E: warehouse and PR330 backfill are untouched. Existing pipeline
remains sanitized ephemeral 15m research, Factory WAIT, Secretary WAIT, no
orders, no trading/PIT/OOS/G0. This package cannot guarantee a network never
fails. A final operational claim requires the original owner-local report;
CI alone is engineering evidence only.
