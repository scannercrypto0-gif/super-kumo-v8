"""R2 delta-only negatives: no fabricated original strategy decisions."""
import copy
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError
from research_wp_r0.aql_r2_original_decision_ingress import capture_original_g2_pair
from tests.test_aql_f1_decision_capture_v1 import fixture
from tests.test_aql_f1_prospective_bridge import envelope


class R2OriginalIngressTests(unittest.TestCase):
    def setUp(self):
        self.base, self.registry = fixture()
        self.shadow, _ = fixture("SHADOW")
        self.c2 = envelope(self.base)
        self.plan = self.base["experiment_plan_sha256"]
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)

    def call(self, producer=None, gate=lambda _: True):
        return capture_original_g2_pair(
            c2=self.c2, plan_sha=self.plan, producer=producer,
            registry=self.registry, journal_dir=self.path,
            pre_f3_gate=gate)

    def event(self, arm, record):
        return {
            "opportunity_id": self.c2["opportunity_id"],
            "arm": arm, "decision_status": "REJECTED",
            "strategy_id": record["strategy_id"],
            "strategy_version": record["arm_strategy_version"],
            "decision_ms": record["decision_ms"],
            "decision_cutoff_ms": record["decision_cutoff_ms"],
            "source_id": record["source_id"],
            "source_version": record["source_version"],
            "correction_generation": record["correction_generation"],
            "feature_snapshot_sha256": "a" * 64,
            "regime_snapshot_sha256": "b" * 64,
            "original_f1_record": record,
        }

    def test_no_producer_is_explicitly_not_connected_without_writes(self):
        result = self.call()
        self.assertEqual(result["connection_status"], "NOT_CONNECTED")
        self.assertEqual(result["proof_status"], "BLOCKED_EXTERNAL_EVIDENCE")
        self.assertEqual(list(self.path.iterdir()), [])

    def test_gate_denied_before_producer(self):
        calls = []
        with self.assertRaisesRegex(CaptureError, "GATE_DENIED"):
            self.call(lambda arm, _: calls.append(arm), gate=lambda _: False)
        self.assertEqual(calls, [])

    def test_no_decision_keeps_both_arms_missing(self):
        result = self.call(lambda arm, _: None)
        self.assertEqual(result["arm_statuses"], {"BASE": "MISSING_CAPTURE", "SHADOW": "MISSING_CAPTURE"})
        self.assertEqual(result["proof_status"], "BLOCKED_EXTERNAL_EVIDENCE")

    def test_missing_original_f1_rejected(self):
        event = self.event("BASE", self.base)
        event["original_f1_record"] = None
        with self.assertRaisesRegex(CaptureError, "ORIGINAL_F1_MISSING"):
            self.call(lambda arm, _: event if arm == "BASE" else None)

    def test_clock_reversal_rejected(self):
        event = self.event("BASE", self.base)
        event["decision_ms"] = event["decision_cutoff_ms"] - 1
        with self.assertRaisesRegex(CaptureError, "CLOCK_REVERSAL"):
            self.call(lambda arm, _: event if arm == "BASE" else None)

    def test_late_source_rejected(self):
        event = self.event("BASE", self.base)
        event["original_f1_record"] = dict(self.base, source_available_at_ms=self.base["decision_cutoff_ms"] + 1)
        with self.assertRaisesRegex(CaptureError, "LATE_SOURCE"):
            self.call(lambda arm, _: event if arm == "BASE" else None)

    def test_strategy_version_drift_rejected(self):
        def producer(arm, _):
            record = self.base if arm == "BASE" else self.shadow
            event = self.event(arm, record)
            if arm == "SHADOW":
                event["strategy_version"] = "different-version"
                event["original_f1_record"] = dict(record, arm_strategy_version="different-version")
            return event
        with self.assertRaisesRegex(CaptureError, "STRATEGY_VERSION_DRIFT"):
            self.call(producer)

    def test_duplicate_event_id_rejected(self):
        def producer(arm, _):
            record = self.base if arm == "BASE" else dict(self.shadow, arm_event_id=self.base["arm_event_id"])
            return self.event(arm, record)
        with self.assertRaisesRegex(CaptureError, "DUPLICATE"):
            self.call(producer)

    def test_trigger_without_direction_rejected(self):
        event = self.event("BASE", self.base)
        event["decision_status"] = "TRIGGERED"
        event["original_f1_record"] = dict(self.base, direction=None)
        with self.assertRaisesRegex(CaptureError, "TRIGGER_WITHOUT"):
            self.call(lambda arm, _: event if arm == "BASE" else None)

    def test_fixture_only_not_claimed_as_original_operational_proof(self):
        # Fixture is for contract verification, not a real G2 producer.
        event = self.event("BASE", self.base)
        result = self.call(lambda arm, _: event if arm == "BASE" else None)
        self.assertEqual(result["proof_status"], "BLOCKED_EXTERNAL_EVIDENCE")
        self.assertEqual(result["arm_statuses"]["SHADOW"], "MISSING_CAPTURE")
        self.assertEqual(result["arm_statuses"]["BASE"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
