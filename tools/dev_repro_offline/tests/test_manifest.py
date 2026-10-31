"""Tests for Stage 3 — TestManifest."""
import pytest
from pathlib import Path
from tools.dev_repro_offline.manifest import (
    TestManifest, ManifestEntry, ManifestEntryStatus,
    build_w1_manifest, save_manifest, load_manifest,
)


def _entry(eid="E1", status=ManifestEntryStatus.EXPECTED) -> ManifestEntry:
    return ManifestEntry(
        entry_id=eid, label=f"Test {eid}",
        command_template="pytest {module} -v",
        module_path="tests/",
        expected_sha="abc1234",
        owner_issue="#1",
        status=status,
    )


def test_add_and_retrieve():
    m = TestManifest()
    m.add(_entry("T1"))
    assert m.get("T1") is not None


def test_duplicate_rejected():
    m = TestManifest()
    m.add(_entry("T1"))
    with pytest.raises(ValueError, match="Duplicate"):
        m.add(_entry("T1"))


def test_digest_stable():
    m = TestManifest(base_sha="abc")
    m.add(_entry("T1"))
    d1 = m.compute_digest()
    d2 = m.compute_digest()
    assert d1 == d2


def test_digest_changes_after_add():
    m = TestManifest(base_sha="abc")
    d1 = m.compute_digest()
    m.add(_entry("T1"))
    assert m.digest != d1


def test_allowed_and_blocked_entries():
    m = TestManifest()
    m.add(_entry("E1", ManifestEntryStatus.EXPECTED))
    m.add(_entry("B1", ManifestEntryStatus.BLOCKED))
    assert len(m.allowed_entries()) == 1
    assert len(m.blocked_entries()) == 1


def test_w1_manifest_has_expected_and_blocked():
    m = build_w1_manifest("dbc191d")
    blocked = {e.entry_id for e in m.blocked_entries()}
    expected = {e.entry_id for e in m.allowed_entries()}
    assert "CORE-W1-UNIT" in blocked
    assert "FACTORY-W1-UNIT" in blocked
    assert "REPRO-SELF-001" in expected


def test_save_load_round_trip(tmp_path):
    m = build_w1_manifest("dbc191d")
    p = tmp_path / "manifest.json"
    save_manifest(m, p)
    loaded = load_manifest(p)
    assert loaded.digest == m.digest
    assert len(loaded.entries) == len(m.entries)


def test_load_detects_tamper(tmp_path):
    m = build_w1_manifest("dbc191d")
    p = tmp_path / "manifest.json"
    save_manifest(m, p)
    # Tamper with file
    text = p.read_text()
    text = text.replace("BLOCKED", "EXPECTED", 1)
    p.write_text(text)
    with pytest.raises(ValueError, match="digest mismatch"):
        load_manifest(p)


def test_save_no_overwrite(tmp_path):
    m = build_w1_manifest("dbc191d")
    p = tmp_path / "manifest.json"
    save_manifest(m, p)
    with pytest.raises(FileExistsError):
        save_manifest(m, p)
