"""
Stage 10 — Adversarial & Reliability Tests
Interrupted saves, tamper detection, permission errors, corrupt digests.
"""
import json
import os
import stat
import pytest
from pathlib import Path
from tools.dev_repro_offline.fingerprint import collect as collect_fp, save as save_fp
from tools.dev_repro_offline.manifest import build_w1_manifest, save_manifest, load_manifest
from tools.dev_repro_offline.evidence import build_evidence_bundle, save_bundle, load_bundle
from tools.dev_repro_offline.runner import run_manifest
from tools.dev_repro_offline.preflight import run_preflight


# ── immutability ──────────────────────────────────────────────────────────────

def test_fingerprint_no_overwrite(tmp_path):
    fp = collect_fp(str(tmp_path))
    p  = tmp_path / "fp.json"
    save_fp(fp, p)
    with pytest.raises(FileExistsError):
        save_fp(fp, p)


def test_manifest_no_overwrite(tmp_path):
    m = build_w1_manifest("abc")
    p = tmp_path / "manifest.json"
    save_manifest(m, p)
    with pytest.raises(FileExistsError):
        save_manifest(m, p)


def test_evidence_no_overwrite(tmp_path):
    fp = collect_fp(str(tmp_path))
    m  = build_w1_manifest(fp.git.head_sha)
    pf = run_preflight(repo_root=str(tmp_path))
    rr = run_manifest(m, str(tmp_path), dry_run=True)
    b  = build_evidence_bundle(fp, m, pf, rr)
    p  = tmp_path / "bundle.json"
    save_bundle(b, p)
    with pytest.raises(FileExistsError):
        save_bundle(b, p)


# ── tamper detection ──────────────────────────────────────────────────────────

def test_manifest_tamper_detected(tmp_path):
    m = build_w1_manifest("abc")
    p = tmp_path / "manifest.json"
    save_manifest(m, p)
    data = json.loads(p.read_text())
    data["base_sha"] = "tampered"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_manifest(p)


def test_bundle_tamper_detected(tmp_path):
    fp = collect_fp(str(tmp_path))
    m  = build_w1_manifest(fp.git.head_sha)
    pf = run_preflight(repo_root=str(tmp_path))
    rr = run_manifest(m, str(tmp_path), dry_run=True)
    b  = build_evidence_bundle(fp, m, pf, rr)
    p  = tmp_path / "bundle.json"
    save_bundle(b, p)
    data = json.loads(p.read_text())
    data["notes"] = "injected"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_bundle(p)


# ── corrupt / missing files ───────────────────────────────────────────────────

def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "nonexistent.json")


def test_load_manifest_corrupt_json(tmp_path):
    p = tmp_path / "corrupt.json"
    p.write_text("{not valid json}", encoding="utf-8")
    with pytest.raises(Exception):  # json.JSONDecodeError
        load_manifest(p)


# ── read-only filesystem simulation ──────────────────────────────────────────

@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "getuid") and os.getuid() == 0),
    reason="chmod not reliable on Windows or when running as root"
)
def test_save_manifest_readonly_dir(tmp_path):
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    readonly.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x — no write
    try:
        m = build_w1_manifest("abc")
        with pytest.raises(PermissionError):
            save_manifest(m, readonly / "manifest.json")
    finally:
        readonly.chmod(stat.S_IRWXU)  # restore so tmp_path cleanup works


# ── namespace isolation ───────────────────────────────────────────────────────

def test_no_protected_namespace_in_module():
    """The toolkit must not import protected namespaces."""
    import sys
    protected = ["src.aql", "research_wp_r0"]
    for ns in protected:
        assert ns not in sys.modules, f"Protected namespace {ns!r} found in sys.modules"


# ── digest collision resistance ───────────────────────────────────────────────

def test_two_manifests_different_digest(tmp_path):
    m1 = build_w1_manifest("sha_a")
    m2 = build_w1_manifest("sha_b")
    assert m1.digest != m2.digest
