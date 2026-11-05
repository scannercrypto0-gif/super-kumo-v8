"""Scanner D only: real Core B #245/#253 query fixture -> same source projection.

These are TEST_ONLY synthetic original-format ZIP fixtures, not genuine
historical-source data, scientific PIT, or a Core-issued Package D attestation.
"""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

import test_aql_core_dual_query_identity_map_v1 as core_fixture
from tools.strategy_service_offline.common import Frozen, digest
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_d.core_query_adapter import (
    scan_same_core_source, _project,
)


class ScannerDReadOnlyCoreSource(unittest.TestCase):
    def setUp(self):
        self.core = core_fixture.DualQueryIdentity(
            methodName="test_two_distinct_query_hashes_preserved_and_replay")
        self.core.setUp()
        self.addCleanup(self.core.doCleanups)
        self.warehouse = self.core.warehouse
        self.native = self.core.native
        self.local = self.core.local
        self.mapping = self.core.mapped()
        self.work = json.loads((FIXTURES/"strategies.json").read_text())
        self.witness_body = {
            "schema": "aql.core.d.synthetic-same-source-research-witness.v1",
            "scope": "SYNTHETIC_SAME_SOURCE_SOFTWARE_ONLY",
            "source_kind": "CORE_ORIGINAL_FORMAT_TEST_ZIP",
            "source_authority": "TEST_ONLY_NOT_PUBLISHER_ATTESTED",
            "historical_pit": "NOT_ATTESTED",
            "historical_known_at_ms": None,
            "research_clock_basis": "DECLARED_SYNTHETIC_FIXTURE_ONLY",
            "trading_authority": "NONE",
            "dataset_id": self.warehouse["dataset_id"],
            "version": self.warehouse["version"],
            "symbol": self.warehouse["symbol"],
            "source_zip_sha256": self.warehouse["source_zip_sha256"],
            "manifest_integrity_sha256": self.warehouse["manifest_integrity_sha256"],
            "warehouse_receipt_sha256": self.warehouse["receipt_sha256"],
            "core245_price_query_sha256": self.native["price_query_sha256"],
            "core253_query_local_sha256": self.local["query_sha256"],
            "decision_cutoff_ms": self.warehouse["decision_cutoff_ms"],
            "scanner_source_id": "generator",
            "scanner_generation_id": "D_CORE_QUERY_FIXTURE_1",
            "scanner_market": "fixture",
            "synthetic_available_at_ms_by_bar": [
                {
                    "bar_open_ms": b["bar_open_ms"],
                    "bar_checksum": b["bar_checksum"],
                    "available_at_ms": b["bar_close_ms"] + 1,
                }
                for b in self.local["bars"]
            ],
            "research_universe_members": [
                {
                    "symbol": self.warehouse["symbol"], "eligible": True,
                    "membership_available_ms": self.warehouse["decision_cutoff_ms"],
                }
            ],
        }
        self.actions = {
            (w["payload"]["strategy_id"], w["payload"]["strategy_version"]): {
                "action": "APPROVE_TEST_ONLY",
                "governance_policy_id": "ATLAS_SCANNER_D_TEST",
                "approver_id": "fixture_action_only",
                "approval_nonce": w["payload"]["strategy_id"],
            } for w in self.work
        }

    def run_d(self, **override):
        w = Frozen.build({**self.witness_body, **override}).receipt()
        return scan_same_core_source(
            self.core.root, self.warehouse, self.native, self.local,
            self.mapping, w, self.work,
            governance_actions=self.actions, symbol_budget=1)

    def test_positive_actual_core_245_253_source_query_replay_and_full_census(self):
        result = self.run_d()
        self.assertEqual(result.sha256, self.run_d().sha256)
        d = result.data
        self.assertEqual(d["source_binding_status"],
                         "CORE_QUERY_TO_SCANNER_BYTES_VERIFIED_SOFTWARE_ONLY")
        self.assertNotEqual(d["source_zip_sha256"], d["scanner_raw_sha256"])
        self.assertTrue(d["distinct_sha_domains_preserved"])
        self.assertEqual(d["strategy_secretary_status"], "NOT_ENQUEUED")
        self.assertEqual(d["trading_authority"], "NONE")
        self.assertEqual(d["orders_created"], 0)
        self.assertIsNone(d["actual_fills"])
        proof = Frozen.restore(d["research_same_source_projection_receipt"]).data
        self.assertEqual(proof["source_relationship"],
                         "DETERMINISTIC_PROJECTION_FROM_VERIFIED_CORE_QUERY")
        self.assertEqual(proof["core_readonly_query_replay"], "VERIFIED_EXACT")
        self.assertEqual(len(proof["source_byte_mapping"]), self.warehouse["bar_count"])
        self.assertEqual(
            [z["core_local_bar_checksum"] for z in proof["source_byte_mapping"]],
            [z["bar_checksum"] for z in self.local["bars"]])
        service = Frozen.restore(d["scanner_c_canonical_service_receipt"]).data
        self.assertEqual(service["strategy_count"], 2)
        self.assertEqual(service["symbol_denominator"], 1)
        self.assertEqual(service["total_attempts"], 2)
        self.assertEqual(service["source_status"], "SYNTHETIC_TEST_ONLY_NATIVE_15M")
        self.assertEqual(len(service["strategy_route_requests"]), 2)
        # Frozen Work policies only admit AAA/BBB/CCC, not Core's BTCUSDT:
        # valid source MUST NOT silently override strategy's symbol policy.
        self.assertTrue(all(
            Frozen.restore(x).data["scanner_nomination_status"] == "INELIGIBLE"
            and Frozen.restore(x).data["strategy_route_status"] == "WAIT"
            and Frozen.restore(x).data["trading_authority"] == "NONE"
            for x in service["strategy_route_requests"]))

    def test_wrong_core_source_and_query_sha_fail_closed(self):
        modified = {**self.witness_body, "source_zip_sha256": "f"*64}
        with self.assertRaisesRegex(ValueError,"D_CORE_D_WITNESS_IDENTITY_OR_SCOPE"):
            self.run_d(**modified)
        changed = deepcopy(self.local)
        changed["bars"][0]["close"] += 1
        changed["query_sha256"] = digest({k:v for k,v in changed.items()
                                          if k != "query_sha256"})
        with self.assertRaises(ValueError):
            _project(self.core.root, self.warehouse, self.native,
                     changed, self.mapping, Frozen.build(self.witness_body).receipt())

    def test_declared_software_known_at_required_no_historical_pit_promotion(self):
        wrong = deepcopy(self.witness_body)
        wrong["historical_known_at_ms"] = self.core.cutoff
        with self.assertRaisesRegex(ValueError, "D_CORE_D_WITNESS_IDENTITY_OR_SCOPE"):
            self.run_d(**wrong)
        wrong = deepcopy(self.witness_body)
        wrong["synthetic_available_at_ms_by_bar"] = []
        with self.assertRaisesRegex(ValueError, "D_TEST_AVAILABILITY_WITNESS_REQUIRED"):
            self.run_d(**wrong)
        wrong = deepcopy(self.witness_body)
        wrong["synthetic_available_at_ms_by_bar"][0]["available_at_ms"] = self.core.cutoff+1
        with self.assertRaisesRegex(ValueError, "D_CORE_D_CLOCK_OR_BAR_CHECKSUM_DRIFT"):
            self.run_d(**wrong)

    def test_wrong_bar_checksum_cutoff_and_universe_fail_closed(self):
        wrong = deepcopy(self.witness_body)
        wrong["synthetic_available_at_ms_by_bar"][0]["bar_checksum"] = "0"*64
        with self.assertRaisesRegex(ValueError, "D_CORE_D_CLOCK_OR_BAR_CHECKSUM_DRIFT"):
            self.run_d(**wrong)
        wrong = deepcopy(self.witness_body)
        wrong["decision_cutoff_ms"] += 1
        with self.assertRaisesRegex(ValueError, "D_CORE_D_WITNESS_IDENTITY_OR_SCOPE"):
            self.run_d(**wrong)
        wrong = deepcopy(self.witness_body)
        wrong["research_universe_members"].append(deepcopy(
            wrong["research_universe_members"][0]))
        with self.assertRaisesRegex(ValueError, "D_SOURCE_UNIVERSE_NOT_SYNTHETIC_WITNESSED"):
            self.run_d(**wrong)

    def test_wrong_policy_or_missing_explicit_test_only_approval_fails_closed(self):
        prior = self.actions
        self.actions = {}
        with self.assertRaisesRegex(ValueError, "C_EXACT_GOVERNANCE_ACTION_SET"):
            self.run_d()
        self.actions = prior
        wrong = deepcopy(self.witness_body)
        wrong["scanner_market"] = "wrong_market"
        with self.assertRaisesRegex(ValueError, "STRATEGY_MARKET_SCOPE"):
            self.run_d(**wrong)

    def test_raw_parent_tamper_and_bad_witness_receipt_fails_closed(self):
        wrong = deepcopy(self.witness_body)
        wrong["warehouse_receipt_sha256"] = "e"*64
        with self.assertRaisesRegex(ValueError, "D_CORE_D_WITNESS_IDENTITY_OR_SCOPE"):
            self.run_d(**wrong)
        invalid = Frozen.build(self.witness_body).receipt()
        invalid["payload"]["source_zip_sha256"] = "a"*64
        with self.assertRaises(ValueError):
            _project(self.core.root, self.warehouse, self.native,
                     self.local, self.mapping, invalid)

if __name__ == "__main__":
    unittest.main()
