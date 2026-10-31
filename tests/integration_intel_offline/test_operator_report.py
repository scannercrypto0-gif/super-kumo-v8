"""Stage 9 — Operator report tests."""
import json
import pytest
from tools.integration_intel_offline.operator_report import (
    build_full_report, render_markdown, render_json, THREAT_MODEL, KNOWN_LIMITATIONS,
)


SNAP_META = {
    "snapshot_at": "2026-10-31T00:00:00Z",
    "main_head_sha": "dbc191d",
    "access_limits": ["cross-chat inaccessible", "Issue #207 status UNKNOWN"],
}
DAG_REPORT = {"cycles": [], "missing_parents": {}, "candidate_review_order": [1], "pr_count": 1, "ambiguous_order": False}
EMPTY_EVIDENCE = {"pr_summary": {}}
NO_CLAIMS = [{"pr_number": 1, "verdict": "NO_CONCERN_DETECTED", "hit_count": 0}]
NO_COVERAGE = [{"pr_number": 1, "coverage_label": "COVERAGE_ADEQUATE"}]
READY_RR = {
    "verdict": "READY_FOR_OWNER_REVIEW",
    "gates": [{"name": "NO_CYCLES", "status": "PASS", "evidence": "ok", "description": "d", "waiver_note": ""}],
    "blockers": [],
    "pending_gates": [],
    "blocker_count": 0,
    "classification": "READ_ONLY__NOT_AN_APPROVAL__OWNER_DECISION_REQUIRED",
}


class TestBuildFullReport:
    def _rpt(self):
        return build_full_report(
            SNAP_META, DAG_REPORT, [], EMPTY_EVIDENCE, NO_CLAIMS, NO_COVERAGE, READY_RR
        )

    def test_report_kind(self):
        assert self._rpt()["report_kind"] == "AQL_INTEGRATION_INTEL_OFFLINE_REPORT"

    def test_snapshot_at_present(self):
        assert self._rpt()["snapshot_at"] == SNAP_META["snapshot_at"]

    def test_access_limits_preserved(self):
        assert len(self._rpt()["access_limits"]) == 2

    def test_threat_model_present(self):
        assert "offline" in self._rpt()["threat_model_summary"].lower()

    def test_known_limitations_list(self):
        assert len(self._rpt()["known_limitations"]) >= 5

    def test_classification_label(self):
        assert "NOT_AN_APPROVAL" in self._rpt()["classification"]

    def test_json_serializable(self):
        s = render_json(self._rpt())
        assert json.loads(s)["report_kind"] == "AQL_INTEGRATION_INTEL_OFFLINE_REPORT"


class TestRenderMarkdown:
    def _md(self):
        return render_markdown(build_full_report(
            SNAP_META, DAG_REPORT, [], EMPTY_EVIDENCE, NO_CLAIMS, NO_COVERAGE, READY_RR
        ))

    def test_contains_title(self):
        assert "AQL Integration Intelligence Report" in self._md()

    def test_verdict_present(self):
        assert "READY_FOR_OWNER_REVIEW" in self._md()

    def test_snapshot_at_present(self):
        assert "2026-10-31" in self._md()

    def test_access_limits_present(self):
        assert "cross-chat inaccessible" in self._md()

    def test_owner_warning_present(self):
        md = self._md()
        assert "owner" in md.lower() or "OWNER" in md

    def test_blocked_verdict_shows_blockers(self):
        blocked_rr = {
            **READY_RR,
            "verdict": "BLOCKED",
            "blockers": [{"name": "NO_CYCLES", "evidence": "cycle found",
                          "description": "d", "status": "FAIL", "waiver_note": ""}],
        }
        r = build_full_report(SNAP_META, DAG_REPORT, [], EMPTY_EVIDENCE, NO_CLAIMS, NO_COVERAGE, blocked_rr)
        md = render_markdown(r)
        assert "Blocker" in md or "cycle found" in md


class TestThreatModelContent:
    def test_offline_first_mentioned(self):
        assert "OFFLINE-FIRST" in THREAT_MODEL

    def test_read_only_mentioned(self):
        assert "READ-ONLY" in THREAT_MODEL

    def test_access_limits_mentioned(self):
        assert "#205" in THREAT_MODEL or "inaccessible" in THREAT_MODEL

    def test_governance_clause(self):
        assert "owner" in THREAT_MODEL.lower()
