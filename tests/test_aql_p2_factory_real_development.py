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
        with self.assertRaisesRegex(LabContractError, "MISSING_REAL_INPUTS"):
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


if __name__ == "__main__":
    unittest.main()
