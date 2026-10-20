# Three-party Communication Protocol — ATLAS Quant Lab
Project ID: `AQL-CRYPTO-RESEARCH-001`; canonical repository: `scannercrypto0-gif/super-kumo-v8`.
Status: PROPOSED
Communication is asynchronous and auditable, not a claim of persistent AI presence.

## Format for each handoff comment
**From:** Owner | ChatGPT | Claude
**To:** Owner | ChatGPT | Claude
**Type:** QUESTION | REVIEW | DECISION_REQUEST | IMPLEMENTATION | TEST_EVIDENCE | BLOCKER
**Context:** issue/PR and exact commit SHA
**Question or result:** one concrete item
**Evidence:** file paths, test logs, data samples
**Requested action:** who should do what
**Deadline:** only if owner specifies
**Status:** OPEN | ANSWERED | BLOCKED

## Source precedence
1. Owner-approved decision records and merged specifications
2. Current main branch and approved issue scope
3. PR evidence and comments
4. Conversation summaries
In case of contradiction, raise a decision-request issue rather than silently choosing.

## At every session start
Verify the canonical identity using `00_START_HERE.md` and `SESSION_PROTOCOL.md` before using previous context; stop on a Project ID or repository mismatch.
Read README, 00_START_HERE, 04_STATE, 02_ROADMAP, GITHUB_OPERATING_MODEL, open assigned issues, relevant PRs.
Record last reviewed commit SHA; do not trust old copies.
At every session end update state, work log, unresolved issues and handoff.

## Work handoff delivery

The owner-approved proactive checkpoint/ledger behavior is defined once in [SESSION_PROTOCOL.md](SESSION_PROTOCOL.md#proactive-work-handoff--owner-approved-atlas-002-requirement). Use [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md) for ONE consolidated copy-ready Work instruction when direct authorized writes are unavailable; no repeated user request is needed. Existing comment format above still applies to actual issue/PR communication. A handoff is not proof of upload or approval; report tool-confirmed links and distinguish pending, branch and merged outcomes. Reading this protocol grants no extra write/merge or person-directed messaging authorization.

## Example
From: Claude
To: ChatGPT
Type: REVIEW
Context: PR #12 commit abc123
Question or result: Market candle close-time handling implemented
Evidence: tests/test_candles.py, test log attached
Requested action: review as-of correctness and failure paths
Status: OPEN
