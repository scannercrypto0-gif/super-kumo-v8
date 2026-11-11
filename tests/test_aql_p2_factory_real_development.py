"""Focused fail-closed real-development readiness tests; no synthetic alpha."""
import copy
import unittest

from research_wp_r0.aql_p2_factory_lab import LabContractError, digest
from research_wp_r0.aql_p2_factory_real_development import (
    prepare_real_development, validate_prereg, dec,
)
from test_aql_p2_factory_lab import fixture


def test_contract():
    schedule, _ = fixture()
    protocol = schedule["protocol"]
    protocol["hypothesis_sha256"] = "e" * 64
    protocol["preregistration_sha256"] = "f" * 64
    schedule["artifact_sha256"] = digest({k:v for k,v in schedule.items() if k!="artifact_sha256"})
    prereg = {
        "schema": "aql.p2.breakout.preregistration.v1",
        "test_only": False,
        "strategy_family": "BREAKOUT",
        "trial_id": protocol["trial_id"],
        "protocol_sha256": protocol["protocol_sha256"],
        "hypothesis_sha256": "e" * 64,
        "preregistration_sha256": "f" * 64,
        "base_definition_sha256": protocol["base_definition_sha256"],
        "shadow_definition_sha256": protocol["shadow_definition_sha256"],
        "horizons_hours": [4, 24, 72],
        "outcome_rule": "CUTOFF_REFERENCE_TO_4_24_72H_CLOSE_AND_EXCURSIONS_V1",
        "source_package_sha256": schedule["source"]["source_package_sha256"],
        "holdout_status": "SEALED_UNOPENED",
    }
    prereg["artifact_sha256"] = digest(prereg)
    costs = {
        "schema": "aql.p2.factory.modeled-costs.v1",
        "test_only": False,
        "model_kind": "MODEL_ONLY_NOT_EXECUTION",
        "trial_id": protocol["trial_id"],
        "preregistration_sha256": prereg["artifact_sha256"],
        "round_trip_fee_bps": "10",
        "round_trip_slippage_bps": "5",
    }
    costs["artifact_sha256"] = digest(costs)
    return schedule, prereg, costs


class RealDevelopmentGateTests(unittest.TestCase):
    def test_synthetic_core_schedule_never_passes_real_gate(self):
        s, p, c = test_contract()
        with self.assertRaisesRegex(LabContractError, "REAL_SOURCE_SCHEDULE_REQUIRED"):
            prepare_real_development(s, p, c, [], [])

    def test_missing_prereg_fails_closed(self):
        s, p, c = test_contract()
        s["test_only"] = False
        s["artifact_sha256"] = digest({k:v for k,v in s.items() if k!="artifact_sha256"})
        with self.assertRaisesRegex(LabContractError, "MISSING_FROZEN_BREAKOUT_PREREG"):
            validate_prereg(s, None, c)

    def test_unsealed_prereg_fails_closed(self):
        s, p, c = test_contract()
        s["test_only"] = False
        s["artifact_sha256"] = digest({k:v for k,v in s.items() if k!="artifact_sha256"})
        p["strategy_family"] = "OTHER"
        with self.assertRaisesRegex(LabContractError, "UNSEALED_PREREG"):
            validate_prereg(s, p, c)

    def test_fake_cost_digest_fails_closed(self):
        s, p, c = test_contract()
        s["test_only"] = False
        s["artifact_sha256"] = digest({k:v for k,v in s.items() if k!="artifact_sha256"})
        p["hypothesis_sha256"] = s["protocol"].get("hypothesis_sha256", "e"*64)
        p["preregistration_sha256"] = s["protocol"].get("preregistration_sha256", "f"*64)
        p["artifact_sha256"] = digest({k:v for k,v in p.items() if k!="artifact_sha256"})
        c["preregistration_sha256"] = p["artifact_sha256"]
        c["artifact_sha256"] = digest({k:v for k,v in c.items() if k!="artifact_sha256"})
        c["round_trip_fee_bps"] = "100"
        with self.assertRaisesRegex(LabContractError, "UNSEALED_COST_MODEL"):
            validate_prereg(s, p, c)

    def test_missing_real_windows_fails_closed(self):
        s, p, c = test_contract()
        s["test_only"] = False
        s["protocol"]["hypothesis_sha256"] = "e"*64
        s["protocol"]["preregistration_sha256"] = "f"*64
        s["artifact_sha256"] = digest({k:v for k,v in s.items() if k!="artifact_sha256"})
        with self.assertRaisesRegex(LabContractError, "INCOMPLETE_WINDOW_DENOMINATOR"):
            prepare_real_development(s, p, c, [], [])

    def test_nonfinite_or_negative_cost_rejected(self):
        for x in ("NaN", "Infinity", "-Infinity", "abc"):
            with self.assertRaises(LabContractError):
                dec(x)

    def test_test_only_prereg_never_upgraded(self):
        s, p, c = test_contract()
        s["test_only"] = False
        s["protocol"]["hypothesis_sha256"] = "e"*64
        s["protocol"]["preregistration_sha256"] = "f"*64
        s["artifact_sha256"] = digest({k:v for k,v in s.items() if k!="artifact_sha256"})
        p["test_only"] = True
        p["artifact_sha256"] = digest({k:v for k,v in p.items() if k!="artifact_sha256"})
        with self.assertRaisesRegex(LabContractError, "REAL_PREREG_REQUIRED"):
            validate_prereg(s, p, c)


    def _paired_censored_fixture(self):
        # TEST_ONLY shape fixture, never genuine Core/Work research.
        s, p, costs = test_contract()
        s["test_only"] = False
        s["artifact_sha256"] = digest({k:v for k,v in s.items() if k!="artifact_sha256"})
        pair = s["pairs"][0]
        pid = pair["pair_id"]
        cutoff = pair["opportunity"]["decision_cutoff_ms"]
        windows = []
        for h in (4, 24, 72):
            w = dict(pair_id=pid, horizon_hours=h,
                     source_package_sha256=s["source"]["source_package_sha256"],
                     reference_price="100", reference_bar_close_ms=cutoff-1,
                     bars=[], availability="CENSORED", availability_reason="COHORT_END")
            w["source_window_sha256"] = digest(w)
            windows.append(w)
        decisions = []
        for arm, status, direction in (("BASE", "TRIGGERED", "LONG"),
                                       ("SHADOW", "REJECTED", None)):
            d = dict(pair_id=pid, arm=arm,
                     policy_sha256=next(x["definition_sha256"] for x in pair["arms"] if x["arm"]==arm),
                     decision_cutoff_ms=cutoff, decision_evidence_sha256="b"*64,
                     direction=direction, disposition=status,
                     signal_disposition="TRIGGERED", modeled_trade_availability="COMPLETE")
            d["decision_sha256"] = digest(d)
            decisions.append(d)
        return s, p, costs, windows, decisions

    def test_rejected_arm_keeps_denominator_and_null_censored_returns(self):
        s,p,c,w,d = self._paired_censored_fixture()
        out = prepare_real_development(s,p,c,w,d)
        self.assertEqual((out["pair_count"],out["outcome_slots"]),(1,6))
        self.assertEqual({r["arm_disposition"] for r in out["outcomes"]},
                         {"TRIGGERED","REJECTED"})
        self.assertTrue(all(r["modeled_net_directional_return"] is None
                            for r in out["outcomes"]))

    def test_forged_rejected_direction_rejected_even_if_rehashed(self):
        s,p,c,w,d = self._paired_censored_fixture()
        d[1]["direction"] = "LONG"
        d[1]["decision_sha256"] = digest({k:v for k,v in d[1].items() if k!="decision_sha256"})
        with self.assertRaisesRegex(LabContractError,"INELIGIBLE_ARM_HAS_DIRECTION"):
            prepare_real_development(s,p,c,w,d)

    def test_false_unknown_with_complete_exit_rejected(self):
        s,p,c,w,d = self._paired_censored_fixture()
        d[0]["direction"] = None
        d[0]["disposition"] = "UNKNOWN"
        d[0]["decision_sha256"] = digest({k:v for k,v in d[0].items() if k!="decision_sha256"})
        with self.assertRaisesRegex(LabContractError,"FALSE_UNKNOWN_ELIGIBILITY"):
            prepare_real_development(s,p,c,w,d)


if __name__ == "__main__":
    unittest.main()
