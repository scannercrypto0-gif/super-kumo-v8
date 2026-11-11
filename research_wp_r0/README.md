# WP-R0 — Research Integrity Vertical Slice

**Status:** isolated synthetic-only prototype; requires actual test evidence and review.  
**Project:** ATLAS Quant Lab `AQL-CRYPTO-RESEARCH-001`.  
**Design dependency:** [research architecture PR #17](https://github.com/scannercrypto0-gif/super-kumo-v8/pull/17), OPEN/DRAFT/unmerged at start. Reference-only; implementation branch starts from main, no cherry-pick or modification to #17 or G0/G1.  
**Gate:** G0 OPEN; WP-R0 explicitly authorized by owner for isolated implementation, not for merge/G0/G1 integration.

## What is implemented

Python stdlib-only module `research_wp_r0/integrity.py` implementing:
- UTC-aware decision-cutoff classifier for verified historical knowledge, modeled replay, and unknown/unavailable events; finalized-bar timing.
- Frozen experiment protocols, digestable deterministic run manifests and seeded normalized run result hashes.
- Version-specific evidence dependency DAG with append-only validity revisions and correction impact set.
- In-memory experiment register with complete/partial publication boundary, stable result idempotency and candidate trial logs.
- Audited holdout custody (opening holdout + subsequent retuning revokes untouched claim).
- Explicit research permission allowlist denying operational trader/gate/billing mutation.
- Independent idealized synthetic-null p-value selection harness with Bonferroni family threshold.

Tests in `tests/test_research_wp_r0.py` exercise temporal leakage, final bars, missing receipt, frozen protocols, deterministic replay, lineage blast radius, holdout re-use, retry/idempotency, synthetic null search and denied authority.

**Run from repository root:**
```bash
python -m unittest discover -s tests -p 'test_research_wp_r0.py' -v
```

No dependencies beyond Python 3.10+ stdlib. Do not run this experimental module inside core market monitoring.

## Strict limitations

This is a **minimal in-memory boundary probe**, not a database-backed production proof. The permission allowlist is an API prototype, **not** an OS/network/database security isolation guarantee. The evidence graph is not persisted. Job scheduling/CPU-IO admission and bounded resource isolation are **specified but not implemented**. No live provider, no Supabase, no real position monitor, no realistic market fills, and no news ingestion. The null harness assumes independent valid Uniform(0,1) p-values; it does not validate signal discovery under dependence, biased labeling, real backtests or multiple AI-driven model searches. Audit logs are ephemeral. Holdout taint semantics apply to this object instance only. Historical receipt metadata must be independently verified upstream.

Counterfactual paper TP/SL semantics and genuine adversarial statistical validity require later work. Test coverage is **not** equivalent to real operational gating.

## Evidence and execution status

- Repository/code writing: authorized for this research-only branch.
- Uploaded test file: yes.
- Local test invocation attempted during preparation; **blocked** before collection because the current execution container could not resolve `raw.githubusercontent.com` to retrieve connector-uploaded source files. The resulting `Ran 0 tests` is **not** a test pass.
- Runtime/unit/integration coverage: **NOT VERIFIED** until command above executes in a checkout or trusted CI and emits evidence.
- Do not promote or merge on the basis of this documentation.

## Acceptance tracking

| ID | Prototype evidence | Limit |
|---|---|---|
| RAI-01 | time classifier + fixtures | source policy integration pending |
| RAI-02 | frozen protocol + holdout audit | persisted access custody pending |
| RAI-03 | seeded result digest tests | verified execution pending |
| RAI-04 | dependency DAG + correction impact | persistence/correction jobs pending |
| RAI-05 | synthetic null Bonferroni harness | dependent-search calibration pending |
| RAI-06 | no operational connector imported | actual resource isolation benchmark pending |
| RAI-07 | API allowlist | enforce at real process/DB boundaries later |
| RAI-08 | not implemented | isolated paper counterfactual future WP |
| RAI-09 | no ingestion/LLM endpoints | untrusted source sandbox future WP |

## Review/next step

1. Run tests and capture Python version, exact commit SHA, command, standard output, fixture/code hash and failures.
2. Review acceptance gaps, especially actual resource quotas and operational permission enforcement. No production integration before relevant G0/G1 gates.
3. Review this branch only; separately approve any merge or new work. Existing PRs and operational contracts remain unmodified.

**No deployment, live trading, merge or G0 approval is authorized.**
