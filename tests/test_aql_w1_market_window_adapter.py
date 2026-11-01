"""Focused RAW authentication boundary: synthetic fixture is NOT PIT custody."""
import copy
import hashlib
import json
import unittest

from research_wp_r0.aql_w1_market_window_adapter import (
    BAR_MS, authenticated_market_windows,
)
from research_wp_r0.aql_w1_f1_prospective_consumer import (
    project_authenticated_market_f1_slots,
)
from tests.test_aql_w1_f1_core_integration import setup

def sample(asof=72*3600000, bars=288):
    plan, f1, registry = setup()
    cutoff = plan["decision_cutoff_ms"]
    raw_bars = [
        {"open_ms": cutoff + i*BAR_MS, "high": "110", "low": "95",
         "finalized_at_ms": cutoff+(i+1)*BAR_MS,
         "published_at_ms": cutoff+(i+1)*BAR_MS+1}
        for i in range(bars)
    ]
    raw = json.dumps(raw_bars, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    plan = {**plan, "source_id": "source", "source_bytes_sha256": digest}
    f1 = {**f1, "source_bytes_sha256": digest}
    from research_wp_r0.aql_f1_decision_capture_v1 import hash_f1
    f1["f1_record_sha256"] = hash_f1(f1)
    receipt = {
        "source_id": "source", "source_version": plan["source_version"],
        "correction_generation": plan["correction_generation"],
        "source_bytes_sha256": digest, "raw_bytes_sha256": digest,
        "published_at_ms": cutoff+bars*BAR_MS+1,
        "finalized_at_ms": cutoff+bars*BAR_MS,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return plan, f1, registry, raw, receipt

class AuthenticatedMarketTests(unittest.TestCase):
    def make(self, *, proof=None, raw=None, receipt=None, source=None, bars=288, asof=None):
        plan, f1, registry, original, ticket = sample(bars=bars)
        if raw is not None: original = raw
        if receipt is not None:
            ticket.update(receipt)
            ticket["receipt_sha256"] = hashlib.sha256(
                json.dumps({k:v for k,v in ticket.items() if k != "receipt_sha256"},
                           sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        if source is not None: plan["source_version"] = source
        windows, checker = authenticated_market_windows(
            [plan], {plan["pair_id"]: original},
            {plan["pair_id"]: ticket}, verify_receipt=proof, asof_ms=asof)
        return windows, checker, plan, f1, registry, ticket

    def test_complete_4h_24h_72h_and_unverified_original(self):
        windows, checker, plan, f1, registry, _ = self.make(proof=lambda _: True)
        self.assertEqual(len(windows), 3)
        self.assertTrue(all(x["coverage_status"]=="COMPLETE" for x in windows))
        self.assertTrue(all(checker(x) for x in windows))
        result = project_authenticated_market_f1_slots(
            [plan], [f1], raw_by_pair={plan["pair_id"]: sample()[3]},
            receipt_by_pair={plan["pair_id"]: sample()[4]},
            indicator_registry=registry, verify_raw_receipt=lambda _: True)
        self.assertEqual(result["arm_slots"], 2)
        self.assertEqual(result["outcome_rows"], 6)
        self.assertEqual(result["capture_status_counts"],
                         {"UNVERIFIED": 1, "MISSING_CAPTURE": 1})
        self.assertTrue(all(x["max_favorable"] is None for x in result["outcomes"]))
        self.assertFalse(result["operational_pit_and_custody_proven"])

    def test_raw_bytes_tamper_fails_closed(self):
        windows, checker, *_ = self.make(proof=lambda _: True, raw=b"[]")
        self.assertEqual(windows, [])
        self.assertFalse(checker({}))

    def test_late_receipt_publication_untrusted(self):
        _, _, plan, _, _, ticket = self.make(proof=lambda _: True)
        # An external receipt authority that refuses late publication must
        # determine truth; a self-declared timestamp cannot create authority.
        windows, checker, *_ = self.make(
            proof=lambda receipt: receipt["published_at_ms"] <= plan["decision_cutoff_ms"])
        self.assertEqual(windows, [])
        self.assertFalse(checker({}))

    def test_source_vintage_drift_fails_closed(self):
        windows, checker, *_ = self.make(proof=lambda _: True, source="other-version")
        self.assertEqual(windows, [])
        self.assertFalse(checker({}))

    def test_missing_bars_not_authenticated_complete(self):
        windows, checker, *_ = self.make(proof=lambda _: True, bars=12)
        self.assertEqual(len(windows), 3)
        self.assertEqual([x["coverage_status"] for x in windows],
                         ["MISSING_DATA"]*3)
        self.assertTrue(all(not checker(x) for x in windows))

    def test_censored_asof_retained(self):
        plan, f1, registry, raw, receipt = sample()
        asof = plan["decision_cutoff_ms"] + 4*3600000 + 100
        windows, checker = authenticated_market_windows(
            [plan], {plan["pair_id"]: raw}, {plan["pair_id"]: receipt},
            verify_receipt=lambda _: True, asof_ms=asof)
        self.assertEqual(len(windows), 3)
        self.assertEqual(windows[2]["coverage_status"], "ARCHIVE_END_CENSORED")
        self.assertFalse(checker(windows[2]))

    def test_no_receipt_verifier_never_authenticated(self):
        windows, checker, *_ = self.make()
        self.assertEqual(windows, [])
        self.assertFalse(checker({}))

    def test_mutated_window_not_reauthenticated(self):
        windows, checker, *_ = self.make(proof=lambda _: True)
        altered = copy.deepcopy(windows[0])
        altered["high"] = "9999"
        self.assertFalse(checker(altered))

    def test_post_verification_inplace_mutation_is_not_authenticated(self):
        windows, checker, *_ = self.make(proof=lambda _: True)
        self.assertTrue(checker(windows[0]))
        windows[0]["high"] = "9999"
        self.assertFalse(checker(windows[0]))

    def test_tampered_receipt_payload_without_rehash_is_rejected(self):
        windows, checker, *_ = self.make(proof=lambda _: True,
                                          receipt={"published_at_ms": 999999999})
        self.assertEqual(windows, [])
        self.assertFalse(checker({}))

    def test_same_candle_tp_sl_unknown_independent(self):
        plan, f1, registry, raw, receipt = sample()
        windows, _ = authenticated_market_windows(
            [plan], {plan["pair_id"]: raw}, {plan["pair_id"]: receipt},
            verify_receipt=lambda _: True)
        self.assertTrue(all(x["tp_sl_first_hit"]=="UNKNOWN" for x in windows))

if __name__ == "__main__":
    unittest.main()
