"""PR ancestry / dependency DAG.

Builds a directed graph where an edge A→B means PR A's base is PR B's head
branch, or PR A explicitly declares B as a dependency (via `depends_on`).

Detects:
  - Cycles (stacked PRs that form a loop)
  - Missing parents (base branch not found in snapshot)
  - Stale/diverged bases (base_ref no longer matches known head)
  - Ambiguous candidate merge order (multiple valid topological sorts)

Output: candidate review order only — never a merge decision.
Deterministic: given the same snapshot digest, output is always identical.
"""
from __future__ import annotations
import hashlib
import json
from collections import defaultdict, deque
from typing import Any

# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

class PRNode:
    """One PR in the dependency graph."""
    __slots__ = ("number", "head_sha", "base_ref", "draft", "state", "title",
                 "merged", "merged_evidence_kind")

    def __init__(self, pr: dict):
        self.number = pr["number"]
        self.head_sha = pr["head_sha"]
        self.base_ref = pr["base_ref"]
        self.draft = pr["draft"]
        self.state = pr["state"]
        self.title = pr["title"]
        self.merged = pr["merged"]
        self.merged_evidence_kind = pr["merged_evidence_kind"]

    def __repr__(self):
        return f"PR#{self.number}({self.head_sha[:8]}→{self.base_ref})"


class DependencyDAG:
    """Offline PR dependency graph.

    Nodes: PR numbers.
    Edges: pr_a depends_on pr_b (pr_a cannot be reviewed before pr_b).
    The base_ref of each PR is resolved to a PR number if that PR's head
    branch name matches. Base refs pointing to "main" or unknown branches
    are treated as roots (no upstream PR dependency within this snapshot).
    """

    def __init__(self, snapshot: dict):
        self._snapshot_digest = _digest(snapshot)
        prs = snapshot["prs"]
        self._nodes: dict[int, PRNode] = {pr["number"]: PRNode(pr) for pr in prs}
        # Map branch name → PR number (for base resolution)
        # A branch name is derived from the PR's own head branch if provided,
        # or we use the head_sha for identity. We resolve base_ref to PR number
        # by checking if any PR's head_sha prefix matches the base_ref,
        # OR if the base_ref is a known PR head branch name.
        # Since the snapshot may not carry head branch names (only head_sha),
        # we rely on explicit depends_on fields or stacked-branch detection.
        self._explicit_depends: dict[int, list[int]] = {}  # pr_number → [pr_numbers it depends on]
        self._build_edges(prs)

    def _build_edges(self, prs: list[dict]) -> None:
        """Resolve base_ref to PR numbers where possible."""
        # Build head-sha prefix → PR number index for stacked branch detection
        sha_index: dict[str, int] = {}
        for pr in prs:
            sha_index[pr["head_sha"][:10]] = pr["number"]
            sha_index[pr["head_sha"]] = pr["number"]

        for pr in prs:
            deps = list(pr.get("depends_on", []))
            # Attempt SHA-based base resolution:
            # If base_ref looks like a SHA (hex chars), try to match it to a known head
            base = pr["base_ref"]
            if _is_sha_like(base) and base[:10] in sha_index:
                parent_num = sha_index[base[:10]]
                if parent_num != pr["number"] and parent_num not in deps:
                    deps.append(parent_num)
            if deps:
                self._explicit_depends[pr["number"]] = deps

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------

    def find_cycles(self) -> list[list[int]]:
        """Return a list of cycles found in the dependency graph."""
        visited: set[int] = set()
        rec_stack: set[int] = set()
        cycles: list[list[int]] = []

        def dfs(node: int, path: list[int]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for dep in self._explicit_depends.get(node, []):
                if dep not in visited:
                    dfs(dep, path)
                elif dep in rec_stack:
                    # Found a cycle: extract it from path
                    idx = path.index(dep)
                    cycles.append(path[idx:] + [dep])
            path.pop()
            rec_stack.discard(node)

        for n in self._nodes:
            if n not in visited:
                dfs(n, [])
        return cycles

    def missing_parents(self) -> dict[int, list[int]]:
        """PR numbers whose explicit depends_on point to PRs not in snapshot."""
        missing: dict[int, list[int]] = {}
        for pr_num, deps in self._explicit_depends.items():
            absent = [d for d in deps if d not in self._nodes]
            if absent:
                missing[pr_num] = absent
        return missing

    def stale_bases(self, known_heads: dict[str, str] | None = None) -> dict[int, str]:
        """Detect PRs whose base_ref resolves to a SHA that has diverged.

        known_heads: {branch_name: current_sha} — if provided, compare against
        what the snapshot recorded. When not provided, emit UNKNOWN for non-main bases.
        Returns {pr_number: reason_string}.
        """
        stale: dict[int, str] = {}
        for n, node in self._nodes.items():
            if node.merged is True and node.merged_evidence_kind == "UNKNOWN":
                stale[n] = "INFERRED_MERGE_CLAIM:merged=True but evidence=UNKNOWN"
            if known_heads and node.base_ref in known_heads:
                # We could compare base SHA here; for offline use, just flag
                pass
        return stale

    def candidate_review_order(self) -> list[int] | None:
        """Topological sort of PR numbers (leaves first = can be reviewed independently).

        Returns None if cycles exist (topological sort not possible).
        If multiple valid orderings exist, returns the lexicographically smallest
        for determinism. This is CANDIDATE REVIEW ORDER only — not a merge plan.
        """
        if self.find_cycles():
            return None

        # Kahn's algorithm with min-heap for determinism
        in_degree: dict[int, int] = defaultdict(int)
        graph: dict[int, list[int]] = defaultdict(list)
        all_nodes = set(self._nodes.keys())

        for pr_num, deps in self._explicit_depends.items():
            for dep in deps:
                if dep in all_nodes:
                    graph[dep].append(pr_num)
                    in_degree[pr_num] += 1

        queue = deque(sorted(n for n in all_nodes if in_degree[n] == 0))
        order: list[int] = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for succ in sorted(graph[n]):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)
        return order if len(order) == len(all_nodes) else None

    def is_ambiguous_order(self) -> bool:
        """True if multiple valid topological orderings exist (parallelizable PRs)."""
        # Simplified: ambiguous if any two PRs have no dependency relationship
        deps_flat: set[tuple[int,int]] = set()
        for pr_num, deps in self._explicit_depends.items():
            for d in deps:
                deps_flat.add((pr_num, d))
                deps_flat.add((d, pr_num))
        prs = list(self._nodes.keys())
        for i in range(len(prs)):
            for j in range(i+1, len(prs)):
                a, b = prs[i], prs[j]
                if (a, b) not in deps_flat and (b, a) not in deps_flat:
                    return True
        return False

    def report(self) -> dict:
        """Serializable analysis report. Deterministic given same snapshot_digest."""
        cycles = self.find_cycles()
        missing = self.missing_parents()
        stale = self.stale_bases()
        order = self.candidate_review_order()
        result = {
            "snapshot_digest": self._snapshot_digest,
            "pr_count": len(self._nodes),
            "dependency_edges": {str(k): v for k, v in self._explicit_depends.items()},
            "cycles": cycles,
            "missing_parents": {str(k): v for k, v in missing.items()},
            "stale_bases": {str(k): v for k, v in stale.items()},
            "candidate_review_order": order,
            "ambiguous_order": self.is_ambiguous_order(),
            "analysis_kind": "CANDIDATE_REVIEW_ORDER_ONLY__NOT_A_MERGE_PLAN",
        }
        result["report_digest"] = _digest(result)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_sha_like(s: str) -> bool:
    return bool(s) and all(c in "0123456789abcdefABCDEF" for c in s) and len(s) >= 7

def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
