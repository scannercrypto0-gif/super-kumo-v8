# ATLAS incremental quality gates — acceptance plan

Status: **trial only**. This document does not certify that any gate has passed.

## Gate sequence

| Gate | Tool / evidence | First enforcement rule |
| --- | --- | --- |
| Static correctness | Ruff `E4,E7,E9,F63,F7,F82` | Enforce only after Linux and Windows trial evidence and review of existing violations. No auto-fixes. |
| Invariants | Hypothesis + pytest | Require property tests against **existing production APIs** (not Python built-ins or test-only reimplementations). |
| Data integrity | Existing ATLAS validation suite | Reject changed, missing, duplicate or inconsistent manifest data with reproducible fixtures. |
| Temporal integrity | Existing ATLAS PIT / no-future-data tests | Historical tests must not read information after decision time. Retrospective-only queries are not PIT evidence. |
| Regression | Targeted existing tests | Select tests based on changed components; avoid unrelated heavy jobs. |
| Portability | Ubuntu + Windows | Collect platform-specific results; never infer Windows PASS from Linux. |

## Hypothesis test candidates (must inspect actual API before implementation)

1. **Manifest round-trip:** for supported manifests, serialization and reloading preserve the same verified content identity.
2. **Tamper detection:** altering any field included in the immutable identity is rejected by the real verifier.
3. **Temporal boundary:** a request with a cutoff never returns bars/events beyond that cutoff.
4. **Idempotency:** replaying the same event/backup request never creates duplicate committed records.

Do not implement placeholder tests that only assert `hashlib`, JSON or Hypothesis itself behaves correctly.

## Baseline and rollout

1. Run trial workflow on both platforms; record job links, tool versions, rule counts, runtime and false positives.
2. Resolve or explicitly baseline any violations without modifying unrelated files.
3. Add property tests using actual public APIs and realistic edge cases.
4. Make **narrow validated checks** required only after stable evidence; keep heavyweight research suites separate.
5. Measure PR review time, escaped defects and flaky checks over subsequent PRs before claiming savings.

## Safety and ownership

- No automatic broad refactoring, no production dependency change, no main merge from this trial.
- Codex's Issue #71 work remains isolated.
- Do not treat DuckDB/Polars benchmarks as proof of production benefit until evaluated on real ATLAS data.
- Final merge requires owner review and explicit acceptance.
