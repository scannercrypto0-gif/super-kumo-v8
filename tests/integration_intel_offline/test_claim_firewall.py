"""Stage 7 — Claim firewall tests. Negative fixtures required."""
import pytest
from tools.integration_intel_offline.claim_firewall import (
    scan_text, scan_pr_record, scan_snapshot_claims,
)


class TestScanText:
    # --- POSITIVE (risk terms should trigger REVIEW_REQUIRED) ---
    def test_proven_triggers(self):
        hits = scan_text("This approach has been proven correct.", "test")
        assert any(h["verdict"] == "REVIEW_REQUIRED" for h in hits)

    def test_guaranteed_triggers(self):
        hits = scan_text("Guaranteed to work in all cases.", "test")
        assert len(hits) >= 1

    def test_production_ready_triggers(self):
        hits = scan_text("The module is production-ready.", "test")
        assert len(hits) >= 1

    def test_safe_to_merge_triggers(self):
        hits = scan_text("Safe to merge now.", "test")
        assert len(hits) >= 1

    def test_merge_ready_triggers(self):
        hits = scan_text("This PR is merge-ready.", "test")
        assert len(hits) >= 1

    def test_statistically_significant_triggers(self):
        hits = scan_text("Results are statistically significant.", "test")
        assert len(hits) >= 1

    def test_approved_triggers(self):
        hits = scan_text("Architecture approved.", "test")
        assert len(hits) >= 1

    def test_100_percent_accurate_triggers(self):
        hits = scan_text("Model is 100% accurate.", "test")
        assert len(hits) >= 1

    # --- NEGATIVE (neutral text must NOT trigger) ---
    def test_neutral_description_no_hits(self):
        hits = scan_text("Refactors the indicator module to improve readability.", "test")
        assert hits == []

    def test_fix_commit_message_no_hits(self):
        hits = scan_text("Fix NaN propagation in compute_values.", "test")
        assert hits == []

    def test_adds_test_message_no_hits(self):
        hits = scan_text("Adds unit tests for edge case handling.", "test")
        assert hits == []

    def test_empty_string_no_hits(self):
        assert scan_text("", "test") == []

    def test_case_insensitive_detection(self):
        hits = scan_text("PROVEN to be correct.", "test")
        assert len(hits) >= 1


class TestScanPrRecord:
    def test_clean_pr_no_concern(self):
        pr = {"number": 1, "title": "Refactor collision module", "body": "See tests."}
        r = scan_pr_record(pr)
        assert r["verdict"] == "NO_CONCERN_DETECTED"
        assert r["hit_count"] == 0

    def test_risky_title_review_required(self):
        pr = {"number": 2, "title": "Production-ready ingestion layer"}
        r = scan_pr_record(pr)
        assert r["verdict"] == "REVIEW_REQUIRED"

    def test_risky_body_review_required(self):
        pr = {"number": 3, "title": "Cleanup", "body": "Safe to merge now."}
        r = scan_pr_record(pr)
        assert r["verdict"] == "REVIEW_REQUIRED"

    def test_classification_label(self):
        pr = {"number": 4, "title": "Minor fix"}
        r = scan_pr_record(pr)
        assert "NOT_A_SCIENTIFIC_VERDICT" in r["classification"]

    def test_missing_body_no_error(self):
        pr = {"number": 5, "title": "Update docs"}
        r = scan_pr_record(pr)
        assert "verdict" in r


class TestScanSnapshotClaims:
    def test_all_prs_returned(self):
        prs = [
            {"number": 1, "title": "Clean fix"},
            {"number": 2, "title": "Guaranteed performance"},
        ]
        results = scan_snapshot_claims(prs)
        assert len(results) == 2

    def test_mixed_results(self):
        prs = [
            {"number": 1, "title": "Fix typo"},
            {"number": 2, "title": "Proven algorithm"},
        ]
        results = {r["pr_number"]: r for r in scan_snapshot_claims(prs)}
        assert results[1]["verdict"] == "NO_CONCERN_DETECTED"
        assert results[2]["verdict"] == "REVIEW_REQUIRED"
