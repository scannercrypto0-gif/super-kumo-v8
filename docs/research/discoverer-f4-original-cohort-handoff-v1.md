# Package F4 — Discoverer independent retrospective historical research intake

Parent #274; baseline accepted Discoverer #268 `149ca90c09b96abb45d3bc2839b657711c9826ac`. New Draft PR #276 is stacked on existing E branch and must remain OPEN/UNMERGED.

## Scope

New `tools/strategy_discoverer_offline/historical_f4_intake.py`: an additive schema `aql.discoverer.f4.original-cohort-research-intake.v1`. Only the independent optional research lane consumes this object; Scanner operational selection/Secretary does not import or depend on Discoverer.

The F4 cohort must identify original publisher BTCUSDT BINANCE:SPOT:USDT native 15m, source data/manifest, original archive SHA, publisher checksum, independently sourced provenance, distinct Core245 native and Core253 local query SHA, separately independently approved retrospective `RESEARCH_ONLY` policy, bounded cutoff at/after last closed bar, and `RETROSPECTIVE_NON_PIT` epistemic classification.

The sealed Discoverer candidate/nomination have stable independent IDs and SHA. Missing source/policy proof returns `WAIT_INDEPENDENT_SOURCE_AND_POLICY`, always `NOT_EVALUATED`, `NOT_CONNECTED`, trading NONE, holdout sealed. A bare caller-supplied 'source authenticated' boolean, a SHA without independent custodian or a self-generated policy-approval object **cannot** promote a historical intake. The new local F4 module never issues an eligible Factory receipt or policy approval.

## Receiver contract and workflow

Factory #267/#271 owns the genuine receiver gate. It MUST independently fetch source/custody and research-only policy approval from Core and independent policy-owner records, revalidate candidate/nomination and durable Discoverer ledger from its own authenticated storage, verify source/cohort/cutoff/query/approval parents, and only then issue a **separate** Factory research intake/ACK plus Lab experiment/result. Existing Factory E consumer is synthetic TEST_ONLY; it must not be relabeled historical. That extension is Factory's branch, not #276. A genuine source-positive F4 integration can only be demonstrated when Core F0-F2 and policy F3 are independently ready, and must remain explicitly `RETROSPECTIVE_NON_PIT`; unknown issuer known-at cannot be promoted.

Discoverer F4 readiness `WAIT` is a safe preflight, not a completed historical end-to-end. Owner #274 requests ONE combined F gate and one independent Audit, not per-month or re-opened E audits.

## New focused verification

`tests/test_package_f4_historical_intake.py` checks WAIT/frozen receipt, no Factory admission without independent approvals, synthetic and unknown denial, cutoff mismatch/future, caller boolean forgery, resealed fake admission, unapproved or aliased Core query parents, swapped nomination. CI `.github/workflows/discoverer-package-f4.yml` runs only these new focused tests on Python 3.11/3.12/3.13. The old #268 durability code and accepted tests were not edited.

## Current prerequisites

Core must provide an authenticated historical batch and dual query receipts; separate Policy Owner must approve retrospective NON_PIT research policy; Factory must implement independent original-cohort consumer and Lab result storage; Audit final F only. None of those external conditions is proven by a Discoverer-owned fixture or GitHub's synthetic CI. No Work, merge, G0, holdout or trading.
