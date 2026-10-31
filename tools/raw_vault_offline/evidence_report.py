"""
Stage 9 — Operational evidence report generator.

Produces a self-contained JSON evidence report covering:
- Vault integrity snapshot
- Correction chain audit
- Coverage analysis summary
- Archival queue snapshot
- Schema + policy versions
- Test result stubs (filled by test runner)

No network. No production data. No protected module imports.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


REPORT_SCHEMA_VERSION = "evidence_report.v1"


@dataclass
class EvidenceReport:
    schema_version: str = REPORT_SCHEMA_VERSION
    generated_at_utc: str = ""
    python_version: str = ""
    # vault
    vault_root: str = ""
    vault_objects_count: int = 0
    vault_manifest_lines: int = 0
    vault_index_entries: int = 0
    vault_orphan_staging: list[str] = field(default_factory=list)
    vault_status: str = "NOT_SCANNED"
    # manifest digest (deterministic over admitted objects)
    manifest_digest: str = ""
    # corrections
    correction_chain_records: int = 0
    correction_lids_covered: list[str] = field(default_factory=list)
    # coverage
    coverage_summaries: list[dict] = field(default_factory=list)
    # archival queue
    archival_queue_snapshot: dict = field(default_factory=dict)
    # test results (populated by test runner)
    test_results: list[dict] = field(default_factory=list)
    test_summary: dict = field(default_factory=dict)
    # policy
    policy_versions: dict = field(default_factory=dict)
    # gaps and notes
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_evidence_report(
    vault=None,             # RawVault instance (optional — may be None if not initialised)
    correction_ledger=None, # CorrectionLedger instance (optional)
    coverage_reports=None,  # list[CoverageReport] (optional)
    archival_queue=None,    # ArchivalQueue instance (optional)
    test_results: Optional[list[dict]] = None,
    vault_root: Optional[str] = None,
    notes: Optional[list[str]] = None,
) -> EvidenceReport:
    """
    Assemble an evidence report from live component instances.

    Parameters
    ----------
    vault              : RawVault or None
    correction_ledger  : CorrectionLedger or None
    coverage_reports   : list of CoverageReport or None
    archival_queue     : ArchivalQueue or None
    test_results       : list of dicts from test runner
    vault_root         : override vault root path string
    notes              : extra notes to include

    Returns
    -------
    EvidenceReport (call .to_json() or .to_dict())
    """
    report = EvidenceReport(
        generated_at_utc=_now_utc(),
        python_version=sys.version,
    )

    # --- vault ---
    if vault is not None:
        scan = vault.recovery_scan()
        report.vault_root = str(vault.root)
        report.vault_objects_count = scan.get("objects_count", 0)
        report.vault_manifest_lines = scan.get("manifest_lines", 0)
        report.vault_index_entries = scan.get("index_entries", 0)
        report.vault_orphan_staging = scan.get("orphan_staging", [])
        report.vault_status = scan.get("status", "UNKNOWN")

        # manifest digest
        entries = vault.manifest_entries()
        canonical = json.dumps(
            entries, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        report.manifest_digest = hashlib.sha256(canonical).hexdigest()
    elif vault_root:
        report.vault_root = vault_root

    # --- corrections ---
    if correction_ledger is not None:
        records = correction_ledger.all_records()
        report.correction_chain_records = len(records)
        lids = list({r.logical_identity_key for r in records})
        report.correction_lids_covered = lids

    # --- coverage ---
    if coverage_reports:
        for cr in coverage_reports:
            report.coverage_summaries.append({
                "instrument": cr.instrument,
                "interval": cr.interval,
                "chunk_start_utc_ms": cr.chunk_start_utc_ms,
                "chunk_end_utc_ms": cr.chunk_end_utc_ms,
                "expected_bar_count": cr.expected_bar_count,
                "present_count": cr.present_count,
                "missing_count": len(cr.missing_slots),
                "duplicate_count": len(cr.duplicate_slots),
                "coverage_fraction": cr.coverage_fraction,
                "has_gaps": cr.has_gaps,
                "overlap_with_prior_chunk": cr.overlap_with_prior_chunk,
                "notes": cr.notes,
            })

    # --- archival queue ---
    if archival_queue is not None:
        report.archival_queue_snapshot = archival_queue.snapshot()

    # --- test results ---
    if test_results:
        report.test_results = test_results
        passed = sum(1 for t in test_results if t.get("status") == "PASS")
        failed = sum(1 for t in test_results if t.get("status") == "FAIL")
        skipped = sum(1 for t in test_results if t.get("status") == "SKIP")
        not_tested = sum(
            1 for t in test_results if t.get("status") == "NOT_TESTED"
        )
        report.test_summary = {
            "total": len(test_results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "not_tested": not_tested,
        }

    # --- policy versions ---
    try:
        from .schema import SCHEMA_VERSION
        report.policy_versions["schema"] = SCHEMA_VERSION
    except ImportError:
        pass
    try:
        from .derived_view import DERIVED_VIEW_POLICY_VERSION
        report.policy_versions["derived_view"] = DERIVED_VIEW_POLICY_VERSION
    except ImportError:
        pass
    try:
        from .archival_sim import QUEUE_FILENAME, RECEIPT_FILENAME
        report.policy_versions["archival_queue_format"] = QUEUE_FILENAME
    except ImportError:
        pass

    report.notes = notes or []

    return report


def save_evidence_report(report: EvidenceReport, output_path: Path) -> Path:
    """Write evidence report JSON to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_json(), encoding="utf-8")
    return output_path
