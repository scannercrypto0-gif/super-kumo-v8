# WP-000 — Repository and governance bootstrap
Status: IMPLEMENTED, PENDING OWNER REVIEW
Gate: G0
Scope: Git baseline, session protocol, state and decision logs, handoff, secrets exclusion.
Non-goals: Binance integration, Supabase project creation, strategies, backtests, deployments.
Acceptance:
- [x] Repository initialized with main branch and baseline commit.
- [x] Architecture pack preserved and versioned.
- [x] Session start/end checklist and handoff template present.
- [ ] Secrets and runtime data excluded by .gitignore (not verified on remote; file absent from inspected main tree).
- [ ] Owner reviews contract and confirms baseline.
- [x] Public remote repository configured with authorized access: https://github.com/scannercrypto0-gif/super-kumo-v8 (main).
Evidence: historical local Git log; README; SESSION_PROTOCOL.md; public main at commit [879233525b2b716514076654d7c9195efaaf70b0](https://github.com/scannercrypto0-gif/super-kumo-v8/commit/879233525b2b716514076654d7c9195efaaf70b0); [active G0-001 review](https://github.com/scannercrypto0-gif/super-kumo-v8/issues/1).
Verification note (2026-10-20): prior IMPLEMENTED status records the bootstrap history, not verified completion of every acceptance item. Owner review and the remote .gitignore check remain pending; G0 remains OPEN.
Next: Owner review; Claude architecture review and WP-001 proposal.
