"""Scanner-owned read-only contracts over existing Core #245/#253 + Secretary.

All data is OFFLINE_RESEARCH_ONLY. This module never creates an order, never
upgrades a historical Scanner UNKNOWN to SELECTED, and never creates ACK on
behalf of a downstream Factory consumer. Core owns the durable outbox; Factory
owns its independent source-consumer ACK verification.
"""
from __future__ import annotations

from datetime import datetime, timezone

from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_core_secretary_routing_v1 import (
    enqueue_nomination, poll_nomination, route_trace,
)
from research_wp_r0.aql_factory_unified_backbone_v1 import consume_core_secretary_route
from tools.scanner_engine_offline.contracts import canonical_bytes, sha256_hex
from tools.strategy_service_offline.common import Frozen, digest, require
from tools.strategy_service_offline.screening import StrategyScreeningSpec

SCHEMA = "aql.scanner-b.core-secretary-source-route.v1"


def _native_unknown(nomination, warehouse):
    require(type(nomination) is dict and nomination.get("schema_version") == "AQL-SCANNER-V1",
            "NATIVE_SCANNER_V1_REQUIRED")
    scan_body = {k: v for k, v in nomination.items() if k != "digest"}
    require(nomination.get("digest") == sha256_hex(canonical_bytes(scan_body)),
            "NATIVE_SCANNER_SEAL_MISMATCH")
    require(nomination.get("stage") == "UNKNOWN"
            and nomination.get("availability_class") in ("UNKNOWN", "RETROSPECTIVE_NON_PIT")
            and nomination.get("publishable") is False
            and nomination.get("delivery_authorized") is False,
            "HISTORICAL_SCANNER_UNKNOWN_REQUIRED")
    source = nomination.get("source_manifest")
    require(type(source) is dict
            and source.get("schema_version") == "AQL-SCANNER-V1"
            and source.get("dataset_id") == warehouse.get("dataset_id")
            and source.get("dataset_sha") == warehouse.get("source_zip_sha256")
            and source.get("cutoff_at") == nomination.get("cutoff_at"),
            "SCANNER_SOURCE_PARENT_DRIFT")
    try:
        clock = datetime.fromisoformat(nomination["cutoff_at"].replace("Z", "+00:00"))
        require(clock.tzinfo is not None and clock.utcoffset() is not None,
                "SCANNER_CUTOFF_NOT_UTC")
        cutoff_ms = int(clock.astimezone(timezone.utc).timestamp()*1000)
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("SCANNER_CUTOFF_INVALID") from exc
    require(cutoff_ms <= warehouse.get("decision_cutoff_ms", -1)
            and nomination.get("candidate_id", "").split(":", 1)[0] == warehouse.get("symbol")
            and nomination.get("market", "").startswith(
                warehouse.get("exchange", "") + ":" + warehouse.get("market", "") + ":"),
            "SCANNER_SYMBOL_MARKET_OR_CUTOFF_DRIFT")


def prepare_source_only_route(root, nomination, work235_spec_receipt,
                              native_price_query, local_query, warehouse_receipt,
                              *, lane="SLOW"):
    """Check distinct Core SHA domains then submit a durable source-only route.

    Native Scanner V1 UNKNOWN is the ONLY supported historical input.
    Strategy policy identity is included in our separate sealed receipt and
    deterministic Core message key, NOT rewritten into Core's frozen schema.
    """
    work = StrategyScreeningSpec.restore_spec(work235_spec_receipt).data
    require(work["scope"] == "TEST_ONLY_UNAPPROVED_POLICY"
            and work["paper_approval"] == "NOT_FOUND", "STRATEGY_NOT_APPROVED")
    identity = bind_dual_query_identities(
        native_price_query, local_query, warehouse_receipt)
    _native_unknown(nomination, warehouse_receipt)
    require(identity["source_zip_sha256"] == nomination["source_manifest"]["dataset_sha"]
            and identity["decision_cutoff_ms"] >= 0
            and identity["historical_known_at_ms"] is None
            and identity["operational_scanner_status"] == "UNKNOWN"
            and identity["trading_authority"] == "NONE"
            and warehouse_receipt.get("interval") == "15m",
            "SOURCE_QUERY_OR_NATIVE_15M_INCOMPATIBLE")
    key = digest({
        "scanner_nomination_sha256": nomination["digest"],
        "core_identity_map_sha256": identity["identity_map_sha256"],
        "strategy_id": work["strategy_id"],
        "strategy_version": work["strategy_version"],
        "strategy_config": work["config_digest"],
        "lane": lane, "schema": SCHEMA,
    })
    queue = enqueue_nomination(
        root, nomination, strategy_id=work["strategy_id"],
        strategy_version=work["strategy_version"],
        warehouse_receipt=warehouse_receipt, lane=lane, idempotency_key=key,
    )
    selected = poll_nomination(root, now_ms=warehouse_receipt["decision_cutoff_ms"], lane=lane)
    # poll may pick another pre-existing queue item; verify OUR immutable Core
    # queue separately through direct trace and let Secretary own dispatch.
    trace = route_trace(root, key)
    require(trace[0]["state"] == "PENDING"
            and trace[0]["payload_sha256"] == queue["payload_sha256"],
            "SECRETARY_QUEUE_OR_TRACE_MISMATCH")
    if selected is not None and selected["message_id"] == key:
        payload = selected["envelope"]
        require(payload["payload_sha256"] == queue["payload_sha256"],
                "SECRETARY_PAYLOAD_TAMPER")
    else:
        # A replayed already-ACKed item is not pollable. Do not create fake ACK.
        require(trace[-1]["state"] in ("PENDING", "RETRY", "ACKED", "QUARANTINED"),
                "SECRETARY_OUTBOX_STATE")
        payload = None
    return Frozen.build({
        "schema": SCHEMA,
        "queue": queue, "secretary_payload": payload,
        "core_identity": identity,
        "native_scanner_nomination": nomination,
        "work235_strategy_id": work["strategy_id"],
        "work235_strategy_version": work["strategy_version"],
        "work235_config_digest": work["config_digest"],
        "work235_strategy_definition_digest": work["definition"]["digest"],
        "source_zip_sha256": identity["source_zip_sha256"],
        "core_245_price_query_sha256": identity["core_245_native_price_query_sha256"],
        "core_253_query_local_sha256": identity["core_253_query_local_sha256"],
        "historical_known_at_ms": None,
        "operational_scanner_status": "UNKNOWN",
        "strategy_decision": "NOT_PERFORMED",
        "work235_native_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
        "secretary_ack_status": trace[-1]["state"],
        "paper_decision": "WAIT",
        "trading_authority": "NONE", "orders_created": 0,
    })


def verify_offline_consumer_ack(root, pending_receipt, warehouse_receipt, ack_receipt=None):
    """Read-only verification; never ACK by itself, never promote to Paper.

    A caller/downstream consumer must have legitimately produced the Core ACK.
    For an absent ACK return WAIT with an explicit reason, not delivery success.
    """
    bound = Frozen.restore(pending_receipt).data
    require(bound["schema"] == SCHEMA
            and bound["operational_scanner_status"] == "UNKNOWN"
            and bound["trading_authority"] == "NONE"
            and bound["source_zip_sha256"] == warehouse_receipt.get("source_zip_sha256"),
            "SOURCE_ROUTE_DRIFT")
    queue = bound["queue"]
    trace = route_trace(root, queue["message_id"])
    if ack_receipt is None:
        require(trace[-1]["state"] in ("PENDING", "RETRY", "QUARANTINED"),
                "MISSING_ACK_AFTER_ACKED")
        return Frozen.build({
            "schema": "aql.scanner-b.secretary-ack-check.v1",
            "source_route_sha256": Frozen.restore(pending_receipt).sha256,
            "state": "WAIT", "reason": "MISSING_SECRETARY_ACK"
                if trace[-1]["state"] != "QUARANTINED" else "QUARANTINED_NOMINATION",
            "trace_tail_sha256": digest(trace[-1]),
            "paper_execution": "NOT_ACTIVATED", "trading_authority": "NONE",
        })
    require(trace[-1]["state"] == "ACKED", "SECRETARY_ACK_NOT_COMMITTED")
    route = bound["secretary_payload"]
    # Durable replay can return a null poll view for an already-ACKED message.
    # A caller must provide the exact immutable Core payload; never reconstruct
    # or forge it from unsealed user arguments.
    require(type(route) is dict and route.get("payload_sha256") == queue["payload_sha256"],
            "SECRETARY_PAYLOAD_NOT_ATTESTED")
    consumer = consume_core_secretary_route(warehouse_receipt, route, queue,
                                             ack_receipt, trace)
    return Frozen.build({
        "schema": "aql.scanner-b.secretary-ack-check.v1",
        "source_route_sha256": Frozen.restore(pending_receipt).sha256,
        "state": "ACKED_SOURCE_ONLY",
        "factory_consumer_receipt_sha256": consumer["artifact_sha256"],
        "core_ack_receipt_sha256": ack_receipt["receipt_sha256"],
        "trace_tail_sha256": digest(trace[-1]),
        "strategy_decision": "NOT_PERFORMED",
        "paper_execution": "NOT_ACTIVATED", "trading_authority": "NONE",
    })
