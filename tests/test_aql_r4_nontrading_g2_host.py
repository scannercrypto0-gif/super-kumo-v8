"""R4 changed-only predecision host sequencing, fail-closed negatives."""
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError
from research_wp_r0.aql_r4_nontrading_g2_host import invoke_g2_nontrading

H = "a"*64
CUT = 1704087000000
C2 = dict(trial_id="R4-offline", opportunity_id="offline-opportunity",
          producer_event_id="offline-event", envelope_sha256=H)
PINS = dict(source_id="offline-fixture-only", source_version="v1",
            source_bytes_sha256=H, correction_generation="g0",
            strategy_id="SF_BREAKOUT_BASE_20_10_DEV_v1",strategy_version="1",
            feature_snapshot_sha256=H,regime_snapshot_sha256=H)


def bars(breakout=False):
    rows = []
    start = CUT-22*900000
    for i in range(22):
        op = start+i*900000
        close = 110.0 if breakout and i==21 else 100.0
        rows.append((op,op+899999,100.0,max(100.0,close)+.5,
                     min(100.0,close)-.5,close,20.0))
    return rows


class R4HostTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.path=Path(t.name)
        self.args=dict(c2_identity=C2,experiment_plan_sha256=H,
                       decision_cutoff_ms=CUT,scheduled_at_ms=CUT-1,
                       availability_mode="RETROSPECTIVE_NON_PIT",
                       pins=PINS,directory=self.path)

    def run_host(self, callback=None, **kwargs):
        args=dict(self.args,**kwargs)
        return invoke_g2_nontrading(**args,bars_provider=callback or bars)

    def test_schedule_frozen_before_callback_and_two_arms(self):
        def source():
            files=list(self.path.glob("*.schedule.json"))
            self.assertEqual(len(files),1)
            self.assertIn(b'"BASE"',files[0].read_bytes())
            self.assertIn(b'"SHADOW"',files[0].read_bytes())
            self.assertEqual(list(self.path.glob("*.result.json")),[])
            return bars()
        x=self.run_host(source)
        self.assertEqual(x["runtime_evaluation_status"],"COMPLETED_LOCAL_NONTRADING")
        self.assertEqual(x["arm_statuses"],{"BASE":"MISSING_CAPTURE","SHADOW":"MISSING_CAPTURE"})
        self.assertEqual(x["decision_status_by_arm"]["BASE"],"NO_SIGNAL")
        self.assertEqual(x["original_g2_event_status"],"NOT_CONNECTED")
        self.assertFalse(x["historical_replay_is_original_proof"])
        self.assertEqual(len(list(self.path.glob("*.result.json"))),1)

    def test_armed_is_never_triggered_or_directional(self):
        x=self.run_host(lambda:bars(True))
        self.assertEqual(x["decision_status_by_arm"],{"BASE":"ARMED","SHADOW":"ARMED"})
        self.assertIsNone(x["evaluation"]["direction"])
        self.assertEqual(x["trade_execution"],"DISABLED")

    def test_replay_rejected_before_provider_call(self):
        self.run_host()
        called=[]
        with self.assertRaisesRegex(CaptureError,"REPLAY_ALREADY_INVOKED"):
            self.run_host(lambda:called.append(True) or bars())
        self.assertEqual(called,[])

    def test_conflicting_schedule_pin_fails_closed(self):
        self.run_host()
        with self.assertRaisesRegex(CaptureError,"SCHEDULE_TAMPER"):
            self.run_host(pins=dict(PINS,source_version="v2"))

    def test_prospective_mode_without_known_at_rejected(self):
        with self.assertRaisesRegex(CaptureError,"SOURCE_KNOWN_AT_UNVERIFIED"):
            self.run_host(availability_mode="PROSPECTIVE_CAPTURE")
        self.assertEqual(len(list(self.path.glob("*.result.json"))),0)

    def test_late_source_rejected_before_writes(self):
        with self.assertRaisesRegex(CaptureError,"SOURCE_LATE"):
            self.run_host(source_available_at_ms=CUT+1)
        self.assertEqual(list(self.path.iterdir()),[])

    def test_future_bar_fails_without_result(self):
        def future():
            extra=bars()
            start=CUT
            extra.append((start,start+899999,100.0,100.5,99.5,100.0,20.0))
            return extra
        with self.assertRaisesRegex(CaptureError,"FUTURE_OR_NONFINAL_BAR"):
            self.run_host(future)
        self.assertEqual(len(list(self.path.glob("*.result.json"))),0)

    def test_bad_source_and_version_rejected(self):
        with self.assertRaisesRegex(CaptureError,"STRATEGY_VERSION_DRIFT"):
            self.run_host(pins=dict(PINS,strategy_version="2"))
        with self.assertRaisesRegex(CaptureError,"SHA_FORMAT"):
            self.run_host(pins=dict(PINS,source_bytes_sha256="bad"))

    def test_fake_original_f1_input_rejected(self):
        with self.assertRaisesRegex(CaptureError,"ORIGINAL_F1_RUNTIME_AUTHORITY_NOT_ESTABLISHED"):
            self.run_host(original_f1_records={"BASE":{},"SHADOW":{}})
        self.assertEqual(list(self.path.iterdir()),[])

    def test_source_not_called_on_invalid_schedule(self):
        called=[]
        with self.assertRaisesRegex(CaptureError,"SCHEDULE_CLOCK"):
            self.run_host(lambda:called.append(1) or bars(),scheduled_at_ms=CUT)
        self.assertEqual(called,[])


if __name__=="__main__":
    unittest.main()
