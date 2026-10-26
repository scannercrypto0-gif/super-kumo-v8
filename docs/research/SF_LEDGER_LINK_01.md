# SF-LEDGER-LINK-01 — Synthetic-only Factory evidence attachment

Authority: owner explicitly approved a *single limited Draft implementation PR*
after provisional SF-DEC-20 B and previously merged #123. No merge/OOS/PAPER/live/G0
permission is included. GitHub is the source of truth.

## Objective and boundary

Re-use the **existing** `AttemptLedger` and `FrozenAttemptWriter`: enroll an
explicit `research-plan-1` family with BASE/SHADOW candidate identities and
sealed digest of the exact Breakout 500-bar synthetic fixture, protocol, scenario
costs and no-selection policy. Both candidate attempt states stay **PENDING**.
They cannot become `COMPLETE`; no PnL result is inserted into the old attempt
event schema. Use a separate *synthetic-result-evidence* table inside the
**same Factory SQLite file** and transaction boundary, not a separate competing
Core lifecycle ledger. This extends the SQLite schema additively without
changing PR-accepted `receipts` rules or user_version=1.

Public narrow API: `frozen_pilot_family`,
`record_synthetic_result`, `read_synthetic_evidence`. Result registration
checks the retained expected family/plan/data digests, full current frozen
family admission, BASE and SHADOW exact version identities, paired scenario
costs, and full result equality against **newly computed deterministic
synthetic replay**. It hashes a canonical evidence record that points to the
existing attempt-ledger checkpoint and two version-result digests. The bounded
append is SQLite-transactional and idempotent for identical result identity;
same identity with changed contents fails. Replay verifies chain plus the
attempt ledger prefix commitment. Caller may pass independently retained
checkpoint for rollback detection. No automatic external custody/anchor is
provided or claimed; caller-supplied digest alone is not authentic prior freeze.

`SYNTHETIC_INTEGRATION_RESULT_NOT_RESEARCH_COMPLETE` is an **evidence label**,
not a recognized AttemptLedger lifecycle state. The old `COMPLETE` path remains
blocked. Core-owned candidate WATCH/TRIGGER/READY, scanner stage and paper
execution events are NOT written here. It is not a real research qualification,
not independently timestamped fills, not real data, not a frozen holdout/OOS,
not PAPER, and not an operational trading engine.

## Acceptance boundary

Focused synthetic tests cover sealed BASE/SHADOW plan admission, append/replay,
digest/candidate identity, idempotent duplicate receipts, missing PENDING,
changed result with recomputed digest (replay mismatch), changed plan/data,
invalid actual-fill/OOS/PAPER claims, tampering, missing evidence and checkpoint
rollback, and preserving old AttemptLedger state. Existing broader tests and
historical P0 remain unmodified. Failure of targeted CI blocks this Draft.
Do not merge without owner approval. Core #92 must acknowledge shared ownership
notes under CROSS-ARCH-01 before any later *joint* implementation.
