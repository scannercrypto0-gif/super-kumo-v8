# AQL dev_repro_offline — Developer Environment Reproducibility Toolkit

**Issue:** #212 · **Label:** `AQL-CLAUDE-DEV-ENV-REPRO-001`  
**Branch:** `feat/aql-dev-repro-offline-212`  
**Status:** Draft PR — NOT merged · NOT production

---

## Purpose

Offline, read-only toolkit for preparing test environments, running
authorised tests, and collecting tamper-evident evidence — with explicit
version pinning and strict separation of W1 component results.

---

## Safety Constraints (Non-Negotiable)

| Constraint | Detail |
|---|---|
| No protected namespace imports | `src.aql.*`, `research_wp_r0.*` banned |
| No branch mutation | No checkout, rebase, merge, cherry-pick |
| No GitHub writes | No PR open/merge from tool |
| No live data | No market data downloads, no exchange API |
| No fixture mutation | Test commands are read-only |
| Dry-run by default | `--execute` required to actually run tests |
| Immutable bundles | Evidence files raise `FileExistsError` on overwrite |
| W1 never claimed integrated | Core 12/12 + Factory 7/7 ≠ 19/19 integrated |

---

## Module Map

```
tools/dev_repro_offline/
├── __init__.py           Stage 1  — namespace ownership and separation guarantees
├── fingerprint.py        Stage 2  — privacy-safe environment fingerprint
├── manifest.py           Stage 3  — SHA-pinned test manifest with BLOCKED entries
├── preflight.py          Stage 4  — non-mutating preflight checks
├── runner.py             Stage 5  — allowlist-gated subprocess runner (dry-run default)
├── evidence.py           Stage 6  — immutable evidence bundles with tamper detection
├── w1_coordinator.py     Stage 7  — W1 component labelling (Core/Factory separated)
├── portability.py        Stage 8  — Bash + PowerShell wrappers, untested platform markers
├── triage.py             Stage 9  — offline failure categorisation (UNKNOWN for ambiguous)
├── cli.py                Stage 11 — one-command operator workflow
└── tests/
    ├── test_fingerprint.py
    ├── test_manifest.py
    ├── test_preflight.py
    ├── test_runner.py
    ├── test_evidence.py
    ├── test_w1_coordinator.py
    ├── test_triage.py
    ├── test_adversarial.py   Stage 10 — adversarial / reliability tests
    └── test_cli.py
```

---

## W1 Evidence Classification

```
Core W1   — 12/12 passes at SHA 6f8d64f… (owner-recorded, PR #180, unmerged)
Factory W1 — 7/7 passes at SHA 57c8d35… (owner-recorded, PR #209, unmerged)

THESE ARE NOT COMBINED. 12 + 7 ≠ 19 integrated passes.
The W1 coordinator enforces this invariant: integrated_claim is always False.
```

---

## Quick Start (Dry-Run)

```bash
# From repository root — NO tests executed, just environment check
python -m tools.dev_repro_offline.cli --dry-run

# To actually run authorised tests (explicit opt-in required)
python -m tools.dev_repro_offline.cli --execute
```

Evidence is written under `evidence/repro-<timestamp>/`:
- `fingerprint.json` — environment fingerprint
- `manifest.json` — test manifest
- `preflight.json` — preflight check results
- `evidence_bundle.json` — immutable, digest-protected bundle
- `w1_coordinator.txt` — W1 component status
- `SUMMARY.md` — human-readable run summary

---

## Design Decisions

### Dry-Run Default
All subprocess execution requires `dry_run=False` to be explicitly passed.
The CLI requires `--execute`. This prevents accidental test mutation.

### Immutable Evidence
All output files raise `FileExistsError` if they already exist.
Digest-protected: any post-write modification is detected on load.

### BLOCKED ≠ FAIL
A `BLOCKED` manifest entry means the test cannot be run at the current HEAD
(e.g., the expected SHA is on an unmerged PR). This is not a failure — it is
an honest record of what can and cannot be verified.

### Available-at / PIT Safety
No timestamps or information unavailable at test runtime are fabricated.
`available_at_utc = "UNKNOWN"` when PIT cannot be determined.

### Privacy
Home paths, usernames, and HTTPS tokens are redacted before any serialisation.
The repository root is stored only as `SHA-256(redacted_path)`.

---

## CI

Workflow: `.github/workflows/dev-repro-offline.yml`

- pytest with ≥75% branch coverage
- AST namespace isolation scan (no protected imports in production modules)

---

## Related Issues & PRs

| Item | Status |
|---|---|
| Issue #212 | Open — this toolkit |
| Issue #180 (Core W1) | SHA `6f8d64f`, PR unmerged |
| Issue #77 (Factory W1) | SHA `57c8d35`, PR #209 unmerged |
| PR #211 (raw_vault_offline) | Draft — Issue #207 |

---

*AQL-CLAUDE-DEV-ENV-REPRO-001 · Not production · No merge without owner approval*
