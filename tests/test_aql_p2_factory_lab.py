"""TEST_ONLY contract checks for Factory P2 consumer (not a historical study)."""
import copy
import unittest

from research_wp_r0.aql_p2_factory_lab import (
    LabContractError, build_lab, digest, validate_schedule,
)


def fixture():
    h = "a" * 64
    protocol = {
        "trial_id": "TEST_ONLY_TRIAL", "protocol_sha256": h,
        "base_definition_sha256": "b" * 64,
        "shadow_definition_sha256": "c" * 64,
        "embargo_ms": 259200000,
        "train_end_exclusive_ms": 1000000000,
        "holdout_start_ms": 1300000000,
        "holdout_end_exclusive_ms": 1500000000,
    }
    source = {"source_id": "TEST_ONLY_SOURCE", "source_package_sha256": "d" * 64}
    opportunity = {
        "trial_id": "TEST_ONLY_TRIAL", "source_id": "TEST_ONLY_SOURCE",
        "source_package_sha256": "d" * 64, "opportunity_id": "TEST_ONLY_OPP",
        "decision_cutoff_ms": 900000000, "decision_ms": 900000001,
        "disposition": "NO_SIGNAL", "evidence_class": "RETROSPECTIVE_NON_PIT",
    }
    pid = digest({"protocol_sha256": h, "trial_id": "TEST_ONLY_TRIAL",
                  "opportunity_id": "TEST_ONLY_OPP"})
    schedule = {
        "schema": "aql.p2.core.paired-schedule.v1", "test_only": True,
        "evidence_class": "RETROSPECTIVE_NON_PIT",
        "holdout_status": "SEALED_UNOPENED",
        "outcome_evaluation": "NOT_PERFORMED",
        "execution_status": "NOT_OBSERVED", "protocol": protocol, "source": source,
        "scheduled_total": 1,
        "pairs": [{"pair_id": pid, "opportunity": opportunity, "arms": [
            {"arm": "BASE", "definition_sha256": "b" * 64},
            {"arm": "SHADOW", "definition_sha256": "c" * 64}]}],
    }
    schedule["artifact_sha256"] = digest(schedule)
    observations = [
        {"pair_id": pid, "arm": arm, "horizon_hours": horizon,
         "availability": "COMPLETE", "availability_reason": None,
         "market_metrics": {"reference_price": 100.0, "observed_high": 101.0,
                            "observed_low": 99.0},
         "directional_metrics": None, "execution_status": "NOT_OBSERVED"}
        for arm in ("BASE", "SHADOW") for horizon in (4, 24, 72)
    ]
    return schedule, observations


def repin(schedule):
    schedule["artifact_sha256"] = digest({
        k: v for k, v in schedule.items() if k != "artifact_sha256"
    })


class FactoryP2Test(unittest.TestCase):
    def test_test_only_complete_denominator(self):
        s, o = fixture()
        result = build_lab(s, o)
        self.assertEqual(result["observation_slots"], 6)
        self.assertEqual(result["disposition_counts"], {"NO_SIGNAL": 1})
        self.assertEqual(result["market_coverage_by_horizon"]["72"]["COMPLETE"], 1)
        self.assertEqual(result["paired_strategy_effect"],
                         "NOT_EVALUABLE_NO_VERIFIED_ARM_OUTCOMES")

    def test_digest_mutation_rejected(self):
        s, _ = fixture()
        s["scheduled_total"] = 2
        with self.assertRaisesRegex(LabContractError, "SCHEDULE_DIGEST_MISMATCH"):
            validate_schedule(s)

    def test_missing_slot_rejected(self):
        s, o = fixture()
        with self.assertRaisesRegex(LabContractError, "INCOMPLETE_DENOMINATOR"):
            build_lab(s, o[:-1])

    def test_duplicate_slot_rejected(self):
        s, o = fixture()
        with self.assertRaisesRegex(LabContractError, "DUPLICATE_SLOT"):
            build_lab(s, o + [o[0]])

    def test_unpaired_market_window_rejected(self):
        s, o = fixture()
        o[3]["market_metrics"]["observed_high"] = 110.0
        with self.assertRaisesRegex(LabContractError, "UNPAIRED_SOURCE_WINDOW"):
            build_lab(s, o)

    def test_no_real_run_by_accident(self):
        s, o = fixture()
        with self.assertRaisesRegex(LabContractError, "REAL_EVALUATION_NOT_AUTHORIZED"):
            build_lab(s, o, test_only=False)

    def test_no_direction_or_fills(self):
        s, o = fixture()
        o[0]["directional_metrics"] = {"mfe": 0.1}
        with self.assertRaisesRegex(LabContractError, "UNVERIFIED_EXECUTION_OR_DIRECTION"):
            build_lab(s, o)

    def test_holdout_sealed(self):
        s, _ = fixture()
        s["holdout_status"] = "OPEN"
        repin(s)
        with self.assertRaisesRegex(LabContractError, "HOLDOUT_OPEN"):
            validate_schedule(s)

    def test_embargo_rejected(self):
        s, _ = fixture()
        s["protocol"]["embargo_ms"] = 100
        repin(s)
        with self.assertRaisesRegex(LabContractError, "EMBARGO_TOO_SHORT"):
            validate_schedule(s)

    def test_missing_reason(self):
        s, o = fixture()
        o[0]["availability"] = "UNKNOWN"
        o[0]["market_metrics"] = None
        with self.assertRaisesRegex(LabContractError, "UNVERIFIED_MISSINGNESS"):
            build_lab(s, o)

    def test_censored_pair(self):
        s, o = fixture()
        for row in o:
            if row["horizon_hours"] == 72:
                row.update(availability="CENSORED",
                           availability_reason="ARCHIVE_END_CENSORED",
                           market_metrics=None)
        result = build_lab(s, o)
        self.assertEqual(result["market_coverage_by_horizon"]["72"]["CENSORED"], 1)


if __name__ == "__main__":
    unittest.main()
