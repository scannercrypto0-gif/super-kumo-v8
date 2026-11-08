"""H2 owner-local operator negative gate tests. Synthetic files only; no E:."""
from __future__ import annotations
import copy
import hashlib
import hmac
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_h2_owner_local_one_shot_v1 import (
    SCHEMA, PINS, Stop, boundaries, canonical, digest, execute,
    fingerprint, native_receipt_check, isolated_overlay, sha_file, verify_owner,
    verified_local_sqlite_snapshot,
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
        "month": "2024-03",
        "start_ms": 1709251200000,
        "end_exclusive_ms": 1709251200000 + 4 * 900000,
        "decision_cutoff_ms": 1709251200000 + 4 * 900000,
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
            "fee_entry_bps": "10", "fee_exit_bps": "10",
            "spread_entry_bps": "2", "spread_exit_bps": "2",
            "slippage_entry_bps": "3", "slippage_exit_bps": "3",
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
        b["end_exclusive_ms"] = b["start_ms"] + 900000 * 5000
        variants.append(b)
        c = scope(self.root)
        c["exact_heads"]["factory"] = "f" * 40
        variants.append(c)
        d = scope(self.root)
        d["costs"]["fee_entry_bps"] = "NaN"
        variants.append(d)
        e = scope(self.root)
        e["costs"]["fee_entry_bps"] = "9"
        variants.append(e)
        for item in variants:
            with self.assertRaises(Stop):
                self.verify(item)

    def test_output_not_inside_raw_or_warehouse(self):
        s = scope(self.root)
        s["results_sqlite"] = str(self.root / "warehouse" / "bad.sqlite")
        with self.assertRaises(Stop):
            boundaries(s, self.key, self.root / "repo")

    def test_idle_shm_zero_wal_allows_readonly_isolated_snapshot(self):
        original = self.root / "warehouse"
        db = original / "warehouse.sqlite"
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE t(x INTEGER)")
            conn.execute("INSERT INTO t VALUES (7)")
            conn.commit()
        finally:
            conn.close()
        (original / "stage").mkdir()
        (original / "stage" / "retained.json").write_text('{"ok":true}')
        (original / "warehouse.sqlite-wal").write_bytes(b"")
        (original / "warehouse.sqlite-shm").write_bytes(b"\\0" * 32768)
        before = fingerprint(original)
        temp = self.root / "overlay-snapshot-test"
        temp.mkdir()
        snapshot = verified_local_sqlite_snapshot(original, temp)
        read = sqlite3.connect((snapshot / "warehouse.sqlite").as_uri()
                               + "?mode=ro&immutable=1", uri=True)
        try:
            self.assertEqual(read.execute("SELECT x FROM t").fetchone(), (7,))
        finally:
            read.close()  # SQLite context manager does not close on Windows.
        self.assertEqual((snapshot / "stage" / "retained.json").read_text(),
                         '{"ok":true}')
        self.assertEqual(fingerprint(original), before)
        self.assertFalse((snapshot / "warehouse.sqlite-shm").exists())

    def test_durable_source_mutation_changes_fingerprint(self):
        durable = self.root / "warehouse" / "archive.json"
        durable.write_text('{"v":1}')
        before = fingerprint(self.root / "warehouse")
        durable.write_text('{"v":2}')
        self.assertNotEqual(before, fingerprint(self.root / "warehouse"))

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

    def test_exact_archive_isolation_with_local_synthetic_commit(self):
        repo = self.root / "synthetic-git"
        repo.mkdir()
        paths = (
            "tools/scanner_strategy_f/research_strategy_plugin.py",
            "research_wp_r0/aql_core_backbone_local_v1.py",
            "research_wp_r0/aql_factory_h_generic_signal_adapter_v1.py",
            "research_wp_r0/aql_core_h_research_secretary_v1.py",
            "tools/atlas_h_generic_secretary_bridge.py",
        )
        for name in paths:
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("VALUE = 1\\n", encoding="utf-8")
        commands = [
            ["git", "init", "-q"],
            ["git", "add", "."],
            ["git", "-c", "user.name=atlas-test", "-c",
             "user.email=atlas-test@example.invalid", "commit", "-qm", "fixture"],
        ]
        for cmd in commands:
            subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        overlay = self.root / "overlay"
        with patch.dict(PINS, {k: sha for k in PINS}):
            token = isolated_overlay(repo, overlay)
        self.assertEqual(len(token), 64)
        for name in paths:
            self.assertTrue((overlay / name).exists())

    def test_valid_native_range_receipt_is_verified_without_pit_claim(self):
        s = scope(self.root)
        rows = [{"bar_open_ms": s["start_ms"] + i * 900000,
                 "bar_close_ms": s["start_ms"] + (i + 1) * 900000 - 1}
                for i in range(4)]
        native = {
            "schema": "aql.core.historical-price-custody-query.v1",
            "status": "OK",
            "coverage": "COMPLETE",
            "dataset_id": s["dataset_id"],
            "version": s["version"],
            "source_bytes_sha256": s["source_bytes_sha256"],
            "manifest_integrity_sha256": s["manifest_integrity_sha256"],
            "decision_cutoff_ms": s["decision_cutoff_ms"],
            "required_bar_count": 4,
            "available_bar_count": 4,
            "missing_bar_opens": [],
            "bars": rows,
        }
        native["price_query_sha256"] = digest(native)
        f = self.root / "native.json"
        f.write_text(json.dumps(native), encoding="utf-8")
        s["native_receipt_sha256"] = sha_file(f)
        self.assertEqual(native_receipt_check(s, native),
                         native["price_query_sha256"])

    def test_receipt_chain_sanitized_and_sealed(self):
        r = execute({}, allow_local_run=False)
        self.assertEqual(r["sha256"],
                         digest({k: v for k, v in r.items() if k != "sha256"}))
        self.assertNotIn(str(self.root), json.dumps(r))


if __name__ == "__main__":
    unittest.main()
