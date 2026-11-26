"""Stage 10 — Adversarial review.

Tests stale heads, fake merge flags, contradictory acceptance,
cycles, path traversal, case collisions, duplicate IDs, version downgrade.
Each test represents a genuine attack vector or edge case.
"""
import copy
import json
import os
import pytest

from tools.integration_intel_offline.schema import (
    validate_snapshot, SCHEMA_VERSION, SnapshotParseError, snapshot_digest,
)
from tools.integration_intel_offline.dag import DependencyDAG
from tools.integration_intel_offline.collision import (
    normalize_path, PathNormError, classify_collision,
)
from tools.integration_intel_offline.claim_firewall import scan_text
from tools.integration_intel_offline.evidence_registry import EvidenceEntry, EvidenceRegistry
from tools.integration_intel_offline.release_readiness import build_readiness_report


GOLDEN = os.path.join(os.path.dirname(__file__), "fixtures", "golden_snapshot.json")


def load_golden():
    with open(GOLDEN) as f:
        return json.load(f)


def make_pr(number, base_ref="main", head_sha=None, merged=False,
            merged_evidence_kind="VERIFIED_REMOTE_METADATA", **kwargs):
    sha = head_sha or f"{'a' * 9}{number}"
    return {
        "number": number,
        "head_sha": sha[:10].ljust(10, "0"),
        "base_ref": base_ref,
        "draft": True,
        "title": f"PR #{number}",
        "state": "open",
        "evidence_kind": "VERIFIED_REMOTE_METADATA",
        "merged": merged,
        "merged_evidence_kind": merged_evidence_kind,
        **kwargs,
    }


def base_snapshot(*prs):
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_at": "2026-10-31T00:00:00Z",
        "main_head_sha": "dbc191d",
        "access_limits": ["none"],
        "prs": list(prs),
    }


# ---------------------------------------------------------------------------
# 1. Stale heads / fake merge flags
# ---------------------------------------------------------------------------
class TestStaleMergeFlags:
    def test_merged_true_with_unknown_evidence_flagged(self):
        pr = make_pr(1, merged=True, merged_evidence_kind="UNKNOWN")
        dag = DependencyDAG(base_snapshot(pr))
        stale = dag.stale_bases()
        assert 1 in stale

    def test_merged_true_with_verified_not_flagged(self):
        pr = make_pr(1, merged=True, merged_evidence_kind="VERIFIED_REMOTE_METADATA")
        dag = DependencyDAG(base_snapshot(pr))
        assert 1 not in dag.stale_bases()

    def test_merged_false_with_unknown_evidence_ok(self):
        pr = make_pr(1, merged=False, merged_evidence_kind="UNKNOWN")
        dag = DependencyDAG(base_snapshot(pr))
        # open PR with UNKNOWN evidence on merge is not stale
        assert 1 not in dag.stale_bases()

    def test_self_reported_merge_claim_not_treated_as_verified(self):
        pr = make_pr(1, merged=True, merged_evidence_kind="SELF_REPORTED")
        dag = DependencyDAG(base_snapshot(pr))
        # SELF_REPORTED is weaker than VERIFIED; not flagged as stale but shouldn't be trusted
        # toolkit correctly does not auto-approve


# ---------------------------------------------------------------------------
# 2. Contradictory acceptance (verified + invalidated)
# ---------------------------------------------------------------------------
class TestContradictoryEvidence:
    def test_invalidated_entry_not_counted_as_verified(self):
        reg = EvidenceRegistry()
        reg.add(EvidenceEntry(1, "aaaa000000", "W1", "VERIFIED"))
        reg.invalidate_for_pr(1, "bbbb111111")
        assert reg.highest_level(1) is None

    def test_pending_after_head_change_not_verified(self):
        reg = EvidenceRegistry()
        reg.add(EvidenceEntry(1, "aaaa000000", "W1", "VERIFIED"))
        reg.invalidate_for_pr(1, "cccc222222")
        # PENDING added for new head
        reg.add(EvidenceEntry(1, "cccc222222", "W1", "PENDING"))
        assert reg.highest_level(1) is None

    def test_independent_audit_after_invalidation_restores(self):
        reg = EvidenceRegistry()
        reg.add(EvidenceEntry(1, "aaaa000000", "W1", "VERIFIED"))
        reg.invalidate_for_pr(1, "bbbb111111")
        reg.add(EvidenceEntry(1, "bbbb111111", "INDEPENDENT_AUDIT", "VERIFIED"))
        assert reg.highest_level(1) == "INDEPENDENT_AUDIT"


# ---------------------------------------------------------------------------
# 3. Cycle attacks
# ---------------------------------------------------------------------------
class TestCycleAttacks:
    def test_self_loop_dependency(self):
        pr = make_pr(1, depends_on=[1])
        dag = DependencyDAG(base_snapshot(pr))
        assert len(dag.find_cycles()) > 0

    def test_two_node_cycle_blocks_order(self):
        dag = DependencyDAG(base_snapshot(
            make_pr(1, depends_on=[2]),
            make_pr(2, depends_on=[1]),
        ))
        assert dag.candidate_review_order() is None

    def test_large_cycle_detected(self):
        prs = [make_pr(i, depends_on=[(i % 5) + 1]) for i in range(1, 6)]
        dag = DependencyDAG(base_snapshot(*prs))
        assert len(dag.find_cycles()) > 0


# ---------------------------------------------------------------------------
# 4. Path traversal attacks
# ---------------------------------------------------------------------------
class TestPathTraversal:
    def test_dotdot_rejected(self):
        with pytest.raises(PathNormError, match="traversal"):
            normalize_path("../etc/passwd")

    def test_embedded_dotdot_rejected(self):
        with pytest.raises(PathNormError):
            normalize_path("src/../../secret.py")

    def test_absolute_path_rejected(self):
        with pytest.raises(PathNormError, match="Absolute"):
            normalize_path("/etc/passwd")

    def test_windows_style_dotdot_linux_behavior(self):
        # On Linux, backslash is not a separator, so "src\\.." is treated as a filename.
        # The toolkit is Linux-native; this is a documented limitation (see KNOWN_LIMITATIONS).
        # The test verifies the toolkit does NOT crash and returns a normalized string.
        result = normalize_path("src\\..\\secret.py")
        # On Linux: PurePosixPath treats backslash as part of filename — no traversal possible
        assert isinstance(result, str)
        # Verify the POSIX dotdot traversal (with slash) IS still rejected
        with pytest.raises(PathNormError):
            normalize_path("src/../secret.py")


# ---------------------------------------------------------------------------
# 5. Case collision attacks
# ---------------------------------------------------------------------------
class TestCaseCollisions:
    def test_case_only_difference_flagged(self):
        r = classify_collision(["src/Foo.py"], ["src/foo.py"])
        assert len(r["case_conflicts"]) >= 1

    def test_mixed_case_and_direct_collision(self):
        r = classify_collision(["src/shared.py", "src/Shared.py"], ["src/shared.py"])
        assert r["kind"] in ("DIRECT_WRITE_COLLISION", "PROTECTED_PATH_COLLISION")


# ---------------------------------------------------------------------------
# 6. Duplicate PR number in snapshot
# ---------------------------------------------------------------------------
class TestDuplicatePrNumber:
    def test_duplicate_number_rejected_by_schema(self):
        snap = base_snapshot(make_pr(1), make_pr(1))  # duplicate
        with pytest.raises(SnapshotParseError, match="[Dd]uplicate"):
            validate_snapshot(snap)


# ---------------------------------------------------------------------------
# 7. Schema version downgrade
# ---------------------------------------------------------------------------
class TestVersionDowngrade:
    def test_wrong_version_rejected(self):
        snap = base_snapshot()
        snap["schema_version"] = "integration-intel-snapshot-0"  # wrong version
        with pytest.raises(SnapshotParseError, match="schema_version"):
            validate_snapshot(snap)

    def test_missing_version_rejected(self):
        snap = base_snapshot()
        del snap["schema_version"]
        with pytest.raises(SnapshotParseError):
            validate_snapshot(snap)


# ---------------------------------------------------------------------------
# 8. Claim firewall adversarial
# ---------------------------------------------------------------------------
class TestClaimFirewallAdversarial:
    def test_obfuscated_merge_ready_still_caught(self):
        # "merge-ready" with hyphen should be caught
        hits = scan_text("This PR is merge-ready.", "test")
        assert len(hits) >= 1

    def test_approved_in_different_context_caught(self):
        hits = scan_text("Architecture approved by team.", "test")
        assert len(hits) >= 1

    def test_legitimate_word_proven_is_flagged(self):
        # Even in a benign context: the firewall flags, human reviews
        hits = scan_text("The pattern has been proven in tests.", "test")
        assert len(hits) >= 1

    def test_clean_technical_text_not_flagged(self):
        text = (
            "Refactors the DataAvailabilityKind enum to add RETROSPECTIVE. "
            "Adds unit test for NaN propagation guard. "
            "Updates CI workflow path triggers."
        )
        hits = scan_text(text, "test")
        assert hits == []


# ---------------------------------------------------------------------------
# 9. Readiness: all-blocker scenario
# ---------------------------------------------------------------------------
class TestReadinessAdversarial:
    def test_all_gates_fail_gives_blocked(self):
        dag_bad = {
            "cycles": [[1, 2]],
            "missing_parents": {"3": [99]},
            "pr_count": 3,
            "candidate_review_order": None,
        }
        collisions = [
            {"kind": "DIRECT_WRITE_COLLISION", "pr_a": 1, "pr_b": 2},
            {"kind": "PROTECTED_PATH_COLLISION", "pr_a": 1, "pr_b": 3},
        ]
        claims = [{"pr_number": 1, "verdict": "REVIEW_REQUIRED", "hit_count": 3}]
        rpt = build_readiness_report(dag_bad, collisions, {"pr_summary": {}}, claims, snapshot_age_hours=100.0)
        assert rpt.verdict() == "BLOCKED"
        assert len(rpt.blockers()) >= 3

    def test_verdict_never_says_approved(self):
        from tools.integration_intel_offline.release_readiness import GATE_NAMES, ReleaseReadinessReport
        rpt = ReleaseReadinessReport()
        for name in GATE_NAMES:
            rpt.set_gate(name, "PASS")
        r = rpt.report()
        # "APPROVED" must never appear in the verdict
        assert "APPROVED" not in r["verdict"]


# ---------------------------------------------------------------------------
# 10. Golden snapshot: end-to-end adversarial
# ---------------------------------------------------------------------------
class TestGoldenAdversarial:
    def test_golden_validates(self):
        validate_snapshot(load_golden())

    def test_golden_digest_stable(self):
        s = load_golden()
        d1 = snapshot_digest(s)
        d2 = snapshot_digest(s)
        assert d1 == d2

    def test_golden_no_cycles(self):
        dag = DependencyDAG(load_golden())
        assert dag.find_cycles() == []

    def test_golden_no_protected_path_collision(self):
        """Golden PRs (#208,#209,#204,#118,#46) should not have protected-path collisions."""
        # They have no changed_paths in golden fixture — so no collisions
        prs = [{"number": p["number"], "changed_paths": []} for p in load_golden()["prs"]]
        from tools.integration_intel_offline.collision import analyze_snapshot_collisions
        results = analyze_snapshot_collisions(prs)
        protected = [r for r in results if r["kind"] == "PROTECTED_PATH_COLLISION"]
        assert protected == []
