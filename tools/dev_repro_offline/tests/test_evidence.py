"""Tests for Stage 6 — Immutable Evidence Bundles."""
import pytest
from pathlib import Path
from tools.dev_repro_offline.fingerprint import collect as collect_fp
from tools.dev_repro_offline.manifest import build_w1_manifest
from tools.dev_repro_offline.preflight import run_preflight
from tools.dev_repro_offline.runner import run_manifest
from tools.dev_repro_offline.evidence import (
    build_evidence_bundle, save_bundle, load_bundle,
)


def _make_bundle(tmp_path):
    fp        = collect_fp(str(tmp_path))
    manifest  = build_w1_manifest(fp.git.head_sha)
    preflight = run_preflight(repo_root=str(tmp_path))
    run_report = run_manifest(manifest, str(tmp_path), dry_run=True)
    return build_evidence_bundle(fp, manifest, preflight, run_report)


def test_bundle_has_digest(tmp_path):
    b = _make_bundle(tmp_path)
    assert b.digest
    assert len(b.digest) == 64  # SHA-256 hex


def test_digest_stable(tmp_path):
    b = _make_bundle(tmp_path)
    assert b.compute_digest() == b.digest


def test_save_no_overwrite(tmp_path):
    b = _make_bundle(tmp_path)
    p = tmp_path / "bundle.json"
    save_bundle(b, p)
    with pytest.raises(FileExistsError):
        save_bundle(b, p)


def test_load_round_trip(tmp_path):
    b = _make_bundle(tmp_path)
    p = tmp_path / "bundle.json"
    save_bundle(b, p)
    loaded = load_bundle(p)
    assert loaded.digest == b.digest
    assert loaded.bundle_id == b.bundle_id


def test_load_detects_tamper(tmp_path):
    b = _make_bundle(tmp_path)
    p = tmp_path / "bundle.json"
    save_bundle(b, p)
    text = p.read_text()
    p.write_text(text.replace(b.bundle_id, "tampered_id"))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_bundle(p)


def test_blocked_entries_recorded(tmp_path):
    b = _make_bundle(tmp_path)
    # CORE-W1-UNIT and FACTORY-W1-UNIT must be blocked
    assert "CORE-W1-UNIT" in b.blocked_entries
    assert "FACTORY-W1-UNIT" in b.blocked_entries


def test_no_pass_for_blocked(tmp_path):
    b = _make_bundle(tmp_path)
    # Blocked entries must not appear in pass list
    for eid in b.blocked_entries:
        assert eid not in b.pass_entries
