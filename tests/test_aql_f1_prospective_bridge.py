"""Focused pre-F3 F1 bridge tests: prospective only, no historical replay."""
import copy
import tempfile
import unittest
from pathlib import Path
from tests.test_aql_f1_decision_capture_v1 import fixture
from research_wp_r0.aql_f1_prospective_bridge import capture_prospective_pair,CaptureError

def envelope(rec,mode="PROSPECTIVE_CAPTURE"):
    return {**rec["c2_identity"],"availability_mode":mode,
            "decision_cutoff_ms":rec["decision_cutoff_ms"],
            **{k:rec[k] for k in ("run_manifest_sha256","prefix_end_exclusive_ms",
                 "prefix_bar_checksums_sha256","gap_inventory_sha256","correction_lineage_sha256")}}

class BridgeTests(unittest.TestCase):
    def test_pair_and_idempotent_restart(self):
        base,registry=fixture();shadow,_=fixture("SHADOW")
        with tempfile.TemporaryDirectory() as d:
            rows=capture_prospective_pair(envelope(base),base["experiment_plan_sha256"],
                     {"BASE":base,"SHADOW":shadow},registry,Path(d))
            self.assertEqual([x["capture_status"] for x in rows],["UNVERIFIED","UNVERIFIED"])
            counts=[(Path(d)/(arm+".jsonl")).read_bytes().count(b"\n") for arm in ("base","shadow")]
            capture_prospective_pair(envelope(base),base["experiment_plan_sha256"],
                     {"BASE":base,"SHADOW":shadow},registry,Path(d))
            self.assertEqual(counts,[1,1])
            self.assertEqual(counts,[(Path(d)/(arm+".jsonl")).read_bytes().count(b"\n") for arm in ("base","shadow")])
    def test_reject_historical_and_missing_shadow(self):
        base,registry=fixture()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(CaptureError,"HISTORICAL_C2_REJECTED"):
                capture_prospective_pair(envelope(base,"RETROSPECTIVE_NON_PIT"),
                     base["experiment_plan_sha256"],{"BASE":base,"SHADOW":None},registry,Path(d))
            rows=capture_prospective_pair(envelope(base),base["experiment_plan_sha256"],
                     {"BASE":base,"SHADOW":None},registry,Path(d))
            self.assertEqual([x["capture_status"] for x in rows],["UNVERIFIED","MISSING_CAPTURE"])
    def test_conflicting_retry_fail_closed(self):
        base,registry=fixture()
        with tempfile.TemporaryDirectory() as d:
            capture_prospective_pair(envelope(base),base["experiment_plan_sha256"],
                     {"BASE":base,"SHADOW":None},registry,Path(d))
            other=copy.deepcopy(base);other["f1_signal_state"]="UNKNOWN"
            from research_wp_r0.aql_f1_decision_capture_v1 import hash_f1
            other["f1_record_sha256"]=hash_f1(other)
            with self.assertRaisesRegex(CaptureError,"JOURNAL_SAME_SLOT_CONFLICT"):
                capture_prospective_pair(envelope(base),base["experiment_plan_sha256"],
                     {"BASE":other,"SHADOW":None},registry,Path(d))

if __name__=="__main__":unittest.main()
