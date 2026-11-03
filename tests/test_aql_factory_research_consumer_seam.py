"""F3 adversarial and F4 consolidated TEST_ONLY Core-style -> Factory gate.

Uses the repository's actual paired-schedule fixture and the UNMOCKED existing
Factory validate_schedule/build_lab, not a private Core PR or new evaluator.
"""
import copy
import unittest

from test_aql_p2_factory_lab import fixture as factory_fixture, repin
from research_wp_r0.aql_p2_factory_lab import LabContractError, digest as digest_schedule
from research_wp_r0.aql_factory_research_consumer_seam import (
    build_research_handoff, build_research_report, digest, seal,
)


def integration_fixture():
    schedule, observations = factory_fixture()
    prototype = copy.deepcopy(schedule["pairs"][0])
    for name, disposition in (
        ("TEST_ONLY_REJECTED", "REJECTED"),
        ("TEST_ONLY_UNKNOWN", "UNKNOWN"),
        ("TEST_ONLY_TRIGGERED", "TRIGGERED"),
    ):
        pair = copy.deepcopy(prototype)
        pair["opportunity"]["opportunity_id"] = name
        pair["opportunity"]["disposition"] = disposition
        pair["pair_id"] = digest_schedule({
            "protocol_sha256": schedule["protocol"]["protocol_sha256"],
            "trial_id": schedule["protocol"]["trial_id"],
            "opportunity_id": name,
        })
        schedule["pairs"].append(pair)
        for row in observations[:6]:
            new_row = copy.deepcopy(row)
            new_row["pair_id"] = pair["pair_id"]
            observations.append(new_row)
    schedule["scheduled_total"] = len(schedule["pairs"])
    repin(schedule)

    # Availability and ambiguous outcomes stay descriptive, never wins/losses.
    for row in observations:
        if row["horizon_hours"] == 24:
            row.update(availability="CENSORED",
                       availability_reason="TEST_ONLY_ARCHIVE_END",
                       market_metrics=None)
        elif row["horizon_hours"] == 72:
            row.update(availability="UNKNOWN",
                       availability_reason="TEST_ONLY_AMBIGUOUS_OR_MISSING",
                       market_metrics=None)

    states = {
        "NO_SIGNAL": ("NO_SIGNAL", "NO_SIGNAL"),
        "REJECTED": ("REJECTED", "REJECTED"),
        "UNKNOWN": ("UNKNOWN", "UNSCANNED"),
        "TRIGGERED": ("NOMINATED", "NULL"),
    }
    rows = []
    for pair in schedule["pairs"]:
        opp = pair["opportunity"]
        for index, arm in enumerate(("BASE", "SHADOW")):
            rows.append({
                "pair_id": pair["pair_id"], "arm": arm,
                "opportunity_id": opp["opportunity_id"],
                "attempt_id": "TEST_ONLY_" + opp["opportunity_id"] + "_" + arm,
                "cohort_id": "TEST_ONLY_COHORT", "strategy_version": "v1",
                "source_manifest_sha256": "f" * 64,
                "source_package_sha256": schedule["source"]["source_package_sha256"],
                "decision_cutoff_ms": opp["decision_cutoff_ms"],
                "feature_available_ms": opp["decision_cutoff_ms"] - 1,
                "feature_availability_class": "RETROSPECTIVE_NON_PIT",
                "feature_snapshot_sha256": "e" * 64,
                "source_disposition": opp["disposition"],
                "status": states[opp["disposition"]][index],
                "descriptive_outcomes_4_24_72h": None,
                "modeled_trade": None, "execution_status": "NOT_OBSERVED",
                "return": None,
            })
    envelope = seal({
        "schema": "aql.factory.research-consumer-seam.v1",
        "test_only": True, "evidence_class": "TEST_ONLY",
        "execution_status": "NOT_OBSERVED", "trading_authority": "NONE",
        "source_schedule_sha256": schedule["artifact_sha256"],
        "source_package_sha256": schedule["source"]["source_package_sha256"],
        "source_manifest_sha256": "f" * 64,
        "cohort_id": "TEST_ONLY_COHORT", "strategy_version": "v1",
        "rows": rows,
    })
    return schedule, envelope, observations


def reseal(envelope):
    envelope.pop("artifact_sha256", None)
    envelope["artifact_sha256"] = digest(envelope)


class FactoryResearchSeamGate(unittest.TestCase):
    def test_f4_real_factory_evaluator_and_replay(self):
        schedule, envelope, observations = integration_fixture()
        original = copy.deepcopy((schedule, envelope, observations))
        report1 = build_research_report(schedule, envelope, observations)
        report2 = build_research_report(schedule, envelope, observations)
        self.assertEqual(report1, report2)
        self.assertEqual((schedule, envelope, observations), original)
        self.assertEqual(report1["scheduled_pairs"], 4)
        self.assertEqual(report1["arm_slots"], 8)
        self.assertEqual(report1["descriptive_observation_slots"], 24)
        self.assertEqual(report1["status_counts"]["NO_SIGNAL"], 2)
        self.assertEqual(report1["status_counts"]["REJECTED"], 2)
        self.assertEqual(report1["status_counts"]["UNKNOWN"], 1)
        self.assertEqual(report1["status_counts"]["UNSCANNED"], 1)
        self.assertEqual(report1["status_counts"]["NOMINATED"], 1)
        self.assertEqual(report1["status_counts"]["NULL"], 1)
        self.assertEqual(sum(report1["status_counts"].values()), 8)
        self.assertEqual(report1["market_coverage_by_horizon"]["4"]["COMPLETE"], 4)
        self.assertEqual(report1["market_coverage_by_horizon"]["24"]["CENSORED"], 4)
        self.assertEqual(report1["market_coverage_by_horizon"]["72"]["UNKNOWN"], 4)
        self.assertEqual(report1["modeled_trade_engine"], "NOT_INVOKED")
        self.assertEqual(report1["fills_pnl_alpha"], "NOT_COMPUTED")
        self.assertEqual(report1["ambiguous_intrabar"], "UNKNOWN_NOT_RESOLVED")
        self.assertEqual(report1["trading_authority"], "NONE")
        self.assertEqual(report1["artifact_sha256"],
                         digest({k: v for k, v in report1.items()
                                 if k != "artifact_sha256"}))
        print("FACTORY_F4_TEST_ONLY_RECEIPT", report1["artifact_sha256"])

    def test_f3_adversarial_receipt_and_source_guards(self):
        cases = (
            ("source-mismatch", lambda s,e,o: e.update(source_package_sha256="a"*64)),
            ("manifest-mismatch", lambda s,e,o: e["rows"][0].update(source_manifest_sha256="a"*64)),
            ("cutoff-mismatch", lambda s,e,o: e["rows"][0].update(decision_cutoff_ms=1)),
            ("late-feature", lambda s,e,o: e["rows"][0].update(feature_available_ms=900000001)),
            ("mixed-cohort", lambda s,e,o: e["rows"][0].update(cohort_id="WRONG")),
            ("mixed-strategy", lambda s,e,o: e["rows"][0].update(strategy_version="WRONG")),
            ("duplicate-attempt", lambda s,e,o: e["rows"][1].update(attempt_id=e["rows"][0]["attempt_id"])),
            ("duplicate-slot", lambda s,e,o: e["rows"].append(copy.deepcopy(e["rows"][0]))),
            ("missing-denominator", lambda s,e,o: e["rows"].pop()),
            ("null-to-zero", lambda s,e,o: e["rows"][-1].update(**{"return":0})),
            ("fabricated-trade", lambda s,e,o: e["rows"][-1].update(modeled_trade={"pnl":0})),
            ("fabricated-descriptive", lambda s,e,o: e["rows"][-1].update(descriptive_outcomes_4_24_72h={"4":1})),
            ("false-nomination", lambda s,e,o: e["rows"][0].update(status="NOMINATED")),
            ("source-disposition", lambda s,e,o: e["rows"][0].update(source_disposition="TRIGGERED")),
            ("future-evidence", lambda s,e,o: e["rows"][0].update(feature_availability_class="LIVE_PIT")),
            ("synthetic-to-real", lambda s,e,o: e.update(test_only=False)),
            ("unauthorized-trade", lambda s,e,o: e.update(trading_authority="ENABLED")),
            ("ambiguous-as-win", lambda s,e,o: o[-1].update(directional_metrics={"win":True})),
            ("coverage-missing", lambda s,e,o: o.pop()),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                schedule, envelope, observations = integration_fixture()
                mutate(schedule, envelope, observations)
                reseal(envelope)
                with self.assertRaises(LabContractError):
                    build_research_report(schedule, envelope, observations)

    def test_f3_input_tamper_and_idempotence(self):
        schedule, envelope, observations = integration_fixture()
        a = build_research_handoff(schedule, envelope)
        b = build_research_handoff(schedule, copy.deepcopy(envelope))
        self.assertEqual(a, b)
        envelope["rows"][0]["status"] = "NOMINATED"
        with self.assertRaisesRegex(LabContractError, "INPUT_RECEIPT_TAMPER"):
            build_research_handoff(schedule, envelope)
        schedule, envelope, observations = integration_fixture()
        schedule["scheduled_total"] += 1
        with self.assertRaises(LabContractError):
            build_research_report(schedule, envelope, observations)


if __name__ == "__main__":
    unittest.main()
