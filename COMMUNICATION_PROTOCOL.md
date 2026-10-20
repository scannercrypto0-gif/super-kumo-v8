# Three-party Communication Protocol — V8
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
Read README, 00_START_HERE, 04_STATE, 02_ROADMAP, GITHUB_OPERATING_MODEL, open assigned issues, relevant PRs.
Record last reviewed commit SHA; do not trust old copies.
At every session end update state, work log, unresolved issues and handoff.

## Example
From: Claude
To: ChatGPT
Type: REVIEW
Context: PR #12 commit abc123
Question or result: Market candle close-time handling implemented
Evidence: tests/test_candles.py, test log attached
Requested action: review as-of correctness and failure paths
Status: OPEN
