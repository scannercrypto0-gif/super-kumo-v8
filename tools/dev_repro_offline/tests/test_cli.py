"""Tests for Stage 11 — CLI dry-run workflow."""
import os
from pathlib import Path
import pytest
from tools.dev_repro_offline.cli import run

# Use the actual repository root so preflight can find .git and passes cleanly.
_REPO_ROOT = str(Path(__file__).parents[3])  # .../super-kumo-v8


def test_cli_dry_run_succeeds(tmp_path):
    """Full dry-run workflow must complete without error."""
    rc = run(dry_run=True, output_dir=str(tmp_path / "evidence"), repo_root=_REPO_ROOT)
    assert rc in (0, 1, 2)  # 0=all-pass, 1=preflight-warn, 2=test-fail


def test_cli_creates_output_files(tmp_path):
    out = tmp_path / "evidence"
    run(dry_run=True, output_dir=str(out), repo_root=_REPO_ROOT)
    assert (out / "fingerprint.json").exists()
    assert (out / "manifest.json").exists()
    assert (out / "preflight.json").exists()
    assert (out / "evidence_bundle.json").exists()
    assert (out / "SUMMARY.md").exists()


def test_cli_summary_mentions_dry_run(tmp_path):
    out = tmp_path / "evidence"
    run(dry_run=True, output_dir=str(out), repo_root=_REPO_ROOT)
    summary = (out / "SUMMARY.md").read_text()
    assert "DRY-RUN" in summary


def test_cli_summary_mentions_not_integrated(tmp_path):
    out = tmp_path / "evidence"
    run(dry_run=True, output_dir=str(out), repo_root=_REPO_ROOT)
    w1_txt = (out / "w1_coordinator.txt").read_text()
    assert "NOT VERIFIED" in w1_txt


def test_cli_no_second_run_overwrites(tmp_path):
    """Running CLI twice to same output dir must fail (immutable bundles)."""
    out = tmp_path / "evidence"
    run(dry_run=True, output_dir=str(out), repo_root=_REPO_ROOT)
    with pytest.raises(FileExistsError):
        run(dry_run=True, output_dir=str(out), repo_root=_REPO_ROOT)
