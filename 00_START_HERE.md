## GitHub collaboration update (proposed)
Read `GITHUB_OPERATING_MODEL.md`, `COMMUNICATION_PROTOCOL.md`, and `GITHUB_SETUP_CHECKLIST.md` before multi-agent work. Automated agent-to-agent messaging is NOT enabled merely by uploading these files.

# ATLAS Quant Lab — Project Control
Status: DRAFT pending owner approval | 2026-10-20
SOURCE OF TRUTH: version-controlled project files, never assistant chat memory.
Start every session: verify identity first, then follow the exact new-session reading order below.
End every session: update `04_STATE.md` and append `05_WORK_LOG.md` with evidence links, reviewed commit, remaining blockers and exact next action through the authorized PR workflow; do not describe proposed work as merged.
Current: G0 APPROVED 2026-10-22 — Issue #1 CLOSED (owner sign-off recorded). R09 credential revocation CRITICAL/UNRESOLVED (mandatory before any V7 code or credential reuse). Active: P0 research implementation on branch `p0/aql-p0-historical-decision-v1` (aql.p0.historical-decision.v1 canonical contract). No trading code, no merge, no live data authorized.
Roles: Owner approves scope and gates; ChatGPT architecture/research reviewer; Claude proposed lead implementer starting Thu 2026-10-22 13:00 Riyadh.
Rule: No stage closure without test evidence, review and owner approval.

## Canonical project identity

- Project name: **ATLAS Quant Lab** (owner-approved provisional name).
- Project ID: `AQL-CRYPTO-RESEARCH-001`.
- Official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8).
- Former name: SUPER KUMO V8.
- Owner: `scannercrypto0-gif`.
- Current phase: **G0 APPROVED** (2026-10-22); Issue #1 CLOSED. R09 mandatory before V7 reuse.
- Operational V8 implementation: **not yet verified or started** in this project. Legacy V8 terminology identifies technical/history context, not implementation evidence.

## Project identity verification — ATLAS-001

Every new ChatGPT, Work or Claude session must verify Project ID `AQL-CRYPTO-RESEARCH-001` and canonical repository `scannercrypto0-gif/super-kumo-v8` against current GitHub files before using previous context. If either mismatches, STOP and report a possible cross-project context collision. A matching former name alone is insufficient.

Unrelated conversations describing V7 step 311, `gate_spot_cvd.py`, or other projects are not authoritative evidence of ATLAS Quant Lab implementation. Preserve legitimate repository history and legacy references; use them only with traceable evidence tied to this Project ID and repository.

## New-session reading order

First verify the Project ID and canonical repository above, then record latest `main` SHA. Read in this order:
1. [README.md](README.md)
2. [04_STATE.md](04_STATE.md)
3. [SESSION_PROTOCOL.md](SESSION_PROTOCOL.md)
4. [01_CONTRACT.md](01_CONTRACT.md)
5. [02_ROADMAP.md](02_ROADMAP.md)
6. [03_DECISIONS.md](03_DECISIONS.md)
7. [COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md)
8. [GITHUB_OPERATING_MODEL.md](GITHUB_OPERATING_MODEL.md)
9. The active task/Issue and relevant PR linked in STATE; read its work package under [work_packages/](work_packages/) when present.
10. [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md); for Claude also [07_CLAUDE_HANDOFF.md](07_CLAUDE_HANDOFF.md).

Resume map: current phase and active task → STATE's “Bootstrap and active work”; blockers → “Five unresolved architecture areas” and “Remaining unresolved governance tasks”; next action → “Next exact task”; prior evidence → [05_WORK_LOG.md](05_WORK_LOG.md) and linked commits/Issues/PRs. Read only relevant log entries and task-specific evidence. Do not repeat completed validation unless affected content changed.

## Reusable startup prompt

> Resume ATLAS Quant Lab (AQL-CRYPTO-RESEARCH-001) from https://github.com/scannercrypto0-gif/super-kumo-v8 and follow 00_START_HERE.md. Verify identity on latest main; stop on mismatch. Activate SESSION_PROTOCOL.md's proactive pending-change ledger and checkpoint handoffs: automatically provide one consolidated copy-ready Work instruction when meaningful work is ready, or perform already-authorized direct writes and return evidence. Reconcile pending items with GitHub; G0 FINAL APPROVED 2026-10-22 per closed Issue #1; R09 unresolved before V7 legacy reuse; G1 completion or live/paper/formal B0/OOS authorization is not implied.

## Proactive documentation and Work handoff

Every session must follow [SESSION_PROTOCOL.md](SESSION_PROTOCOL.md#proactive-work-handoff--owner-approved-atlas-002-requirement) and use [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md). The user need not ask again to document meaningful completed work or prepare a consolidated Work instruction. No handoff is needed for an empty change set; do not duplicate already-confirmed direct GitHub work.

## Handoff continuity and completeness — G0-GOV-01

Before generating any new Work handoff, read [HANDOFF_REGISTER.md](HANDOFF_REGISTER.md) and apply [G0-GOV-01](03_DECISIONS.md#g0-gov-01--work-handoff-continuity-and-completeness). Use the latest owner-confirmed submitted baseline plus addenda, account for every delta, and audit completeness. Ask for inaccessible handoff references; never claim unseen cross-chat or execution coverage. The G0-GOV-01 rule remains owner-approved provisional pending its own final adoption; the G0 gate itself was FINAL APPROVED 2026-10-22 per closed Issue #1. R09 remains unresolved before V7 legacy reuse; G1 approval is separate.

## G0 reconciliation source map
Read STATE's dated evidence ledger and the decision register's reconciliation matrix for current source-PR status, provisional INT-01–06 and unresolved parameters. Branch proposals are not main. The canonical GOV-01 definition appears once in DECISIONS; HANDOFF_REGISTER preserves distinct lifecycle events. This reconciliation changes documentation only; it does not grant new implementation, G1, live/paper, formal B0 or OOS authorization beyond the already recorded G0 FINAL APPROVED 2026-10-22 per closed Issue #1.
