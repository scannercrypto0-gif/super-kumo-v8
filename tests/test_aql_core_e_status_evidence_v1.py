import unittest

from research_wp_r0.aql_core_e_historical_boundary_v1 import (
    BLOCKED, preflight_historical_source,
)
from research_wp_r0.aql_core_e_status_evidence_v1 import (
    CUSTODY_ONLY, WAIT, make_core_e_status, verify_core_e_status,
)


class CoreEStatusTests(unittest.TestCase):
    def setUp(self):
        self.p = preflight_historical_source(
            zip_path=None, publisher_checksum_sha256=None,
            dataset_id="BTCUSDT-2024-03", source_kind="ORIGINAL_PUBLISHER")

    def test_missing_source_is_sealed_and_unknown_hashes_null(self):
        r = make_core_e_status(preflight_receipt=self.p)
        self.assertEqual(r["status"], WAIT)
        self.assertEqual(r["source_sha256"], None)
        self.assertIsNone(r["warehouse_receipt_sha256"])
        self.assertIsNone(r["core_245_native_price_query_sha256"])
        self.assertIsNone(r["core_253_local_query_sha256"])
        self.assertEqual(r["trading_authority"], "NONE")
        self.assertEqual(r["historical_pit"], "NOT_ATTESTED")
        self.assertTrue(verify_core_e_status(r, self.p))

    def test_exact_replay_and_mutation_denied(self):
        a = make_core_e_status(preflight_receipt=self.p)
        b = make_core_e_status(preflight_receipt=self.p)
        self.assertEqual(a, b)
        for key, value in (("status", "HISTORICAL_READY"),
                           ("historical_policy_approval", "APPROVED"),
                           ("secretary_historical_route", "ACKED"),
                           ("trading_authority", "LIVE"),
                           ("source_sha256", "a" * 64)):
            other = dict(a)
            other[key] = value
            self.assertFalse(verify_core_e_status(other, self.p))

    def test_forged_input_denied(self):
        d = dict(self.p)
        d["dataset_id"] = "MALICIOUS-SOURCE"
        with self.assertRaises(ValueError):
            make_core_e_status(preflight_receipt=d)

    def test_denies_unverified_warehouse_or_policy(self):
        for kwargs in ({"warehouse_receipt": {}},
                       {"native_query": {}},
                       {"local_query": {}},
                       {"source_authentication": "INDEPENDENTLY_VERIFIED"},
                       {"historical_policy": "APPROVED"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                make_core_e_status(preflight_receipt=self.p, **kwargs)

    def test_denies_malformed_preflight(self):
        for value in (None, {}, [], {"schema": "bad"}, 123):
            with self.subTest(value=value), self.assertRaises(ValueError):
                make_core_e_status(preflight_receipt=value)


if __name__ == "__main__":
    unittest.main()
