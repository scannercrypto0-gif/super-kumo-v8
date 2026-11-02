"""R3 closed-prefix Breakout rule tests: never consume future bars or mint G2."""
import unittest

from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError, digest
from research_wp_r0.aql_r3_breakout_closed_prefix import evaluate_breakout_closed_prefix


def bars(count=22, breakout=False):
    records = []
    for i in range(count):
        start = 1704067200000 + i * 900000
        close = 110.0 if breakout and i == count-1 else 100.0
        records.append((start, start+899999, 100.0,
                        max(100.0, close)+0.5, min(100.0, close)-0.5,
                        close, 20.0))
    return records


class R3BreakoutClosedPrefix(unittest.TestCase):
    def evaluate(self, records=None, **kw):
        r = records if records is not None else bars()
        cutoff = kw.pop("decision_cutoff_ms", r[-1][1]+1)
        return evaluate_breakout_closed_prefix(
            r, decision_cutoff_ms=cutoff,
            availability_mode=kw.pop("availability_mode", "RETROSPECTIVE_NON_PIT"),
            source_id="pinned-original-archive",
            source_version="v1",
            correction_generation="g0", **kw)

    def test_no_signal_retrospective_stays_blocked(self):
        x = self.evaluate()
        self.assertEqual(x["breakout_signal_state"], "NO_SIGNAL")
        self.assertEqual(x["original_g2_event_status"], "NOT_CONNECTED")
        self.assertEqual(x["proof_status"], "BLOCKED_EXTERNAL_EVIDENCE")
        self.assertIsNone(x["direction"])

    def test_breakout_is_armed_never_triggered(self):
        x = self.evaluate(bars(breakout=True))
        self.assertEqual(x["breakout_signal_state"], "ARMED")
        self.assertEqual(x["reason_code"], "AWAITING_F3_ELIGIBILITY_NOT_TRIGGERED")
        self.assertIsNone(x["direction"])
        self.assertEqual(x["execution"], "DISABLED")

    def test_short_warmup_has_explicit_reason(self):
        x = self.evaluate(bars(20))
        self.assertEqual(x["reason_code"], "WARMUP_PERIOD")
        self.assertEqual(x["breakout_signal_state"], "NO_SIGNAL")

    def test_future_bar_even_if_appended_rejected(self):
        r = bars()
        with self.assertRaisesRegex(CaptureError, "FUTURE_OR_NONFINAL_BAR"):
            self.evaluate(r + bars(23)[-1:], decision_cutoff_ms=r[-1][1]+1)

    def test_backdated_or_future_cutoff_rejected(self):
        r = bars()
        with self.assertRaisesRegex(CaptureError, "FUTURE_OR_NONFINAL_BAR"):
            self.evaluate(r, decision_cutoff_ms=r[-1][1])
        with self.assertRaisesRegex(CaptureError, "LAST_BAR_NOT_AT_CUTOFF"):
            self.evaluate(r, decision_cutoff_ms=r[-1][1]+900001)

    def test_gap_duplicate_and_out_of_order_fail_closed(self):
        r = bars()
        for other in (r[:5]+r[6:], r[:10]+r[9:]):
            with self.assertRaisesRegex(CaptureError, "GAP_DUPLICATE_OR_OUT_OF_ORDER"):
                self.evaluate(other)

    def test_prefix_sha_tamper_fails(self):
        r = bars()
        pinned = digest([list(v) for v in r])
        self.assertEqual(self.evaluate(r,expected_prefix_sha256=pinned)["prefix_sha256"], pinned)
        modified = list(r)
        modified[0] = tuple(list(modified[0][:-1])+[99.0])
        with self.assertRaisesRegex(CaptureError, "PREFIX_SHA_DRIFT"):
            self.evaluate(modified, expected_prefix_sha256=pinned)

    def test_strategy_version_drift_rejected(self):
        with self.assertRaisesRegex(CaptureError, "UNAPPROVED_STRATEGY_DRIFT"):
            self.evaluate(strategy_version="2")

    def test_nonfinal_ohlcv_invalid(self):
        r = bars()
        bad = list(r)
        bad[-1] = tuple(list(bad[-1][:3])+[50.0]+list(bad[-1][4:]))
        with self.assertRaisesRegex(CaptureError, "BAD_OHLCV"):
            self.evaluate(bad)

    def test_prospective_input_label_not_automatic_original_event(self):
        x = self.evaluate(availability_mode="PROSPECTIVE_CAPTURE")
        self.assertEqual(x["original_g2_event_status"], "NOT_CONNECTED")
        self.assertEqual(x["pre_f3_capture_status"], "NOT_CONNECTED")
        self.assertEqual(x["proof_status"], "BLOCKED_EXTERNAL_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
