"""
P0-C Regression Tests — Issue #215 Gate 2
==========================================
Bug: ReleaseReadinessReport.verdict() returns READY_FOR_OWNER_REVIEW when:
  (a) some of the 7 gates are missing (never set_gate() called for them), or
  (b) gates have status PENDING (not yet evaluated to PASS).

These tests must FAIL on the unfixed code (SHA f4cfcb2)
and PASS after the fix.

Run to reproduce:
    pytest tests/integration_intel_offline/test_p0c_regression.py -v
"""
from __future__ import annotations
import pytest
from tools.integration_intel_offline.release_readiness import (
    ReleaseReadinessReport,
    GATE_NAMES,
)


class TestP0CFalseReadiness:

    def test_missing_gates_are_blocked_not_ready(self):
        """
        P0-C-1: If fewer than 7 gates are set, verdict must be BLOCKED (not READY).
        BUG: current code only checks GATE_NAMES[0]; 6 missing gates pass silently.
        """
        rpt = ReleaseReadinessReport()
        # Only set the first gate PASS — 6 gates missing
        rpt.set_gate(GATE_NAMES[0], "PASS", evidence="set")
        assert rpt.verdict() != "READY_FOR_OWNER_REVIEW", (
            "P0-C-1 BUG: verdict is READY with only 1/7 gates set. "
            "All 7 gates must be explicitly PASS before returning READY."
        )

    def test_pending_gate_is_blocked_not_ready(self):
        """
        P0-C-2: A PENDING gate must produce BLOCKED, not READY.
        BUG: the loop only checks for 'FAIL'; PENDING slips through.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence="ok")
        # Override one gate to PENDING
        rpt.set_gate(GATE_NAMES[3], "PENDING", evidence="still evaluating")
        assert rpt.verdict() == "BLOCKED", (
            "P0-C-2 BUG: PENDING gate did not produce BLOCKED verdict. "
            "A PENDING gate means the check has not been evaluated to PASS."
        )

    def test_waived_without_note_is_blocked(self):
        """
        P0-C-3: A WAIVED gate must have a non-empty waiver_note to be accepted.
        WAIVED without a justification is a data-quality error → BLOCKED.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence="ok")
        # WAIVED with no note should block
        rpt.set_gate(GATE_NAMES[5], "WAIVED", waiver_note="")
        assert rpt.verdict() == "BLOCKED", (
            "P0-C-3 BUG: WAIVED gate with empty waiver_note produced READY. "
            "A waiver without justification is invalid."
        )

    def test_empty_report_is_not_ready(self):
        """
        P0-C-4: A report with zero gates set must never produce READY.
        BUG: current code falls through to UNKNOWN only if GATE_NAMES[0] missing.
        With 0 gates, GATE_NAMES[0] is indeed missing, so this one hits UNKNOWN.
        After fix it must still be BLOCKED (more explicit than UNKNOWN).
        """
        rpt = ReleaseReadinessReport()
        verdict = rpt.verdict()
        assert verdict in ("BLOCKED", "UNKNOWN"), (
            f"P0-C-4 BUG: empty report returned {verdict!r}. "
            "Must be BLOCKED or UNKNOWN, never READY_FOR_OWNER_REVIEW."
        )
        assert verdict != "READY_FOR_OWNER_REVIEW"

    def test_all_seven_gates_pass_is_ready(self):
        """
        P0-C-COMPAT: With all 7 gates PASS and non-empty evidence, verdict must
        be READY_FOR_OWNER_REVIEW (no regression on the happy path).
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence=f"{name} verified")
        assert rpt.verdict() == "READY_FOR_OWNER_REVIEW", (
            "P0-C-COMPAT: all 7 PASS gates should produce READY_FOR_OWNER_REVIEW."
        )

    def test_six_pass_one_fail_is_blocked(self):
        """
        P0-C-5: Existing behaviour — a single FAIL blocks all 7. Must remain blocked.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence="ok")
        rpt.set_gate(GATE_NAMES[2], "FAIL", evidence="collision found")
        assert rpt.verdict() == "BLOCKED"

    def test_six_pass_one_missing_is_blocked(self):
        """
        P0-C-6: 6 PASS gates + 1 missing gate must still be BLOCKED.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES[:-1]:   # all but last
            rpt.set_gate(name, "PASS", evidence="ok")
        # GATE_NAMES[-1] never set
        assert rpt.verdict() == "BLOCKED", (
            "P0-C-6 BUG: 6/7 PASS gates produced READY. "
            "All 7 must be present and PASS."
        )

    def test_waived_with_note_is_ready_when_rest_pass(self):
        """
        P0-C-COMPAT2: WAIVED gates WITH a justification note are acceptable.
        After fix, all 7 gates present (6 PASS + 1 WAIVED-with-note) → READY.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence="ok")
        rpt.set_gate(GATE_NAMES[6], "WAIVED",
                     waiver_note="Snapshot age check waived: offline environment confirmed")
        assert rpt.verdict() == "READY_FOR_OWNER_REVIEW", (
            "P0-C-COMPAT2: WAIVED gate with a note should not block when all 7 are set."
        )
