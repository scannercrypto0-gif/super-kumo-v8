"""
Gate 2 Regression Tests — Issue #215
=====================================
PM requirement (Issue #215 #issuecomment-6554887311):
  "All 7 required gates must be present and explicitly PASS;
   WAIVED-with-note is NOT PASS."

Bug: ReleaseReadinessReport.verdict() returns READY_FOR_OWNER_REVIEW when a
gate is WAIVED even with a non-empty waiver_note.

These tests must FAIL on the unfixed code (SHA 2baf135)
and PASS after the Gate 2 fix.

Run to reproduce:
    pytest tests/integration_intel_offline/test_g2_waived_regression.py -v
"""
from __future__ import annotations
import pytest
from tools.integration_intel_offline.release_readiness import (
    ReleaseReadinessReport,
    GATE_NAMES,
)


class TestG2WaivedWithNoteNotPass:

    def test_waived_with_note_must_be_blocked_not_ready(self):
        """
        G2-WAIVED-1: PM says WAIVED-with-note is NOT PASS.
        Any WAIVED gate — regardless of waiver_note content — must produce BLOCKED.
        BUG on 2baf135: WAIVED-with-note slips through to READY_FOR_OWNER_REVIEW.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence="ok")
        # One gate WAIVED with a justification note — PM says this is still NOT PASS
        rpt.set_gate(
            GATE_NAMES[6],
            "WAIVED",
            waiver_note="Snapshot age check waived: offline environment confirmed",
        )
        assert rpt.verdict() == "BLOCKED", (
            "G2-WAIVED-1 BUG: WAIVED gate with note produced READY_FOR_OWNER_REVIEW. "
            "PM requirement (Issue #215): WAIVED-with-note is NOT PASS. "
            "Only explicit PASS on all 7 gates is acceptable."
        )

    def test_waived_early_gate_with_note_must_be_blocked(self):
        """
        G2-WAIVED-2: WAIVED gate is blocked regardless of which gate position it occupies.
        Test with gate index 0 (NO_CYCLES) to confirm order independence.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence="ok")
        rpt.set_gate(
            GATE_NAMES[0],
            "WAIVED",
            waiver_note="Cycles waived for single-PR workflow",
        )
        assert rpt.verdict() == "BLOCKED", (
            "G2-WAIVED-2: WAIVED gate at position 0 with note must produce BLOCKED."
        )

    def test_only_explicit_pass_on_all_7_produces_ready(self):
        """
        G2-PASS-ONLY: The only path to READY_FOR_OWNER_REVIEW is all 7 gates
        explicitly set to PASS. No WAIVED gate, however justified, is sufficient.
        """
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS", evidence=f"{name} verified")
        assert rpt.verdict() == "READY_FOR_OWNER_REVIEW", (
            "G2-PASS-ONLY: all 7 gates explicitly PASS must reach READY_FOR_OWNER_REVIEW."
        )
        # Now WAIVE one — must immediately block
        rpt.set_gate(
            GATE_NAMES[3],
            "WAIVED",
            waiver_note="Protected collision waived by PM on 2026-11-01",
        )
        assert rpt.verdict() == "BLOCKED", (
            "G2-PASS-ONLY: switching one PASS to WAIVED-with-note must produce BLOCKED."
        )
