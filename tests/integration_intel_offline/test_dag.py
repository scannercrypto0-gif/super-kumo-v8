"""Stage 3 — PR ancestry DAG tests.

Tests: cycle detection, missing parents, stale base detection,
deterministic candidate review order, and ambiguity detection.
"""
import copy
import pytest
from tools.integration_intel_offline.schema import SCHEMA_VERSION
from tools.integration_intel_offline.dag import DependencyDAG, _digest

BASE_SNAPSHOT = {
    "schema_version": SCHEMA_VERSION,
    "snapshot_at": "2026-10-31T00:00:00Z",
    "main_head_sha": "dbc191d",
    "access_limits": ["cross-chat inaccessible"],
    "prs": [],
}

def make_pr(number, base_ref="main", head_sha=None, **kwargs):
    sha = head_sha or f"{'0'*9}{number}"
    return {
        "number": number,
        "head_sha": sha[:10] if len(sha) >= 10 else sha.ljust(10, "0"),
        "base_ref": base_ref,
        "draft": True,
        "title": f"PR #{number}",
        "state": "open",
        "evidence_kind": "VERIFIED_REMOTE_METADATA",
        "merged": False,
        "merged_evidence_kind": "VERIFIED_REMOTE_METADATA",
        **kwargs,
    }

def make_snapshot(*prs):
    s = copy.deepcopy(BASE_SNAPSHOT)
    s["prs"] = list(prs)
    return s


class TestNoDependencies:
    def test_single_pr_no_cycle(self):
        dag = DependencyDAG(make_snapshot(make_pr(1)))
        assert dag.find_cycles() == []

    def test_single_pr_order(self):
        dag = DependencyDAG(make_snapshot(make_pr(1)))
        assert dag.candidate_review_order() == [1]

    def test_two_independent_prs_ambiguous(self):
        dag = DependencyDAG(make_snapshot(make_pr(1), make_pr(2)))
        assert dag.is_ambiguous_order() is True

    def test_no_missing_parents(self):
        dag = DependencyDAG(make_snapshot(make_pr(1)))
        assert dag.missing_parents() == {}


class TestExplicitDependencies:
    def test_linear_chain_order(self):
        """PR 3 depends on PR 2 depends on PR 1 → review order: 1, 2, 3."""
        pr1 = make_pr(1)
        pr2 = make_pr(2, depends_on=[1])
        pr3 = make_pr(3, depends_on=[2])
        dag = DependencyDAG(make_snapshot(pr1, pr2, pr3))
        order = dag.candidate_review_order()
        assert order is not None
        assert order.index(1) < order.index(2) < order.index(3)

    def test_no_ambiguity_in_chain(self):
        pr1 = make_pr(1)
        pr2 = make_pr(2, depends_on=[1])
        dag = DependencyDAG(make_snapshot(pr1, pr2))
        assert dag.is_ambiguous_order() is False

    def test_missing_parent_detected(self):
        pr2 = make_pr(2, depends_on=[99])  # PR 99 not in snapshot
        dag = DependencyDAG(make_snapshot(pr2))
        missing = dag.missing_parents()
        assert 2 in missing
        assert 99 in missing[2]


class TestCycleDetection:
    def test_simple_cycle(self):
        """PR 1 depends on PR 2, PR 2 depends on PR 1 → cycle."""
        pr1 = make_pr(1, depends_on=[2])
        pr2 = make_pr(2, depends_on=[1])
        dag = DependencyDAG(make_snapshot(pr1, pr2))
        cycles = dag.find_cycles()
        assert len(cycles) > 0
        # Both nodes must appear in some cycle
        all_in_cycles = {n for c in cycles for n in c}
        assert 1 in all_in_cycles
        assert 2 in all_in_cycles

    def test_cycle_blocks_order(self):
        pr1 = make_pr(1, depends_on=[2])
        pr2 = make_pr(2, depends_on=[1])
        dag = DependencyDAG(make_snapshot(pr1, pr2))
        assert dag.candidate_review_order() is None

    def test_three_node_cycle(self):
        pr1 = make_pr(1, depends_on=[3])
        pr2 = make_pr(2, depends_on=[1])
        pr3 = make_pr(3, depends_on=[2])
        dag = DependencyDAG(make_snapshot(pr1, pr2, pr3))
        assert len(dag.find_cycles()) > 0

    def test_no_cycle_in_tree(self):
        pr1 = make_pr(1)
        pr2 = make_pr(2, depends_on=[1])
        pr3 = make_pr(3, depends_on=[1])
        dag = DependencyDAG(make_snapshot(pr1, pr2, pr3))
        assert dag.find_cycles() == []


class TestStaleBases:
    def test_unknown_merged_flagged(self):
        pr = make_pr(1, merged=True, merged_evidence_kind="UNKNOWN")
        dag = DependencyDAG(make_snapshot(pr))
        stale = dag.stale_bases()
        assert 1 in stale
        assert "UNKNOWN" in stale[1]

    def test_verified_merge_not_stale(self):
        pr = make_pr(1, merged=True, merged_evidence_kind="VERIFIED_REMOTE_METADATA")
        dag = DependencyDAG(make_snapshot(pr))
        stale = dag.stale_bases()
        assert 1 not in stale


class TestDeterminism:
    def test_report_digest_is_stable(self):
        snap = make_snapshot(make_pr(1), make_pr(2, depends_on=[1]))
        dag1 = DependencyDAG(snap)
        dag2 = DependencyDAG(snap)
        assert dag1.report()["report_digest"] == dag2.report()["report_digest"]

    def test_order_is_deterministic(self):
        snap = make_snapshot(make_pr(3), make_pr(1), make_pr(2))
        dag = DependencyDAG(snap)
        o1 = dag.candidate_review_order()
        o2 = dag.candidate_review_order()
        assert o1 == o2

    def test_analysis_kind_label(self):
        dag = DependencyDAG(make_snapshot(make_pr(1)))
        report = dag.report()
        assert "NOT_A_MERGE_PLAN" in report["analysis_kind"]


class TestGoldenSnapshotDAG:
    """Run DAG on the golden fixture from Stage 2."""
    def test_golden_no_cycles(self):
        import json, os
        path = os.path.join(os.path.dirname(__file__), "fixtures", "golden_snapshot.json")
        with open(path) as f:
            snap = json.load(f)
        dag = DependencyDAG(snap)
        assert dag.find_cycles() == []

    def test_golden_order_not_none(self):
        import json, os
        path = os.path.join(os.path.dirname(__file__), "fixtures", "golden_snapshot.json")
        with open(path) as f:
            snap = json.load(f)
        dag = DependencyDAG(snap)
        assert dag.candidate_review_order() is not None
