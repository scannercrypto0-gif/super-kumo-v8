"""
Tests for Stage 6: correction chain — lineage, cycle detection, conflicts, audit.
"""
import pytest

from tools.raw_vault_offline.corrections import (
    CorrectionLedger,
    MissingParent,
    CycleDetected,
    ConflictingCorrection,
)
from tools.raw_vault_offline.schema import MalformedIdentity


LID = "a" * 64   # synthetic logical identity key


def _ledger(tmp_path) -> CorrectionLedger:
    return CorrectionLedger(tmp_path / "corrections.jsonl")


# ── basic add + chain ────────────────────────────────────────────────────────

def test_add_first_correction(tmp_path):
    ledger = _ledger(tmp_path)
    sha_gen0 = "0" * 64
    sha_gen1 = "1" * 64
    rec = ledger.add_correction(
        new_content_sha256=sha_gen1,
        parent_content_sha256=sha_gen0,
        logical_identity_key=LID,
        reason="Corrected bad close price",
        evidence="vendor re-issued 2024-01-02",
    )
    assert rec.correction_generation == 1
    assert rec.content_sha256 == sha_gen1


def test_chain_for_returns_sorted(tmp_path):
    ledger = _ledger(tmp_path)
    sha0, sha1, sha2 = "0"*64, "1"*64, "2"*64
    ledger.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                          logical_identity_key=LID, reason="r1", evidence="e1")
    ledger.add_correction(new_content_sha256=sha2, parent_content_sha256=sha1,
                          logical_identity_key=LID, reason="r2", evidence="e2")
    chain = ledger.chain_for(LID)
    assert len(chain) == 2
    assert chain[0].correction_generation == 1
    assert chain[1].correction_generation == 2


def test_latest_sha(tmp_path):
    ledger = _ledger(tmp_path)
    sha0, sha1, sha2 = "0"*64, "1"*64, "2"*64
    ledger.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                          logical_identity_key=LID, reason="r", evidence="e")
    ledger.add_correction(new_content_sha256=sha2, parent_content_sha256=sha1,
                          logical_identity_key=LID, reason="r", evidence="e")
    assert ledger.latest_sha(LID) == sha2


def test_latest_sha_by_generation(tmp_path):
    ledger = _ledger(tmp_path)
    sha0, sha1, sha2 = "0"*64, "1"*64, "2"*64
    ledger.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                          logical_identity_key=LID, reason="r", evidence="e")
    ledger.add_correction(new_content_sha256=sha2, parent_content_sha256=sha1,
                          logical_identity_key=LID, reason="r", evidence="e")
    assert ledger.latest_sha(LID, generation=1) == sha1
    assert ledger.latest_sha(LID, generation=2) == sha2
    assert ledger.latest_sha(LID, generation=99) is None


def test_latest_sha_no_corrections(tmp_path):
    ledger = _ledger(tmp_path)
    assert ledger.latest_sha(LID) is None


# ── cycle detection ───────────────────────────────────────────────────────────

def test_cycle_detected(tmp_path):
    ledger = _ledger(tmp_path)
    sha0, sha1 = "0"*64, "1"*64
    ledger.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                          logical_identity_key=LID, reason="r", evidence="e")
    with pytest.raises(CycleDetected):
        # sha1 already exists as a content_sha256 in the ledger
        ledger.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                              logical_identity_key=LID, reason="r2", evidence="e2")


# ── conflicting correction ────────────────────────────────────────────────────

def test_conflicting_correction(tmp_path):
    ledger = _ledger(tmp_path)
    sha0, sha1, sha2 = "0"*64, "1"*64, "2"*64
    ledger.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                          logical_identity_key=LID, reason="r", evidence="e")
    with pytest.raises(ConflictingCorrection):
        # same parent sha0 + same LID, different new sha
        ledger.add_correction(new_content_sha256=sha2, parent_content_sha256=sha0,
                              logical_identity_key=LID, reason="r2", evidence="e2")


# ── validation: blank fields ──────────────────────────────────────────────────

def test_blank_reason_rejected(tmp_path):
    ledger = _ledger(tmp_path)
    with pytest.raises(MalformedIdentity):
        ledger.add_correction(new_content_sha256="1"*64, parent_content_sha256="0"*64,
                              logical_identity_key=LID, reason="   ", evidence="e")


def test_blank_evidence_rejected(tmp_path):
    ledger = _ledger(tmp_path)
    with pytest.raises(MalformedIdentity):
        ledger.add_correction(new_content_sha256="1"*64, parent_content_sha256="0"*64,
                              logical_identity_key=LID, reason="r", evidence="")


# ── audit_diff ────────────────────────────────────────────────────────────────

def test_audit_diff(tmp_path):
    ledger = _ledger(tmp_path)
    sha0, sha1 = "0"*64, "1"*64
    ledger.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                          logical_identity_key=LID, reason="fix", evidence="proof")
    diff = ledger.audit_diff(LID)
    assert diff["generation_count"] == 1
    assert diff["lineage"][0]["generation"] == 1
    assert diff["lineage"][0]["sha256"] == sha1


def test_audit_diff_empty(tmp_path):
    ledger = _ledger(tmp_path)
    diff = ledger.audit_diff(LID)
    assert diff["generation_count"] == 0
    assert diff["lineage"] == []


# ── persistence across instances ─────────────────────────────────────────────

def test_persistence_across_reload(tmp_path):
    path = tmp_path / "corrections.jsonl"
    ledger1 = CorrectionLedger(path)
    sha0, sha1 = "0"*64, "1"*64
    ledger1.add_correction(new_content_sha256=sha1, parent_content_sha256=sha0,
                           logical_identity_key=LID, reason="r", evidence="e")
    # reload
    ledger2 = CorrectionLedger(path)
    chain = ledger2.chain_for(LID)
    assert len(chain) == 1
    assert chain[0].content_sha256 == sha1
