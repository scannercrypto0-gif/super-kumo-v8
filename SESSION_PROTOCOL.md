# ATLAS Quant Lab session protocol — mandatory

## START

Every new ChatGPT, Work or Claude session must verify Project ID `AQL-CRYPTO-RESEARCH-001` and canonical repository `scannercrypto0-gif/super-kumo-v8` against current GitHub files before using previous context. If either mismatches, STOP and report a possible cross-project context collision. A matching former name alone is insufficient.

Unrelated conversations describing V7 step 311, `gate_spot_cvd.py`, or other projects are not authoritative evidence of ATLAS Quant Lab implementation. Preserve legitimate repository history and legacy references; use them only with traceable evidence tied to this Project ID and repository.

- Confirm repository location, branch and latest commit (`git status`, `git log -1`).
- Follow the exact reading order and resume map in `00_START_HERE.md`; use the active task and evidence linked from `04_STATE.md`.
- Restate current gate, active WP, blockers, and one exact next action.
- Re-read GitHub each session and reconcile any pending items with actual main, active Issues/PRs and evidence; do not assume a previous handoff was executed.
- Do not implement tasks outside the approved WP.

## EXECUTION
- Use one WP per branch; define acceptance tests before code.
- Preserve point-in-time data semantics, reproducibility and versioning.
- Record failing tests and missing evidence; no silent gate closure.
- Document new architectural choices in `03_DECISIONS.md` before adoption.

## Proactive Work handoff — owner-approved ATLAS-002 requirement

During every ChatGPT, ChatGPT Work or Claude conversation, maintain a logical pending-change ledger (in-session, not a new governance file): bugs discovered; root causes and confirmed fixes; code changes and completed tasks; approved architectural decisions; proposed but unapproved decisions; new requirements/features; validation evidence; blockers and next actions. Keep confirmed facts separate from hypotheses and approvals separate from proposals. Record each item's pending, handed-off, branch-confirmed or merged status with evidence where available.

Checkpoints occur when a meaningful task completes, related changes form a useful batch, a bug is resolved, an approved decision needs documentation, work moves to a new phase, or the user indicates session end. At each checkpoint proactively provide ONE consolidated copy-ready ChatGPT Work instruction using `HANDOFF_TEMPLATE.md`, without waiting for a request. Batch related items; do not generate handoffs when no meaningful changes exist.

If direct authorized GitHub write capability is available, perform the approved scoped action instead of asking the user to relay the same work; return confirmed evidence and remaining pending items. Otherwise automatically supply the consolidated Work instruction. Do not claim GitHub persistence until Work or another authorized tool confirms it. A prepared instruction is pending, a branch/PR is not merged main. Reconcile at the next session.

Prefer existing Issues, PRs and documents over duplicates. Include exact known files and evidence; mark unknown file paths for inspection rather than guessing. Never silently approve architecture, trading logic, promotions or gate closure. Handoff text never includes credentials, API keys or sensitive data. This is proactive behavior within an active conversation, not background automation or a guarantee that an assistant can access GitHub without a connected tool.

## Mandatory continuity and completeness — G0-GOV-01

Before any new Work handoff, follow [the canonical provisional rule](03_DECISIONS.md#g0-gov-01--work-handoff-continuity-and-completeness) and read [HANDOFF_REGISTER.md](HANDOFF_REGISTER.md). Establish the last owner-confirmed SUBMITTED handoff plus addenda, not merely the latest draft. Reconcile the complete since-baseline delta against verified GitHub and actually accessible chats; map every item to included / already documented with evidence / owner-deferred / unresolved. Audit before issuance, request missing references for inaccessible baseline/addenda, and label coverage gaps honestly. Record ID/date/scope/submission confirmation/addenda/resulting PR/review/merge evidence in the register. This applies across chat boundaries and does not grant access to other chats or final approval.

## END
- Completed work must update `04_STATE.md` and append `05_WORK_LOG.md` on GitHub through the authorized PR workflow, with direct evidence links to the relevant PR, commit, Issue, or validation output. Distinguish branch/proposed results from merged main; retain prior log entries.
- Record commit hash, tests executed, outcomes, outstanding issues and next exact task.
- Produce a handoff message using `HANDOFF_TEMPLATE.md`.
- Owner approves gate closures; reviewers cannot self-approve.

## RECOVERY
If context is missing, STOP and reread repository. Never reconstruct the project state from model memory alone.
