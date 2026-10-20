# ADR register — PROPOSED, not yet approved
001 new V8, legacy V7.3 read-only reference
002 modular monolith
003 Binance Spot USDT only
004 Supabase central, optional object storage and local spool
005 independent paper trades without capital portfolio
006 momentum first
007 independent same-symbol traders, correlated evidence
008 external events research-first
009 owner approves shadow promotion
010 point-in-time immutable decisions
011 4/24/72h forward horizons, max/min
012 gate evidence and owner signoff required
New ADR: ID | problem | options | decision | tradeoffs | affected interfaces | migration | approval.
Never overwrite approved decisions; supersede explicitly.

## G0-GOV-01 — Work Handoff Continuity and Completeness

Status: **OWNER-APPROVED PROVISIONAL GOVERNANCE RULE — NOT FINAL G0 APPROVAL**.
Scope: every future Work handoff across ChatGPT, ChatGPT Work and Claude conversations for ATLAS Quant Lab (`AQL-CRYPTO-RESEARCH-001`). Recording this rule does not implement application code or authorize merges.

Before issuing a new handoff:
1. Identify the latest handoff the owner confirms was actually submitted, including every subsequent addendum. Do not substitute the latest draft, PR creation time or tool-received instruction for explicit owner confirmation of submission elsewhere.
2. Consult [the canonical handoff register](HANDOFF_REGISTER.md), current GitHub evidence, and available conversation records, including other chats only when actually accessible.
3. Build a delta ledger of EVERY decision, owner clarification, requirement, correction and exception agreed since that submitted baseline; capture source/reference, date, approval status and known addenda.
4. Cross-check each delta item against the new handoff and repository documentation actually verified, including unmerged branches distinguished from main.
5. Give every item exactly one accountable disposition: INCLUDED (new handoff section), ALREADY DOCUMENTED (verified file/commit/PR evidence and merge state), OWNER-DEFERRED (owner decision/reference and revisit condition), or UNRESOLVED (gap/blocker and next action). Never silently drop an item.
6. Never claim another conversation, Work execution, PR or repository change was inspected unless its evidence was actually accessed; summaries and hearsay are not execution confirmation.
7. If an earlier handoff/addendum is inaccessible, explicitly mark the coverage gap and request the missing reference/content. Do not claim full completeness; do not issue a purportedly complete handoff until material gaps are resolved or explicitly scoped/deferred by the owner.
8. Run a final completeness audit before issuing: baseline/submission evidence and addenda identified, ledger items all mapped, approvals/proposals separated, repository evidence current, gaps stated. Report PASS or COVERAGE GAP; do not relabel a gap as PASS.
9. Record new handoff ID, date, scope, owner-confirmed submission status/evidence, addenda, resulting PR and review/merge status in [HANDOFF_REGISTER.md](HANDOFF_REGISTER.md). Distinguish drafted, submitted, tool-received, PR-open and merged facts; reconcile later updates with evidence rather than guessing.
10. All decisions remain provisional until the owner explicitly grants final approval; neither handoff completeness nor a documentation merge is architecture/trading/gate approval.

Use existing protocols and [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md); register only traceability metadata and delta audit, not duplicate full decision specifications. Direct authorized-write checkpoints use the same evidence/continuity discipline and record actual actions, without generating duplicate copy/paste work.
