# AQL Integration Intelligence Toolkit
**Issue:** #210 — AQL-CLAUDE-INTEGRATION-RELEASE-INTELLIGENCE-001  
**Branch:** `integration/aql-intel-001`  
**Classification:** READ-ONLY · OFFLINE-FIRST · NO MERGES · NO APPROVALS

---

## Purpose

A modular, offline-first toolkit for analysing the ATLAS Quant Lab PR
estate: dependency graphs, file-level collisions, acceptance evidence,
CI coverage gaps, scientific claim flags, and release-readiness gates.

**This toolkit never merges, approves, deploys, or accesses live GitHub at runtime.**

---

## Modules

| Module | Stage | Purpose |
|--------|-------|---------|
| `denylist.py` | 1 | Protected path registry; `assert_allowed()` for write safety |
| `schema.py` | 2 | Snapshot JSON schema validation + digest |
| `dag.py` | 3 | PR dependency DAG: cycles, missing parents, candidate review order |
| `collision.py` | 4 | File-level collision classifier (DIRECT / PROTECTED / SHARED CONTRACT) |
| `evidence_registry.py` | 5 | Immutable acceptance evidence index; invalidates on head SHA change |
| `ci_coverage_plan.py` | 6 | Read-only coverage label + proposed test commands (never executed) |
| `claim_firewall.py` | 7 | Risk-term scanner; emits REVIEW_REQUIRED, never a scientific verdict |
| `release_readiness.py` | 8 | 7-gate readiness report; verdict is READY_FOR_OWNER_REVIEW or BLOCKED |
| `operator_report.py` | 9 | Full JSON + Markdown report builder with threat model and limitations |

---

## Threat Model

1. **OFFLINE-FIRST** — No network calls at runtime. Snapshot is the sole input.
2. **READ-ONLY** — No git writes, PR approvals, merges, or deployments.
3. **STALE DATA RISK** — Every report includes `snapshot_age_hours`. Re-snapshot if stale.
4. **EVIDENCE TRUST** — Evidence is self-reported unless labeled `INDEPENDENT_AUDIT`.
5. **CLAIM FIREWALL** — Pattern-based only; novel risk phrasings may not be detected.
6. **PATH ANALYSIS** — Linux case-sensitive; Windows case conflicts flagged but not enforced.
7. **GOVERNANCE** — Only the project owner (`scannercrypto0-gif`) can approve or close stages.
8. **ACCESS LIMITS** — Cross-chat sources (PM notebook #205) and Issue #207 RAW vault status are UNKNOWN.

---

## Known Limitations

- Claim firewall is regex-based; novel risk phrasings may not be detected.
- Coverage plan proposes tests but cannot execute them.
- DAG cycle detection runs on declared `depends_on` only; implicit stacking may not be captured.
- Evidence entries are self-reported unless marked `INDEPENDENT_AUDIT`.
- Snapshot staleness is reported but not automatically remediated.
- Path collision analysis is Linux-native; Windows behavior may differ.
- Cross-chat sources (PM notebook #205) are inaccessible.
- Issue #207 RAW vault delivery status is UNKNOWN.

---

## Test Coverage

| Stage | Test File | Tests |
|-------|-----------|-------|
| 1 | `test_denylist.py` | 16 |
| 2 | `test_schema.py` | 22 |
| 3 | `test_dag.py` | 18 |
| 4 | `test_collision.py` | 18 |
| 5 | `test_evidence_registry.py` | 11 |
| 6 | `test_ci_coverage_plan.py` | 11 |
| 7 | `test_claim_firewall.py` | 22 |
| 8 | `test_release_readiness.py` | 15 |
| 9 | `test_operator_report.py` | 15 |
| 10 | `test_adversarial.py` | 29 |
| **Total** | | **177 PASS, 0 FAIL** |

---

## Governance

This toolkit does not declare any PR approved, any stage closed, or any
release authorized. Those decisions belong exclusively to the project owner.

All analysis output includes a `classification` field that explicitly states
this. The `READY_FOR_OWNER_REVIEW` verdict is not an approval — it means
the automated gates have no blocking findings to report.
