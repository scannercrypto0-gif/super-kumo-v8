## GitHub collaboration update (proposed)
Read `GITHUB_OPERATING_MODEL.md`, `COMMUNICATION_PROTOCOL.md`, and `GITHUB_SETUP_CHECKLIST.md` before multi-agent work. Automated agent-to-agent messaging is NOT enabled merely by uploading these files.

# ATLAS Quant Lab — Project Control
Status: DRAFT pending owner approval | 2026-10-20
SOURCE OF TRUTH: version-controlled project files, never assistant chat memory.
Start every session: verify identity first, then follow the exact new-session reading order below.
End every session: update `04_STATE.md` and append `05_WORK_LOG.md` with evidence links, reviewed commit, remaining blockers and exact next action through the authorized PR workflow; do not describe proposed work as merged.
Current: G0 OPEN; WP-000 bootstrap published at https://github.com/scannercrypto0-gif/super-kumo-v8, pending owner review; active work is G0-001 architecture review in Issue #1. ChatGPT Round 1 is complete with conditional acceptance, not approval; Claude review, critical-question resolution and owner sign-off remain pending. No trading code started.
Roles: Owner approves scope and gates; ChatGPT architecture/research reviewer; Claude proposed lead implementer starting Thu 2026-10-22 13:00 Riyadh.
Rule: No stage closure without test evidence, review and owner approval.

## Canonical project identity

- Project name: **ATLAS Quant Lab** (owner-approved provisional name).
- Project ID: `AQL-CRYPTO-RESEARCH-001`.
- Official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8).
- Former name: SUPER KUMO V8.
- Owner: `scannercrypto0-gif`.
- Current phase: **G0 OPEN**; G0-001 remains OPEN.
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

> Resume ATLAS Quant Lab, Project ID AQL-CRYPTO-RESEARCH-001, from https://github.com/scannercrypto0-gif/super-kumo-v8. Verify both identity fields on latest main before using previous context; stop on mismatch. Follow 00_START_HERE.md's reading order, report current gate, active task, blockers and next authorized action, then work only within approved scope. Update STATE and append WORK_LOG with evidence links through the authorized PR workflow; do not close G0 without owner approval.
