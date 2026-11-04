"""One focused Scanner B test batch. Synthetic only; NO retained Feb/Aug rerun."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_archive_custody_bridge_v1 import digest as core_digest
from research_wp_r0.aql_core_secretary_routing_v1 import (
    acknowledge_nomination, retry_or_quarantine, route_trace,
)
from tools.scanner_engine_offline.contracts import canonical_bytes, sha256_hex
from tools.strategy_service_offline.common import canonical, Frozen, raw_sha
from tools.strategy_service_offline.run import FIXTURES
from .native15m import native_15m_policy, scan_native15m, safe_wait_for_paper
from .core_secretary import prepare_source_only_route, verify_offline_consumer_ack
from .factory_handoff import prepare_factory_handoff


def seal(obj, key):
    return {**obj, key: core_digest(obj)}


class Native15mGate(unittest.TestCase):
    def setUp(self):
        self.work = json.loads((FIXTURES/"strategies.json").read_text())
        self.policies = [native_15m_policy(w).receipt() for w in self.work]
        self.cutoff = 10 * 900_000
        self.market = "fixture"
        rows = []
        for symbol in ("AAA", "BBB", "CCC"):
            for i in range(10):
                if symbol == "AAA":
                    close = 100+2*i
                elif symbol == "BBB":
                    close = 140-2*i
                else:
                    close = 110+(2 if i % 2 else -2)
                rows.append({
                    "symbol": symbol, "timeframe": "15m", "source_id": "generator",
                    "open_ms": i*900_000, "close_ms": (i+1)*900_000-1,
                    "available_ms": (i+1)*900_000,
                    "finalized": True, "open": close, "high": close+1,
                    "low": close-1, "close": close, "volume": 2,
                })
        self.source = {
            "schema": "aql.strategy-service.synthetic-bars.v1",
            "source_id": "generator", "generation_id": "fixture_v1", "rows": rows,
        }
        self.raw = canonical(self.source)
        self.manifest = {
            "schema": "aql.strategy-service.source.v1", "timeframe": "15m",
            "market": self.market, "source_id": "generator",
            "generation_id": "fixture_v1", "start_ms": 0,
            "end_exclusive_ms": self.cutoff, "cutoff_ms": self.cutoff,
            "evidence_class": "TEST_ONLY", "external_verifier": "NOT_CONNECTED",
            "raw_sha256": raw_sha(self.raw),
        }
        self.universe = {
            "schema": "aql.strategy-service.universe.v1", "count_unit": "SYMBOL",
            "cutoff_ms": self.cutoff, "evidence_class": "TEST_ONLY",
            "source_raw_sha256": self.manifest["raw_sha256"],
            "members": [
                {"symbol": symbol, "eligible": symbol != "EEE",
                 "membership_available_ms": self.cutoff}
                for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE")
            ],
        }

    def run_scan(self):
        return scan_native15m(
            self.policies, self.work, self.raw,
            self.manifest, self.universe,
            cutoff_ms=self.cutoff, symbol_budget=3)

    def reseal_source(self):
        self.raw = canonical(self.source)
        self.manifest["raw_sha256"] = raw_sha(self.raw)
        self.universe["source_raw_sha256"] = self.manifest["raw_sha256"]

    def rows(self):
        return [Frozen.restore(x).data for x in self.run_scan().data["nominations"]]

    def test_all_strategy_symbol_pairs_and_safety(self):
        result = self.run_scan()
        rows = [Frozen.restore(x).data for x in result.data["nominations"]]
        self.assertEqual(len(rows), 10)
        self.assertEqual({(x["strategy_id"], x["symbol"]) for x in rows},
                         {(s, sym) for s in ("test_momentum", "test_reversion")
                          for sym in ("AAA", "BBB", "CCC", "DDD", "EEE")})
        for sid in ("test_momentum", "test_reversion"):
            sub = [x for x in rows if x["strategy_id"] == sid]
            counts = Counter(x["status"] for x in sub)
            self.assertEqual(sum(counts.values()), 5)
            self.assertTrue(all(x["denominator"] == 5 and
                                sum(x["strategy_census"].values()) == 5 for x in sub))
            self.assertEqual(next(x for x in sub if x["symbol"] == "DDD")["status"], "UNSCANNED")
            self.assertEqual(next(x for x in sub if x["symbol"] == "EEE")["status"], "INELIGIBLE")
            self.assertTrue(all(x["timeframe"] == "15m" and
                                x["operational_scanner_status"] == "UNKNOWN" and
                                x["trading_authority"] == "NONE" and
                                x["publishable"] is False and
                                x["delivery_authorized"] is False for x in sub))
        self.assertEqual(result.data["work235_native_15m"], "NOT_CONNECTED_15M_UNSUPPORTED")
        self.assertEqual(result.data["discoverer_dependency"], "OPTIONAL")
        self.assertEqual(result.data["paper_execution"], "NOT_ACTIVATED")

    def test_distinct_strategy_preferences_and_denominator(self):
        rows = self.rows()
        targets = {(x["strategy_id"], x["symbol"]) for x in rows if x["status"] == "SELECTED"}
        self.assertEqual(targets, {("test_momentum", "AAA"), ("test_reversion", "BBB")})
        self.assertEqual(self.run_scan().payload, self.run_scan().payload)

    def test_no_unauthorized_paper_promotion(self):
        result = self.run_scan()
        receipt = next(r for r in result.data["nominations"] if r["payload"]["status"] == "SELECTED")
        spec = next(s for s in self.policies if s["payload"]["strategy_id"] == receipt["payload"]["strategy_id"])
        boundary = safe_wait_for_paper(receipt, spec).data
        self.assertEqual((boundary["decision"], boundary["orders_created"]), ("WAIT", 0))
        wrong = next(s for s in self.policies if s is not spec)
        with self.assertRaisesRegex(ValueError, "STRATEGY_VERSION_CONFIG_MISMATCH"):
            safe_wait_for_paper(receipt, wrong)
        forged = deepcopy(receipt)
        forged["payload"]["delivery_authorized"] = True
        forged = Frozen.build(forged["payload"]).receipt()
        with self.assertRaisesRegex(ValueError, "PAPER_AUTHORITY"):
            safe_wait_for_paper(forged, spec)

    def test_source_sha_tamper_and_missing_bytes_fail_closed(self):
        self.raw += b" "
        self.assertEqual({x["status"] for x in self.rows() if x["symbol"] in ("AAA", "BBB")},
                         {"UNKNOWN"})
        self.raw = b""
        self.assertEqual({x["status"] for x in self.rows() if x["symbol"] in ("AAA", "BBB")},
                         {"UNKNOWN"})

    def test_missing_known_at_no_historical_upgrade(self):
        self.manifest["evidence_class"] = "RETROSPECTIVE_NON_PIT"
        self.universe["evidence_class"] = "RETROSPECTIVE_NON_PIT"
        rows = self.rows()
        self.assertEqual({x["status"] for x in rows if x["symbol"] in ("AAA", "BBB")},
                         {"UNKNOWN"})
        self.assertTrue(all(not x["feature_evidence"] for x in rows))

    def test_gap_duplicates_future_pit_nonfinal_and_wrong_timeframe(self):
        changes = [
            lambda rows: rows.pop(3),
            lambda rows: rows.insert(3, deepcopy(rows[2])),
            lambda rows: rows[0].update(available_ms=None),
            lambda rows: rows[0].update(available_ms=self.cutoff+1),
            lambda rows: rows[0].update(finalized=False),
            lambda rows: rows[0].update(timeframe="5m"),
            lambda rows: rows[0].update(source_id="forged"),
            lambda rows: rows[0].update(open_ms=900_000),
            lambda rows: rows[0].update(high=0),
        ]
        for mutate in changes:
            with self.subTest(mutate=changes.index(mutate)):
                original = deepcopy(self.source)
                mutate(self.source["rows"])
                self.reseal_source()
                by_sym = [x for x in self.rows() if x["symbol"] == "AAA"]
                self.assertTrue(all(x["status"] == "UNKNOWN" for x in by_sym))
                self.source = original
                self.reseal_source()

    def test_cross_strategy_source_config_and_universe_negatives(self):
        broken = deepcopy(self.policies)
        broken[0]["payload"]["config_digest"] = "f"*64
        with self.assertRaisesRegex(ValueError, "FROZEN_DIGEST_DRIFT"):
            scan_native15m(broken, self.work, self.raw,
                           self.manifest, self.universe,
                           cutoff_ms=self.cutoff, symbol_budget=3)
        self.universe["members"].append(deepcopy(self.universe["members"][0]))
        with self.assertRaisesRegex(ValueError, "UNIVERSE_DUPLICATES"):
            self.run_scan()

    def test_no_implicit_timeframe_conversion(self):
        self.manifest["timeframe"] = "5m"
        with self.assertRaisesRegex(ValueError, "SOURCE_SCOPE_OR_TIMEFRAME"):
            self.run_scan()


class CoreSecretaryGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.work = json.loads((FIXTURES/"strategies.json").read_text())[0]
        source, manifest = "a"*64, "b"*64
        base = dict(dataset_id="demo_btc", version=1,
                    source_bytes_sha256=source,
                    manifest_integrity_sha256=manifest,
                    decision_cutoff_ms=900_000)
        nbar = {
            "bar_open_ms": 0, "bar_close_ms": 899_999,
            "checksum": "c"*64, "observation_lower_bound_ms": 900_000,
            "historical_known_at_ms": None,
        }
        lbar = {**nbar, "bar_checksum": nbar["checksum"]}
        del lbar["checksum"]
        self.native = seal({
            **base, "schema": "aql.core.historical-price-custody-query.v1",
            "status": "OK", "coverage": "COMPLETE", "missing_bar_opens": [],
            "source_availability": "RETROSPECTIVE_NON_PIT",
            "scientific_pit": "NOT_ATTESTED", "historical_known_at_ms": None,
            "required_bar_count": 1, "available_bar_count": 1,
            "bars": [nbar],
        }, "price_query_sha256")
        self.local = seal({
            **base, "schema": "aql.core.local-history-query.v1",
            "coverage": "COMPLETE", "missing_bar_opens": [],
            "source_availability": "RETROSPECTIVE_NON_PIT",
            "historical_pit": "NOT_ATTESTED", "required_bar_count": 1,
            "available_bar_count": 1, "bars": [lbar],
        }, "query_sha256")
        self.warehouse = seal({
            "schema": "aql.core.local-history-warehouse.v1",
            "status": "OFFLINE_LOCAL_WAREHOUSE_COMMITTED",
            "dataset_id": base["dataset_id"], "version": 1,
            "symbol": "BTCUSDT", "market": "SPOT", "exchange": "BINANCE",
            "interval": "15m", "source_zip_sha256": source,
            "manifest_integrity_sha256": manifest,
            "decision_cutoff_ms": 900_000,
            "bar_count": 1, "coverage": "COMPLETE",
            "availability": "RETROSPECTIVE_NON_PIT",
            "historical_known_at": "NOT_ATTESTED",
            "vault": {"vault": "EXISTING_PINNED_RAW_VAULT", "sha256": source},
            "execution": "DISABLED", "scientific_result": "INSUFFICIENT_EVIDENCE",
        }, "receipt_sha256")
        cutoff = datetime.fromtimestamp(900, timezone.utc).isoformat()
        scan = {
            "schema_version": "AQL-SCANNER-V1", "scanner_id": "test_scanner",
            "candidate_id": "BTCUSDT:900000", "profile_id": "INTRADAY",
            "market": "BINANCE:SPOT:USDT", "cutoff_at": cutoff,
            "availability_class": "RETROSPECTIVE_NON_PIT", "stage": "UNKNOWN",
            "source_manifest": {
                "dataset_id": "demo_btc", "dataset_sha": source,
                "schema_version": "AQL-SCANNER-V1", "cutoff_at": cutoff,
                "created_at": cutoff,
            },
            "feature_snapshot": {}, "reasons": ["KNOWN_AT_NOT_ATTESTED"],
            "coverage": {}, "score": None, "score_status": "SCORE_UNAVAILABLE",
            "publishable": False, "delivery_authorized": False,
        }
        self.nomination = {**scan, "digest": sha256_hex(canonical_bytes(scan))}

    def prepare(self):
        return prepare_source_only_route(self.root, self.nomination, self.work,
                                         self.native, self.local, self.warehouse)

    def test_dual_sha_domains_pending_replay_and_verified_ack(self):
        first = self.prepare()
        again = self.prepare()
        self.assertEqual(first.payload, again.payload)
        self.assertNotEqual(first.data["core_245_price_query_sha256"],
                            first.data["core_253_query_local_sha256"])
        waiting = verify_offline_consumer_ack(self.root, first.receipt(), self.warehouse)
        self.assertEqual(waiting.data["state"], "WAIT")
        self.assertEqual(waiting.data["reason"], "MISSING_SECRETARY_ACK")
        queue = first.data["queue"]
        ack = acknowledge_nomination(self.root,
                                     message_id=queue["message_id"],
                                     payload_sha256=queue["payload_sha256"],
                                     acknowledgement_sha256="d"*64)
        verified = verify_offline_consumer_ack(
            self.root, first.receipt(), self.warehouse, ack)
        self.assertEqual(verified.data["state"], "ACKED_SOURCE_ONLY")
        self.assertEqual(verified.data["strategy_decision"], "NOT_PERFORMED")
        self.assertEqual(verified.data["trading_authority"], "NONE")
        second_ack = acknowledge_nomination(self.root,
                                            message_id=queue["message_id"],
                                            payload_sha256=queue["payload_sha256"],
                                            acknowledgement_sha256="d"*64)
        self.assertEqual(ack, second_ack)
        self.assertEqual(len(route_trace(self.root, queue["message_id"])), 2)

    def test_ack_after_restart_readonly_payload_and_tamper_rejected(self):
        first = self.prepare()
        queue = first.data["queue"]
        ack = acknowledge_nomination(
            self.root, message_id=queue["message_id"],
            payload_sha256=queue["payload_sha256"],
            acknowledgement_sha256="d"*64)
        # A fresh call after the original PENDING item was ACKed cannot poll it:
        replay = self.prepare()
        self.assertIsNone(replay.data["secretary_payload"])
        result = verify_offline_consumer_ack(
            self.root, replay.receipt(), self.warehouse, ack)
        self.assertEqual(result.data["state"], "ACKED_SOURCE_ONLY")
        self.assertEqual(result.data["trading_authority"], "NONE")
        # A resealed mutation of the durable delivery body must never pass.
        from research_wp_r0.aql_core_backbone_local_v1 import _connect
        con = _connect(self.root)
        try:
            raw = con.execute(
                "SELECT delivery_json FROM distribution_outbox WHERE message_id=?",
                (queue["message_id"],)).fetchone()[0]
            value = json.loads(raw)
            value["strategy_id"] = "forged"
            con.execute(
                "UPDATE distribution_outbox SET delivery_json=? WHERE message_id=?",
                (json.dumps(value,sort_keys=True,separators=(",",":")),
                 queue["message_id"]))
            con.commit()
        finally:
            con.close()
        with self.assertRaisesRegex(ValueError, "SECRETARY_OUTBOX_PAYLOAD_TAMPER"):
            verify_offline_consumer_ack(
                self.root, replay.receipt(), self.warehouse, ack)

    def test_factory_handoff_sealed_census_wait_and_source_ack(self):
        native = Native15mGate(methodName="test_all_strategy_symbol_pairs_and_safety")
        native.setUp()
        scan = native.run_scan().receipt()
        pending = self.prepare()
        args = dict(
            expected_source_zip_sha256=self.warehouse["source_zip_sha256"],
            expected_core245_sha256=self.native["price_query_sha256"],
            expected_core253_sha256=self.local["query_sha256"],
        )
        wait = verify_offline_consumer_ack(self.root, pending.receipt(), self.warehouse)
        handoff = prepare_factory_handoff(scan, pending.receipt(), wait.receipt(), **args)
        self.assertEqual(handoff.data["synthetic_attempt_denominator"], 10)
        self.assertEqual(len(handoff.data["synthetic_native15m_strategy_census"]), 2)
        self.assertEqual(handoff.data["secretary_source_only_state"], "WAIT")
        self.assertFalse(handoff.data["source_only_is_strategy_selection"])
        self.assertEqual(handoff.data["trading_authority"], "NONE")
        self.assertEqual(handoff.payload,
                         prepare_factory_handoff(scan, pending.receipt(), wait.receipt(), **args).payload)
        queue = pending.data["queue"]
        ack = acknowledge_nomination(
            self.root, message_id=queue["message_id"],
            payload_sha256=queue["payload_sha256"],
            acknowledgement_sha256="d"*64)
        checked = verify_offline_consumer_ack(
            self.root, pending.receipt(), self.warehouse, ack)
        approved = prepare_factory_handoff(scan, pending.receipt(), checked.receipt(), **args).data
        self.assertEqual(approved["secretary_source_only_state"], "ACKED_SOURCE_ONLY")
        self.assertEqual(approved["secretary_source_only_ack_sha256"], ack["receipt_sha256"])
        self.assertEqual(approved["strategy_to_original_source"], "NOT_CONNECTED_NO_PIT_PROMOTION")
        self.assertEqual(approved["orders_created"], 0)

    def test_factory_handoff_mismatched_parent_rejected(self):
        native = Native15mGate(methodName="test_all_strategy_symbol_pairs_and_safety")
        native.setUp()
        scan = native.run_scan().receipt()
        pending = self.prepare()
        wait = verify_offline_consumer_ack(self.root, pending.receipt(), self.warehouse)
        kwargs = dict(
            expected_source_zip_sha256=self.warehouse["source_zip_sha256"],
            expected_core245_sha256=self.native["price_query_sha256"],
            expected_core253_sha256=self.local["query_sha256"],
        )
        kwargs["expected_core253_sha256"] = "f"*64
        with self.assertRaisesRegex(ValueError, "FACTORY_HANDOFF_SOURCE_QUERY_DOMAIN"):
            prepare_factory_handoff(scan, pending.receipt(), wait.receipt(), **kwargs)
        forged = deepcopy(scan)
        forged["payload"]["nominations"][0]["payload"]["status"] = "SELECTED"
        forged = Frozen.build(forged["payload"]).receipt()
        kwargs["expected_core253_sha256"] = self.local["query_sha256"]
        with self.assertRaisesRegex(ValueError, "FROZEN_DIGEST_DRIFT"):
            prepare_factory_handoff(forged, pending.receipt(), wait.receipt(), **kwargs)

    def test_native_scanner_unknown_not_promoted(self):
        bad = deepcopy(self.nomination)
        bad["stage"] = "NOMINATED"
        bad["digest"] = sha256_hex(canonical_bytes({k:v for k,v in bad.items() if k != "digest"}))
        with self.assertRaisesRegex(ValueError, "HISTORICAL_SCANNER_UNKNOWN_REQUIRED"):
            prepare_source_only_route(self.root, bad, self.work,
                                      self.native, self.local, self.warehouse)

    def test_source_sha_version_and_receipt_mismatch(self):
        cases = [
            ("source mismatch", self.native, "source_bytes_sha256", "f"*64, "price_query_sha256"),
            ("version mismatch", self.local, "version", 2, "query_sha256"),
            ("source manifest mismatch", self.warehouse, "manifest_integrity_sha256", "f"*64, "receipt_sha256"),
            ("coverage incomplete", self.local, "coverage", "PARTIAL", "query_sha256"),
        ]
        for label, parent, field, value, key in cases:
            with self.subTest(label=label):
                old = parent[field]
                parent[field] = value
                parent[key] = core_digest({k:v for k,v in parent.items() if k != key})
                with self.assertRaises(ValueError):
                    self.prepare()
                parent[field] = old
                parent[key] = core_digest({k:v for k,v in parent.items() if k != key})

    def test_quarantine_never_ack(self):
        result = self.prepare()
        queue = result.data["queue"]
        for i in range(3):
            outcome = retry_or_quarantine(
                self.root, message_id=queue["message_id"],
                payload_sha256=queue["payload_sha256"],
                reason="NO_CONSUMER_ACK", now_ms=i*1000, max_attempts=3)
        self.assertEqual(outcome["state"], "QUARANTINED")
        wait = verify_offline_consumer_ack(self.root, result.receipt(), self.warehouse)
        self.assertEqual(wait.data["reason"], "QUARANTINED_NOMINATION")
        with self.assertRaises(ValueError):
            acknowledge_nomination(self.root, message_id=queue["message_id"],
                                     payload_sha256=queue["payload_sha256"],
                                     acknowledgement_sha256="d"*64)


if __name__ == "__main__":
    unittest.main()
