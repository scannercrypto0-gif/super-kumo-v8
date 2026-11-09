import unittest
from unittest.mock import patch

from tools import atlas_h_generic_secretary_bridge as bridge

CORE = "research_wp_r0.aql_core_backbone_local_v1"
FACTORY = "research_wp_r0.aql_factory_h_generic_signal_adapter_v1"


class ResearchAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.query = {
            "dataset_id": "test", "version": 1, "source_bytes_sha256": "a" * 64,
            "manifest_integrity_sha256": "b" * 64, "query_sha256": "c" * 64,
            "start_ms": 0, "end_exclusive_ms": 900000, "decision_cutoff_ms": 900000,
        }
        self.scope = {key: value for key, value in self.query.items()
                      if key not in ("start_ms", "end_exclusive_ms")}
        self.scope.update(rights_reference="operator-policy:fixture", valid_until_ms=1001)
        self.packet = {"core_query": self.query, "experiment_id": "fixture", "sha256": "input"}
        self.package = {"sha256": "package", "scientific_lab": {"sha256": "lab"}}
        self.result = {"receipt_sha256": "result"}

    def call(self, lane, scope=None):
        return bridge.deliver_generic_research_wait(
            secretary_root=None, packet=self.packet, factory_package=self.package,
            factory_result=self.result, lane=lane,
            source_scope=self.scope if scope is None else scope, warehouse_root="unused",
        )

    def test_research_classification_never_enqueues_and_cannot_promote_non_pit(self):
        with (
            patch.object(bridge, "time_ns", return_value=1_000_000_000),
            patch.object(bridge, "route_generic_research_result") as enqueue,
            patch.object(bridge, "build_generic_research_result_route",
                         return_value={"scanner_batch_sha256": "batch",
                                       "cost_policy_sha256": "cost"}),
            patch(CORE + ".query_local", return_value=self.query) as query_local,
            patch(FACTORY + "._verified", return_value=(
                {"source_class": "OWNER_LOCAL_RECOVERY_DIAGNOSTIC"},
                None, None, None, {"sha256": "cost"}, "batch")),
        ):
            result = self.call("EXPERIMENTAL")
            self.assertEqual((result["lane"], result["status"]), ("EXPERIMENTAL", "ACCEPTED"))
            self.assertFalse(result["secretary_enqueued"])
            self.assertEqual(result["trading_authority"], "NONE")
            body = {key: value for key, value in result.items() if key != "receipt_sha256"}
            self.assertEqual(result["receipt_sha256"], bridge.digest(body))
            validation = self.call("RESEARCH_VALIDATED")
            self.assertEqual((validation["lane"], validation["status"]), ("EXPERIMENTAL", "BLOCKED"))
            self.assertEqual(validation["reason"], "PIT_OOS_VALIDATION_EVIDENCE_UNAVAILABLE")
            query_local.assert_called_with(
                "unused", "test", 1, 0, 900000, 900000,
                required_source_sha256="a" * 64, require_complete=True, sqlite_immutable=True,
            )
            query_local.return_value = {**self.query, "decision_cutoff_ms": 900001}
            with self.assertRaisesRegex(bridge.GenericBridgeError, "READBACK_DRIFT"):
                self.call("EXPERIMENTAL")
            enqueue.assert_not_called()

    def test_scope_is_required_and_bound_to_source_and_expiry(self):
        with patch.object(bridge, "time_ns", return_value=1_000_000_000):
            with self.assertRaisesRegex(bridge.GenericBridgeError, "TRUSTED_SOURCE_SCOPE_REQUIRED"):
                self.call("EXPERIMENTAL", {})
            for patch_fields in ({"source_bytes_sha256": "other"},
                                 {"rights_reference": ""}, {"valid_until_ms": 1000}):
                with self.subTest(patch_fields=patch_fields):
                    with self.assertRaisesRegex(bridge.GenericBridgeError, "MISMATCH_OR_EXPIRED"):
                        self.call("EXPERIMENTAL", {**self.scope, **patch_fields})

    def test_operational_or_unknown_lane_rejected_before_routing(self):
        with patch.object(bridge, "build_generic_research_result_route") as build:
            for lane in ("LIVE", "PAPER", "ORDER", "VALIDATED", ""):
                with self.subTest(lane=lane):
                    with self.assertRaisesRegex(bridge.GenericBridgeError, "LANE_FORBIDDEN"):
                        self.call(lane)
            build.assert_not_called()
