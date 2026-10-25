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

## Observed trial evidence — 2026-10-25

- Tested head: `f548f47d9d35204696f740ed646ac19a6f35bdaf`.
- Tooling trial: [run 40189107631](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40189107631), Ubuntu and Windows jobs successful. Ubuntu log: **3 Hypothesis property tests passed**; this is not proof of general defect-detection efficacy.
- Ruff on Ubuntu reported **505 findings** and exited with code 1. Ruff is **advisory at step level**; the overall green job must not be described as Ruff passing. Baseline attribution (existing vs introduced) has **not** been verified.
- G1 [run 40189107642](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40189107642), local archive, SF-IND-02 and SF-STRAT-01 workflows all succeeded at that head. A previously intermittent Windows AG-F02 failure has **not** been root-caused or fixed merely by a subsequent pass.
- Production dependencies remain unchanged; Ruff and Hypothesis are optional development dependencies and run in a separate trial workflow.
- Current evaluation: **CI compatibility demonstrated; tool benefit and cost not yet accepted. No merge approval.**

### Outstanding measurable acceptance evidence

1. Compare Ruff's exact rule counts and locations on the common base / current main versus the PR head using the **same pinned Ruff version and config**. Report only confirmed new findings as new; do not relabel all 505 as legacy.
2. Demonstrate a seeded realistic regression caught by Ruff's selected rules, and a separate seeded archive-contract defect caught by Hypothesis. Keep mutations out of production/main and record the expected failing test plus passing control.
3. Record both-platform durations, versions, resource cost and flaky outcomes; evaluate whether the additional feedback justifies maintenance overhead.
4. Verify no production runtime impact, no core-run blocking, and reversible removal of the optional dependencies/workflow.
5. Request explicit owner approval only after the above; do not treat green CI as automatic adoption.

### PIT boundary-control trial follow-up — 2026-10-25

- `397c884a` introduced a real `decision_context` future-availability rejection property; run 40190172722 passed on Windows and Ubuntu (4 tests on Ubuntu).
- `6c9a143f` added a matching acceptance control but accidentally committed literal `\\n` escape sequences into the test file; run 40190389820 failed on both platforms during collection with `IndentationError`. This is a **test authoring failure**, not a demonstrated production PIT defect.
- `0a67fee1` corrected the formatting. [Run 40190585768](https://github.com/scannercrypto0-gif/super-kumo-v8/actions/runs/40190585768) succeeded on both platforms, with 4 Hypothesis tests passing on Ubuntu in 3.02s; Ruff still reported 505 findings and exited 1 (advisory).
- This is a **positive and negative control for the PIT contract**, but **not a mutation test**: a deliberately weakened implementation has not yet been shown to be detected. Do not claim a defect-detection superiority result from this evidence alone.
