"""R4/H2 B: purely synthetic owner-authority separation and fail-closed tests.

No original E: data, genuine signing keys, publisher I/O or H2 runs.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
from pathlib import Path
import tempfile
import unittest

from tools.atlas_h2_owner_research_authority_v1 import (
    AUTHORITY, SCHEMA, COST_SCHEMA, COST_DOMAIN, SCOPE_DOMAIN,
    AuthorityBlocked, _canonical, _digest, inspect_owner_assertion,
)


class OwnerPersonalResearchAuthority(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.key = self.root / "preexisting-test-only.key"
        self.secret = b"synthetic-fixture-NOT-A-REAL-OWNER-SECRET-0000"
        self.key.write_bytes(self.secret)
        costs = {
            "fee_entry_bps": "10", "fee_exit_bps": "10",
            "spread_entry_bps": "2", "spread_exit_bps": "2",
            "slippage_entry_bps": "3", "slippage_exit_bps": "3",
            "funding_bps_per_bar": "0",
        }
        self.policy = {
            "schema": COST_SCHEMA, "costs": costs, "market": "SPOT",
            "direction": "LONG", "research_class": "RETROSPECTIVE_NON_PIT",
            "authorization_class": "OWNER_EXPLICIT_COST_ONLY",
            "single_use_experiment_id": "RESEARCH-H-GENERIC-TEST-ONE",
        }
        self.scope = {
            "dataset_id": "BINANCE-SPOT-BTCUSDT-15M-2024-03",
            "version": 1, "month": "2024-03",
            "start_ms": 1709251200000, "end_exclusive_ms": 1711929600000,
            "decision_cutoff_ms": 1711929600000,
            "source_bytes_sha256": "a"*64,
            "manifest_integrity_sha256": "b"*64,
            "core245_native_receipt_sha256": "c"*64,
            "core253_query_sha256": "d"*64,
            "strategy_id": "h_manual_distinct_test",
            "strategy_definition_sha256": "e"*64,
            "strategy_config_sha256": "f"*64,
            "evaluator_code_sha256": "1"*64,
            "cost_policy_sha256": _digest(self.policy),
            "experiment_id": "RESEARCH-H-GENERIC-TEST-ONE",
            "owner_authorization_ref": "TEST_ONLY_NEVER_OWNER_APPROVAL",
            "research_class": "RETROSPECTIVE_NON_PIT",
            "historical_pit": "NOT_ATTESTED",
            "publisher_pit_attested": False,
            "explicit_readonly_no_export": True,
            "source_output_separate": True, "single_use": True,
        }

    def packet(self, *, scope=None, policy=None, resign=True):
        scope = deepcopy(self.scope if scope is None else scope)
        policy = deepcopy(self.policy if policy is None else policy)
        return {
            "schema": SCHEMA, "authority_class": AUTHORITY,
            "independent_license_review_status": "NOT_ATTESTED",
            "scope": scope, "cost_policy": policy,
            "owner_scope_mac": hmac.new(
                self.secret, SCOPE_DOMAIN+_canonical(scope),
                hashlib.sha256).hexdigest(),
            "owner_cost_mac": hmac.new(
                self.secret, COST_DOMAIN+_canonical(policy),
                hashlib.sha256).hexdigest(),
        }

    def inspect(self, packet):
        return inspect_owner_assertion(
            packet, trusted_owner_verifier_key=self.key)

    def test_synthetic_both_mac_verified_but_no_license_or_original_run(self):
        result = self.inspect(self.packet())
        self.assertEqual(result["status"],
                         "OWNER_SCOPE_AND_COST_MAC_VERIFIED_ONLY")
        self.assertTrue(result["owner_scope_verified"])
        self.assertTrue(result["owner_separate_cost_verified"])
        self.assertFalse(result["actual_source_receipts_verified"])
        self.assertFalse(result["original_source_io_performed"])
        self.assertFalse(result["original_h2_execution_permitted"])
        self.assertEqual(result["independent_license_review"], "NOT_ATTESTED")
        self.assertEqual(result["historical_pit"], "NOT_ATTESTED")

    def test_owner_assertion_cannot_self_claim_independent_rights(self):
        p = self.packet()
        p["independent_license_review_status"] = "INDEPENDENTLY_VERIFIED"
        with self.assertRaisesRegex(
            AuthorityBlocked, "OWNER_ASSERTION_NOT_INDEPENDENT_LICENSE"
        ):
            self.inspect(p)
        p["independent_license_review_status"] = "NOT_ATTESTED"
        p["authority_class"] = "INDEPENDENTLY_REVIEWED_LICENSE"
        with self.assertRaisesRegex(
            AuthorityBlocked, "OWNER_ASSERTION_NOT_INDEPENDENT_LICENSE"
        ):
            self.inspect(p)

    def test_modified_source_or_manifest_even_with_original_mac_fails(self):
        for field in ("source_bytes_sha256", "manifest_integrity_sha256",
                      "core245_native_receipt_sha256",
                      "core253_query_sha256", "strategy_definition_sha256"):
            with self.subTest(field=field):
                p=self.packet()
                p["scope"][field] = "0"*64
                with self.assertRaisesRegex(
                    AuthorityBlocked,"OWNER_SCOPE_MAC_INVALID"
                ):
                    self.inspect(p)

    def test_costs_need_independent_owner_mac(self):
        p=self.packet()
        p["cost_policy"]["costs"]["fee_entry_bps"]="20"
        p["scope"]["cost_policy_sha256"]=_digest(p["cost_policy"])
        # New cost digest needs new scope MAC; original cost MAC still refuses.
        p["owner_scope_mac"]=hmac.new(
            self.secret,SCOPE_DOMAIN+_canonical(p["scope"]),
            hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_SEPARATE_COST_MAC_INVALID"
        ):
            self.inspect(p)

    def test_zero_fees_funding_or_nonfinite_rejected_even_if_signed(self):
        for name,value in (("fee_entry_bps","0"),
                           ("spread_exit_bps","0"),
                           ("slippage_entry_bps","0"),
                           ("funding_bps_per_bar","1"),
                           ("fee_exit_bps","NaN")):
            with self.subTest(name=name,value=value):
                policy=deepcopy(self.policy)
                policy["costs"][name]=value
                scope=deepcopy(self.scope)
                scope["cost_policy_sha256"]=_digest(policy)
                with self.assertRaisesRegex(AuthorityBlocked,
                                             "OWNER_COST"):
                    self.inspect(self.packet(scope=scope,policy=policy))

    def test_pit_export_and_reuse_forbidden_before_mac(self):
        for field,value in (("historical_pit","ATTESTED"),
                            ("publisher_pit_attested",True),
                            ("explicit_readonly_no_export",False),
                            ("source_output_separate",False),
                            ("single_use",False)):
            with self.subTest(field=field):
                scope=deepcopy(self.scope)
                scope[field]=value
                with self.assertRaisesRegex(AuthorityBlocked,
                                             "OWNER_SCOPE_PIT_EXPORT"):
                    self.inspect(self.packet(scope=scope))

    def test_partial_or_wrong_month_refused(self):
        for field,value in (("decision_cutoff_ms",1711928700000),
                            ("end_exclusive_ms",1711928700000),
                            ("month","2024-04")):
            with self.subTest(field=field):
                scope=deepcopy(self.scope)
                scope[field]=value
                with self.assertRaisesRegex(AuthorityBlocked,
                                             "OWNER_SCOPE_"):
                    self.inspect(self.packet(scope=scope))

    def test_core245_and_core253_cannot_be_aliased(self):
        scope=deepcopy(self.scope)
        scope["core253_query_sha256"]=scope["core245_native_receipt_sha256"]
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_SCOPE_SOURCE_OR_STRATEGY_IDENTITY"
        ):
            self.inspect(self.packet(scope=scope))

    def test_untrusted_key_or_different_key_fails(self):
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_TRUST_ROOT_NOT_PROVISIONED"
        ):
            inspect_owner_assertion(self.packet(),
                                    trusted_owner_verifier_key=None)
        other=self.root/"different.key"
        other.write_bytes(b"test-other-key-"*4)
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_SCOPE_MAC_INVALID"
        ):
            inspect_owner_assertion(self.packet(),
                                    trusted_owner_verifier_key=other)

    def test_wrong_strategy_or_cost_document_identity_refused(self):
        scope=deepcopy(self.scope)
        scope["strategy_id"]="some_other_strategy"
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_SCOPE_SOURCE_OR_STRATEGY_IDENTITY"
        ):
            self.inspect(self.packet(scope=scope))
        policy=deepcopy(self.policy)
        policy["single_use_experiment_id"]="DIFFERENT_EXPERIMENT"
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_COST_POLICY_BINDING"
        ):
            self.inspect(self.packet(policy=policy))


if __name__ == "__main__":
    unittest.main()
