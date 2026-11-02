"""Stage 4 — File-level collision analyzer tests."""
import pytest
from tools.integration_intel_offline.collision import (
    normalize_path, normalize_set, case_variants,
    classify_collision, analyze_snapshot_collisions,
    PathNormError,
)


class TestNormalize:
    def test_simple_path(self):
        assert normalize_path("src/foo/bar.py") == "src/foo/bar.py"

    def test_traversal_rejected(self):
        with pytest.raises(PathNormError, match="traversal"):
            normalize_path("../etc/passwd")

    def test_double_traversal_rejected(self):
        with pytest.raises(PathNormError):
            normalize_path("src/../../secret.py")

    def test_absolute_rejected(self):
        with pytest.raises(PathNormError, match="Absolute"):
            normalize_path("/etc/passwd")

    def test_normalize_set_drops_empty(self):
        s = normalize_set(["a/b.py", "", "  "])
        assert s == {"a/b.py"}


class TestCaseVariants:
    def test_no_conflicts(self):
        assert case_variants({"src/foo.py", "src/bar.py"}) == []

    def test_case_conflict_detected(self):
        conflicts = case_variants({"src/Foo.py", "src/foo.py"})
        assert len(conflicts) == 1

    def test_no_conflict_different_paths(self):
        assert case_variants({"src/Foo.py", "tests/foo.py"}) == []


class TestClassifyCollision:
    def test_non_overlap(self):
        r = classify_collision(["src/a.py"], ["src/b.py"])
        assert r["kind"] == "NON_OVERLAP"
        assert r["shared_paths"] == []

    def test_direct_write_collision(self):
        r = classify_collision(["src/shared.py"], ["src/shared.py"])
        assert r["kind"] == "DIRECT_WRITE_COLLISION"
        assert "src/shared.py" in r["shared_paths"]

    def test_protected_path_escalated(self):
        r = classify_collision(
            ["src/aql/observation/positions.py"],
            ["src/aql/observation/positions.py"],
        )
        assert r["kind"] == "PROTECTED_PATH_COLLISION"
        assert "src/aql/observation/positions.py" in r["protected_collisions"]

    def test_possible_shared_contract(self):
        r = classify_collision(["src/aql_new/"], ["src/aql_new/sub/mod.py"])
        assert r["kind"] == "POSSIBLE_SHARED_CONTRACT"

    def test_classification_label_present(self):
        r = classify_collision(["a.py"], ["b.py"])
        assert "NOT_A_MERGE_DECISION" in r["classification"]

    def test_case_conflict_flagged_in_non_overlap(self):
        r = classify_collision(["src/Foo.py"], ["src/foo.py"])
        # Different paths (case-different) are still a DIRECT_WRITE_COLLISION
        # on case-insensitive filesystems; on Linux they're distinct
        assert r["kind"] in ("DIRECT_WRITE_COLLISION", "NON_OVERLAP")
        # But case conflicts should be flagged regardless
        assert len(r["case_conflicts"]) >= 1


class TestAnalyzeSnapshotCollisions:
    def test_two_non_overlapping_prs(self):
        prs = [
            {"number": 1, "changed_paths": ["src/a.py"]},
            {"number": 2, "changed_paths": ["src/b.py"]},
        ]
        assert analyze_snapshot_collisions(prs) == []

    def test_two_colliding_prs(self):
        prs = [
            {"number": 1, "changed_paths": ["src/shared.py"]},
            {"number": 2, "changed_paths": ["src/shared.py"]},
        ]
        results = analyze_snapshot_collisions(prs)
        assert len(results) == 1
        assert results[0]["kind"] == "DIRECT_WRITE_COLLISION"
        assert results[0]["pr_a"] == 1
        assert results[0]["pr_b"] == 2

    def test_protected_collision_in_pairwise(self):
        prs = [
            {"number": 208, "changed_paths": ["research_wp_r0/indicator_library.py"]},
            {"number": 999, "changed_paths": ["research_wp_r0/indicator_library.py"]},
        ]
        results = analyze_snapshot_collisions(prs)
        assert results[0]["kind"] == "PROTECTED_PATH_COLLISION"

    def test_three_prs_only_one_collision(self):
        prs = [
            {"number": 1, "changed_paths": ["src/x.py"]},
            {"number": 2, "changed_paths": ["src/x.py"]},
            {"number": 3, "changed_paths": ["src/y.py"]},
        ]
        results = analyze_snapshot_collisions(prs)
        assert len(results) == 1
        assert {results[0]["pr_a"], results[0]["pr_b"]} == {1, 2}
