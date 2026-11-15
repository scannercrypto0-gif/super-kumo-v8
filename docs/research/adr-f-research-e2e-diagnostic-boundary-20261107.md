# ADR-F-DIAG-01 — Isolated owner-local research E2E diagnostic (provisional B)

**Project:** AQL-CRYPTO-RESEARCH-001  
**Decision owner:** ATLAS PM / architecture (#205)  
**Engineering owner:** Integration (#271), with Core (#275), Scanner (#277), Factory (#267)  
**Date:** 2026-11-07  
**Status:** PROVISIONALLY APPROVED; **not** G0, PR merge, StrategyApproval, F5 acceptance, Paper/live trading, or a claim of independent third-party attestation.

## 1. Objective and alternatives

The immediate goal is to prove that the **already existing** local-first historical research pipeline can consume **the original owner-local** BTCUSDT Spot native 15-minute cohort end to end, compute causally valid strategy diagnostics and reproduce immutable results. The goal is **not** to certify profitable strategies, grant privileged strategy selection, forge an independent signer, or waive the original F5 evidence gate.

* **A — remove existing signatures/approval checks:** REJECTED; would weaken the verified Core/Scanner/Factory F5 contracts.
* **B — isolated, restricted diagnostic with local provenance and deterministic replay:** CHOSEN PROVISIONALLY; exposes no privileged approval outputs.
* **C — full externally independently attested five-role F5:** RETAINED as a **separate mandatory** acceptance/authority gate, not silently reclassified as B.

No standalone Trust Authority service, new canonical warehouse, new RAW pipeline, new duplicate query interface, or broad refactor is authorized by this ADR.

## 2. Non-negotiable trust boundary

Create/use an **explicitly distinct** `RESEARCH_E2E_DIAGNOSTIC` entrypoint and receipt schema, isolated from the currently fail-closed F5 producer/consumer paths. This entrypoint has read-only source access, research-only computing permissions, zero trading permissions, and no ability to invoke any privileged ACK/approval writer. It may use the existing strategy-evaluation and historical-rule calculation kernels as pure functions, **not** invoke protected authentic-F5 admission with a bypass flag.

The diagnostic MUST NOT mint, infer, or serialize a positive `SELECTED`, `Source ACK`, `StrategyApproval`, `Factory Consumer ACK`, `AUTHENTIC_F5_LAB_PASS`, `PIT_ATTESTED`, `G0`, `PAPER_ACTIVATED`, orders, fills, positions or live trading authority. F5 validators and five-role Ed25519 trust registry checks stay unchanged and fail-closed. Never reinterpret a diagnostic owner instruction or self-generated key as independent issuer authority.

If owners cannot implement this isolation without weakening existing trust checks, record `DESIGN_BLOCKED_SECURITY_BOUNDARY` with a concrete API conflict and stop; do not tunnel diagnostics through an approved F5 or Factory consumer-ACK interface.

## 3. Exact original-source scope

Use owner-reported private F2 delivery [Core #275/6658725082](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/275#issuecomment-6658725082) as an **expected pin, not independent re-verification**:

* 2024 BTCUSDT Spot 15m; **10 actually admitted months and 29,376 reported bars**: Jan, Mar, Apr, May, Jun, Jul, Sep, Oct, Nov, Dec.
* February and August 2024 are **inventory-only, not admitted/readback**. Under the existing two frozen Work235 strategies, maintain **24 immutable strategy-month attempt IDs** = 20 potentially runnable + **4 Feb/Aug `UNKNOWN_RETAINED_NOT_READBACK`**. Never call 24 attempts 24 completed backtests; any eligible attempt not actually executed must remain PENDING/NOT_RUN.
* F2 report SHA256: `daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40`; F1 manifest SHA256: `f559c82c2c3827382338ab8f84f4a71a1e6705e08105b9b1bdbfaceb3bcbc8b7`; F1 ledger SHA256: `557c38ecb58d9c0c22784ee105c6cb0a29bf2d4dc2ba44f5ed4e2a08c1a89862`.
* Use existing immutable RAW #211 → **single** canonical warehouse #226 → **distinct** original native #245 and local #253 read-only query receipts. Do not re-ingest private F2, replay stale claims as verified bytes, fabricate missing publisher CHECKSUMs, or copy private ZIP/OHLCV to GitHub. Path to E: is configuration, not interface identity.

An authorized private operator must inspect the real bytes and month membership in its own environment. Matching owner-reported hashes alone is not an independent publisher-rights, known-at/PIT, or external signer attestation.

## 4. Minimal input/output contract for Integration

A one-command private operator wrapper can use existing tools; no new trust platform is needed. Its input must identify: exact assembled Git commits and imported-module byte digests; operator-authorized read-only original F2 report and source/RAW/warehouse parents; per-month native #245 and local #253 query identity and coverage; immutable 24-attempt census IDs; two frozen Work235 strategy IDs, code/definition/DNA/config digests; fully closed UTC 900,000-ms bar cutoffs; explicit fee, spread and slippage assumptions; immutable results-store namespace; and output directory. Protect local source paths, keys and OHLCV.

Produce a **versioned** `aql.research-e2e.diagnostic.v1` sanitized receipt with at least:

- `kind=RESEARCH_E2E_DIAGNOSTIC`, `scope=RETROSPECTIVE_NON_PIT`, `independent_attestation=NOT_ATTESTED`, `operational_authority=NONE`, `owner_operator_authorized` and actual execution environment/scope.
- Exact component HEAD/module SHA, parent F2 + month-level source/warehouse/native/local-query digests, frozen strategy/code/config and UTC cutoff digests.
- A stable **24-attempt census** with per-attempt `NOT_RUN` / `EXECUTED` / `FAILED` / `UNKNOWN_RETAINED_NOT_READBACK` plus the corresponding non-fabricated result/reason/receipt hash; Feb/Aug always UNKNOWN here.
- Causal event/fill accounting: fully closed signal candle, **next-open** execution, stated fees/spread/slippage, ambiguous same-bar stop/target treatment **UNKNOWN**, and explicit missing/gap/coverage failures.
- Immutable run and replay digests, store schema/transaction ID, negative-case outcomes, reproducibility notes and a clear disposition.

Allowed dispositions: `ENGINEERING_PASS_PRIVATE_NOT_RUN`, `DESIGN_BLOCKED_SECURITY_BOUNDARY`, `SOURCE_OR_OPERATOR_INPUT_MISSING`, `DIAGNOSTIC_FAILED`, `RESEARCH_E2E_DIAGNOSTIC_PASS`. The last status is only for **actual owner-authorized original-byte readback, real evaluator and causal Lab execution, deterministic restart/replay, complete denominator and passed negatives**. Public CI fixture/ephemeral signer test cannot produce it.

A diagnostic receipt must never be accepted by the signed F5 Source ACK / StrategyApproval / Consumer ACK interfaces: explicit type/version/authority checks should reject it, even when its SHA and original data are valid.

## 5. One consolidated acceptance test

Integration owns one aggregated run and sanitized handoff; avoid repeated old microgates. The consolidated check must include:

1. Exact current PR HEAD pins for Core/Scanner/Factory/Integration and imported-byte identity; isolate diagnostic from F5. Windows RawVault NTFS lock/crash/fsync/restart checks already covered by Core Windows CI — don't waste a duplicate full cycle unless affected code changed.
2. Original private ZIP/checksum/RAW/warehouse/#245/#253 source graph, 10 admitted months/29,376 reported bars validated against real readback, and Feb/Aug inventory-only.
3. Scanner's actual original Core `query_local` 15m closed-bar evaluation for the two frozen strategies, independent diagnostic code/config/indicator SHA and exact month/cutoff; no future-bar access.
4. Factory **actual causal** calculations for eligible attempts, immutable results, deterministic restart/replay, v1→v2 SQLite migration regression, and duplicate/altered-input rejection; record gaps and unknowns rather than forcing positive trades.
5. Adversarial negatives: wrong ZIP/source or query digest, changed strategy/config, month swap, malicious future timestamp, altered receipt/ledger, replay mismatch, attempted diagnostic-to-F5 authority promotion; each must fail closed.
6. Explicit clean boundary: no signed/unsigned fake approval, no `SELECTED`, `PIT_ATTESTED`, Paper/holdout/trading; compare exact same receipt SHA across restarts. Only sanitized SHA, counts, tests and reasons may go to GitHub.

If owner-private E: is unavailable, deliver one **tested engineering wrapper + exact operator invocation and missing-input checklist**, and report `ENGINEERING_PASS_PRIVATE_NOT_RUN`; never substitute synthetic source or claim a private Lab happened.

## 6. Ownership and gate policy

* **PM/architecture #205:** own this decision, scope/acceptance boundary and final architectural review.
* **Integration #271:** sole implementation/assembly and final diagnostic evidence owner; coordinate latest exact PR heads, operator command, one result packet.
* **Core #275:** read-only source/warehouse/dual-query identities and closed-bar membership; F5 Secretary signatures remain untouched.
* **Scanner #277:** original-bar research evaluator with frozen strategy/code/cutoff and complete attempt census; F5 selection remains unapproved.
* **Factory #267:** original diagnostic causal calculation, sealed results/replay and negative controls; no Consumer ACK.
* **Audit #256:** independent **original F5** verification remains deferred until real signed authorities and original Lab packet exist. If a separate diagnostic review is useful, it cannot be advertised as F5 acceptance.

**Two deliberately separate end states:**

* `RESEARCH_E2E_DIAGNOSTIC_PASS`: scoped pipeline functioning on owner-local original bars, **NON_PIT**, no trusted external approvals or operational rights.
* `AUTHENTIC_F5_ACCEPTED`: **not covered by this ADR**; still needs independently verifiable source rights/custodian, authentic research-only policy and independent evaluator, distinct Core source/strategy and Factory consumer ACK, original Lab/replay, and independent Audit.

**Current recorded state at decision:** exact-head engineering CI reported PASS (Integration #42344221691); private original diagnostic **not executed or independently witnessed here**; authentic F5 `BLOCKED_EXTERNAL_INPUT`. All affected PRs remain OPEN/DRAFT/UNMERGED. Provisional until final owner G0.
