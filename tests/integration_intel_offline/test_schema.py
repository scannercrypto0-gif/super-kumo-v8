"""Stage 2 — Offline snapshot schema validation tests.

Tests strict parsing, evidence kind classification, duplicate rejection,
malformed input rejection, and golden fixture load.
"""
import copy
import json
import os
import pytest
from tools.integration_intel_offline.schema import (
    validate_snapshot, snapshot_digest, load_snapshot,
    SnapshotParseError, SCHEMA_VERSION,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
GOLDEN_PATH = os.path.join(FIXTURES_DIR, "golden_snapshot.json")

MINIMAL_PR = {
    "number": 1,
    "head_sha": "abc1234",
    "base_ref": "main",
    "draft": False,
    "title": "Test PR",
    "state": "open",
    "evidence_kind": "VERIFIED_REMOTE_METADATA",
    "merged": False,
    "merged_evidence_kind": "VERIFIED_REMOTE_METADATA",
}

MINIMAL_DOC = {
    "schema_version": SCHEMA_VERSION,
    "snapshot_at": "2026-10-31T00:00:00Z",
    "main_head_sha": "dbc191d",
    "access_limits": ["cross-chat inaccessible"],
    "prs": [MINIMAL_PR],
}


def make_doc(**overrides):
    d = copy.deepcopy(MINIMAL_DOC)
    d.update(overrides)
    return d


class TestValidDocAccepted:
    def test_minimal_doc_passes(self):
        assert validate_snapshot(MINIMAL_DOC) is MINIMAL_DOC

    def test_all_evidence_kinds_accepted(self):
        for kind in ["VERIFIED_REMOTE_METADATA", "SELF_REPORTED", "INFERRED", "UNKNOWN"]:
            pr = {**MINIMAL_PR, "evidence_kind": kind, "merged_evidence_kind": kind}
            validate_snapshot(make_doc(prs=[pr]))

    def test_merged_none_accepted(self):
        pr = {**MINIMAL_PR, "merged": None, "merged_evidence_kind": "UNKNOWN"}
        validate_snapshot(make_doc(prs=[pr]))

    def test_multiple_prs_accepted(self):
        pr2 = {**MINIMAL_PR, "number": 2}
        validate_snapshot(make_doc(prs=[MINIMAL_PR, pr2]))


class TestSchemaRejection:
    def test_wrong_schema_version(self):
        with pytest.raises(SnapshotParseError, match="schema_version"):
            validate_snapshot(make_doc(schema_version="wrong-1"))

    def test_missing_prs_key(self):
        d = copy.deepcopy(MINIMAL_DOC)
        del d["prs"]
        with pytest.raises(SnapshotParseError, match="missing required keys"):
            validate_snapshot(d)

    def test_empty_access_limits(self):
        with pytest.raises(SnapshotParseError, match="access_limits"):
            validate_snapshot(make_doc(access_limits=[]))

    def test_not_a_dict(self):
        with pytest.raises(SnapshotParseError, match="JSON object"):
            validate_snapshot([1, 2, 3])

    def test_short_main_head_sha(self):
        with pytest.raises(SnapshotParseError, match="main_head_sha"):
            validate_snapshot(make_doc(main_head_sha="abc"))


class TestPRRecordRejection:
    def _bad_pr(self, **overrides):
        return {**MINIMAL_PR, **overrides}

    def test_duplicate_pr_number(self):
        pr2 = copy.deepcopy(MINIMAL_PR)
        with pytest.raises(SnapshotParseError, match="Duplicate PR"):
            validate_snapshot(make_doc(prs=[MINIMAL_PR, pr2]))

    def test_invalid_evidence_kind(self):
        with pytest.raises(SnapshotParseError, match="evidence_kind"):
            validate_snapshot(make_doc(prs=[self._bad_pr(evidence_kind="MADE_UP")]))

    def test_invalid_state(self):
        with pytest.raises(SnapshotParseError, match="state"):
            validate_snapshot(make_doc(prs=[self._bad_pr(state="merged")]))

    def test_short_head_sha(self):
        with pytest.raises(SnapshotParseError, match="head_sha"):
            validate_snapshot(make_doc(prs=[self._bad_pr(head_sha="abc")]))

    def test_draft_not_bool(self):
        with pytest.raises(SnapshotParseError, match="draft"):
            validate_snapshot(make_doc(prs=[self._bad_pr(draft="yes")]))

    def test_merged_invalid_type(self):
        with pytest.raises(SnapshotParseError, match="merged"):
            validate_snapshot(make_doc(prs=[self._bad_pr(merged="yes")]))

    def test_missing_pr_key(self):
        pr = copy.deepcopy(MINIMAL_PR)
        del pr["base_ref"]
        with pytest.raises(SnapshotParseError, match="missing keys"):
            validate_snapshot(make_doc(prs=[pr]))


class TestDigest:
    def test_digest_is_deterministic(self):
        d1 = snapshot_digest(MINIMAL_DOC)
        d2 = snapshot_digest(MINIMAL_DOC)
        assert d1 == d2

    def test_digest_changes_on_mutation(self):
        d1 = snapshot_digest(MINIMAL_DOC)
        modified = make_doc(snapshot_at="2026-11-01T00:00:00Z")
        d2 = snapshot_digest(modified)
        assert d1 != d2


class TestGoldenFixture:
    def test_golden_fixture_loads_and_validates(self):
        doc, digest = load_snapshot(GOLDEN_PATH)
        assert doc["schema_version"] == SCHEMA_VERSION
        assert len(doc["prs"]) >= 5

    def test_golden_contains_key_prs(self):
        doc, _ = load_snapshot(GOLDEN_PATH)
        numbers = {pr["number"] for pr in doc["prs"]}
        assert 208 in numbers  # Claude hardening
        assert 209 in numbers  # Factory W1
        assert 204 in numbers  # P0

    def test_golden_digest_is_stable(self):
        doc, d1 = load_snapshot(GOLDEN_PATH)
        doc2, d2 = load_snapshot(GOLDEN_PATH)
        assert d1 == d2

    def test_golden_access_limits_present(self):
        doc, _ = load_snapshot(GOLDEN_PATH)
        combined = " ".join(doc["access_limits"])
        assert "inaccessible" in combined.lower()
        assert "207" in combined
