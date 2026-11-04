"""Single owner-authorized Bundle B cross-PR SOFTWARE-contract gate.

SYNTHETIC in-memory bytes only. This is not a new authentic-source E2E,
operational Work #235 15m, G0, or any trading/Paper activation.
The actual classes below are the pinned Core #226, Factory #255 and Scanner #257
contract tests. Running all in one process exposes cross-branch interface and
dependency drift without rewriting their code or rerunning accepted Feb/Aug.
"""
from __future__ import annotations

import unittest
import json
from pathlib import Path
from research_wp_r0.aql_archive_custody_bridge_v1 import digest as core_digest
from datetime import datetime, timezone
from research_wp_r0.aql_factory_unified_backbone_v1 import freeze
from research_wp_r0.aql_factory_core_query_bridge_v1 import run_isolated_bundle_b
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_core_secretary_routing_v1 import acknowledge_nomination, route_trace
from tools.scanner_engine_offline.contracts import canonical_bytes, sha256_hex
from tools.scanner_strategy_b.core_secretary import prepare_source_only_route, verify_offline_consumer_ack
from tools.strategy_service_offline.run import FIXTURES

from test_aql_core_dual_query_identity_map_v1 import DualQueryIdentity
from test_aql_factory_core_query_bridge_v1 import BundleBBridgeTests
from test_aql_factory_same_source_lab_paper_v1 import SameSourceLabPaperTests
from tools.scanner_strategy_b.test_integration import (
    Native15mGate, CoreSecretaryGate,
)
from tools.scanner_strategy_b.test_portfolio import PortfolioGate


class CrossLayerSameSourceSyntheticGate(unittest.TestCase):
    """One chain uses computed Core receipts and genuine Core outbox APIs.

    The input is original-format SYNTHETIC TEST_ONLY, NOT owner-retained source.
    The Work policy in source-only Secretary and the Core ROC rule are distinct
    experimental identities; no operational strategy approval is inferred.
    """

    def test_core_factory_scanner_secretary_one_synthetic_source(self):
        case = DualQueryIdentity("test_two_distinct_query_hashes_preserved_and_replay")
        case.setUp()
        self.addCleanup(case.doCleanups)
        warehouse, native, local, calc = (
            case.warehouse, case.native, case.local, case.calc)
        core_map = bind_dual_query_identities(native, local, warehouse, calc)
        self.assertEqual(core_map["strategy_evaluation_sha256"],
                         calc["evaluation_sha256"])
        self.assertNotEqual(core_map["core_245_native_price_query_sha256"],
                            core_map["core_253_query_local_sha256"])

        # Source is built only from the actual Core fixture receipts above,
        # and explicitly marked test-only; it is not an authentic-source claim.
        source = freeze({
            "schema": "aql.factory.unified-custody-source.v1",
            "dataset_id": warehouse["dataset_id"], "version": warehouse["version"],
            "source_bytes_sha256": warehouse["source_zip_sha256"],
            "manifest_integrity_sha256": warehouse["manifest_integrity_sha256"],
            "core_253_warehouse_receipt_sha256": warehouse["receipt_sha256"],
            "core_price_query_sha256": native["price_query_sha256"],
            "core_253_warehouse_query_sha256": local["query_sha256"],
            "cutoff_ms": warehouse["decision_cutoff_ms"],
            "coverage": "COMPLETE", "missing_bar_opens": [],
            "bar_count_available": warehouse["bar_count"],
            "bar_count_required": warehouse["bar_count"],
            "raw_warehouse_query": "CONNECTED_PINNED_CORE_253_RAW_WAREHOUSE",
            "core_query_consumer": "CONNECTED_READ_ONLY_CORE_CUSTODY",
            "source_eligible_for_historical_pit": False,
            "fixture_evidence_class": "SYNTHETIC_TEST_ONLY",
            "holdout": "SEALED_UNOPENED", "trading_authority": "NONE",
        })
        product = run_isolated_bundle_b(source, native, local, calc)
        self.assertEqual(product, run_isolated_bundle_b(source, native, local, calc))
        self.assertEqual(product["bridge"]["core_245_price_query_sha256"],
                         core_map["core_245_native_price_query_sha256"])
        self.assertEqual(product["bridge"]["core_253_query_local_sha256"],
                         core_map["core_253_query_local_sha256"])
        self.assertEqual(product["lab"]["core_lab_evaluation_sha256"],
                         calc["evaluation_sha256"])
        self.assertEqual(product["lab"]["source_zip_sha256"],
                         warehouse["source_zip_sha256"])
        self.assertIn(product["paper"]["decision"], ("WAIT", "REJECT"))
        self.assertEqual(product["paper"]["orders_created"], 0)
        self.assertIsNone(product["paper"]["actual_fills"])
        self.assertEqual(product["paper"]["work235_actual_route"],
                         "NOT_CONNECTED_15M_UNSUPPORTED")

        stamp = datetime.fromtimestamp(
            warehouse["decision_cutoff_ms"] / 1000, timezone.utc).isoformat()
        scan = {
            "schema_version": "AQL-SCANNER-V1",
            "scanner_id": "bundle_b_synthetic_gate",
            "candidate_id": "BTCUSDT:INTEGRATION_TEST_ONLY",
            "profile_id": "INTRADAY", "market": "BINANCE:SPOT:USDT",
            "cutoff_at": stamp,
            "availability_class": "RETROSPECTIVE_NON_PIT",
            "stage": "UNKNOWN",
            "source_manifest": {
                "dataset_id": warehouse["dataset_id"],
                "dataset_sha": warehouse["source_zip_sha256"],
                "schema_version": "AQL-SCANNER-V1",
                "cutoff_at": stamp, "created_at": stamp,
            },
            "feature_snapshot": {}, "reasons": ["KNOWN_AT_NOT_ATTESTED"],
            "coverage": {}, "score": None,
            "score_status": "SCORE_UNAVAILABLE",
            "publishable": False, "delivery_authorized": False,
        }
        native_nomination = {
            **scan, "digest": sha256_hex(canonical_bytes(scan)),
        }
        work_spec = json.loads((FIXTURES / "strategies.json").read_text())[0]
        route = prepare_source_only_route(
            case.root, native_nomination, work_spec, native, local, warehouse)
        self.assertEqual(route.data["core_245_price_query_sha256"],
                         product["bridge"]["core_245_price_query_sha256"])
        self.assertEqual(route.data["core_253_query_local_sha256"],
                         product["bridge"]["core_253_query_local_sha256"])
        pending = verify_offline_consumer_ack(case.root, route.receipt(), warehouse)
        self.assertEqual(pending.data["state"], "WAIT")
        self.assertEqual(pending.data["reason"], "MISSING_SECRETARY_ACK")
        queue = route.data["queue"]
        ack = acknowledge_nomination(
            case.root, message_id=queue["message_id"],
            payload_sha256=queue["payload_sha256"],
            acknowledgement_sha256="f" * 64)
        confirmed = verify_offline_consumer_ack(
            case.root, route.receipt(), warehouse, ack)
        self.assertEqual(confirmed.data["state"], "ACKED_SOURCE_ONLY")
        self.assertEqual(confirmed.data["strategy_decision"], "NOT_PERFORMED")
        self.assertEqual(len(route_trace(case.root, queue["message_id"])), 2)
        again = acknowledge_nomination(
            case.root, message_id=queue["message_id"],
            payload_sha256=queue["payload_sha256"],
            acknowledgement_sha256="f" * 64)
        self.assertEqual(again, ack)
        self.assertEqual(product["batch"]["trading_authority"], "NONE")
        self.assertEqual(product["batch"]["orders_created"], 0)
        report = {
            "schema": "aql.integration.bundle-b-software-evidence.v1",
            "source_class": "IN_MEMORY_SYNTHETIC_TEST_ONLY",
            "new_authentic_month": "SOURCE_UNAVAILABLE",
            "core_245_native_price_query_sha256": native["price_query_sha256"],
            "core_253_query_local_sha256": local["query_sha256"],
            "core_253_raw_warehouse_receipt_sha256": warehouse["receipt_sha256"],
            "source_zip_sha256": warehouse["source_zip_sha256"],
            "manifest_integrity_sha256": warehouse["manifest_integrity_sha256"],
            "core_dual_query_identity_sha256": core_map["identity_map_sha256"],
            "core_strategy_evaluation_sha256": calc["evaluation_sha256"],
            "factory_source_receipt_sha256": source["artifact_sha256"],
            "factory_bridge_sha256": product["bridge"]["artifact_sha256"],
            "factory_projected_source_sha256":
                product["adapted_source"]["artifact_sha256"],
            "factory_lab_sha256": product["lab"]["artifact_sha256"],
            "factory_paper_sha256": product["paper"]["artifact_sha256"],
            "factory_batch_sha256": product["batch"]["artifact_sha256"],
            "strategy_id": calc["strategy_id"],
            "strategy_version": calc["strategy_version"],
            "strategy_digest": calc["strategy_digest"],
            "strategy_attempt_denominator": calc["attempt_denominator"],
            "strategy_decision_slots": calc["decision_slots"],
            "strategy_decision_counts": calc["decision_counts"],
            "secretary_source_only_strategy_id": route.data["work235_strategy_id"],
            "secretary_source_only_strategy_config":
                route.data["work235_config_digest"],
            "strategy_identity_with_secretary": "NOT_CLAIMED_SOURCE_ONLY",
            "scanner_nomination_sha256": native_nomination["digest"],
            "scanner_operational_status": "UNKNOWN",
            "secretary_route_sha256": route.sha256,
            "secretary_queue_message_id": queue["message_id"],
            "secretary_queue_payload_sha256": queue["payload_sha256"],
            "secretary_ack_sha256": ack["receipt_sha256"],
            "secretary_factory_consumer_sha256":
                confirmed.data["factory_consumer_receipt_sha256"],
            "secretary_ack_state": confirmed.data["state"],
            "paper_decision": product["paper"]["decision"],
            "paper_route": product["paper"]["work235_actual_route"],
            "orders": product["paper"]["orders_created"],
            "positions": product["paper"]["paper_positions"],
            "fills": product["paper"]["actual_fills"],
            "historical_pit": "NOT_ATTESTED",
            "holdout": "SEALED_UNOPENED",
            "trading_authority": "NONE",
        }
        report["receipt_sha256"] = core_digest(report)
        self.assertEqual(report["receipt_sha256"],
                         core_digest({k: v for k, v in report.items()
                                      if k != "receipt_sha256"}))
        Path("atlas_bundle_b_ci_receipts.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + chr(10),
            encoding="utf8")
        print("ATLAS_B_RECEIPT_SHA256=" + report["receipt_sha256"])


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    for case in (CrossLayerSameSourceSyntheticGate, DualQueryIdentity, BundleBBridgeTests,
                 SameSourceLabPaperTests, Native15mGate, CoreSecretaryGate,
                 PortfolioGate):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == "__main__":
    unittest.main()
