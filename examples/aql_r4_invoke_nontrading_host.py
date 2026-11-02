"""Run one offline/nontrading R4 host call, preserving proof limits.

This script uses an explicitly generated test prefix and MUST NOT be
presented as authentic prospective G2/issuer evidence.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from research_wp_r0.aql_r4_nontrading_g2_host import invoke_g2_nontrading
from research_wp_r0.aql_f1_decision_capture_v1 import jcs_bytes

H = "a"*64
CUT = 1704087000000

def sample_bars():
    out=[]
    for i in range(22):
        start=CUT-(22-i)*900000
        out.append([start,start+899999,100,101,99,100,20])
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",type=Path,required=True)
    x=p.parse_args()
    result=invoke_g2_nontrading(
        c2_identity={"trial_id":"R4-SAFE-OFFLINE-DEMO",
                     "opportunity_id":"FIXTURE_NOT_ORIGINAL",
                     "producer_event_id":"FIXTURE_ONLY",
                     "envelope_sha256":H},
        experiment_plan_sha256=H,decision_cutoff_ms=CUT,scheduled_at_ms=CUT-1,
        availability_mode="RETROSPECTIVE_NON_PIT",
        pins={"source_id":"FIXTURE_NOT_ISSUER","source_version":"v1",
              "source_bytes_sha256":H,"correction_generation":"g0",
              "strategy_id":"SF_BREAKOUT_BASE_20_10_DEV_v1","strategy_version":"1",
              "feature_snapshot_sha256":H,"regime_snapshot_sha256":H},
        bars_provider=sample_bars,directory=x.out_dir)
    print("report_sha256="+result["result_sha256"])
    print("proof_status="+result["proof_status"])
    print("original_g2_event_status="+result["original_g2_event_status"])

if __name__=="__main__":main()
