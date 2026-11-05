import tempfile
import unittest

from research_wp_r0.aql_core_f_bulk_source_v1 import (
    acquire_private_batch, build_coverage_ledger, build_manifest,
    target_months, verify_coverage_ledger, verify_manifest,
)


class TestCoreFBulkSource(unittest.TestCase):
    def test_default_year_census(self):
        m = build_manifest()
        self.assertTrue(verify_manifest(m))
        self.assertEqual(m["month_count"], 12)
        self.assertEqual(m["target_new_months"], 10)
        self.assertEqual(m["expected_bars_total"], 35136)
        self.assertEqual(m["previously_pinned_months"], ["2024-02", "2024-08"])
        self.assertEqual(m["max_new_archive_bytes"], 80_000_000)
        self.assertEqual(m["max_new_checksum_bytes"], 5120)
        self.assertTrue(all(x["original_archive_sha256"] is None for x in m["rows"]))
        self.assertTrue(all(x["independent_publisher_checksum_sha256"] is None for x in m["rows"]))

    def test_explicit_bounds_and_month_grid(self):
        self.assertEqual(target_months("2024-02", "2024-04"),
                         ["2024-02", "2024-03", "2024-04"])
        m = build_manifest(first="2024-02", last="2024-03", max_workers=1)
        self.assertEqual([r["expected_native_15m_bars"] for r in m["rows"]], [2784, 2976])
        for args in [
            {"first": "2023-12"}, {"last": "2025-01"},
            {"first": "2024-12", "last": "2024-01"},
            {"max_workers": 0}, {"max_workers": 5},
            {"private_storage_required": False},
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                build_manifest(**args)

    def test_no_source_has_exact_denominator_and_no_fake_success(self):
        m = build_manifest()
        a = build_coverage_ledger(m)
        self.assertTrue(verify_coverage_ledger(m, a))
        self.assertEqual(a["census"]["MISSING_SOURCE"], 10)
        self.assertEqual(a["census"]["RETAINED_PREVIOUSLY_PINNED"], 2)
        self.assertEqual(a["census"]["ACCEPTED_PREFLIGHT"], 0)
        self.assertEqual(a["source_access"], "REQUIRES_OWNER_AUTHORIZED_PRIVATE_RUNNER")
        self.assertIsNone(a["core_245_native_query_sha256"])
        self.assertIsNone(a["core_253_local_query_sha256"])
        self.assertEqual(a, build_coverage_ledger(m))

    def test_tamper_manifest_and_ledger_denied(self):
        m = build_manifest(first="2024-03", last="2024-04")
        changed = {**m, "rows": [*m["rows"]]}
        changed["rows"][0] = {**changed["rows"][0], "expected_native_15m_bars": 1}
        self.assertFalse(verify_manifest(changed))
        l = build_coverage_ledger(m)
        for key, value in (
            ("source_access", "VERIFIED"),
            ("raw_admission", "COMMITTED"),
            ("secretary_historical_route", "ACKED"),
            ("trading_authority", "LIVE"),
            ("core_245_native_query_sha256", "a" * 64),
        ):
            other = {**l, key: value}
            self.assertFalse(verify_coverage_ledger(m, other))
        other = {**l, "entries": [*l["entries"]]}
        other["entries"][0] = {**other["entries"][0], "status": "ACCEPTED_PREFLIGHT"}
        self.assertFalse(verify_coverage_ledger(m, other))

    def test_retained_not_reacquired(self):
        m = build_manifest(first="2024-02", last="2024-03")
        with self.assertRaises(ValueError):
            build_coverage_ledger(m, {"2024-02": {"status": "ACCEPTED_PREFLIGHT"}})

    def test_private_network_not_allowed_by_default(self):
        m = build_manifest(first="2024-03", last="2024-03")
        with tempfile.TemporaryDirectory() as private:
            with self.assertRaisesRegex(ValueError, "PRIVATE_NETWORK_RIGHTS_PROVENANCE_OPT_IN_REQUIRED"):
                acquire_private_batch(m, private)
            with self.assertRaisesRegex(ValueError, "PRIVATE_NETWORK_RIGHTS_PROVENANCE_OPT_IN_REQUIRED"):
                acquire_private_batch(m, private, allow_network=True)
        self.assertTrue(verify_manifest(m))

    def test_accepted_must_not_claim_raw_or_pit(self):
        m = build_manifest(first="2024-03", last="2024-03")
        receipt = {
            "status": "ACCEPTED_PREFLIGHT",
            "archive_sha256": "a" * 64,
            "checksum_file_sha256": "b" * 64,
            "preflight_receipt_sha256": "c" * 64,
            "observed_bars": 2976,
            "raw_vault": "COMMITTED",
            "warehouse": "NOT_YET_ADMITTED",
            "historical_pit": "NOT_ATTESTED",
        }
        with self.assertRaises(ValueError):
            build_coverage_ledger(m, {"2024-03": receipt})
        receipt["raw_vault"] = "NOT_YET_ADMITTED"
        l = build_coverage_ledger(m, {"2024-03": receipt})
        self.assertTrue(verify_coverage_ledger(m, l))
        self.assertEqual(l["census"]["ACCEPTED_PREFLIGHT"], 1)
        receipt["historical_pit"] = "ATTESTED"
        with self.assertRaises(ValueError):
            build_coverage_ledger(m, {"2024-03": receipt})

    def test_missing_and_quarantined_cannot_claim_parent_hashes(self):
        m = build_manifest(first="2024-03", last="2024-03")
        for status in ("MISSING_SOURCE", "REJECTED_QUARANTINED"):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "NONACCEPTED_SOURCE_HASHES_FORBIDDEN"):
                build_coverage_ledger(m, {"2024-03": {"status": status, "archive_sha256": "f" * 64}})


if __name__ == "__main__":
    unittest.main()
