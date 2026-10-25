# Factory integrity — custody and acceptance runbook

Status: **ADMISSION REMEDIATION FOR REVIEW; EXTERNAL CUSTODY BLOCKED / NOT ATTESTED**.

## Scope
Factory-only remediation from merged #78/#89, linked to #77. Do not use an old
unmerged research stack or create another storage backend. No live orders,
evaluator, merge to main or final holdout. COMPLETE remains disabled.

## Owner custody procedure
1. Produce the immutable full research-plan bytes and digest **before** the
   first attempt. Keep the manifest and digest outside the writer's control.
2. Use an eligible empty Factory AttemptLedger, then construct
   `FrozenAttemptWriter(ledger, raw_plan, expected_digest)`. Its constructor
   binds exact plan/digest and admission flag transactionally before receipts.
   Reopening the same plan is idempotent. Reopen with expected_checkpoint from
   a separately trusted prior receipt. Reject nonempty unsealed history,
   different plans, missing schema/policy or unsupported journal mode; never
   silently repair, migrate or retroactively bless a legacy database.
3. Append through that writer. Ledger-side membership is mandatory inside
   the write lock even if a direct caller supplies admission=lambda *_:None.
   Unplanned family/candidate/strategy rejects; protected-but-unbound ledgers
   cannot use callbacks as membership authority. A callback remains an extra
   policy check, not a way to replace the sealed manifest.
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

## Current limitations and threat model
- The default-path callback bypass was a caller/API-level defect; it is the
  remediation scope here. Local integrity is not an OS security boundary.
- A writer with filesystem privileges can alter the policy table or anchor
  unless OS-level custody separation prevents it.
- The standalone export helper cannot attest to a user's external drive
  being mounted, writable, disconnected, or independently administered.
- No independent external copy has been created or verified by this PR.
- No real evaluator is wired; no completed-trade performance claims allowed.

**Decision: NOT READY for security/governance closure until the above
external custody and bypass controls have independent evidence.**

## Reproducible custody-gap inventory (no new infrastructure)

| Existing asset | What code/tests establish | What they do not establish |
|---|---|---|
| frozen_research_plan / reconciliation | Canonical candidate/protocol/data/split/baseline/metric/selection/cost commitments and missing/pending inventory | Source authenticity, real historical coverage, untuned OOS or evaluated results |
| AttemptLedger / frozen writer | Serialized local seal, exact plan membership, immutable receipt/checkpoint replay | Attacker-proof local SQLite policy, independent checkpoint owner or initial plan approval |
| factory_custody_envelope | Domain-separated unkeyed checksum and exact supplied-plan/checkpoint comparison | Signature, authenticated custody, independently supplied reference or trusted timestamp |
| factory_custody_export | Exclusive export path, file flush, readback, supported directory-sync attempt | Actual separate media, independent ACL/account administration, guaranteed Windows directory durability or power-loss protection |

Run `python -B -m pytest -p no:cacheprovider research_wp_r0/test_frozen_default_admission.py -v`.
Its same-principal local-export case creates a synthetic anchor in a disposable
writer-writable directory, replaces it with a different correctly checksummed
envelope, and shows that only the retained original reference detects replacement.
Changing the reference too makes self-consistency pass. This is a local gap
demonstration, not external custody or evidence of an actual incident.

## Separate custody acceptance plan — BLOCKED

1. Owner identifies a separately administered destination/identity and initial
   trusted plan reference, explicit access/retention/restore policy and secure
   route. No provider/media/account is selected or accessed by this PR.
2. Under the actual research writer identity, prove OS/account denial of edits,
   deletion and replacement of retained anchors; record sanitized independent
   operator evidence. A local hash test or a second path is insufficient.
3. Independent custodian reads back the pre-attempt plan reference and later
   checkpoint, binds them to exact source/data/split versions and records custody
   time/identity. This does not invent missing source receipts or open holdout.
4. Isolated restore drill verifies expected original commitments, missing or
   replaced DB, prefix rollback and wrong/full rewritten plan+receipt+anchor
   rejection relative to the independently retained reference. Preserve all
   incident originals; no automatic repair or production data deletion.
5. Independent reviewer accepts only demonstrated sub-scopes. Until real custody
   evidence exists, #77 remains blocked regardless of admission tests/CI success.

Result versus attempt: PENDING/INPUTS/INVALID/FAILED/ABANDONED are receipt states;
NOT_EVALUATED inventory and an export hash are not completed evaluations,
profitability/OOS evidence or promotion authority. No new evaluator or service.
