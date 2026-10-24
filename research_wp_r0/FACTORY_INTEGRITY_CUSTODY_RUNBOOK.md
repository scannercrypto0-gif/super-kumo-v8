# Factory integrity — custody and acceptance runbook

Status: **CODE TESTED; EXTERNAL CUSTODY NOT ATTESTED**.

## Scope
Only `research_wp_r0` on the stacked Draft PR. No live orders, no evaluator,
no merge to `main`. `EVALUATED` remains forbidden.

## Owner custody procedure
1. Produce the immutable full research-plan bytes and digest **before** the
   first attempt. Keep the manifest and digest outside the writer's control.
2. Use an existing dedicated SQLite ledger with `require_admission=True`.
   Reopen it with `expected_checkpoint` from a trusted previous receipt.
3. Append attempts through `FrozenAttemptWriter`. Direct writes must fail
   once the durable admission policy is enabled. Do not expose an arbitrary
   `admission` callback to untrusted writers.
4. At a known checkpoint, use `export_custody_envelope` to write a new
   non-overwriting anchor filename on a separately controlled destination.
   The export helper does **not** create isolation or secure the destination.
5. Verify the exported file using `verify_exported_custody`, then physically
   disconnect or restrict write access to the custody location. Preserve
   plan bytes, checkpoint, and custody file together.
6. During recovery, compare the retained external checkpoint to the SQLite
   chain and verify the external custody file. Fail closed on any mismatch,
   missing database, missing anchor, or unverified plan.

## Acceptance evidence required
- CI success on **the final SHA** for the focused OS/Python matrix and full
  Factory regression.
- Independent operator records: exact plan digest, checkpoint tuple,
  external custody path/media, export timestamp, read-back verification,
  access-control proof, and restore rehearsal outcome.
- Review all code paths that instantiate `AttemptLedger`; existing legacy
  ledgers default to unprotected until explicitly enrolled.
- Exercise **multiprocess** writes and restart tests separately. Existing
  ThreadPoolExecutor tests are concurrent threads, not process isolation.
- The custody file is unkeyed SHA-256 evidence, **not** a signature or proof
  against a malicious writer able to replace both database and anchor.

## Current limitations
- A caller with direct Python access to `AttemptLedger.record_attempt`
  may supply its own admission callback. Durable policy enforces callback
  presence, not the callback's provenance or frozen-plan identity.
- A writer with filesystem privileges can alter the policy table or anchor
  unless OS-level custody separation prevents it.
- The standalone export helper cannot attest to a user's external drive
  being mounted, writable, disconnected, or independently administered.
- No independent external copy has been created or verified by this PR.
- No real evaluator is wired; no completed-trade performance claims allowed.

**Decision: NOT READY for security/governance closure until the above
external custody and bypass controls have independent evidence.**
