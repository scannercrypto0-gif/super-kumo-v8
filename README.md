## GitHub collaboration update (proposed)
Read `GITHUB_OPERATING_MODEL.md`, `COMMUNICATION_PROTOCOL.md`, and `GITHUB_SETUP_CHECKLIST.md` before multi-agent work. Automated agent-to-agent messaging is NOT enabled merely by uploading these files.

# SUPER KUMO V8

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

## Setup
This is a **local Git repository**, not a GitHub/GitLab remote.
To publish it later, create a private empty remote repository and run:
```bash
git remote add origin <YOUR_PRIVATE_REMOTE_URL>
git push -u origin main
```
Do not share a Supabase service-role key or exchange secret in chat.

## Current next step
Review and approve G0 contract, then Claude reviews `07_CLAUDE_HANDOFF.md` and proposes WP-001.
