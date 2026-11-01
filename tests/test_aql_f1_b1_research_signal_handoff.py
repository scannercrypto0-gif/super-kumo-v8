"""B1 changed-path tests against Core F1 host and historical F3 boundary."""
import copy
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError, digest, hash_f1
from research_wp_r0.aql_f1_prospective_host_v1 import run_prospective_host
from research_wp_r0.aql_f1_research_signal_handoff_v1 import project_original_signal_handoffs
from tests.test_aql_f1_decision_capture_v1 import fixture
from tests.test_aql_f1_prospective_bridge import envelope


def _schedule(rec):
    return dict(pair_id=rec["pair_id"], c2_identity=copy.deepcopy(rec["c2_identity"]),
        experiment_plan_sha256=rec["experiment_plan_sha256"],
        source_version=rec["source_version"], source_bytes_sha256=rec["source_bytes_sha256"],
        correction_generation=rec["correction_generation"],
        decision_cutoff_ms=rec["decision_cutoff_ms"])


def _long_candidate():
    rec, registry = fixture("BASE", state="ARMED", direction="LONG", eligible="YES")
    rec["strategy_id"] = "SF_BREAKOUT_BASE_20_10_DEV_v1"
    for key, price in (("tp", "110"), ("sl", "90")):
        rec[key] = dict(status="DEFINED_PREDECISION", level=price, unit="USDT",
            basis="ABSOLUTE", reference_price_kind="bar-close",
            defined_at_ms=rec["decision_cutoff_ms"], tick_size="0.01",
            decimal_scale=2, rounding_mode="HALF_EVEN")
    rec["f1_record_sha256"] = hash_f1(rec)
    return rec, registry


class B1SignalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.base, self.registry = _long_candidate()
        self.shadow, _ = fixture("SHADOW")
        self.c2 = envelope(self.base)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def host(self, records=None, *, c2=None, directory=None, **kwargs):
        return run_prospective_host(
            c2 or self.c2,
            self.base["experiment_plan_sha256"],
            {"BASE": self.base, "SHADOW": self.shadow} if records is None else records,
            self.registry, Path(directory or self.tmp.name),
            pre_f3_gate=lambda _: True, **kwargs)

    def project(self, handoffs, captures, plans=None, **kw):
        return project_original_signal_handoffs(
            plans or [_schedule(self.base)], handoffs, captures, self.registry, **kw)

    def test_real_strategy_candidate_metadata_but_no_signed_provenance(self):
        handoff = self.host()
        result = self.project([handoff], [self.base, self.shadow])
        self.assertEqual(result["arm_denominator"], 2)
        self.assertEqual([r["capture_status"] for r in result["signal_rows"]],
                         ["UNVERIFIED", "UNVERIFIED"])
        first = next(r for r in result["signal_rows"] if r["arm"] == "BASE")
        self.assertEqual(first["strategy_id"], "SF_BREAKOUT_BASE_20_10_DEV_v1")
        self.assertEqual(first["claimed_candidate_unverified"], {
            "signal_state": "ARMED", "direction": "LONG",
            "entry_reference_price": "100", "target_price": "110", "stop_price": "90"})
        self.assertIsNone(first["research_direction"])
        self.assertIsNone(first["research_target_price"])
        self.assertIsNone(first["research_stop_price"])
        self.assertFalse(first["directional_outcomes_allowed"])
        self.assertFalse(result["original_vendor_clock_custody_freeze_anchor_proven"])

    def test_two_scheduled_pairs_keep_four_arm_rows(self):
        first = self.host()
        second_base = copy.deepcopy(self.base)
        second_shadow = copy.deepcopy(self.shadow)
        for row in (second_base, second_shadow):
            row["c2_identity"]["opportunity_id"] = "other-opp"
            row["opportunity_id"] = "other-opp"
            row["pair_id"] = digest({
                "experiment_plan_sha256": row["experiment_plan_sha256"],
                "c2_identity": row["c2_identity"]})
            row["f1_record_sha256"] = hash_f1(row)
        other = self.host({"BASE": second_base, "SHADOW": second_shadow},
                          c2=envelope(second_base),
                          directory=Path(self.tmp.name) / "other")
        projection = self.project([first, other], [self.base, self.shadow,
                             second_base, second_shadow],
                             plans=[_schedule(self.base), _schedule(second_base)])
        self.assertEqual(projection["scheduled_pairs"], 2)
        self.assertEqual(projection["arm_denominator"], 4)
        self.assertTrue(all(row["research_direction"] is None
                            for row in projection["signal_rows"]))

    def test_missing_shadow_preserves_denominator(self):
        h = self.host({"BASE": self.base, "SHADOW": None})
        p = self.project([h], [self.base])
        self.assertEqual([x["capture_status"] for x in p["signal_rows"]],
                         ["UNVERIFIED", "MISSING_CAPTURE"])

    def test_changed_vintage_quarantined_even_with_valid_f1_digest(self):
        changed = copy.deepcopy(self.base)
        changed["source_version"] = "changed-vintage"
        changed["f1_record_sha256"] = hash_f1(changed)
        h = self.host({"BASE": changed, "SHADOW": self.shadow})
        p = self.project([h], [changed, self.shadow])
        self.assertEqual(p["signal_rows"][0]["capture_status"], "QUARANTINED")
        self.assertEqual(p["signal_rows"][0]["reason_code"],
                         "PREREGISTERED_SOURCE_CUTOFF_MISMATCH")

    def test_tampered_handoff_hash_rejected(self):
        h = self.host()
        h["slots"][0]["capture_status"] = "RECORDED"
        with self.assertRaisesRegex(CaptureError, "HOST_HANDOFF_DIGEST"):
            self.project([h], [self.base, self.shadow])

    def test_duplicate_scheduled_identity_rejected(self):
        h = self.host()
        with self.assertRaisesRegex(CaptureError, "DUPLICATE_SCHEDULE"):
            self.project([h], [self.base, self.shadow],
                         plans=[_schedule(self.base), _schedule(self.base)])

    def test_untrusted_proof_callback_never_promotes_unverified_host(self):
        h = self.host()
        p = self.project([h], [self.base, self.shadow],
                         independent_proof_verifier=lambda _: True)
        self.assertTrue(all(x["capture_status"] == "UNVERIFIED"
                            for x in p["signal_rows"]))
        self.assertTrue(all(not x["directional_outcomes_allowed"]
                            for x in p["signal_rows"]))

    def test_actual_p0_f3_not_prospective(self):
        from research_wp_r0.aql_p0_c2_producer import produce_envelopes
        from research_wp_r0.aql_p0_f3_fill_model import model_fills
        import inspect
        self.assertIn("RETROSPECTIVE_NON_PIT", inspect.getsource(produce_envelopes))
        self.assertNotIn("capture_then_call_f3", inspect.getsource(model_fills))
        # Historical source is rejected by original host, not silently upgraded.
        c2 = envelope(self.base, "RETROSPECTIVE_NON_PIT")
        with self.assertRaisesRegex(CaptureError, "HISTORICAL"):
            self.host(c2=c2)


if __name__ == "__main__":
    unittest.main()
