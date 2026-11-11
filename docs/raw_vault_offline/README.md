# AQL Raw Vault Offline — `tools/raw_vault_offline/`

**Issue**: #207 · **Branch**: `feat/aql-raw-vault-offline-207`  
**Status**: Draft — NOT merged to `main`  
**Classification**: Offline non-production research toolkit. No live exchange, no production data, no protected namespace imports.

---

## Purpose

Provides a modular, fixture-driven offline toolkit for:

1. Storing and verifying raw historical market-data fixtures (content-addressed, immutable)
2. Detecting temporal gaps, duplicates, and out-of-order bars
3. Tracking a transparent correction lineage (generation-0 preserved forever)
4. Deriving normalised research views with per-row provenance
5. Simulating async archival with crash recovery and retention dry-runs
6. Producing reproducible operational evidence reports

This toolkit is **research infrastructure only**. It never touches live APIs, production databases, or existing protected modules.

---

## Module Map

| Stage | File | Responsibility |
|-------|------|---------------|
| 1 | `__init__.py` | Namespace declaration, separation guarantees |
| 2 | `schema.py` | Enums, failure taxonomy, `RawObjectMeta`, `content_key`, `logical_identity_key`, `safe_filename` |
| 3 | `vault.py` | Write-once content-addressed vault (fsync + atomic rename, fcntl.flock) |
| 4 | `archive_verifier.py` | ZIP/CSV custody verification, adversarial fixture generator |
| 5 | `coverage.py` | Temporal gap/overlap/duplicate/out-of-order analysis |
| 6 | `corrections.py` | Append-only correction chain ledger (JSONL) |
| 7 | `derived_view.py` | Offline canonical row view with per-row provenance |
| 8 | `archival_sim.py` | Durable archival queue, crash recovery, retention dry-run |
| 9 | `evidence_report.py` | Operational evidence report generator |
| — | `tests/` | Isolated pytest suite covering all stages |

---

## Key Design Decisions

### Two-key model
- **Content key**: `SHA-256(raw_bytes)` — addresses the physical object
- **Logical identity key**: `SHA-256(canonical JSON of identity fields)` — addresses the logical slot

Same content + same identity → idempotent admission.  
Same identity + different content → `IdentityConflict` (fail closed, never overwrite).

### Immutability
- Objects are written once via `staged temp → fsync → atomic rename`
- No delete path. No overwrite path.
- Corrections add new objects; generation-0 bytes are permanently addressable.

### Half-open intervals
All temporal coverage windows use `[start_utc_ms, end_utc_ms)`.  
Gaps are **reported**, never silently filled.

### Crash safety
- Vault: `.staging/*.obj.tmp` is atomically renamed on commit; orphans are recoverable
- Archival queue: durable JSONL intent log; `PROCESSING` → `PENDING` on restart
- Correction ledger: append-only JSONL; no mutation of existing entries

### No PIT fabrication
`available_at_utc` is `"UNKNOWN"` when source capture time is unavailable.  
`pit_capture_declared=False` unless explicitly known.

---

## Separation Guarantees

This toolkit **does NOT** import from:
- `src/aql/observation/**`
- `src/aql/collector/**`
- `src/aql/delivery/**`
- `src/aql/journal/**`
- `src/aql/recovery/**`
- `src/aql/storage/**`
- `src/aql/archive/**`
- `research_wp_r0/**`

The CI workflow (`raw-vault-offline.yml`) enforces this with an AST import scanner.

---

## Running Tests

```bash
# From repo root
python -m pytest tools/raw_vault_offline/tests/ -v --tb=short
```

No live network, no credentials, no exchange access required.

---

## Evidence Report

```python
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline.corrections import CorrectionLedger
from tools.raw_vault_offline.archival_sim import ArchivalQueue
from tools.raw_vault_offline.evidence_report import build_evidence_report, save_evidence_report
from pathlib import Path

vault = RawVault(Path("/tmp/test_vault"))
report = build_evidence_report(vault=vault, notes=["offline dry-run"])
save_evidence_report(report, Path("/tmp/evidence.json"))
```

---

## Constraints (from Issue #207)

- No modifications to any protected production module
- No live API calls, real-time collector, or streaming ingestion
- No production migrations, market orders, or trading activation
- Synthetic fixture bytes and public source format documentation only
- Draft PR only — no merge to `main`
