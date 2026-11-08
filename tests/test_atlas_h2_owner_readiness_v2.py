"""PKG-0 original H2 readiness: synthetic proof denials, NO ORIGINAL RUN."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_atlas_h2_owner_evidence_recovery_v2 import OwnerRecoverySafeSynthetic
from tools.atlas_h2_owner_personal_batch_v1 import _load_intake
from tools.atlas_h2_owner_readiness_v2 import (
    verify_signed_parent, validate_owner_readiness,
)
from tools.atlas_h2_binance_public_lane_v1 import Blocked
from tools.atlas_h2_owner_research_authority_v1 import AuthorityBlocked


class OwnerH2ReadinessGates(unittest.TestCase):
    def setUp(self):
        self.case=OwnerRecoverySafeSynthetic(methodName="test_genuine_shaped_synthetic_mock_proofs_generate_four_not_h2")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case._do()
        self.key=self.case.identity_dir/"owner-signing.key"
        self.tech,self.envelope,_=_load_intake(self.case.evidence)

    def verify(self,out=None,packet=None):
        return verify_signed_parent(
            self.tech,self.envelope if packet is None else packet,
            self.key,self.case.output if out is None else out)

    def test_owner_v2_valid_forward_signed_root_is_preflight_only(self):
        scope,policy,identity=self.verify()
        self.assertEqual(scope["strategy_id"],"h_manual_distinct_test")
        self.assertEqual(policy["costs"]["funding_bps_per_bar"],"0")
        self.assertFalse(identity["original_h2_execution_permitted"])
        self.assertFalse((self.case.evidence/"h2-personal-one-use-claim.json").exists())
        self.assertFalse((self.case.output/"h2-personal-scope-claim.json").exists())

    def test_unauthorized_new_output_root_fails(self):
        other=self.case.root/"new-owner-output"
        other.mkdir()
        with self.assertRaisesRegex(
            Blocked,"READINESS_SIGNED_OUTPUT_ROOT_OR_CODE_PINS_DRIFT"):
            self.verify(out=other)

    def test_nonce_rewrite_without_owner_mac_fails(self):
        packet=json.loads(json.dumps(self.envelope))
        packet["assertion"]["scope"]["one_use_nonce"]="f"*32
        with self.assertRaises(AuthorityBlocked):
            self.verify(packet=packet)

    def test_tampered_cost_policy_fails_without_signed_owner_mac(self):
        packet=json.loads(json.dumps(self.envelope))
        packet["assertion"]["cost_policy"]["costs"]["fee_entry_bps"]="1000"
        with self.assertRaises(AuthorityBlocked):
            self.verify(packet=packet)

    def test_key_revoke_denied_before_original(self):
        reg=self.case.identity_dir/"owner-revocations.json"
        reg.write_text(json.dumps({
            "schema":"aql.integration.h2.owner-revocations.v2",
            "revoked_key_ids":[self.case.identity["key_id"]]}))
        with self.assertRaises(AuthorityBlocked):
            self.verify()
        self.assertFalse((self.case.evidence/"h2-personal-one-use-claim.json").exists())

    def test_modified_ast_bytes_fail_exact_intake_sha(self):
        path=self.case.evidence/"manual-third-ast.json"
        path.write_text(path.read_text()+" ")
        with self.assertRaisesRegex(
            Blocked,"PERSONAL_RECEIPT_FILE_SHA_DRIFT"):
            _load_intake(self.case.evidence)

    def test_wrong_core245_receipt_identity_denied(self):
        path=self.case.evidence/"core245-native-receipt.json"
        doc=json.loads(path.read_text())
        doc["schema"]="aql.archive-custody.local-registration.v1"
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(
            Blocked,"PERSONAL_RECEIPT_FILE_SHA_DRIFT"):
            _load_intake(self.case.evidence)

    def test_missing_original_source_preflight_stops_without_one_use_claim(self):
        repo=self.case.root/"repo"
        repo.mkdir()
        data=validate_owner_readiness(
            self.case.evidence,self.case.output,self.key,repo,
            publisher=lambda *a,**kw: self.case._pub())
        self.assertEqual(data["status"],"BLOCKED")
        self.assertFalse(data["one_use_claim_created"])
        self.assertFalse(data["original_h2_executed"])
        self.assertFalse((self.case.evidence/"h2-personal-one-use-claim.json").exists())
        self.assertFalse((self.case.output/"h2-personal-scope-claim.json").exists())
        self.assertFalse((self.case.output/"results.sqlite").exists())
        self.assertEqual(
            (self.case.private/"historical"/"BTCUSDT-15m-2024-03.zip").read_bytes(),
            b"ONLY-SYNTHETIC-TEST-ARCHIVE-NOT-REAL")

    def test_already_claimed_root_blocks_without_original(self):
        (self.case.output/"h2-personal-scope-claim.json").write_text("test")
        repo=self.case.root/"repo"
        repo.mkdir()
        data=validate_owner_readiness(
            self.case.evidence,self.case.output,self.key,repo)
        self.assertEqual(data["status"],"BLOCKED")
        self.assertIn("READINESS_OUTPUT_ALREADY_CLAIMED",data["reason"])
        self.assertFalse(data["original_h2_executed"])

    def test_absent_publisher_proof_does_not_touch_sources(self):
        repo=self.case.root/"repo"
        repo.mkdir()
        data=validate_owner_readiness(
            self.case.evidence,self.case.output,self.key,repo,
            publisher=lambda *a,**kw: (_ for _ in ()).throw(
                Blocked("OFFICIAL_PROVIDER_UNAVAILABLE")))
        self.assertEqual(data["status"],"BLOCKED")
        self.assertFalse(data["one_use_claim_created"])


if __name__=="__main__":
    unittest.main()
