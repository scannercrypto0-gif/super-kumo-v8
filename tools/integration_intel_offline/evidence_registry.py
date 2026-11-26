"""Stage 5 — Evidence provenance registry.

Immutable indexed record of test/acceptance evidence per PR.
Keys: (pr_number, head_sha_prefix). Value invalidates when head changes.
Keeps W0/W1/implementation acceptance distinct.
Missing independent audit stays PENDING.
P0 waiver is scope-limited.
"""
from __future__ import annotations
import hashlib
import json
from typing import Literal

AcceptanceLevel = Literal["W0", "W1", "IMPLEMENTATION", "INDEPENDENT_AUDIT", "UNKNOWN"]
EvidenceStatus = Literal["VERIFIED", "PENDING", "INVALIDATED", "WAIVED_SCOPE_LIMITED", "UNKNOWN"]


class EvidenceEntry:
    __slots__ = ("pr_number", "head_sha", "level", "status", "test_command",
                 "result", "independence_label", "notes")

    def __init__(self, pr_number: int, head_sha: str, level: AcceptanceLevel,
                 status: EvidenceStatus, test_command: str | None = None,
                 result: str | None = None, independence_label: str = "SELF_ATTESTED",
                 notes: str = ""):
        self.pr_number = pr_number
        self.head_sha = head_sha[:10]
        self.level = level
        self.status = status
        self.test_command = test_command
        self.result = result
        self.independence_label = independence_label
        self.notes = notes

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    def invalidate(self, new_sha: str) -> "EvidenceEntry":
        return EvidenceEntry(
            self.pr_number, new_sha, self.level,
            "INVALIDATED", self.test_command,
            f"INVALIDATED: head moved from {self.head_sha} to {new_sha[:10]}",
            self.independence_label, self.notes,
        )


class EvidenceRegistry:
    """Append-only evidence index. Invalidates entries when head SHA changes."""

    def __init__(self):
        self._entries: list[EvidenceEntry] = []

    def add(self, entry: EvidenceEntry) -> None:
        self._entries.append(entry)

    def invalidate_for_pr(self, pr_number: int, new_sha: str) -> int:
        """Mark all VERIFIED entries for pr_number as INVALIDATED. Returns count."""
        count = 0
        for i, e in enumerate(self._entries):
            if e.pr_number == pr_number and e.status == "VERIFIED" and e.head_sha != new_sha[:10]:
                self._entries[i] = e.invalidate(new_sha)
                count += 1
        return count

    def entries_for(self, pr_number: int) -> list[EvidenceEntry]:
        return [e for e in self._entries if e.pr_number == pr_number]

    def highest_level(self, pr_number: int) -> AcceptanceLevel | None:
        order = ["INDEPENDENT_AUDIT", "W1", "W0", "IMPLEMENTATION", "UNKNOWN"]
        for level in order:
            if any(e.level == level and e.status == "VERIFIED"
                   for e in self.entries_for(pr_number)):
                return level  # type: ignore
        return None

    def is_independent_audit_pending(self, pr_number: int) -> bool:
        entries = self.entries_for(pr_number)
        has_independent = any(
            e.level == "INDEPENDENT_AUDIT" and e.status == "VERIFIED" for e in entries
        )
        return not has_independent

    def registry_digest(self) -> str:
        return hashlib.sha256(
            json.dumps([e.to_dict() for e in self._entries],
                       sort_keys=True).encode()
        ).hexdigest()

    def report(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self._entries],
            "pr_summary": self._pr_summary(),
            "registry_digest": self.registry_digest(),
            "classification": "EVIDENCE_INDEX_ONLY__NOT_RELEASE_APPROVAL",
        }

    def _pr_summary(self) -> dict:
        prs: set[int] = {e.pr_number for e in self._entries}
        return {
            str(n): {
                "highest_level": self.highest_level(n),
                "independent_audit_pending": self.is_independent_audit_pending(n),
                "entry_count": len(self.entries_for(n)),
            }
            for n in sorted(prs)
        }
