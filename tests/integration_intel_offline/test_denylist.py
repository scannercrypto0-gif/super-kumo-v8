"""Stage 1 — Protected-path denylist tests.

Verifies that PROTECTED paths are correctly blocked and ALLOWED namespace
paths are correctly permitted. No network, no merges, no writes to repo.
"""
import pytest
from tools.integration_intel_offline.denylist import (
    classify_path, assert_allowed, FREEZE_META, FREEZE_DIGEST, PathClass
)


class TestProtectedPaths:
    def test_w1_core_blocked(self):
        assert classify_path("src/aql/observation/position_journal.py").status == "PROTECTED"

    def test_w1_core_init_blocked(self):
        assert classify_path("src/aql/__init__.py").status == "PROTECTED"

    def test_research_wp_r0_blocked(self):
        assert classify_path("research_wp_r0/indicator_library.py").status == "PROTECTED"

    def test_research_wp_r0_attempt_ledger_blocked(self):
        assert classify_path("research_wp_r0/attempt_ledger.py").status == "PROTECTED"

    def test_core_docs_blocked(self):
        assert classify_path("docs/core/some_doc.md").status == "PROTECTED"

    def test_existing_tools_blocked(self):
        assert classify_path("tools/offline_custody_kit.py").status == "PROTECTED"
        assert classify_path("tools/g1_public_smoke.py").status == "PROTECTED"

    def test_existing_tests_blocked(self):
        assert classify_path("tests/test_sf_ind_01.py").status == "PROTECTED"
        assert classify_path("tests/test_sf_dep_guard.py").status == "PROTECTED"


class TestAllowedPaths:
    def test_toolkit_module_allowed(self):
        assert classify_path("tools/integration_intel_offline/denylist.py").status == "ALLOWED"

    def test_toolkit_test_allowed(self):
        assert classify_path("tests/integration_intel_offline/test_denylist.py").status == "ALLOWED"

    def test_toolkit_docs_allowed(self):
        assert classify_path("docs/integration_intel_offline/README.md").status == "ALLOWED"


class TestAssertAllowed:
    def test_protected_raises(self):
        with pytest.raises(PermissionError, match="PROTECTED"):
            assert_allowed("src/aql/observation/positions.py")

    def test_unclassified_raises(self):
        with pytest.raises(PermissionError, match="UNCLASSIFIED"):
            assert_allowed("some_random_file.py")

    def test_allowed_passes(self):
        assert_allowed("tools/integration_intel_offline/schema.py")  # no raise


class TestFreezeProvenance:
    def test_freeze_digest_is_stable(self):
        import hashlib, json
        expected = hashlib.sha256(
            json.dumps(FREEZE_META, sort_keys=True).encode()
        ).hexdigest()
        assert FREEZE_DIGEST == expected

    def test_main_head_recorded(self):
        assert FREEZE_META["main_head_sha"] == "dbc191d"

    def test_access_limits_documented(self):
        # Cross-chat sources inaccessible must be stated
        assert any("inaccessible" in s for s in FREEZE_META["access_limits"])
        # Issue #207 unverified must be stated
        assert any("#207" in s for s in FREEZE_META["access_limits"])
