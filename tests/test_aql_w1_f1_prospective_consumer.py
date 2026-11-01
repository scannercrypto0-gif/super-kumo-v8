"""Focused contract-seam tests: no original P0 replay and no runtime PIT proof."""
import copy
import unittest
from research_wp_r0.aql_w1_f1_prospective_consumer import project_f1_research_slots
from research_wp_r0.aql_w1_opportunity_outcomes import EvidenceError

H = "a" * 64
S = "b" * 64
PAIR = "c" * 64
K = dict(trial_id="T", opportunity_id="O", producer_event_id="E", envelope_sha256=H)
PLAN = dict(pair_id=PAIR, c2_identity=K, decision_cutoff_ms=900000,
            source_version="src-v1", source_bytes_sha256=S,
            correction_generation="gen0", experiment_plan_sha256="d" * 64)


def capture(arm, **changes):
    row = dict(schema_version="aql.f1-decision-capture.v1", pair_id=PAIR,
               c2_identity=K, arm=arm, f1_record_sha256=H, producer_sequence=1,
               arm_event_sha256=S, experiment_plan_sha256="d" * 64,
               source_version="src-v1", source_bytes_sha256=S,
               correction_generation="gen0", decision_cutoff_ms=900000,
               f1_signal_state="ARMED" if arm == "BASE" else "NO_SIGNAL",
               direction="LONG" if arm == "BASE" else None,
               predecision_eligibility="YES" if arm == "BASE" else "NOT_ESTABLISHED",
               reference=dict(price="100", reference_available_at_ms=900000,
                              measurement_policy_sha256="e" * 64),
               tp=dict(status="DEFINED_PREDECISION"),
               sl=dict(status="DEFINED_PREDECISION"),
               indicators=[dict(indicator_id="RSI14", role="OBSERVE_ONLY",
                                value_kind="NUMBER", value="58.2", missing_reason=None)])
    row.update(changes)
    return row


def window(h=86400000, **changes):
    row = dict(pair_id=PAIR, horizon_ms=h, decision_cutoff_ms=900000,
               source_version="src-v1", source_bytes_sha256=S,
               correction_generation="gen0", coverage_status="COMPLETE",
               expected_bars=h // 900000, observed_bars=h // 900000,
               high="110", low="95", tp_sl_first_hit="UNKNOWN")
    row.update(changes)
    return row


def accepted(_):
    return 'RECORDED'


def market_accepted(_):
    return True


class FactoryF1ProjectionTests(unittest.TestCase):
    def project(self, captures=(), windows=(), **kwargs):
        return project_f1_research_slots([PLAN], captures, windows, **kwargs)

    def test_full_denominator_missing_arm_and_all_horizons(self):
        report = self.project([capture("BASE")])
        self.assertEqual(report["arm_slots"], 2)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertEqual(report["capture_status_counts"], {"MISSING_CAPTURE": 1, "UNVERIFIED": 1})
        self.assertTrue(all(r["max_favorable"] is None for r in report["outcomes"]))

    def test_verified_original_market_still_requires_market_proof(self):
        report = self.project([capture("BASE"), capture("SHADOW")],
                              [window()], verify_original=accepted)
        self.assertTrue(all(r["max_favorable"] is None for r in report["outcomes"]))
        self.assertEqual(report["capture_status_counts"], {"RECORDED": 2})

    def test_complete_signed_and_no_signal_market_only(self):
        report = self.project([capture("BASE"), capture("SHADOW")],
                              [window()], verify_original=accepted, verify_market=market_accepted)
        rows = {r["arm"]: r for r in report["outcomes"] if r["horizon_ms"] == 86400000}
        self.assertEqual((rows["BASE"]["max_favorable"], rows["BASE"]["max_adverse"]), ("10", "5"))
        self.assertEqual(rows["BASE"]["tp_sl_first_hit"], "UNKNOWN")
        self.assertEqual(rows["BASE"]["excursion_status"], "EVALUABLE")
        self.assertEqual(rows["BASE"]["measurement_class"], "ARM_SPECIFIC_POLICY")
        self.assertEqual(rows["BASE"]["observe_only_indicators"][0]["indicator_id"], "RSI14")
        self.assertEqual(rows["SHADOW"]["measurement_class"], "MARKET_ONLY")
        self.assertIsNone(rows["SHADOW"]["max_favorable"])

    def test_genuinely_comparable_two_arm_signed_pair(self):
        base = capture("BASE")
        shadow = capture("SHADOW", direction="SHORT", f1_signal_state="ARMED",
                         predecision_eligibility="YES")
        report = self.project([base, shadow], [window()],
                              verify_original=accepted, verify_market=market_accepted)
        rows = [r for r in report["outcomes"] if r["horizon_ms"] == 86400000]
        self.assertEqual({r["measurement_class"] for r in rows}, {"COMMON_PAIRED"})
        self.assertEqual({r["max_favorable"] for r in rows}, {"10", "5"})

    def test_censored_retained_no_signed_extrema(self):
        report = self.project([capture("BASE")],
                              [window(coverage_status="ARCHIVE_END_CENSORED", observed_bars=24)],
                              verify_original=accepted, verify_market=market_accepted)
        row = next(r for r in report["outcomes"] if r["arm"] == "BASE" and r["horizon_ms"] == 86400000)
        self.assertEqual(row["coverage_status"], "ARCHIVE_END_CENSORED")
        self.assertIsNone(row["max_adverse"])

    def test_bad_source_vintage_fails_closed(self):
        report = self.project([capture("BASE")], [window(source_version="future-correction")],
                              verify_original=accepted, verify_market=accepted)
        row = next(r for r in report["outcomes"] if r["arm"] == "BASE" and r["horizon_ms"] == 86400000)
        self.assertEqual(row["coverage_status"], "UNKNOWN")
        self.assertIsNone(row["max_favorable"])

    def test_present_invalid_quarantine_and_conflict(self):
        bad = capture("BASE", f1_record_sha256="not-a-hash")
        report = self.project([bad], verify_original=accepted)
        self.assertEqual(report["capture_status_counts"]["QUARANTINED"], 1)
        conflict = self.project([capture("BASE"), capture("BASE", producer_sequence=2)],
                                verify_original=accepted)
        self.assertEqual(conflict["capture_status_counts"]["QUARANTINED"], 1)

    def test_identical_replay_is_idempotent(self):
        row = capture("BASE")
        report = self.project([row, copy.deepcopy(row)], verify_original=accepted)
        self.assertEqual(report["capture_status_counts"]["RECORDED"], 1)

    def test_orphan_and_duplicate_market_rejected(self):
        with self.assertRaises(EvidenceError):
            self.project([capture("SHADOW", pair_id="d" * 64)])
        with self.assertRaises(EvidenceError):
            self.project(windows=[window(), window()])

    def test_core_quarantine_verdict_not_silently_unverified(self):
        report = self.project([capture("BASE")], verify_original=lambda _: "QUARANTINED")
        self.assertEqual(report["capture_status_counts"]["QUARANTINED"], 1)

    def test_f3_rejected_separate_from_original_f1(self):
        effects = [{"c2_identity": K, "effect_disposition": "REJECTED"}]
        report = self.project([capture("BASE")], f3_effects=effects)
        self.assertTrue(all(r["f3_effect_disposition"] == "REJECTED" for r in report["outcomes"]))
        self.assertTrue(all(r["f1_signal_state"] is None for r in report["outcomes"]))
        with self.assertRaises(EvidenceError):
            self.project([capture("BASE")], f3_effects=[])

    def test_mismatched_original_source_is_quarantined(self):
        report = self.project([capture("BASE", source_version="wrong")], verify_original=accepted)
        self.assertEqual(report["capture_status_counts"]["QUARANTINED"], 1)

    def test_directionless_never_signed_even_complete(self):
        row = capture("BASE", direction=None)
        report = self.project([row], [window()], verify_original=accepted, verify_market=accepted)
        result = next(x for x in report["outcomes"] if x["arm"] == "BASE" and x["horizon_ms"] == 86400000)
        self.assertEqual(result["excursion_status"], "NO_DIRECTION")
        self.assertIsNone(result["max_favorable"])


if __name__ == "__main__":
    unittest.main()
