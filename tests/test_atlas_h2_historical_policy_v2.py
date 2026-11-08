"""Option C: mutually exclusive H2 research classes; synthetic, no owner IO."""
from __future__ import annotations
import copy
import unittest
from test_atlas_h2_readiness_preflight import valid
from tools.atlas_h2_historical_policy_v2 import assess,SCHEMA

def request(kind="RETROSPECTIVE_NON_PIT"):
    r=valid()
    r["schema"]=SCHEMA
    r["research_class"]=kind
    r["source_provenance"]["publisher_pit_attested"]=kind=="PIT_REQUIRED"
    return r

class OptionC(unittest.TestCase):
    def assert_safety(self,output,kind):
        self.assertEqual(output["research_class"],kind)
        self.assertFalse(output["owner_private_data_accessed"])
        self.assertFalse(output["warehouse_written"])
        self.assertFalse(output["pit_sensitive_claims_allowed"])
        self.assertFalse(output["scientific_claims_allowed"])
        self.assertEqual(output["economic_approval"],"NOT_GRANTED")
        self.assertEqual(output["trading_authority"],"NONE")
        self.assertEqual(output["f5"],"BLOCKED_EXTERNAL_INPUT")

    def test_retrospective_non_pit_is_not_pit(self):
        out=assess(request())
        self.assertEqual(out["status"],"READY_FOR_OWNER_AUTHORIZATION")
        self.assertEqual(out["historical_pit"],"NOT_ATTESTED")
        self.assert_safety(out,"RETROSPECTIVE_NON_PIT")

    def test_pit_required_declarative_only(self):
        out=assess(request("PIT_REQUIRED"))
        self.assertEqual(out["status"],"READY_FOR_OWNER_AUTHORIZATION")
        self.assert_safety(out,"PIT_REQUIRED")
        self.assertEqual(out["historical_pit"],"NOT_VERIFIED")

    def test_pit_required_missing_proof_waits(self):
        r=request("PIT_REQUIRED")
        r["source_provenance"]["publisher_pit_attested"]=False
        out=assess(r)
        self.assertEqual(out["status"],"WAIT_PROVENANCE")
        self.assert_safety(out,"PIT_REQUIRED")

    def test_non_pit_forged_true_pit_refused(self):
        r=request()
        r["source_provenance"]["publisher_pit_attested"]=True
        out=assess(r)
        self.assertEqual(out["status"],"BLOCKED_CONTRACT")
        self.assert_safety(out,"RETROSPECTIVE_NON_PIT")

    def test_missing_source_permission_denied_both(self):
        for kind in ("PIT_REQUIRED","RETROSPECTIVE_NON_PIT"):
            r=request(kind)
            r["owner_permission"]["granted"]=False
            self.assertEqual(assess(r)["status"],"WAIT_SOURCE_PERMISSION")

    def test_missing_cost_policy_denied_both(self):
        for kind in ("PIT_REQUIRED","RETROSPECTIVE_NON_PIT"):
            r=request(kind)
            r["owner_cost_policy"]["owner_authorized"]=False
            self.assertEqual(assess(r)["status"],"WAIT_COST_POLICY")

    def test_no_source_rights_denied_both(self):
        for kind in ("PIT_REQUIRED","RETROSPECTIVE_NON_PIT"):
            r=request(kind)
            r["source_provenance"]["source_rights_attested"]=False
            self.assertEqual(assess(r)["status"],"WAIT_PROVENANCE")

    def test_wrong_factory_head_denied(self):
        r=request()
        r["exact_heads"]["factory"]="0"*40
        self.assertEqual(assess(r)["status"],"BLOCKED_CONTRACT")

    def test_unknown_mode_denied(self):
        r=request()
        r["research_class"]="PIT_ASSUMED"
        self.assertEqual(assess(r)["status"],"BLOCKED_CONTRACT")

    def test_v1_request_cannot_silently_pass_v2(self):
        self.assertEqual(assess(valid())["status"],"BLOCKED_CONTRACT")

    def test_missing_pit_flag_refused(self):
        r=request()
        del r["source_provenance"]["publisher_pit_attested"]
        self.assertEqual(assess(r)["status"],"WAIT_PROVENANCE")

    def test_unknown_field_denied(self):
        r=request()
        r["owner_private_path"]="E:/original"
        self.assertEqual(assess(r)["status"],"BLOCKED_CONTRACT")

if __name__=="__main__":
    unittest.main()
