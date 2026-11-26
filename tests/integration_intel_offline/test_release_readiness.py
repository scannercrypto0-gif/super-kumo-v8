"""Stage 8 — Release-readiness graph tests."""
import pytest
from tools.integration_intel_offline.release_readiness import (
    ReleaseReadinessReport, build_readiness_report, GATE_NAMES,
)


def clean_dag():
    return {"cycles": [], "missing_parents": {}, "candidate_review_order": [1, 2], "pr_count": 2}

def clean_evidence():
    return {"pr_summary": {"1": {"highest_level": "W1"}}}

def clean_claims():
    return [{"pr_number": 1, "verdict": "NO_CONCERN_DETECTED", "hit_count": 0}]

def clean_coverage():
    return [{"pr_number": 1, "coverage_label": "COVERAGE_ADEQUATE"}]


class TestReleaseReadinessReport:
    def test_all_pass_gives_ready(self):
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence="ok")
        assert rpt.verdict() == "READY_FOR_OWNER_REVIEW"

    def test_one_fail_gives_blocked(self):
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS")
        rpt.set_gate("NO_CYCLES", "FAIL", evidence="cycle detected")
        assert rpt.verdict() == "BLOCKED"

    def test_blockers_list(self):
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS")
        rpt.set_gate("NO_CYCLES", "FAIL", evidence="x")
        assert len(rpt.blockers()) == 1

    def test_pending_gates_list(self):
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS")
        rpt.set_gate("SNAPSHOT_FRESH", "PENDING")
        assert len(rpt.pending_gates()) == 1

    def test_report_classification_label(self):
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS")
        r = rpt.report()
        assert "OWNER_DECISION_REQUIRED" in r["classification"]
        assert "APPROVAL" not in r["verdict"]

    def test_unknown_gate_raises(self):
        rpt = ReleaseReadinessReport()
        with pytest.raises(AssertionError):
            rpt.set_gate("NONEXISTENT_GATE", "PASS")


class TestBuildReadinessReport:
    def test_clean_state_ready(self):
        rpt = build_readiness_report(
            clean_dag(), [], clean_evidence(), clean_claims(), snapshot_age_hours=1.0
        )
        assert rpt.verdict() == "READY_FOR_OWNER_REVIEW"

    def test_cycle_blocks(self):
        dag = {**clean_dag(), "cycles": [[1, 2, 1]], "missing_parents": {}}
        rpt = build_readiness_report(dag, [], clean_evidence(), clean_claims(), snapshot_age_hours=1.0)
        assert rpt.verdict() == "BLOCKED"
        assert any(b["name"] == "NO_CYCLES" for b in rpt.blockers())

    def test_direct_collision_blocks(self):
        collision = [{"kind": "DIRECT_WRITE_COLLISION", "pr_a": 1, "pr_b": 2}]
        rpt = build_readiness_report(clean_dag(), collision, clean_evidence(), clean_claims(), snapshot_age_hours=1.0)
        assert rpt.verdict() == "BLOCKED"

    def test_protected_collision_blocks(self):
        collision = [{"kind": "PROTECTED_PATH_COLLISION", "pr_a": 1, "pr_b": 2}]
        rpt = build_readiness_report(clean_dag(), collision, clean_evidence(), clean_claims(), snapshot_age_hours=1.0)
        assert rpt.verdict() == "BLOCKED"

    def test_stale_snapshot_blocks(self):
        rpt = build_readiness_report(
            clean_dag(), [], clean_evidence(), clean_claims(), snapshot_age_hours=30.0
        )
        assert rpt.verdict() == "BLOCKED"
        assert any(b["name"] == "SNAPSHOT_FRESH" for b in rpt.blockers())

    def test_unknown_age_pending(self):
        rpt = build_readiness_report(clean_dag(), [], clean_evidence(), clean_claims())
        pending = [g["name"] for g in rpt.pending_gates()]
        assert "SNAPSHOT_FRESH" in pending

    def test_review_required_claim_blocks(self):
        claims = [{"pr_number": 1, "verdict": "REVIEW_REQUIRED", "hit_count": 2}]
        rpt = build_readiness_report(clean_dag(), [], clean_evidence(), claims, snapshot_age_hours=1.0)
        assert rpt.verdict() == "BLOCKED"

    # ── EVIDENCE_VERIFIED: no any-one-PR shortcut (Issue #215 audit delta) ──

    def test_evidence_verified_requires_all_prs(self):
        """PASS only when every PR in pr_summary has a highest_level."""
        evidence = {"pr_summary": {
            "1": {"highest_level": "W1"},
            "2": {"highest_level": None},   # unverified
        }}
        rpt = build_readiness_report(clean_dag(), [], evidence, clean_claims(), snapshot_age_hours=1.0)
        # Gate must be PENDING (not PASS) because PR 2 is unverified
        gate = next(g for g in rpt.pending_gates() if g["name"] == "EVIDENCE_VERIFIED")
        assert "2" in gate["evidence"]
        assert rpt.verdict() == "BLOCKED"

    def test_evidence_verified_empty_summary_is_pending(self):
        """Empty pr_summary must stay PENDING, not be shortcut to PASS."""
        evidence = {"pr_summary": {}}
        rpt = build_readiness_report(clean_dag(), [], evidence, clean_claims(), snapshot_age_hours=1.0)
        pending_names = [g["name"] for g in rpt.pending_gates()]
        assert "EVIDENCE_VERIFIED" in pending_names
        assert rpt.verdict() == "BLOCKED"

    def test_evidence_verified_all_prs_pass(self):
        """PASS only when every PR in pr_summary is verified."""
        evidence = {"pr_summary": {
            "1": {"highest_level": "W1"},
            "2": {"highest_level": "W2"},
        }}
        rpt = build_readiness_report(clean_dag(), [], evidence, clean_claims(), snapshot_age_hours=1.0)
        gates = {g["name"]: g for g in rpt.report()["gates"]}
        assert gates["EVIDENCE_VERIFIED"]["status"] == "PASS"
        assert rpt.verdict() == "READY_FOR_OWNER_REVIEW"

    def test_evidence_verified_single_unverified_pr_blocks(self):
        """A single unverified PR among many blocks the gate."""
        evidence = {"pr_summary": {
            "208": {"highest_level": "W1"},
            "211": {"highest_level": "W2"},
            "213": {"highest_level": None},  # this PR is unverified
            "214": {"highest_level": "W1"},
        }}
        rpt = build_readiness_report(clean_dag(), [], evidence, clean_claims(), snapshot_age_hours=1.0)
        gate = next(g for g in rpt.pending_gates() if g["name"] == "EVIDENCE_VERIFIED")
        assert "213" in gate["evidence"]
