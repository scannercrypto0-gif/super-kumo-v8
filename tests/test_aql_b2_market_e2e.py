"""B2 changed-path tests against the exact Core/B1 original Actions artifacts."""
import copy
import json
import os
import unittest
from pathlib import Path

from research_wp_r0.aql_b2_market_e2e import (
    CORE_SHA, B1_ARTIFACT_SHA, HORIZONS, build_report, canonical,
    digest, test_market_window, actual_consumer_projection,
)


class B2PinnedIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpath = Path(os.environ.get("AQL_B2_CORE_JSON", "/tmp/aql-b2-core.json"))
        cls.bpath = Path(os.environ.get("AQL_B2_MARKET_ARTIFACT", "/tmp/aql-b2-originals.zip"))
        if not cls.cpath.is_file() or not cls.bpath.is_file():
            raise unittest.SkipTest("Pinned CI artifacts not supplied")
        cls.cb = cls.cpath.read_bytes()
        cls.bb = cls.bpath.read_bytes()
        assert digest(cls.cb) == CORE_SHA
        assert digest(cls.bb) == B1_ARTIFACT_SHA
        cls.core = json.loads(cls.cb)

    def test_exact_artifact_bounded_replay_deterministic(self):
        a = build_report(self.cb, self.bb)
        b = build_report(self.cb, self.bb)
        self.assertEqual(canonical(a), canonical(b))
        self.assertEqual((a["n"], a["observed_2n"], a["factory_consumer_6n"]), (2, 4, 12))
        self.assertEqual(a["test_market_association_6n"], 12)
        self.assertEqual(a["factory_consumer_captures"], {"UNVERIFIED": 4})
        self.assertEqual(a["interfaces"]["core_F1_to_authenticated_2024_market"], "NOT_CONNECTED")

    def test_raw_core_digest_tamper_rejected(self):
        tampered = self.cb + b" "
        with self.assertRaisesRegex(ValueError, "CORE_PINNED_INPUT_DIGEST_DRIFT"):
            build_report(tampered, self.bb)

    def test_raw_market_zip_digest_tamper_rejected(self):
        tampered = self.bb + b"x"
        with self.assertRaisesRegex(ValueError, "B1_PINNED_ARTIFACT_DIGEST_DRIFT"):
            build_report(self.cb, tampered)

    def test_missing_shadow_keeps_2n_and_6n_with_explicit_missing(self):
        source = copy.deepcopy(self.core)
        victim = source["schedule"][0]["pair_id"]
        source["original_candidates_test_only"] = [
            row for row in source["original_candidates_test_only"]
            if not (row["pair_id"] == victim and row["arm"] == "SHADOW")
        ]
        out = actual_consumer_projection(source)
        self.assertEqual(out["arm_slots"], 4)
        self.assertEqual(out["outcome_rows"], 12)
        missing = [x for x in out["outcomes"] if x["pair_id"] == victim and x["arm"] == "SHADOW"]
        self.assertEqual(len(missing), 3)
        self.assertTrue(all(x["capture_status"] == "MISSING_CAPTURE" for x in missing))

    def test_direct_join_to_2024_rejected(self):
        result = build_report(self.cb, self.bb)
        self.assertEqual(result["historical_direct_join"]["status"],
                         "REJECTED_EXPECTED_SOURCE_AND_TIME_MISMATCH")
        self.assertEqual(result["historical_direct_join"]["original_core_cutoff_ms"], 900000)
        for row in result["test_market_association"]["rows"]:
            self.assertIsNone(row["market_window"]["signed_mfe"])
            self.assertIsNone(row["research_direction"])
            self.assertEqual(row["strategy_result"], "NOT_AUTHORIZED")

    def test_censored_window_not_complete_or_directional(self):
        cutoff = 1707955200000  # fixed deterministic cutoff, not a source clock
        bars = {cutoff: (100, 90, "95", "98")}
        out = test_market_window(bars, cutoff, HORIZONS[-1])
        self.assertEqual(out["coverage_status"], "CENSORED_OR_MISSING")
        self.assertEqual(out["observed_bars"], 1)
        self.assertIsNone(out["signed_mae"])

    def test_core_duplicate_schedule_rejected(self):
        source = copy.deepcopy(self.core)
        source["schedule"][1] = copy.deepcopy(source["schedule"][0])
        with self.assertRaises(Exception):
            actual_consumer_projection(source)

    def test_core_source_vintage_drift_fails_closed(self):
        source = copy.deepcopy(self.core)
        source["schedule"][0]["source_version"] = "DRIFT"
        out = actual_consumer_projection(source)
        affected = [r for r in out["outcomes"] if r["pair_id"] == source["schedule"][0]["pair_id"]]
        self.assertTrue(all(r["capture_status"] == "QUARANTINED" for r in affected))


if __name__ == "__main__":
    unittest.main()
