## GitHub collaboration update (proposed)
Read `GITHUB_OPERATING_MODEL.md`, `COMMUNICATION_PROTOCOL.md`, and `GITHUB_SETUP_CHECKLIST.md` before multi-agent work. Automated agent-to-agent messaging is NOT enabled merely by uploading these files.

# ATLAS Quant Lab

## Canonical project identity

- Project name: **ATLAS Quant Lab** (owner-approved provisional name).
- Project ID: `AQL-CRYPTO-RESEARCH-001`.
- Official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8).
- Former name: SUPER KUMO V8.
- Owner: `scannercrypto0-gif`.
- Current phase: **G0 OPEN**; G0-001 remains OPEN.
- Operational V8 implementation: **not yet verified or started** in this project. Legacy V8 terminology identifies technical/history context, not implementation evidence.

## Context isolation

Every new ChatGPT, Work or Claude session must verify Project ID `AQL-CRYPTO-RESEARCH-001` and canonical repository `scannercrypto0-gif/super-kumo-v8` against current GitHub files before using previous context. If either mismatches, STOP and report a possible cross-project context collision. A matching former name alone is insufficient.

Unrelated conversations describing V7 step 311, `gate_spot_cvd.py`, or other projects are not authoritative evidence of ATLAS Quant Lab implementation. Preserve legitimate repository history and legacy references; use them only with traceable evidence tied to this Project ID and repository.


**Status:** G0 OPEN — design contract DRAFT, no trading code or cloud integration.

## First read (every session)
1. `00_START_HERE.md`
2. `01_CONTRACT.md`
3. `02_ROADMAP.md`
4. `03_DECISIONS.md`
5. `04_STATE.md`
6. Current work package in `work_packages/`

## Workflow
- Work on a separate branch `wp/NNN-short-name`.
- Every change includes acceptance evidence and an update to `04_STATE.md` and `05_WORK_LOG.md`.
- Owner approval is required to close a gate or promote a strategy.
- ChatGPT and Claude must read repository files; chat memory is not authoritative.
- Never commit credentials, raw personal data, or proprietary market-data dumps.
- `git status` and `git log -5 --oneline` at each session start.

## Official repository and setup
- Source of truth: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8) (Public).
- Official owner: `scannercrypto0-gif`.
- Default branch: `main`.
- Bootstrap: WP-000 governance files are published; owner review remains pending.
- Active work: [G0-001 architecture review — Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) (OPEN).
- [ChatGPT architecture review — Round 1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1#issuecomment-6285495222): **CONDITIONALLY ACCEPTABLE — NOT YET APPROVED**.

To obtain a local checkout:

```bash
git clone https://github.com/scannercrypto0-gif/super-kumo-v8.git
cd super-kumo-v8
git switch main
```
Do not share a Supabase service-role key or exchange secret in chat.

## Current next step
Claude performs an independent architecture review using `07_CLAUDE_HANDOFF.md`. The owner resolves or explicitly defers critical questions with rationale and approves the final contract before authorizing G0 closure and G1 work. The five unresolved areas are paper execution, temporal integrity, recovery/idempotency, research methodology, and operational budgets; see [current state](04_STATE.md). G0 and G0-001 remain OPEN; this review does not authorize production implementation.
