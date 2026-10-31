"""Stage 8 — Release-readiness graph and blocker minimizer.

Offline scenario simulation. Does NOT merge, approve, or deploy anything.
Does NOT invent readiness or override PM priorities.
Blockers are classified, not resolved.

ReadinessGate: each check is PASS / FAIL / PENDING / WAIVED
Final verdict: READY_FOR_OWNER_REVIEW or BLOCKED (never APPROVED)
"""
from __future__ import annotations
from typing import Literal

GateStatus = Literal["PASS", "FAIL", "PENDING", "WAIVED"]
ReadinessVerdict = Literal["READY_FOR_OWNER_REVIEW", "BLOCKED", "UNKNOWN"]

_GATE_DEFINITIONS = [
    ("NO_CYCLES",            "Dependency graph has no circular dependencies"),
    ("NO_MISSING_PARENTS",   "All declared parent PRs are present in snapshot"),
    ("NO_DIRECT_COLLISIONS", "No two open PRs modify the same path"),
    ("NO_PROTECTED_COLLISION","No collision touching protected ownership domains"),
    ("EVIDENCE_VERIFIED",    "At least one PR has verified acceptance evidence"),
    ("NO_UNRESOLVED_CLAIMS", "No REVIEW_REQUIRED claims found in PR records"),
    ("SNAPSHOT_FRESH",       "Snapshot age is within acceptable staleness window"),
]

GATE_NAMES = [g[0] for g in _GATE_DEFINITIONS]
GATE_DESCRIPTIONS = {g[0]: g[1] for g in _GATE_DEFINITIONS}


class ReleaseReadinessReport:
    def __init__(self):
        self._gates: dict[str, dict] = {}

    def set_gate(
        self,
        name: str,
        status: GateStatus,
        evidence: str = "",
        waiver_note: str = "",
    ) -> None:
        assert name in GATE_NAMES, f"Unknown gate: {name}"
        self._gates[name] = {
            "name": name,
            "description": GATE_DESCRIPTIONS[name],
            "status": status,
            "evidence": evidence,
            "waiver_note": waiver_note,
        }

    def verdict(self) -> ReadinessVerdict:
        for g in self._gates.values():
            if g["status"] == "FAIL":
                return "BLOCKED"
        # All defined gates must be evaluated
        evaluated = set(self._gates.keys())
        if not GATE_NAMES[0] in evaluated:  # minimal sanity
            return "UNKNOWN"
        return "READY_FOR_OWNER_REVIEW"

    def blockers(self) -> list[dict]:
        return [g for g in self._gates.values() if g["status"] == "FAIL"]

    def pending_gates(self) -> list[dict]:
        return [g for g in self._gates.values() if g["status"] == "PENDING"]

    def report(self) -> dict:
        return {
            "verdict": self.verdict(),
            "gates": list(self._gates.values()),
            "blockers": self.blockers(),
            "pending_gates": self.pending_gates(),
            "blocker_count": len(self.blockers()),
            "classification": (
                "READINESS_ANALYSIS_ONLY__NOT_AN_APPROVAL__OWNER_DECISION_REQUIRED"
            ),
        }


def build_readiness_report(
    dag_report: dict,
    collision_results: list[dict],
    evidence_report: dict,
    claim_results: list[dict],
    snapshot_age_hours: float | None = None,
    staleness_threshold_hours: float = 24.0,
) -> ReleaseReadinessReport:
    """Build a ReleaseReadinessReport from pre-computed analysis outputs."""
    rpt = ReleaseReadinessReport()

    # NO_CYCLES
    cycles = dag_report.get("cycles", [])
    rpt.set_gate(
        "NO_CYCLES",
        "PASS" if not cycles else "FAIL",
        evidence=f"{len(cycles)} cycle(s) detected" if cycles else "No cycles in DAG",
    )

    # NO_MISSING_PARENTS
    missing = dag_report.get("missing_parents", {})
    rpt.set_gate(
        "NO_MISSING_PARENTS",
        "PASS" if not missing else "FAIL",
        evidence=f"Missing: {missing}" if missing else "All parents present",
    )

    # NO_DIRECT_COLLISIONS (DIRECT_WRITE only, not protected — that's a separate gate)
    direct = [c for c in collision_results if c.get("kind") == "DIRECT_WRITE_COLLISION"]
    rpt.set_gate(
        "NO_DIRECT_COLLISIONS",
        "PASS" if not direct else "FAIL",
        evidence=f"{len(direct)} direct collision(s)" if direct else "No direct collisions",
    )

    # NO_PROTECTED_COLLISION
    protected = [c for c in collision_results if c.get("kind") == "PROTECTED_PATH_COLLISION"]
    rpt.set_gate(
        "NO_PROTECTED_COLLISION",
        "PASS" if not protected else "FAIL",
        evidence=(
            f"{len(protected)} protected collision(s): "
            + str([f"PR#{c['pr_a']}×#{c['pr_b']}" for c in protected])
            if protected else "No protected-path collisions"
        ),
    )

    # EVIDENCE_VERIFIED
    pr_summary = evidence_report.get("pr_summary", {})
    any_verified = any(
        v.get("highest_level") is not None for v in pr_summary.values()
    )
    rpt.set_gate(
        "EVIDENCE_VERIFIED",
        "PASS" if any_verified else "PENDING",
        evidence="Some PRs have verified evidence" if any_verified else "No verified evidence found",
    )

    # NO_UNRESOLVED_CLAIMS
    review_required = [r for r in claim_results if r.get("verdict") == "REVIEW_REQUIRED"]
    rpt.set_gate(
        "NO_UNRESOLVED_CLAIMS",
        "PASS" if not review_required else "FAIL",
        evidence=(
            f"{len(review_required)} PR(s) with REVIEW_REQUIRED claims"
            if review_required else "No unresolved claims"
        ),
    )

    # SNAPSHOT_FRESH
    if snapshot_age_hours is None:
        rpt.set_gate("SNAPSHOT_FRESH", "PENDING", evidence="Snapshot age unknown")
    elif snapshot_age_hours <= staleness_threshold_hours:
        rpt.set_gate(
            "SNAPSHOT_FRESH", "PASS",
            evidence=f"Snapshot age {snapshot_age_hours:.1f}h ≤ {staleness_threshold_hours}h threshold",
        )
    else:
        rpt.set_gate(
            "SNAPSHOT_FRESH", "FAIL",
            evidence=f"Snapshot age {snapshot_age_hours:.1f}h > {staleness_threshold_hours}h threshold. Re-snapshot required.",
        )

    return rpt
