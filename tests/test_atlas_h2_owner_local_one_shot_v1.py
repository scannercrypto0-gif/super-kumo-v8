"""H2 owner-local operator negative gate tests. Synthetic files only; no E:."""
from __future__ import annotations
import copy
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_h2_owner_local_one_shot_v1 import (
    SCHEMA, PINS, Stop, boundaries, canonical, digest, execute,
    fingerprint, native_receipt_check, verify_owner,
)


def scope(root):
    return {
        "single_use": True,
        "explicit_readonly_no_export": True,
        "source_rights_attested": True,
        "research_class": "RETROSPECTIVE_NON_PIT",
        "publisher_pit_attested": False,
        "owner_cost_authorized": True,
        "exact_heads": PINS.copy(),
        "start_ms": 0,
        "end_exclusive_ms": 4 * 900000,
        "decision_cutoff_ms": 4 * 900000,
        "dataset_id": "BINANCE-SPOT-BTCUSDT-15M-2024-03-F-v1",
        "version": 1,
        "strategy_id": "h_manual_distinct_test",
        "strategy_definition_sha256": "a" * 64,
        "source_bytes_sha256": "b" * 64,
        "manifest_integrity_sha256": "c" * 64,
        "native_receipt_sha256": "d" * 64,
        "native_receipt_file": str(root / "native.json"),
        "strategy_definition_file": str(root / "strategy.json"),
        "warehouse_root": str(root / "warehouse"),
        "vault_root": str(root / "vault"),
        "results_sqlite": str(root / "output" / "results.sqlite"),
        "secretary_root": str(root / "output" / "secretary"),
        "evidence_json": str(root / "output" / "audit.json"),
        "experiment_id": "RESEARCH-H-GENERIC-OWNER-TEST",
        "factory_code_sha256": "e" * 64,
        "costs": {
            "fee_entry_bps": "1", "fee_exit_bps": "1",
            "spread_entry_bps": "1", "spread_exit_bps": "1",
            "slippage_entry_bps": "1", "slippage_exit_bps": "1",
            "funding_bps_per_bar": "0",
        },
    }


def signed(s, key=b"k" * 32):
    return {
        "schema": SCHEMA, "scope": s,
        "owner_approval_mac": hmac.new(
            key, canonical({"schema": SCHEMA, "scope": s}),
            hashlib.sha256).hexdigest(),
    }


class H2Operator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key = self.root / "private-owner-key"
        self.key.write_bytes(b"k" * 32)
        for name in ("vault", "warehouse", "output"):
            (self.root / name).mkdir()

    def verify(self, s):
        return verify_owner(signed(s), self.key)

    def test_default_does_not_touch_source(self):
        with patch("pathlib.Path.open", side_effect=AssertionError("IO")):
            r = execute({}, allow_local_run=False)
        self.assertEqual(r["status"], "WAIT_SOURCE_PERMISSION")
        self.assertEqual(r["f5"], "BLOCKED_EXTERNAL_INPUT")

    def test_missing_verifier_key_fails_without_source(self):
        r = execute(signed(scope(self.root)), repo=self.root,
                    allow_local_run=True)
        self.assertEqual(r["status"], "WAIT_SOURCE_PERMISSION")

    def test_authentication_tamper_is_denied(self):
        m = signed(scope(self.root))
        m["scope"]["dataset_id"] += "-tamper"
        with self.assertRaises(Stop):
            verify_owner(m, self.key)

    def test_fake_permission_or_pit_refused(self):
        for name, value in [
            ("explicit_readonly_no_export", False),
            ("source_rights_attested", False),
            ("publisher_pit_attested", True),
            ("owner_cost_authorized", False),
            ("single_use", False),
        ]:
            s = scope(self.root)
            s[name] = value
            with self.subTest(name=name), self.assertRaises(Stop):
                self.verify(s)

    def test_zero_cost_unbounded_and_stale_sha_refused(self):
        variants = []
        a = scope(self.root)
        a["costs"] = {k: "0" for k in a["costs"]}
        variants.append(a)
        b = scope(self.root)
        b["end_exclusive_ms"] = 900000 * 5000
        variants.append(b)
        c = scope(self.root)
        c["exact_heads"]["factory"] = "f" * 40
        variants.append(c)
        d = scope(self.root)
        d["costs"]["fee_entry_bps"] = "NaN"
        variants.append(d)
        for item in variants:
            with self.assertRaises(Stop):
                self.verify(item)

    def test_output_not_inside_raw_or_warehouse(self):
        s = scope(self.root)
        s["results_sqlite"] = str(self.root / "warehouse" / "bad.sqlite")
        with self.assertRaises(Stop):
            boundaries(s, self.key, self.root / "repo")

    def test_pending_wal_fails_closed(self):
        (self.root / "warehouse" / "warehouse.sqlite-wal").write_bytes(b"x")
        with self.assertRaises(Stop):
            fingerprint(self.root / "warehouse")

    def test_native_receipt_cannot_claim_complete_without_source(self):
        s = scope(self.root)
        native = {"schema": "aql.core.historical-price-custody-query.v1",
                  "status": "OK", "coverage": "COMPLETE",
                  "required_bar_count": 4, "available_bar_count": 3,
                  "missing_bar_opens": [2700000]}
        native["price_query_sha256"] = digest(native)
        (self.root / "native.json").write_text(json.dumps(native))
        with self.assertRaises(Stop):
            native_receipt_check(s, native)

    def test_receipt_chain_sanitized_and_sealed(self):
        r = execute({}, allow_local_run=False)
        self.assertEqual(r["sha256"],
                         digest({k: v for k, v in r.items() if k != "sha256"}))
        self.assertNotIn(str(self.root), json.dumps(r))


if __name__ == "__main__":
    unittest.main()
