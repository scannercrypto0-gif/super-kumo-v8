"""Owner-personal H2 synthetic-only guarded full preflight, no original E: IO."""
from __future__ import annotations
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.atlas_h2_owner_personal_batch_v1 import (
    run_owner_personal_batch, scope_commitment,
)
from tools.atlas_h2_owner_research_authority_v1 import (
    AUTHORITY, SCHEMA, COST_SCHEMA, COST_DOMAIN, SCOPE_DOMAIN, _canonical,
    _digest,
)
from tools.atlas_h2_binance_public_lane_v1 import LANE_SCHEMA
from tools.atlas_h2_owner_local_one_shot_v1 import (
    OWNER_LIMITED_COSTS, digest, sha_file,
)
from research_wp_r0.strategy_definition import digest as ast_digest


class OwnerPersonalBatchSynthetic(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.intake=self.root/"intake"
        self.intake.mkdir()
        self.output=self.root/"output"
        self.output.mkdir()
        self.warehouse=self.root/"warehouse"
        self.vault=self.root/"vault"
        self.archive=self.root/"original"
        for folder in (self.warehouse,self.vault,self.archive):
            folder.mkdir()
        self.repo=self.root/"repo"
        self.repo.mkdir()
        self.key=self.root/"owner-trust.key"
        self.secret=b"TEST-ONLY-LOCAL-OWNER-KEY-NOT-PRODUCTION-0000"
        self.key.write_bytes(self.secret)
        self.zip=self.archive/"BTCUSDT-15m-2024-03.zip"
        self.zip.write_bytes(b"SYNTHETIC-ONLY-FIXTURE-ZIP")
        self.zip_sha=sha_file(self.zip)
        self.manifest_sha="b"*64
        self.native_sha=None
        start=1709251200000
        bars=[{"bar_open_ms":start+i*900000,
               "bar_close_ms":start+(i+1)*900000-1}
              for i in range(2976)]
        native={
            "schema":"aql.core.historical-price-custody-query.v1",
            "status":"OK","coverage":"COMPLETE",
            "dataset_id":"BINANCE-SPOT-BTCUSDT-15M-2024-03",
            "version":1,
            "source_bytes_sha256":self.zip_sha,
            "manifest_integrity_sha256":self.manifest_sha,
            "decision_cutoff_ms":1711929600000,
            "required_bar_count":2976,"available_bar_count":2976,
            "missing_bar_opens":[],"bars":bars,
        }
        self.native_sha=digest(native)
        native["price_query_sha256"]=self.native_sha
        (self.intake/"core245-native-receipt.json").write_text(
            json.dumps(native))
        definition={"strategy_id":"h_manual_distinct_test",
                    "scope":"RESEARCH_ONLY","fixture":True}
        ast_sha=ast_digest(definition)
        (self.intake/"manual-third-ast.json").write_text(
            json.dumps({"definition":definition,"digest":ast_sha}))
        self.tech={
            "schema":LANE_SCHEMA,
            "owner_authorization_ref":"#205/6718325330",
            "one_time_scope_authorized":True,
            "warehouse_root":str(self.warehouse),
            "vault_root":str(self.vault),
            "local_source_zip":str(self.zip),
            "dataset_id":"BINANCE-SPOT-BTCUSDT-15M-2024-03",
            "version":1,"month":"2024-03",
            "start_ms":start,"end_exclusive_ms":1711929600000,
            "decision_cutoff_ms":1711929600000,
            "source_bytes_sha256":self.zip_sha,
            "manifest_integrity_sha256":self.manifest_sha,
            "native_receipt_file_sha256":sha_file(
                self.intake/"core245-native-receipt.json"),
            "strategy_file_sha256":sha_file(
                self.intake/"manual-third-ast.json"),
            "strategy_definition_sha256":ast_sha,
            "strategy_id":"h_manual_distinct_test",
            "factory_code_sha256":"c"*64,
            "experiment_id":"RESEARCH-H-MARCH-TEST-ONLY",
        }
        self.policy={
            "schema":COST_SCHEMA,"costs":OWNER_LIMITED_COSTS.copy(),
            "market":"SPOT","direction":"LONG",
            "research_class":"RETROSPECTIVE_NON_PIT",
            "authorization_class":"OWNER_EXPLICIT_COST_ONLY",
            "single_use_experiment_id":self.tech["experiment_id"],
        }
        self.scope={
            "dataset_id":self.tech["dataset_id"],"version":1,
            "month":"2024-03","start_ms":start,
            "end_exclusive_ms":1711929600000,
            "decision_cutoff_ms":1711929600000,
            "source_bytes_sha256":self.zip_sha,
            "manifest_integrity_sha256":self.manifest_sha,
            "core245_native_receipt_sha256":self.native_sha,
            "core253_query_sha256":"d"*64,
            "strategy_id":"h_manual_distinct_test",
            "strategy_definition_sha256":ast_sha,
            "strategy_config_sha256":"e"*64,
            "evaluator_code_sha256":"f"*64,
            "cost_policy_sha256":_digest(self.policy),
            "experiment_id":self.tech["experiment_id"],
            "owner_authorization_ref":scope_commitment(
                self.tech,self.output),
            "research_class":"RETROSPECTIVE_NON_PIT",
            "historical_pit":"NOT_ATTESTED",
            "publisher_pit_attested":False,
            "explicit_readonly_no_export":True,
            "source_output_separate":True,
            "single_use":True,
        }
        self.write()

    def write(self):
        (self.intake/"technical-intake.json").write_text(
            json.dumps(self.tech))
        packet={
            "schema":SCHEMA,"authority_class":AUTHORITY,
            "scope":self.scope,"cost_policy":self.policy,
            "independent_license_review_status":"NOT_ATTESTED",
            "owner_scope_mac":hmac.new(
                self.secret,SCOPE_DOMAIN+_canonical(self.scope),
                hashlib.sha256).hexdigest(),
            "owner_cost_mac":hmac.new(
                self.secret,COST_DOMAIN+_canonical(self.policy),
                hashlib.sha256).hexdigest(),
        }
        (self.intake/"owner-personal-assertion.json").write_text(
            json.dumps(packet))

    def fetch(self, *_):
        return None

    def proof(self, *_args,**_kwargs):
        return {"zip_bytes_sha256":self.zip_sha,
                "checksum_response_sha256":"a"*64,
                "bar_count":2976,
                "first_open_ms":1709251200000,
                "end_exclusive_ms":1711929600000,
                "filename":self.zip.name}

    def call(self,**kw):
        return run_owner_personal_batch(
            self.intake,self.output,
            owner_key=kw.get("key",self.key),
            git_repo=self.repo,
            confirm_one_run=kw.get("confirmed",True),
            fetcher=self.fetch,
            operator=kw.get("operator",lambda *a,**k:{
                "status":"EXPERIMENT_ENGINEERING_PASS",
                "reason":"MOCKED_NO_REAL_SOURCE",
                "sha256":"9"*64,
            }))

    def test_owner_mac_and_publisher_match_reach_mocked_operator_once(self):
        with patch(
            "tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
            side_effect=self.proof
        ):
            result=self.call()
        self.assertEqual(result["status"],"PASS_ENGINEERING_ONLY")
        self.assertEqual(result["details"]["third_party_rights"],
                         "UNVERIFIED")
        self.assertEqual(result["details"]["independent_license_review"],
                         "NOT_ATTESTED")
        self.assertTrue((self.intake/"h2-personal-one-use-claim.json").exists())
        with patch("tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
                   side_effect=self.proof):
            retry=self.call(operator=lambda *a,**k:
                            self.fail("must not run twice"))
        self.assertEqual(retry["status"],"BLOCKED")
        self.assertIn("PERSONAL_ONE_RUN_ALREADY_CLAIMED",retry["reasons"])

    def test_missing_owner_key_blocks_before_provider_or_original(self):
        with patch("tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
                   side_effect=AssertionError("no publisher needed")):
            r=self.call(key=None)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertEqual(r["source_read_status"],"NOT_ATTEMPTED")

    def test_tampered_technical_source_even_with_owner_mac_is_rejected(self):
        self.tech["local_source_zip"]=str(self.root/"wrong.zip")
        self.write()
        with patch("tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
                   side_effect=AssertionError("must not reach provider")):
            result=self.call()
        self.assertIn("OWNER_PERSONAL_TECH_ROOT_OR_PIN_DRIFT",result["reasons"])
        self.assertEqual(result["source_read_status"],"NOT_ATTEMPTED")

    def test_unsigned_cost_edit_blocks_before_provider(self):
        packet_path=self.intake/"owner-personal-assertion.json"
        p=json.loads(packet_path.read_text())
        p["cost_policy"]["costs"]["fee_entry_bps"]="11"
        packet_path.write_text(json.dumps(p))
        with patch("tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
                   side_effect=AssertionError("must not query provider")):
            result=self.call()
        self.assertIn("OWNER_PERSONAL_SCOPE_OR_COST_MAC_UNVERIFIED",
                      result["reasons"])

    def test_owner_only_signature_cannot_become_external_license(self):
        p=self.intake/"owner-personal-assertion.json"
        packet=json.loads(p.read_text())
        packet["independent_license_review_status"]="INDEPENDENTLY_VERIFIED"
        p.write_text(json.dumps(packet))
        result=self.call()
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("OWNER_PERSONAL_SCOPE_OR_COST_MAC_UNVERIFIED",
                      result["reasons"])

    def test_publisher_digest_mismatch_blocks_before_original(self):
        def mismatch(*a,**kw):
            data=self.proof()
            data["zip_bytes_sha256"]="9"*64
            return data
        with patch("tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
                   side_effect=mismatch):
            result=self.call(operator=lambda *a,**k:
                            self.fail("must not run"))
        self.assertIn("PERSONAL_PUBLISHER_SOURCE_OR_MONTH_MISMATCH",
                      result["reasons"])
        self.assertEqual(result["source_read_status"],"NOT_ATTEMPTED")

    def test_missing_real_core245_or_registration_substitution_rejected(self):
        native=self.intake/"core245-native-receipt.json"
        native.write_text(json.dumps({
            "schema":"aql.archive-custody.local-registration.v1"}))
        self.tech["native_receipt_file_sha256"]=sha_file(native)
        self.scope["owner_authorization_ref"]=scope_commitment(
            self.tech,self.output)
        self.write()
        with patch("tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
                   side_effect=self.proof):
            result=self.call()
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["source_read_status"],"NOT_ATTEMPTED")

    def test_wrong_ast_plugin_shape_rejected_before_provider(self):
        p=self.intake/"manual-third-ast.json"
        p.write_text(json.dumps({"payload":{},"sha256":"a"*64}))
        self.tech["strategy_file_sha256"]=sha_file(p)
        self.scope["owner_authorization_ref"]=scope_commitment(
            self.tech,self.output)
        self.write()
        with patch("tools.atlas_h2_owner_personal_batch_v1.verify_public_month",
                   side_effect=AssertionError("must not fetch")):
            result=self.call()
        self.assertEqual(result["reasons"],
                         ["H2_MANUAL_AST_SLOT_SCHEMA_MISMATCH"])


if __name__=="__main__":
    unittest.main()
