"""Tests for Stage 7 — W1 Evidence Coordinator."""
from tools.dev_repro_offline.manifest import build_w1_manifest
from tools.dev_repro_offline.runner import run_manifest, RunStatus
from tools.dev_repro_offline.w1_coordinator import (
    build_w1_coordinator_report, W1CoordinatorReport, W1Component,
)


def test_coordinator_never_claims_integration(tmp_path):
    manifest = build_w1_manifest("dbc191d")
    run_report = run_manifest(manifest, str(tmp_path), dry_run=True)
    report = build_w1_coordinator_report(run_report, "dbc191d")
    assert report.integrated_claim is False


def test_core_and_factory_are_blocked_not_pass(tmp_path):
    manifest = build_w1_manifest("dbc191d")
    run_report = run_manifest(manifest, str(tmp_path), dry_run=True)
    report = build_w1_coordinator_report(run_report, "dbc191d")
    assert report.core_result is not None
    assert report.factory_result is not None
    assert report.core_result.status == RunStatus.BLOCKED
    assert report.factory_result.status == RunStatus.BLOCKED


def test_core_not_verified_at_expected_sha(tmp_path):
    manifest = build_w1_manifest("dbc191d")
    run_report = run_manifest(manifest, str(tmp_path), dry_run=True)
    report = build_w1_coordinator_report(run_report, "dbc191d")
    assert not report.core_result.is_verified_at_expected_sha


def test_factory_not_verified_at_expected_sha(tmp_path):
    manifest = build_w1_manifest("dbc191d")
    run_report = run_manifest(manifest, str(tmp_path), dry_run=True)
    report = build_w1_coordinator_report(run_report, "dbc191d")
    assert not report.factory_result.is_verified_at_expected_sha


def test_summary_mentions_not_integrated(tmp_path):
    manifest = build_w1_manifest("dbc191d")
    run_report = run_manifest(manifest, str(tmp_path), dry_run=True)
    report = build_w1_coordinator_report(run_report, "dbc191d")
    summary = report.summary()
    assert "NOT VERIFIED" in summary
    assert "integrated" in summary.lower()


def test_repro_self_is_dry_run(tmp_path):
    manifest = build_w1_manifest("dbc191d")
    run_report = run_manifest(manifest, str(tmp_path), dry_run=True)
    report = build_w1_coordinator_report(run_report, "dbc191d")
    # In dry-run the repro self test is DRY_RUN, not PASS
    assert report.repro_result is not None
    assert report.repro_result.status == RunStatus.DRY_RUN
