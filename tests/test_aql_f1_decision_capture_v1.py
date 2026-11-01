"""Focused prospective F1 Core r1.2a positive/negative tests. No P0 replay."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import (
 CaptureError,canonical_decimal,digest,hash_f1,jcs_bytes,status_slots,validate_f1,
 validate_commit_receipt,validate_ack,validate_excursion,write_original_candidate,duplicate_keys_reject,
)
H="a"*64

def fixture(arm="BASE",state="NO_SIGNAL",direction=None,eligible="NOT_ESTABLISHED"):
    c2={"trial_id":"trial","opportunity_id":"opp","producer_event_id":"evt","envelope_sha256":H}
    registry={"rsi14":"OBSERVE_ONLY","trend":"DECISION"}
    pair=digest({"experiment_plan_sha256":H,"c2_identity":c2})
    cutoff=900000
    rec={
      "schema_version":"aql.f1-decision-capture.v1","canonicalization_id":"JCS-RFC8785-v1",
      **c2,"run_manifest_sha256":H,"experiment_plan_sha256":H,"c2_identity":c2,"pair_id":pair,
      "arm":arm,"arm_event_id":"arm-"+arm,"arm_event_sha256":H,"arm_strategy_version":"s1",
      "strategy_id":"s","strategy_digest":H,"decision_cutoff_ms":cutoff,"decision_ms":cutoff,
      "capture_ms":cutoff+1,"producer_sequence":0,"previous_event_sha256":None,
      "source_asof_ms":cutoff-1,"source_available_at_ms":cutoff,"prefix_start_ms":0,
      "prefix_end_exclusive_ms":cutoff,"source_availability_evidence_ref":"source-ref",
      "prefix_bar_checksums_sha256":H,"source_id":"source","source_version":"v1",
      "correction_generation":"g1","input_disposition":"EVALUABLE","dataset_version":1,
      "source_bytes_sha256":H,"gap_inventory_sha256":H,"correction_lineage_sha256":H,
      "feature_policy_version":"f1","selection_policy_version":"p1",
      "indicator_inventory_manifest_sha256":digest(registry),
      "indicators":[
        {"indicator_id":"rsi14","role":"OBSERVE_ONLY","definition_version":"rsi-v1","parameters_sha256":H,
         "unit":"ratio","lookback_bars":14,"value_kind":"UNKNOWN","value":None,"missing_reason":"INPUT_NOT_FINAL",
         "source_asof_ms":None,"available_at_ms":None,"input_prefix_sha256":None,"availability_evidence_ref":None},
        {"indicator_id":"trend","role":"DECISION","definition_version":"trend-v1","parameters_sha256":H,
         "unit":"boolean","lookback_bars":3,"value_kind":"BOOLEAN","value":False,"missing_reason":None,
         "source_asof_ms":cutoff-1,"available_at_ms":cutoff,"input_prefix_sha256":H,"availability_evidence_ref":"indicator-proof"},
      ],
      "f1_signal_state":state,"f1_reason_code":None,"direction":direction,
      "predecision_eligibility":eligible,"eligibility_reason_code":None,
      "eligibility_evidence_ref":"elig-proof" if eligible=="YES" else None,
      "eligibility_available_at_ms":cutoff if eligible=="YES" else None,
      "target_policy_id":"target","target_policy_version":"1","stop_policy_id":"stop","stop_policy_version":"1",
      "target_policy_sha256":H,"stop_policy_sha256":H,"execution_assumptions_sha256":H,
      "reference":{"reference_kind":"bar-close","price":"100","unit":"USDT","tick_size":"0.01",
                   "decimal_scale":2,"rounding_mode":"HALF_EVEN","reference_asof_ms":cutoff-1,
                   "reference_available_at_ms":cutoff,"reference_evidence_ref":"price-proof","measurement_policy_sha256":H},
      "tp":{"status":"NOT_ESTABLISHED","level":None,"unit":None,"basis":None,"reference_price_kind":None,
            "defined_at_ms":None,"tick_size":None,"decimal_scale":None,"rounding_mode":None},
      "sl":{"status":"NOT_ESTABLISHED","level":None,"unit":None,"basis":None,"reference_price_kind":None,
            "defined_at_ms":None,"tick_size":None,"decimal_scale":None,"rounding_mode":None},
    }
    rec["f1_record_sha256"]=hash_f1(rec)
    return rec,registry

class ProspectiveTests(unittest.TestCase):
    def test_jcs_and_decimals(self):
        self.assertEqual(jcs_bytes({"b":2,"a":1}),b'{"a":1,"b":2}')
        self.assertEqual(digest({"b":2,"a":1}),hashlib.sha256(b'{"a":1,"b":2}').hexdigest())
        self.assertEqual(canonical_decimal("001.2300",4,"HALF_EVEN"),"1.23")
        self.assertEqual(canonical_decimal("-0.000",4,"HALF_EVEN"),"0")
        for n in ("1e2","NaN","1.23.4"):
            with self.subTest(n=n),self.assertRaises(CaptureError):canonical_decimal(n,4,"HALF_EVEN")
        with self.assertRaises(CaptureError):canonical_decimal("1.23",2,"HALF_EVEN","0.05")
        with self.assertRaises(CaptureError):jcs_bytes({"bad":3.14})
        with self.assertRaises(CaptureError):duplicate_keys_reject([("a",1),("a",2)])
    def test_original_no_signal_observe_only(self):
        rec,registry=fixture();validate_f1(rec,registry)
        self.assertIsNone(rec["direction"])
        self.assertEqual(rec["indicators"][0]["role"],"OBSERVE_ONLY")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"f1.jsonl";write_original_candidate(p,rec,registry)
            self.assertTrue(p.read_bytes().endswith(b"\n"))
    def test_source_arrives_late(self):
        rec,registry=fixture();rec["source_available_at_ms"]+=1;rec["f1_record_sha256"]=hash_f1(rec)
        with self.assertRaisesRegex(CaptureError,"SOURCE_LATE"):validate_f1(rec,registry)
    def test_indicator_late_eligibility_absent(self):
        rec,registry=fixture();rec["indicators"][1]["available_at_ms"]+=1;rec["f1_record_sha256"]=hash_f1(rec)
        with self.assertRaisesRegex(CaptureError,"INDICATOR_AVAIL_LATE"):validate_f1(rec,registry)
        rec,registry=fixture(eligible="YES");rec["eligibility_evidence_ref"]=None;rec["f1_record_sha256"]=hash_f1(rec)
        with self.assertRaisesRegex(CaptureError,"ELIGIBILITY_PROOF_MISSING"):validate_f1(rec,registry)
    def test_corrupted_hash_and_c2_identity(self):
        rec,registry=fixture();rec["direction"]="LONG"
        with self.assertRaisesRegex(CaptureError,"F1_DIGEST_MISMATCH"):validate_f1(rec,registry)
        rec,registry=fixture();rec["c2_identity"]["opportunity_id"]="other";rec["f1_record_sha256"]=hash_f1(rec)
        with self.assertRaisesRegex(CaptureError,"C2_IDENTITY_MISMATCH"):validate_f1(rec,registry)
    def test_status_idempotence_conflict_missing_unverified(self):
        base,registry=fixture();shadow,_=fixture("SHADOW")
        c2=[base["c2_identity"]];pair=base["pair_id"];plan=base["experiment_plan_sha256"]
        got=status_slots(c2,plan,{(pair,"BASE"):[base]},registry)
        self.assertEqual([s["capture_status"] for s in got],["UNVERIFIED","MISSING_CAPTURE"])
        got=status_slots(c2,plan,{(pair,"BASE"):[base,copy.deepcopy(base)],(pair,"SHADOW"):[shadow]},registry,lambda _:True)
        self.assertEqual([s["capture_status"] for s in got],["RECORDED","RECORDED"])
        changed=copy.deepcopy(base);changed["f1_signal_state"]="UNKNOWN";changed["f1_record_sha256"]=hash_f1(changed)
        got=status_slots(c2,plan,{(pair,"BASE"):[base,changed]},registry,lambda _:True)
        self.assertEqual(got[0]["capture_status"],"QUARANTINED")
    def test_commit_and_optional_ack_binding(self):
        rec,_=fixture()
        receipt={"schema_version":"aql.f1-commit-receipt.v1","receipt_id":"receipt",
          "f1_record_sha256":rec["f1_record_sha256"],"producer_sequence":0,"previous_event_sha256":None,
          "frozen_arm_event_sha256":H,"committed_at_ms":900001,"durable_store_ref":"store",
          "independent_anchor_ref":"external-proof"}
        receipt["commit_receipt_sha256"]=digest(receipt);validate_commit_receipt(receipt,rec)
        ack={"schema_version":"aql.f1-ack.v1","ack_id":"ack","ack_for_f1_record_sha256":rec["f1_record_sha256"],
             "ack_for_commit_receipt_sha256":receipt["commit_receipt_sha256"],"acknowledged_at_ms":900002,
             "ack_evidence_class":"ORIGINAL_RUNTIME"}
        ack["ack_sha256"]=digest(ack);validate_ack(ack,rec,receipt)
        ack["ack_for_commit_receipt_sha256"]=H
        with self.assertRaisesRegex(CaptureError,"ACK_BINDING"):validate_ack(ack,rec,receipt)
    def test_market_only_unsigned(self):
        original,_=fixture(state="ARMED",direction="LONG",eligible="YES")
        outcome={"measurement_class":"MARKET_ONLY","coverage_status":"COMPLETE","excursion_status":"NO_DIRECTION",
                 "max_favorable":None,"max_adverse":None,"tp_sl_first_hit":"UNKNOWN"}
        validate_excursion(outcome,original,True)
        outcome["max_favorable"]="2"
        with self.assertRaisesRegex(CaptureError,"SIGNED_MFE_MAE_FORBIDDEN"):validate_excursion(outcome,original,True)
        outcome.update(measurement_class="COMMON_PAIRED",excursion_status="EVALUABLE",max_adverse="-1")
        validate_excursion(outcome,original,True)
        with self.assertRaisesRegex(CaptureError,"SIGNED_MFE_MAE_FORBIDDEN"):validate_excursion(outcome,original,False)
    def test_invalid_original_quarantined(self):
        rec,registry=fixture();rec["f1_record_sha256"]=H
        result=status_slots([rec["c2_identity"]],rec["experiment_plan_sha256"],{(rec["pair_id"],"BASE"):[rec]},registry)
        self.assertEqual(result[0]["capture_status"],"QUARANTINED")

if __name__=="__main__":unittest.main()
