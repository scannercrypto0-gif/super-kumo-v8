"""R3 Factory focused fixtures; never genuine prospective G2 or PIT evidence."""
import copy
import unittest
from research_wp_r0.aql_r3_factory_event_outcome_consumer import digest,project_r3,read_json

H="a"*64
CUTOFF=900000
IDENT=dict(trial_id="T",opportunity_id="O",producer_event_id="E",envelope_sha256=H)
PLAN="b"*64
PAIR=digest({"experiment_plan_sha256":PLAN,"c2_identity":IDENT})
S=dict(c2_identity=IDENT,pair_id=PAIR,experiment_plan_sha256=PLAN,
       decision_cutoff_ms=CUTOFF,scheduled_at_ms=0,availability_mode="PROSPECTIVE_CAPTURE",
       source_id="SRC",source_version="v1",source_bytes_sha256="c"*64,
       correction_generation="gen0",strategy_id="SF_BREAKOUT_BASE_20_10_DEV_v1",
       strategy_version="1",feature_snapshot_sha256="d"*64,regime_snapshot_sha256="e"*64)
R=dict(schema_version="aql.r3-breakout-closed-prefix-evaluation.v1",
       original_g2_event_status="NOT_CONNECTED",pre_f3_capture_status="NOT_CONNECTED",
       f3_monitor_status="NOT_CONNECTED",proof_status="BLOCKED_EXTERNAL_EVIDENCE",
       execution="DISABLED",direction=None,breakout_signal_state="ARMED",
       prefix_sha256="f"*64,source_id="SRC",
       strategy_id="SF_BREAKOUT_BASE_20_10_DEV_v1",decision_cutoff_ms=CUTOFF)

def window(h=4,**changes):
    due=CUTOFF+h*3600000
    w=dict(pair_id=PAIR,horizon_hours=h,decision_cutoff_ms=CUTOFF,
           window_start_ms=CUTOFF,window_end_exclusive_ms=due,
           available_at_ms=due,source_artifact_sha256="9"*64,evidence_ref="issuer-manifest",
           coverage_status="COMPLETE",expected_bars=h*4,observed_bars=h*4,
           source_end_exclusive_ms=due)
    w.update({k:S[k] for k in ("source_id","source_version","source_bytes_sha256",
             "correction_generation","strategy_id","strategy_version",
             "feature_snapshot_sha256","regime_snapshot_sha256")})
    w.update(changes)
    return w

class FactoryR3Tests(unittest.TestCase):
    def run_projection(self,schedule=None,**kw):
        return project_r3([copy.deepcopy(S)] if schedule is None else schedule,
                          asof_ms=kw.pop("asof_ms",CUTOFF+4*3600000),**kw)

    def test_n_2n_6n_and_missing_capture(self):
        r=self.run_projection()
        self.assertEqual((r["scheduled_opportunities"],r["arm_slots"],r["horizon_rows"]),(1,2,6))
        self.assertEqual({x["arm"] for x in r["opportunity_ledger"][0]["arms"]},{"BASE","SHADOW"})
        self.assertEqual({x["capture_status"] for x in r["outcomes"]},{"MISSING_CAPTURE"})
        self.assertEqual(r["original_g2_event_status"],"BLOCKED_ON_REAL_G2_EVENT")

    def test_pending_maturity_disconnected(self):
        early=self.run_projection(asof_ms=CUTOFF)
        self.assertEqual(early["coverage_counts"],{"PENDING":6})
        mature=self.run_projection()
        self.assertEqual(mature["coverage_counts"],{"NOT_CONNECTED":2,"PENDING":4})

    def test_complete_requires_monitor_verification(self):
        r=self.run_projection(monitor_windows=[window()],verify_monitor=lambda _:True)
        self.assertEqual(r["coverage_counts"],{"COMPLETE":2,"PENDING":4})
        self.assertTrue(all(x["directional_mfe_mae"] is None and x["fills_pnl"] is None for x in r["outcomes"]))
        self.assertEqual(r["original_g2_event_status"],"BLOCKED_ON_REAL_G2_EVENT")

    def test_censored_and_unknown_with_evidence(self):
        a=window(coverage_status="CENSORED",observed_bars=12,
                 source_end_exclusive_ms=CUTOFF+3*3600000)
        r=self.run_projection(monitor_windows=[a],verify_monitor=lambda _:True)
        self.assertEqual(r["coverage_counts"]["CENSORED"],2)
        b=window(coverage_status="UNKNOWN",observed_bars=0,
                 source_end_exclusive_ms=CUTOFF,missing_reason="GAP")
        r=self.run_projection(monitor_windows=[b],verify_monitor=lambda _:True)
        self.assertEqual(r["coverage_counts"]["UNKNOWN"],2)

    def test_no_independent_verifier_no_positive(self):
        r=self.run_projection(monitor_windows=[window()])
        self.assertEqual(r["coverage_counts"]["NOT_CONNECTED"],2)
        r=self.run_projection(monitor_windows=[window()],verify_monitor=lambda _:False)
        self.assertEqual(r["coverage_counts"]["UNKNOWN"],2)

    def test_duplicate_schedule_pair_and_pin(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SCHEDULE"):
            self.run_projection(schedule=[S,S])
        with self.assertRaisesRegex(ValueError,"SCHEDULE_SHA_DRIFT"):
            self.run_projection(expected_schedule_sha256="0"*64)
        with self.assertRaisesRegex(ValueError,"PAIR_SHA_DRIFT"):
            self.run_projection(schedule=[dict(S,pair_id="a"*64)])

    def test_duplicate_and_early_monitor(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_MONITOR"):
            self.run_projection(monitor_windows=[window(),window()])
        with self.assertRaisesRegex(ValueError,"MONITOR_EARLY_OR_FUTURE"):
            self.run_projection(monitor_windows=[window(available_at_ms=CUTOFF)])
        with self.assertRaisesRegex(ValueError,"MONITOR_EARLY_OR_FUTURE"):
            self.run_projection(monitor_windows=[window()],asof_ms=CUTOFF)

    def test_source_strategy_and_cutoff_drift(self):
        for change in (dict(source_version="wrong"),dict(correction_generation="gen1"),
                       dict(strategy_version="new"),dict(decision_cutoff_ms=CUTOFF+900000)):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.run_projection(monitor_windows=[window(**change)])

    def test_core_research_is_not_original_or_scheduled(self):
        r=self.run_projection(schedule=[],research_evaluations=[R])
        self.assertEqual((r["scheduled_opportunities"],r["horizon_rows"]),(0,0))
        self.assertFalse(r["core_research_evaluations_not_counted"][0]["counted_as_opportunity"])
        with self.assertRaisesRegex(ValueError,"RESEARCH_NOT_ORIGINAL_EVENT"):
            self.run_projection(schedule=[],research_evaluations=[dict(R,original_g2_event_status="PRESENT")])
        with self.assertRaisesRegex(ValueError,"NOT_CORE_HOST_HANDOFF"):
            self.run_projection(handoffs=[R])

    def test_core_f1_host_unverified_and_replay(self):
        host=dict(schema_version="aql.f1-prospective-host-handoff.v1",
                  pair_id=PAIR,c2_identity=IDENT,experiment_plan_sha256=PLAN,
                  proof_scope="RESEARCH_ONLY_HOST_VERIFIER_NOT_TRUST_ROOT",
                  slots=[dict(pair_id=PAIR,arm=a,capture_status="RECORDED",f1_record_sha256=H)
                         for a in ("BASE","SHADOW")])
        host["handoff_sha256"]=digest(host)
        r=self.run_projection(handoffs=[host])
        self.assertEqual({x["capture_status"] for x in r["outcomes"]},{"UNVERIFIED"})
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_ORPHAN_HANDOFF"):
            self.run_projection(handoffs=[host,host])
        with self.assertRaisesRegex(ValueError,"HANDOFF_SHA_DRIFT"):
            self.run_projection(handoffs=[dict(host,handoff_sha256="0"*64)])

    def test_historical_and_duplicate_json_rejected(self):
        with self.assertRaisesRegex(ValueError,"RETROSPECTIVE_SCHEDULE"):
            self.run_projection(schedule=[dict(S,availability_mode="RETROSPECTIVE_NON_PIT")])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
            read_json(b'{"a":1,"a":2}')

    def test_deterministic_no_g0_no_pnl(self):
        a=self.run_projection();b=self.run_projection()
        self.assertEqual(a,b)
        self.assertEqual(a["report_sha256"],digest({k:v for k,v in a.items() if k!="report_sha256"}))
        self.assertFalse(a["g0_merge_paper_shadow_live_authorized"])
        self.assertEqual(a["directional_evaluation_status"],"NOT_EVALUABLE")

if __name__=="__main__":unittest.main()
