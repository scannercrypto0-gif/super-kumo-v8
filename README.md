## GitHub collaboration update (proposed)
Read `GITHUB_OPERATING_MODEL.md`, `COMMUNICATION_PROTOCOL.md`, and `GITHUB_SETUP_CHECKLIST.md` before multi-agent work. Automated agent-to-agent messaging is NOT enabled merely by uploading these files.

# ATLAS Quant Lab

## Canonical project identity

- Project name: **ATLAS Quant Lab** (owner-approved provisional name).
- Project ID: `AQL-CRYPTO-RESEARCH-001`.
- Official repository: [scannercrypto0-gif/super-kumo-v8](https://github.com/scannercrypto0-gif/super-kumo-v8).
- Former name: SUPER KUMO V8.
- Owner: `scannercrypto0-gif`.
- Current phase: **G0 APPROVED** (2026-10-22); Issue #1 closed. R09 credential revocation mandatory before any V7 code/credential reuse.
- Operational V8 implementation: **not yet verified or started** in this project. Legacy V8 terminology identifies technical/history context, not implementation evidence.

## Context isolation

Every new ChatGPT, Work or Claude session must verify Project ID `AQL-CRYPTO-RESEARCH-001` and canonical repository `scannercrypto0-gif/super-kumo-v8` against current GitHub files before using previous context. If either mismatches, STOP and report a possible cross-project context collision. A matching former name alone is insufficient.

Unrelated conversations describing V7 step 311, `gate_spot_cvd.py`, or other projects are not authoritative evidence of ATLAS Quant Lab implementation. Preserve legitimate repository history and legacy references; use them only with traceable evidence tied to this Project ID and repository.


**Status:** G0 APPROVED (2026-10-22) — Issue #1 closed. R09 credential revocation unresolved (mandatory before V7 reuse). P0 research implementation in progress on branch `p0/aql-p0-historical-decision-v1`.

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
- G0 gate: [Issue #1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1) **CLOSED/APPROVED 2026-10-22**. Active P0 research on branch `p0/aql-p0-historical-decision-v1`.
- [ChatGPT architecture review — Round 1](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1#issuecomment-6285495222): **CONDITIONALLY ACCEPTABLE — NOT YET APPROVED**.

To obtain a local checkout:

```bash
git clone https://github.com/scannercrypto0-gif/super-kumo-v8.git
cd super-kumo-v8
git switch main
```
Do not share a Supabase service-role key or exchange secret in chat.

## Current next step
G0 FINAL APPROVED 2026-10-22 per closed Issue #1. R09 credential revocation remains unresolved and mandatory before V7 legacy reuse. G1 remains a separate gate; G0 approval does not authorize live/paper trading, formal B0/OOS evaluation, or a P0 historical smoke run. Current bounded P0 DEV integration is tracked in Draft PR #204 and requires independent Audit disposition before any separately authorized trial; see [current state](04_STATE.md).
