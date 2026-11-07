"""Core H additive synthetic-only adapter contract tests; never owner E:."""
from copy import deepcopy
import unittest

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_f_recovery_readonly_v1 import (
    EXPECTED_RECOVERY_BYTES_SHA256, EXPECTED_RECOVERY_INTERNAL_SHA256,
    SCHEMA as SOURCE_SCHEMA,
)
from research_wp_r0.aql_core_h_portable_query_v1 import (
    REQUEST_SCHEMA, SCHEMA, STEP_MS, adapt_verified_recovery_month,
)

MONTH = "2024-01"
START = 1704067200000
DATASET = "BINANCE-SPOT-BTCUSDT-15M-2024-01-F-v1"
SHA_FIELDS = ("source_zip_sha256", "manifest_integrity_sha256",
              "warehouse_receipt_sha256", "core245_native_query_sha256",
              "core253_local_query_sha256", "dual_map_sha256")


def fixture():
    native = []
    local = []
    for i in range(3):
        opened = START + i * STEP_MS
        a = {"bar_open_ms": opened, "bar_close_ms": opened + STEP_MS - 1,
             "checksum": ("%064x" % (i + 1)),
             "observation_lower_bound_ms": opened,
             "historical_known_at_ms": None, "close": "100.00"}
        native.append(a)
        local.append({**a, "bar_checksum": a["checksum"]})
    body = {
        "schema": SOURCE_SCHEMA, "status": "SOURCE_BACKED_RECOVERY_READBACK_ONLY",
        "dataset_id": DATASET, "month": MONTH,
        "start_ms": START, "end_exclusive_ms": START + 3 * STEP_MS,
        "decision_cutoff_ms": START + 4 * STEP_MS,
        "bar_count": 3, "opaque_recovery_file_pin_verified": True,
        "recovery_internal_canonical_recomputed": False,
        "recovery_file_sha256": EXPECTED_RECOVERY_INTERNAL_SHA256,
        "recovery_raw_bytes_sha256": EXPECTED_RECOVERY_BYTES_SHA256,
        "historical_pit": "NOT_ATTESTED", "trading_authority": "NONE",
        "source_ack_sha256": None, "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        **{k: str(i + 1) * 64 for i, k in enumerate(SHA_FIELDS)},
    }
    return {"receipt": {**body, "receipt_sha256": digest(body)},
            "native_bars": native, "local_bars": local}


def request(*, start=START, end=START + 3 * STEP_MS,
            cutoff=START + 4 * STEP_MS, complete=True):
    return {"schema": REQUEST_SCHEMA, "month": MONTH, "dataset_id": DATASET,
            "start_ms": start, "end_exclusive_ms": end,
            "decision_cutoff_ms": cutoff, "require_complete": complete}


class PortableResearchQueryTests(unittest.TestCase):
    def test_complete_deterministic_immutable_input(self):
        parent = fixture()
        before = deepcopy(parent)
        a = adapt_verified_recovery_month(parent, request())
        b = adapt_verified_recovery_month(parent, request())
        self.assertEqual(a, b)
        self.assertEqual(parent, before)
        self.assertEqual(a["receipt"]["schema"], SCHEMA)
        self.assertEqual(a["receipt"]["status"], "COMPLETE")
        self.assertEqual(a["receipt"]["available_bar_count"], 3)
        self.assertEqual(a["receipt"]["historical_pit"], "NOT_ATTESTED")
        self.assertIsNone(a["receipt"]["historical_known_at_ms"])
        self.assertEqual(a["receipt"]["trading_authority"], "NONE")
        self.assertEqual(a["receipt"]["source_zip_sha256"],
                         parent["receipt"]["source_zip_sha256"])
        self.assertNotEqual(a["receipt"]["core245_native_query_sha256"],
                            a["receipt"]["core253_local_query_sha256"])

    def test_cutoff_partial_unknown_and_fail_closed(self):
        parent = fixture()
        a = adapt_verified_recovery_month(
            parent, request(cutoff=START + STEP_MS - 1, complete=False))
        self.assertEqual(a["receipt"]["status"], "UNKNOWN")
        self.assertEqual(a["receipt"]["available_bar_count"], 0)
        self.assertEqual(len(a["receipt"]["missing_bar_opens"]), 3)
        b = adapt_verified_recovery_month(
            parent, request(cutoff=START + STEP_MS, complete=False))
        self.assertEqual(b["receipt"]["status"], "PARTIAL")
        self.assertEqual(b["receipt"]["available_bar_count"], 1)
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_OR_FUTURE_RANGE"):
            adapt_verified_recovery_month(
                parent, request(cutoff=START + STEP_MS - 1, complete=True))

    def test_identity_seals_and_parent_mutation_rejected(self):
        for field, bad in [
            ("source_zip_sha256", "f" * 64),
            ("historical_pit", "ATTESTED"),
            ("trading_authority", "LIVE"),
            ("source_ack_sha256", "a" * 64),
            ("opaque_recovery_file_pin_verified", False),
            ("recovery_raw_bytes_sha256", "f" * 64),
            ("recovery_internal_canonical_recomputed", True),
        ]:
            parent = fixture()
            parent["receipt"][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                adapt_verified_recovery_month(parent, request())
        parent = fixture()
        parent["local_bars"][1]["bar_checksum"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "DUAL_BAR_IDENTITY"):
            adapt_verified_recovery_month(parent, request())
        parent = fixture()
        parent["native_bars"][1]["bar_open_ms"] += 1
        with self.assertRaisesRegex(ValueError, "DUAL_BAR_IDENTITY"):
            adapt_verified_recovery_month(parent, request())

    def test_reject_unadmitted_month_unaligned_range_and_bool_cutoff(self):
        with self.assertRaisesRegex(ValueError, "MONTH_NOT_ADMITTED"):
            adapt_verified_recovery_month(
                fixture(), {**request(), "month": "2024-02"})
        with self.assertRaisesRegex(ValueError, "RANGE_GRID_OR_TYPE"):
            adapt_verified_recovery_month(
                fixture(), {**request(), "start_ms": START + 1})
        with self.assertRaisesRegex(ValueError, "RANGE_GRID_OR_TYPE"):
            adapt_verified_recovery_month(
                fixture(), {**request(), "decision_cutoff_ms": True})
        with self.assertRaisesRegex(ValueError, "RANGE_OUTSIDE"):
            adapt_verified_recovery_month(
                fixture(), request(end=START + 4 * STEP_MS))


if __name__ == "__main__":
    unittest.main()
