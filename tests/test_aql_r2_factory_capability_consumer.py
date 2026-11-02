"""R2 Factory capability-only negative boundary; no synthetic G2 event."""
import hashlib
import json
import unittest

from research_wp_r0.aql_r2_factory_capability_consumer import consume_capability

BASE = {
    "schema_version": "aql.r2-original-decision-ingress.v1",
    "connection_status": "NOT_CONNECTED",
    "proof_status": "BLOCKED_EXTERNAL_EVIDENCE",
    "reason_code": "ORIGINAL_G2_PRODUCER_NOT_CONNECTED",
    "opportunity_id": "NOT_CONNECTED_NO_REAL_G2_EVENT",
    "arm_statuses": {"BASE": "MISSING_CAPTURE", "SHADOW": "MISSING_CAPTURE"},
}


def encoded(doc):
    return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode()


class FactoryR2CapabilityTests(unittest.TestCase):
    def check(self, doc):
        return consume_capability(encoded(doc), enforce_core_pin=False)

    def test_disconnected_has_zero_real_denominator_and_no_outcomes(self):
        result = self.check(BASE)
        self.assertEqual(result["scheduled_opportunity_count"], 0)
        self.assertEqual(result["scheduled_denominator_status"], "NOT_SUPPLIED")
        self.assertEqual(result["original_g2_event_count"], 0)
        self.assertEqual(result["outcome_rows_4h_24h_72h"], {"4h": 0, "24h": 0, "72h": 0})
        self.assertEqual(result["f3_monitor_status"], "NOT_CONNECTED")
        for key in ("directional_mfe_mae", "tp_sl", "fills_pnl", "paired_uplift"):
            self.assertIsNone(result[key])

    def test_replay_deterministic(self):
        self.assertEqual(self.check(BASE), self.check(BASE))

    def test_pin_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA_DRIFT"):
            consume_capability(encoded(BASE))

    def test_duplicate_json_key_rejected(self):
        raw = encoded(BASE).rstrip(b"\n")[:-1] + b',"connection_status":"NOT_CONNECTED"}'
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            consume_capability(raw, enforce_core_pin=False)

    def test_forged_event_or_pair_rejected(self):
        for field, value in (("pair_id", "forged"), ("handoff_sha256", "0" * 64),
                             ("direction", "LONG"), ("decision_status", "TRIGGERED")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "FORGED_EVENT"):
                self.check(dict(BASE, **{field: value}))

    def test_sentinel_not_scheduled_opportunity(self):
        with self.assertRaisesRegex(ValueError, "FAKE_SCHEDULE"):
            self.check(dict(BASE, opportunity_id="real-opportunity-1"))

    def test_missing_arm_rejected(self):
        with self.assertRaisesRegex(ValueError, "FAKE_SCHEDULE_OR_ARM"):
            self.check(dict(BASE, arm_statuses={"BASE": "MISSING_CAPTURE"}))

    def test_false_connected_claim_rejected(self):
        with self.assertRaisesRegex(ValueError, "SCHEMA_OR_CONNECTION"):
            self.check(dict(BASE, connection_status="ORIGINAL_EVENTS_RECEIVED"))

    def test_false_proof_rejected(self):
        with self.assertRaisesRegex(ValueError, "FALSE_PROOF"):
            self.check(dict(BASE, proof_status="INDEPENDENT_PROOF_REPORTED_BY_HOST"))

    def test_nonfinite_rejected(self):
        raw = encoded(BASE).rstrip(b"\n")[:-1] + b',"extra":NaN}'
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            consume_capability(raw, enforce_core_pin=False)


if __name__ == "__main__":
    unittest.main()
