"""Focused fail-closed Factory #238 tests. No original source or trading."""
import copy
import unittest

from research_wp_r0.aql_factory_authentic_research_admission import (
    ResearchAdmissionError, assess_research_admission, seal,
)


def fixture():
    return {
        "schema": "aql.factory.authentic-research-admission.v1",
        "execution_authority": "NONE", "paper_live": False,
        "holdout": "SEALED_UNOPENED", "source_kind": "TEST_ONLY",
        "source_bytes_sha256": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "dataset_version_sha256": "c" * 64,
        "plan_digest": "d" * 64,
        "dataset_id": "TEST_ONLY", "strategy_id": "F006",
        "strategy_version": "1", "strategy_definition_digest": "e" * 64,
        "decision_cutoff_ms": 1000, "availability": "SYNTHETIC_TEST",
        "expected_attempts": 3,
        "attempts": [
            dict(attempt_id="a1", strategy_id="F006", strategy_version="1",
                 plan_digest="d"*64, decision_cutoff_ms=1000,
                 feature_available_ms=900, state="PROPOSED",
                 duplicate_of=None, result=None, holdout_access=False),
            dict(attempt_id="a2", strategy_id="F006", strategy_version="1",
                 plan_digest="d"*64, decision_cutoff_ms=1000,
                 feature_available_ms=None, state="INVALID",
                 duplicate_of=None, result=None, holdout_access=False),
            dict(attempt_id="a3", strategy_id="F006", strategy_version="1",
                 plan_digest="d"*64, decision_cutoff_ms=1000,
                 feature_available_ms=None, state="DUPLICATE",
                 duplicate_of="a1", result=None, holdout_access=False),
        ],
    }


class TestAuthenticResearchAdmission(unittest.TestCase):
    def test_repeatability_and_no_scientific_promotion(self):
        source = fixture()
        original = copy.deepcopy(source)
        a = assess_research_admission(seal(source))
        b = assess_research_admission(seal(source))
        self.assertEqual(a, b)
        self.assertEqual(source, original)
        self.assertEqual(a["attempt_count"], 3)
        self.assertEqual(a["attempt_states"]["DUPLICATE"], 1)
        self.assertEqual(a["scientific_result"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(a["strategy_rule_trigger_evaluation"], "NOT_PERFORMED")
        self.assertFalse(a["pit_verified"])

    def test_original_digest_never_grants_authentic_status(self):
        source = fixture()
        source["source_kind"] = "ORIGINAL_UNVERIFIED"
        source["availability"] = "RETROSPECTIVE_NON_PIT"
        result = assess_research_admission(seal(source))
        self.assertEqual(result["admission"], "AUTHENTIC_SOURCE_NOT_CONNECTED")
        self.assertFalse(result["source_original_bytes_verified"])

    def test_negative_matrix(self):
        changes = [
            lambda p: p.update(expected_attempts=2),
            lambda p: p["attempts"].append(copy.deepcopy(p["attempts"][0])),
            lambda p: p["attempts"][0].update(feature_available_ms=1001),
            lambda p: p["attempts"][0].update(result={"return": 0}),
            lambda p: p["attempts"][0].update(holdout_access=True),
            lambda p: p["attempts"][2].update(duplicate_of="a3"),
            lambda p: p["attempts"][2].update(duplicate_of="missing"),
            lambda p: p["attempts"][2].update(duplicate_of=None),
            lambda p: p["attempts"][1].update(strategy_version="2"),
            lambda p: p["attempts"][1].update(plan_digest="f"*64),
            lambda p: p.update(holdout="OPEN"),
            lambda p: p.update(execution_authority="PAPER"),
            lambda p: p.update(source_kind="AUTHENTIC_VERIFIED"),
            lambda p: p.update(availability="CONFIRMED_PIT"),
            lambda p: p.update(source_bytes_sha256="not-a-digest"),
            lambda p: p["attempts"][0].update(state="WIN"),
            lambda p: p["attempts"][0].update(decision_cutoff_ms=999),
            lambda p: p["attempts"][0].update(feature_available_ms=True),
        ]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                p = fixture()
                change(p)
                with self.assertRaises(ResearchAdmissionError):
                    assess_research_admission(seal(p))

    def test_seal_tampering(self):
        packet = seal(fixture())
        packet["attempts"][0]["state"] = "FAILED"
        with self.assertRaises(ResearchAdmissionError):
            assess_research_admission(packet)


if __name__ == "__main__":
    unittest.main()
