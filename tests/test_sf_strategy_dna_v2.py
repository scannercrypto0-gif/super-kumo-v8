"""Focused synthetic acceptance; legacy suites run separately unchanged in CI."""
import copy
from dataclasses import FrozenInstanceError
import json
import unittest
from research_wp_r0.strategy_definition import StrategyDefinition, digest
from research_wp_r0.strategy_dna_v2 import StrategyDNAV2, SyntheticRoleReport, evaluate_synthetic
from research_wp_r0.strategy_dna_v2_example import example

class StrategyDNAV2Tests(unittest.TestCase):
    def setUp(self):
        self.v1,self.dna,self.assets = example()
    def run_report(self,assets=None,dna=None):
        return evaluate_synthetic(dna or self.dna,self.assets if assets is None else assets,
                                  decision_cutoff_ms=1000)
    def test_legacy_golden_unchanged(self):
        self.assertEqual(self.v1.digest,"024283f5e191a49199cf2e65aada9f87113c076d6190653a57fbb1b5c739ef86")
        before=self.v1.payload
        self.run_report()
        self.assertEqual(before,self.v1.payload)
        self.assertEqual(digest({"b":1.0,"a":-0.0}),"f4c1d8bd90d7ccd720aa5a69a67185fb9caf4f35926a4eacf53a86d0e70bdf88")
    def test_v2_roundtrip_retained_hash(self):
        clone=StrategyDNAV2.from_json(self.dna.to_json(),v1_definition=self.v1,expected_digest=self.dna.digest)
        self.assertEqual(clone.payload,self.dna.payload)
        self.assertEqual(clone.scanner_profile.spec,self.dna.spec["scanner_profile"])
        self.assertEqual(clone.decision_profile.spec,self.dna.spec["decision_profile"])
        self.assertEqual(clone.monitoring_profile.spec,self.dna.spec["monitoring_profile"])
    def test_v1_not_implicitly_accepted(self):
        with self.assertRaises(ValueError): evaluate_synthetic(self.v1,self.assets,decision_cutoff_ms=1000)
    def test_frozen_and_defensive_copy(self):
        with self.assertRaises(FrozenInstanceError): self.dna.payload=b"changed"
        spec=self.dna.spec;spec["execution"]="PAPER"
        self.assertEqual(self.dna.spec["execution"],"DISABLED")
    def test_revision_requires_new_version(self):
        spec=self.dna.spec;spec["decision_profile"]["entry"]["threshold"]=.9
        with self.assertRaises(ValueError): self.dna.revise(spec,v1_definition=self.v1)
        spec["strategy_version"]="v2_2"
        newer=self.dna.revise(spec,v1_definition=self.v1)
        self.assertNotEqual(newer.digest,self.dna.digest)
        self.assertEqual(newer.spec["v1_digest"],self.v1.digest)
    def test_v2_tamper_rejected(self):
        wrapper=json.loads(self.dna.to_json());wrapper["dna"]["strategy_version"]="forged"
        with self.assertRaises(ValueError):
            StrategyDNAV2.from_json(json.dumps(wrapper),v1_definition=self.v1,expected_digest=self.dna.digest)
    def test_incompatible_scope_and_binding_rejected(self):
        for key,value in [("v1_digest","bad"),("schema_version","1"),("execution","PAPER"),
                          ("v1_link_mode","AST_TO_SCORE"),("scope","LIVE")]:
            with self.subTest(key=key):
                spec=self.dna.spec;spec[key]=value
                with self.assertRaises(ValueError): StrategyDNAV2(spec,v1_definition=self.v1)
    def test_invalid_weights_and_ranges(self):
        for field,val in [("weight",0),("weight",-1),("weight",float("nan")),("upper",0)]:
            with self.subTest(field=field,val=val):
                spec=self.dna.spec;spec["decision_profile"]["entry"]["terms"][0][field]=val
                with self.assertRaises(ValueError): StrategyDNAV2(spec,v1_definition=self.v1)
    def test_unknown_typed_fields_and_versions(self):
        for role in ["scanner_profile","decision_profile","monitoring_profile"]:
            spec=self.dna.spec
            item = (spec[role]["filters"][0] if role=="scanner_profile" else
                    spec[role]["entry"]["terms"][0] if role=="decision_profile" else spec[role]["features"][0])
            item["field"]="unknown"
            with self.assertRaises(ValueError): StrategyDNAV2(spec,v1_definition=self.v1)
        spec=self.dna.spec;spec["indicators"][0]["version"]="999"
        with self.assertRaises(ValueError): StrategyDNAV2(spec,v1_definition=self.v1)
    def test_unhashable_reference_rejected(self):
        spec=self.dna.spec;spec["scanner_profile"]["filters"][0]["reference"]=[]
        with self.assertRaises(ValueError): StrategyDNAV2(spec,v1_definition=self.v1)
    def test_scanner_reasons_and_weight_explanations(self):
        r=self.run_report().spec
        self.assertEqual([x["selected"] for x in r["core"]["scanner"]],[True,True,False])
        self.assertIn("minimum_trend:FILTER_REJECTED",r["core"]["scanner"][2]["reasons"])
        d=r["core"]["decisions"][0]
        self.assertEqual(d["signal"],"ENTRY_CONDITION_MET")
        self.assertAlmostEqual(d["entry"]["score"],.875)
        self.assertAlmostEqual(sum(x["contribution"] for x in d["entry"]["terms"]),d["entry"]["score"])
        self.assertEqual(r["core"]["decisions"][1]["signal"],"WAIT")
        self.assertEqual(r["core"]["decisions"][2]["signal"],"NOT_EVALUATED_SCANNER")
    def test_mandatory_overrides_high_score(self):
        self.assets[0]["features"]["trend"]["values"]["value"]=50
        d=self.run_report().spec["core"]["decisions"][0]["entry"]
        self.assertFalse(d["eligible"]);self.assertIn("mandatory_trend:MANDATORY_NOT_SATISFIED",d["reasons"])
    def test_stable_ranking_capacity_and_ties(self):
        spec=self.dna.spec;spec["scanner_profile"]["max_candidates"]=1
        self.assets[1]["features"]["trend"]["values"]["value"]=90
        dna=StrategyDNAV2(spec,v1_definition=self.v1)
        r=self.run_report(dna=dna).spec
        self.assertTrue(r["core"]["scanner"][0]["selected"])
        self.assertIn("CAPACITY_EXCLUDED",r["core"]["scanner"][1]["reasons"])
        self.assertEqual(self.run_report(list(reversed(self.assets)),dna).payload,self.run_report(dna=dna).payload)
    def test_universe_and_venue_rejection(self):
        self.assets[0]["symbol"]="ZZZ";self.assets[0]["venue"]="other"
        s=self.run_report().spec["core"]["scanner"][-1]
        self.assertIn("SYMBOL_NOT_ALLOWED",s["reasons"]);self.assertIn("VENUE_NOT_ALLOWED",s["reasons"])
    def test_missing_critical_does_not_renormalize(self):
        del self.assets[0]["features"]["strength"]
        d=self.run_report().spec["core"]["decisions"][0]
        self.assertEqual(d["signal"],"BLOCKED");self.assertIsNone(d["entry"]["score"])
        self.assertFalse(d["entry"]["eligible"])
    def test_future_data_not_eligible_or_exposed(self):
        for name in ["trend","strength"]:
            assets=copy.deepcopy(self.assets);assets[0]["features"][name]["available_at_ms"]=1001
            r=self.run_report(assets).spec
            if name=="trend":
                self.assertFalse(r["core"]["scanner"][0]["selected"])
                reading=r["core"]["scanner"][0]["rules"][0]["reading"]
            else: reading=r["core"]["decisions"][0]["entry"]["terms"][1]["reading"]
            self.assertEqual(reading["status"],"LATE");self.assertIsNone(reading["value"])
    def test_temporal_order_source_finality_and_version(self):
        for field,value in [("as_of_ms",980),("is_final",False),("source_id","unknown"),
                            ("source_generation_id","other"),("indicator_digest","wrong"),
                            ("observed_at_ms",True)]:
            with self.subTest(field=field):
                assets=copy.deepcopy(self.assets);assets[0]["features"]["trend"][field]=value
                r=self.run_report(assets).spec["core"]["scanner"][0]
                self.assertFalse(r["selected"])
    def test_old_content_recent_arrival_stays_stale(self):
        self.assets[0]["features"]["trend"]["as_of_ms"]=800
        self.assets[0]["features"]["trend"]["available_at_ms"]=999
        reading=self.run_report().spec["core"]["scanner"][0]["rules"][0]["reading"]
        self.assertEqual(reading["status"],"STALE")
    def test_monitor_value_missing_fault_noninterference(self):
        baseline=self.run_report().spec["core"]
        variants=[None,[],{"quality":"DROPPED"},{"quality":"NOT_APPLICABLE"}]
        for value in [0,999,float("nan"),float("inf")]:
            obs=copy.deepcopy(self.assets[0]["features"]["observe"]);obs["values"]["value"]=value
            variants.append(obs)
        for observation in variants:
            with self.subTest(observation=observation):
                assets=copy.deepcopy(self.assets);assets[0]["features"]["observe"]=observation
                self.assertEqual(self.run_report(assets).spec["core"],baseline)
    def test_monitor_future_stale_and_identity_noninterference(self):
        baseline=self.run_report().spec["core_digest"]
        for field,value,status in [("available_at_ms",1001,"LATE"),("as_of_ms",1,"STALE"),
                                   ("indicator_digest","bad","UNVERIFIED")]:
            assets=copy.deepcopy(self.assets);assets[0]["features"]["observe"][field]=value
            r=self.run_report(assets).spec
            self.assertEqual(r["core_digest"],baseline)
            self.assertEqual(r["monitoring"][0]["observations"][0]["status"],status)
            self.assertIsNone(r["monitoring"][0]["observations"][0]["value"])
    def test_expected_monitoring_for_excluded(self):
        del self.assets[2]["features"]["observe"]
        row=self.run_report().spec["monitoring"][2]
        self.assertEqual(row["coverage_scope"],"SCANNER_EXCLUDED")
        self.assertEqual((row["expected"],row["available"]),(1,0))
        self.assertEqual(row["observations"][0]["status"],"MISSING")
    def test_monitor_config_revision_preserves_policy_not_full_identity(self):
        spec=self.dna.spec;spec["strategy_version"]="v2_2"
        spec["monitoring_profile"]["features"][0]["max_age_ms"]=99
        other=self.dna.revise(spec,v1_definition=self.v1)
        self.assertNotEqual(other.digest,self.dna.digest)
        self.assertEqual(other.decision_policy_digest,self.dna.decision_policy_digest)
        a=self.run_report().spec;b=self.run_report(dna=other).spec
        self.assertEqual(a["core"]["scanner"],b["core"]["scanner"])
        for x,y in zip(a["core"]["decisions"],b["core"]["decisions"]):
            self.assertEqual(x["signal"],y["signal"])
    def test_explicit_same_indicator_multiple_roles(self):
        spec=self.dna.spec;spec["monitoring_profile"]["features"].append(
            dict(feature_id="trend_observe",reference="trend",field="value",max_age_ms=100))
        dna=StrategyDNAV2(spec,v1_definition=self.v1)
        self.assertEqual(self.run_report(dna=dna).spec["monitoring"][0]["available"],2)
    def test_monitor_cannot_claim_authority(self):
        spec=self.dna.spec;spec["monitoring_profile"]["authority"]="SIGNAL"
        with self.assertRaises(ValueError): StrategyDNAV2(spec,v1_definition=self.v1)
    def test_ambiguous_entry_exit_rejected(self):
        spec=self.dna.spec;spec["decision_profile"]["exit"]["threshold"]=0
        dna=StrategyDNAV2(spec,v1_definition=self.v1)
        self.assertEqual(self.run_report(dna=dna).spec["core"]["decisions"][0]["signal"],"AMBIGUOUS_REJECTED")
    def test_duplicate_assets_rejected(self):
        with self.assertRaises(ValueError):self.run_report(self.assets+[self.assets[0]])
    def test_deterministic_replay_and_input_preservation(self):
        before=copy.deepcopy(self.assets)
        self.assertEqual(self.run_report().payload,self.run_report().payload)
        self.assertEqual(self.assets,before)
    def test_report_tamper_retained_digest(self):
        report=self.run_report()
        self.assertEqual(SyntheticRoleReport.from_json(report.to_json(),expected_digest=report.digest).payload,report.payload)
        wrapper=json.loads(report.to_json());wrapper["report"]["orders_created"]=True
        wrapper["digest"]=digest(wrapper["report"])
        with self.assertRaises(ValueError):
            SyntheticRoleReport.from_json(json.dumps(wrapper),expected_digest=report.digest)
    def test_no_execution_or_evidence_promotion(self):
        r=self.run_report().spec
        self.assertFalse(r["orders_created"]);self.assertEqual(r["execution"],"DISABLED")
        self.assertEqual(r["oos"],"NOT_ACCESSED");self.assertEqual(r["independent_custody"],"NOT_VERIFIED")
        self.assertEqual(r["temporal_evidence"],"SYNTHETIC_STRUCTURAL_ONLY")
    def test_decision_cutoff_strict_and_invalid_source_values(self):
        for cutoff in [True,-1,1.5]:
            with self.assertRaises(ValueError):evaluate_synthetic(self.dna,self.assets,decision_cutoff_ms=cutoff)
        for value in [None,True,float("nan"),float("inf")]:
            assets=copy.deepcopy(self.assets);assets[0]["features"]["strength"]["values"]["value"]=value
            self.assertFalse(self.run_report(assets).spec["core"]["decisions"][0]["entry"]["eligible"])

if __name__=="__main__":
    unittest.main()
