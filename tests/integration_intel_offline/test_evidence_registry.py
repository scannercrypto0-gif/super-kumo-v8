"""Stage 5 — Evidence registry tests."""
import pytest
from tools.integration_intel_offline.evidence_registry import (
    EvidenceEntry, EvidenceRegistry,
)


def make_entry(pr_number=1, head_sha="abcdef1234", level="W1",
               status="VERIFIED", **kwargs):
    return EvidenceEntry(pr_number, head_sha, level, status, **kwargs)


class TestEvidenceEntry:
    def test_head_sha_truncated(self):
        e = make_entry(head_sha="abcdef123456789")
        assert len(e.head_sha) == 10

    def test_to_dict_keys(self):
        d = make_entry().to_dict()
        assert "pr_number" in d and "level" in d and "status" in d

    def test_invalidate_changes_status(self):
        e = make_entry(head_sha="aaaa000000")
        inv = e.invalidate("bbbb111111")
        assert inv.status == "INVALIDATED"
        assert "bbbb111111"[:10] in inv.head_sha or "aaaa" in inv.result


class TestEvidenceRegistry:
    def test_add_and_retrieve(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=10))
        assert len(reg.entries_for(10)) == 1

    def test_entries_for_wrong_pr_empty(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=10))
        assert reg.entries_for(99) == []

    def test_invalidate_on_head_change(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=5, head_sha="aaaa000000", status="VERIFIED"))
        count = reg.invalidate_for_pr(5, "bbbb111111")
        assert count == 1
        assert reg.entries_for(5)[0].status == "INVALIDATED"

    def test_invalidate_same_sha_noop(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=5, head_sha="abcdef1234", status="VERIFIED"))
        count = reg.invalidate_for_pr(5, "abcdef1234")
        assert count == 0

    def test_highest_level_independent_wins(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=1, level="W1", status="VERIFIED"))
        reg.add(make_entry(pr_number=1, level="INDEPENDENT_AUDIT", status="VERIFIED"))
        assert reg.highest_level(1) == "INDEPENDENT_AUDIT"

    def test_highest_level_none_when_no_verified(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=1, level="W1", status="PENDING"))
        assert reg.highest_level(1) is None

    def test_independent_audit_pending_true(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=2, level="W0", status="VERIFIED"))
        assert reg.is_independent_audit_pending(2) is True

    def test_independent_audit_pending_false(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=2, level="INDEPENDENT_AUDIT", status="VERIFIED"))
        assert reg.is_independent_audit_pending(2) is False

    def test_registry_digest_stable(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=1))
        d1 = reg.registry_digest()
        d2 = reg.registry_digest()
        assert d1 == d2

    def test_report_classification_label(self):
        reg = EvidenceRegistry()
        r = reg.report()
        assert "NOT_RELEASE_APPROVAL" in r["classification"]

    def test_report_pr_summary_keys(self):
        reg = EvidenceRegistry()
        reg.add(make_entry(pr_number=42, status="VERIFIED", level="W0"))
        r = reg.report()
        assert "42" in r["pr_summary"]
        assert "independent_audit_pending" in r["pr_summary"]["42"]
