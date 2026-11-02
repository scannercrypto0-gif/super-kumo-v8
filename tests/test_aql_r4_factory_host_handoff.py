"""Focused R4 Factory tests: software handoff only, never original G2."""
import copy
import unittest

from research_wp_r0.aql_r3_factory_event_outcome_consumer import digest
from research_wp_r0.aql_r4_factory_host_handoff import consume_r4_host

H = "a" * 64
CUT = 1704087000000
C2 = {"trial_id": "R4-SAFE-OFFLINE-DEMO", "opportunity_id": "FIXTURE_NOT_ORIGINAL",
      "producer_event_id": "FIXTURE_ONLY", "envelope_sha256": H}
PINS = {"source_id": "FIXTURE_NOT_ISSUER", "source_version": "v1",
        "source_bytes_sha256": H, "correction_generation": "g0",
        "strategy_id": "SF_BREAKOUT_BASE_20_10_DEV_v1", "strategy_version": "1",
        "feature_snapshot_sha256": H, "regime_snapshot_sha256": H}


def fixture():
    pair = digest({"experiment_plan_sha256": H, "c2_identity": C2})
    schedule = dict(schema_version="aql.r4-predecision-schedule.v1",
        c2_identity=C2, pair_id=pair, experiment_plan_sha256=H,
        decision_cutoff_ms=CUT, scheduled_at_ms=CUT - 1,
        availability_mode="RETROSPECTIVE_NON_PIT", **PINS,
        arms=[{"arm": a, "capture_status": "MISSING_CAPTURE"}
              for a in ("BASE", "SHADOW")],
        source_available_at_ms=None, scheduled_source_proof="UNVERIFIED_LOCAL_INPUT")
    schedule["schedule_sha256"] = digest(schedule)
    evaluation = dict(schema_version="aql.r3-breakout-closed-prefix-evaluation.v1",
        original_g2_event_status="NOT_CONNECTED",
        pre_f3_capture_status="NOT_CONNECTED", f3_monitor_status="NOT_CONNECTED",
        proof_status="BLOCKED_EXTERNAL_EVIDENCE", execution="DISABLED",
        direction=None, breakout_signal_state="NO_SIGNAL",
        decision_cutoff_ms=CUT, prefix_sha256=H,
        source_id=PINS["source_id"], source_version="v1",
        correction_generation="g0", strategy_id=PINS["strategy_id"],
        strategy_version="1")
    result = dict(schema_version="aql.r4-nontrading-evaluation-host.v1",
        schedule_sha256=schedule["schedule_sha256"], pair_id=pair,
        c2_identity=C2, availability_mode="RETROSPECTIVE_NON_PIT",
        source_available_at_ms=None, runtime_invocation="CALLED_NOW_IN_THIS_HOST",
        runtime_evaluation_status="COMPLETED_LOCAL_NONTRADING",
        original_g2_event_status="NOT_CONNECTED",
        original_f1_capture_status="BLOCKED_ON_ORIGINAL_F1_RECORD_AND_INDEPENDENT_EVIDENCE",
        original_f1_missing_fields=["validated_original_f1_record_BASE"],
        proof_status="BLOCKED_EXTERNAL_EVIDENCE",
        arm_statuses={"BASE": "MISSING_CAPTURE", "SHADOW": "MISSING_CAPTURE"},
        decision_status_by_arm={"BASE": "NO_SIGNAL", "SHADOW": "NO_SIGNAL"},
        evaluation=evaluation, f3_monitor_status="NOT_CONNECTED",
        trade_execution="DISABLED", historical_replay_is_original_proof=False)
    result["result_sha256"] = digest(result)
    return schedule, result


class FactoryR4Tests(unittest.TestCase):
    def test_valid_fixture_is_segregated(self):
        s, r = fixture()
        report = consume_r4_host(s, r, asof_ms=CUT)
        self.assertEqual(report["software_handoff_status"], "SOFTWARE_HANDOFF_ACCEPTED")
        self.assertEqual((report["scheduled_opportunities"], report["arm_slots"],
                          report["horizon_rows"]), (0, 0, 0))
        self.assertEqual(report["genuine_original_event_status"], "BLOCKED_ON_REAL_G2_EVENT")

    def reject(self, edit, expected):
        s, r = fixture()
        edit(s, r)
        with self.assertRaisesRegex(ValueError, expected):
            consume_r4_host(s, r, asof_ms=CUT)

    def test_schedule_hash_tamper(self):
        self.reject(lambda s, r: s.update(source_version="v2"), "R4_SCHEDULE_SHA_DRIFT")

    def test_result_hash_tamper(self):
        self.reject(lambda s, r: r.update(pair_id="forged"), "R4_RESULT_SHA_DRIFT")

    def test_relinked_result_pair(self):
        def change(s, r):
            r["pair_id"] = "forged"
            r["result_sha256"] = digest({k: v for k, v in r.items() if k != "result_sha256"})
        self.reject(change, "R4_RESULT_SCHEDULE_MISMATCH")

    def test_promoted_original(self):
        def change(s, r):
            r["original_g2_event_status"] = "RECORDED"
            r["result_sha256"] = digest({k: v for k, v in r.items() if k != "result_sha256"})
        self.reject(change, "R4_FORGED_ORIGINAL")

    def test_false_triggered(self):
        def change(s, r):
            r["decision_status_by_arm"]["BASE"] = "TRIGGERED"
            r["result_sha256"] = digest({k: v for k, v in r.items() if k != "result_sha256"})
        self.reject(change, "R4_DECISION_FORGED")

    def test_fake_prospective_mode(self):
        def change(s, r):
            s["availability_mode"] = "PROSPECTIVE_CAPTURE"
            s["schedule_sha256"] = digest({k: v for k, v in s.items() if k != "schedule_sha256"})
        self.reject(change, "R4_UNSUPPORTED_PROSPECTIVE_CLAIM")

    def test_arm_capture_forgery(self):
        def change(s, r):
            r["arm_statuses"]["BASE"] = "RECORDED"
            r["result_sha256"] = digest({k: v for k, v in r.items() if k != "result_sha256"})
        self.reject(change, "R4_ARM_CAPTURE_FORGED")

    def test_future_source(self):
        def change(s, r):
            s["source_available_at_ms"] = CUT + 1
            s["schedule_sha256"] = digest({k: v for k, v in s.items() if k != "schedule_sha256"})
        self.reject(change, "R4_SOURCE_LATE")


if __name__ == "__main__":
    unittest.main()
