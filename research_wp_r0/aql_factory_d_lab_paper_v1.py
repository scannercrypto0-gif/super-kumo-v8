"""Factory D: same-source AAA TEST_ONLY Lab and isolated Paper.

A real descriptive Lab computation over the *re-read* Core D warehouse bars,
not a fake strategy performance result. The durable Core D Secretary must have
recorded a genuine independent Factory consumer ACK before either path runs.
Paper constructs an explicitly declined native PaperIntent and an empty native
PositionLedger; no orders, positions, fills, or broker side effects.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_core_d_canonical_secretary_v1 import strategy_d_snapshot
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError
from src.aql.observation.contracts import PaperIntent
from src.aql.observation.positions import PositionLedger
from tools.strategy_service_offline.common import Frozen

LAB_SCHEMA = "aql.factory.d.same-source-descriptive-lab.v1"
PAPER_SCHEMA = "aql.factory.d.isolated-paper-decision.v1"
BATCH_SCHEMA = "aql.factory.d.canonical-lab-paper-gate.v1"
ACK_SCHEMA = "aql.factory.d.canonical-strategy-consumer-ack.v1"


def _need(ok, reason):
    if not ok:
        raise LabHandoffError("FACTORY_D_LAB_PAPER_" + reason)


def _sealed(obj, field):
    _need(type(obj) is dict and type(obj.get(field)) is str
          and len(obj[field]) == 64
          and digest({k: v for k, v in obj.items() if k != field})
              == obj[field], "BAD_SEAL_" + field)


def _number(value):
    _need(type(value) in (int, float, str), "NON_NUMERIC_BAR")
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise LabHandoffError("FACTORY_D_LAB_PAPER_BAD_PRICE") from exc
    _need(v.is_finite(), "NONFINITE_BAR")
    return v


def _sealed_body(body, key):
    return {**body, key: digest(body)}


def run_factory_d_same_source_lab_paper(
    *, core_root, route_id, now_ms, factory_ack, gate, warehouse,
    native_price_query, local_query, identity_map, core_d_witness,
    scanner_d_handoff,
):
    """Execute pinned D cohort Lab→isolated Paper after genuine Core durable ACK.

    Lab computes observed synthetic candle diagnostics (not alpha or trades).
    Paper is a real invocation of the native PaperIntent and PositionLedger
    interfaces, always declined. Historical PIT and operational Paper remain
    blocked. The function does not recreate or acknowledge a strategy route.
    """
    _need(type(route_id) is str and bool(route_id)
          and type(now_ms) is int, "ROUTE_CLOCK")
    snap = strategy_d_snapshot(core_root, route_id, now_ms=now_ms)
    for obj, key in ((snap, "route_receipt_sha256"),
                     (factory_ack, "consumer_ack_sha256"),
                     (gate, "gate_sha256"),
                     (warehouse, "receipt_sha256"),
                     (native_price_query, "price_query_sha256"),
                     (local_query, "query_sha256"),
                     (identity_map, "identity_map_sha256")):
        _sealed(obj, key)
    _need(snap.get("state") == "ACKED_CONSUMER"
          and snap.get("route_ready_for_factory_test_only") is True
          and snap.get("route_id") == route_id
          and snap.get("consumer_ack_sha256") == factory_ack["consumer_ack_sha256"]
          and factory_ack.get("schema") == ACK_SCHEMA
          and factory_ack.get("route_id") == route_id
          and factory_ack.get("decision") == "ACCEPTED_TEST_ONLY_RESEARCH"
          and snap.get("gate_sha256") == gate["gate_sha256"]
          and factory_ack.get("strategy_gate_sha256") == gate["gate_sha256"]
          and snap.get("scanner_c_approval_sha256")
              == factory_ack.get("scanner_c_approval_sha256")
              == gate.get("scanner_c_approval_sha256")
          and snap.get("source_ack_sha256")
              == factory_ack.get("source_ack_sha256")
              == gate.get("source_ack_sha256")
          and snap.get("scanner_d_handoff_sha256")
              == gate.get("scanner_d_handoff_sha256")
          and snap.get("core_d_witness_sha256")
              == gate.get("core_d_witness_sha256")
          and gate.get("schema") == "aql.core.d.same-source-strategy-route-gate.v1"
          and gate.get("decision") == "RESEARCH_CANDIDATE_VERIFIED_TEST_ONLY"
          and gate.get("scanner_c_governance_action") == "APPROVE_TEST_ONLY"
          and gate.get("scanner_c_scope") == "SYNTHETIC_OFFLINE_ENGINEERING_ONLY"
          and gate.get("nomination_status") == "SELECTED"
          and gate.get("symbol") == snap.get("symbol") == "AAA"
          and gate.get("timeframe") == snap.get("timeframe") == "15m"
          and snap.get("strategy_id") == factory_ack.get("strategy_id")
              == gate.get("strategy_id")
          and snap.get("strategy_version") == factory_ack.get("strategy_version")
              == gate.get("strategy_version")
          and snap.get("strategy_definition_digest")
              == gate.get("strategy_definition_digest")
          and snap.get("config_digest") == factory_ack.get("config_digest")
              == gate.get("config_digest")
          and snap.get("cutoff_ms") == factory_ack.get("cutoff_ms")
              == gate.get("cutoff_ms")
          and snap.get("source_zip_sha256")
              == factory_ack.get("source_zip_sha256")
              == gate.get("source_zip_sha256")
          and snap.get("historical_pit") == gate.get("historical_pit")
              == "NOT_ATTESTED"
          and snap.get("historical_known_at_ms") is None
          and snap.get("trading_authority") == gate.get("trading_authority")
              == factory_ack.get("trading_authority") == "NONE"
          and factory_ack.get("paper_authority") == "NONE"
          and snap.get("paper_execution") == "NOT_ACTIVATED"
          and snap.get("orders_created") == factory_ack.get("orders_created") == 0
          and snap.get("paper_positions") == factory_ack.get("paper_positions") == 0
          and snap.get("actual_fills") is None
          and factory_ack.get("actual_fills") is None,
          "ACKED_ROUTE_STRATEGY_AUTHORITY")
    witness = Frozen.restore(core_d_witness)
    handoff = Frozen.restore(scanner_d_handoff)
    _need(witness.sha256 == gate["core_d_witness_sha256"]
          and handoff.sha256 == gate["scanner_d_handoff_sha256"]
          and handoff.data.get("source_zip_sha256") == gate["source_zip_sha256"]
          and handoff.data.get("source_binding_status")
              == "CORE_QUERY_TO_SCANNER_BYTES_VERIFIED_SOFTWARE_ONLY"
          and handoff.data.get("trading_authority") == "NONE"
          and witness.data.get("scanner_source_id") == "generator"
          and witness.data.get("scanner_generation_id") == "fixture_v1",
          "SCANNER_WITNESS_LINEAGE")
    _need(warehouse.get("status") == "OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
          and warehouse.get("test_only") is True
          and warehouse.get("source_evidence_class") == "SYNTHETIC_TEST"
          and warehouse.get("symbol") == "AAA"
          and warehouse.get("interval") == "15m"
          and warehouse.get("source_zip_sha256") == gate["source_zip_sha256"]
          and warehouse.get("manifest_integrity_sha256")
              == gate.get("manifest_integrity_sha256")
          and warehouse.get("receipt_sha256") == gate["warehouse_receipt_sha256"]
          and warehouse.get("decision_cutoff_ms") == gate["cutoff_ms"]
          and native_price_query.get("price_query_sha256")
              == gate["core_245_price_query_sha256"]
              == factory_ack["core_245_price_query_sha256"]
          and local_query.get("query_sha256")
              == gate["core_253_query_local_sha256"]
              == factory_ack["core_253_query_local_sha256"]
          and native_price_query.get("price_query_sha256")
              != local_query.get("query_sha256")
          and local_query.get("historical_pit") == "NOT_ATTESTED",
          "CORE_SOURCE_QUERY_PARENTS")
    # Recompute both domain identities from the original Core-issued receipts.
    _need(bind_dual_query_identities(native_price_query, local_query, warehouse)
          == identity_map, "DUAL_QUERY_MAP_MISMATCH")
    # Re-read durable Core SQLite + immutable stage bytes, rather than trusting
    # a caller-supplied signed price array alone.
    verified_query = query_local(
        core_root, local_query["dataset_id"], local_query["version"],
        local_query["start_ms"], local_query["end_exclusive_ms"],
        local_query["decision_cutoff_ms"],
        required_source_sha256=gate["source_zip_sha256"],
        require_complete=True)
    _need(verified_query == local_query and local_query.get("coverage") == "COMPLETE"
          and local_query.get("missing_bar_opens") == []
          and local_query.get("available_bar_count") == 8
          and local_query.get("required_bar_count") == 8
          and len(local_query.get("bars", [])) == 8
          and warehouse.get("bar_count") == 8,
          "DURABLE_8_BAR_REPLAY")
    bars = local_query["bars"]
    prev = None
    close_values = []
    total_volume = Decimal(0)
    movement = {"UP": 0, "DOWN": 0, "FLAT": 0}
    for index, bar in enumerate(bars):
        t = bar.get("bar_open_ms")
        end = bar.get("bar_close_ms")
        _need(type(t) is int
              and t == local_query["start_ms"] + index * 900_000
              and type(end) is int and end == t + 900_000 - 1
              and type(bar.get("observation_lower_bound_ms")) is int
              and end < bar["observation_lower_bound_ms"] <= gate["cutoff_ms"]
              and bar.get("historical_known_at_ms") is None
              and type(bar.get("bar_checksum")) is str
              and len(bar["bar_checksum"]) == 64,
              "BAR_GRID_CLOCK_OR_CHECKSUM")
        o, h, l, c, v = (_number(bar.get(key)) for key in
                          ("open", "high", "low", "close", "volume"))
        _need(Decimal(0) < l <= o <= h and l <= c <= h and v >= 0,
              "OHLCV_COHERENCE")
        movement["UP" if c > o else "DOWN" if c < o else "FLAT"] += 1
        total_volume += v
        close_values.append(c)
        prev = t
    # Descriptive observation only: forward closes were not known at a prior
    # decision timestamp. Do not use these as predictive strategy signals.
    observed = []
    for i in range(len(close_values) - 1):
        ret = (close_values[i+1] / close_values[i]) - 1
        observed.append({
            "bar_open_ms": bars[i]["bar_open_ms"],
            "next_bar_open_ms": bars[i+1]["bar_open_ms"],
            "observed_next_close_return": str(ret),
            "causal_use": "POST_HOC_DIAGNOSTIC_ONLY",
        })
    lab = _sealed_body({
        "schema": LAB_SCHEMA, "route_id": route_id,
        "decision": "DESCRIPTIVE_COMPUTED_SYNTHETIC_TEST_ONLY",
        "secretary_receipt_sha256": snap["route_receipt_sha256"],
        "factory_consumer_ack_sha256": factory_ack["consumer_ack_sha256"],
        "strategy_gate_sha256": gate["gate_sha256"],
        "scanner_c_approval_sha256": gate["scanner_c_approval_sha256"],
        "scanner_d_handoff_sha256": handoff.sha256,
        "core_d_witness_sha256": witness.sha256,
        "source_ack_sha256": gate["source_ack_sha256"],
        "source_zip_sha256": gate["source_zip_sha256"],
        "warehouse_receipt_sha256": warehouse["receipt_sha256"],
        "core_245_price_query_sha256": native_price_query["price_query_sha256"],
        "core_253_query_local_sha256": local_query["query_sha256"],
        "dual_query_map_sha256": identity_map["identity_map_sha256"],
        "strategy_id": gate["strategy_id"],
        "strategy_version": gate["strategy_version"],
        "config_digest": gate["config_digest"],
        "strategy_definition_digest": gate["strategy_definition_digest"],
        "symbol": "AAA", "timeframe": "15m",
        "cutoff_ms": gate["cutoff_ms"],
        "observed_bar_count": len(bars),
        "post_hoc_one_bar_observations": observed,
        "observed_one_bar_denominator": len(observed),
        "bar_direction_census": movement,
        "total_observed_volume": str(total_volume),
        "strategy_rule_performance": "NOT_EVALUATED_NO_TRIAL_TIMELINE",
        "estimated_alpha": None, "modeled_fills": None,
        "source_evidence": "SYNTHETIC_TEST_ONLY_NOT_PUBLISHER",
        "historical_pit": "NOT_ATTESTED",
        "historical_known_at_ms": None,
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "operational_scanner_status": "UNKNOWN",
        "holdout": "SEALED_UNOPENED",
        "paper_execution": "NOT_ACTIVATED", "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0, "actual_fills": None,
    }, "lab_sha256")
    # Invoke native isolated Paper primitives; no broker, no ledger mutation.
    ledger = PositionLedger()
    _need(not ledger.positions and not ledger.events, "PAPER_LEDGER_NOT_EMPTY")
    delivery_id = digest({
        "lab_sha256": lab["lab_sha256"],
        "strategy_gate_sha256": gate["gate_sha256"],
        "policy": "D_SYNTHETIC_NO_PIT_OPERATIONAL_PAPER_FORBIDDEN",
    })
    intent = asdict(PaperIntent(lab["lab_sha256"], delivery_id, "declined"))
    paper = _sealed_body({
        "schema": PAPER_SCHEMA, "route_id": route_id,
        "lab_sha256": lab["lab_sha256"],
        "strategy_gate_sha256": gate["gate_sha256"],
        "factory_consumer_ack_sha256": factory_ack["consumer_ack_sha256"],
        "source_zip_sha256": gate["source_zip_sha256"],
        "decision": "REJECT",
        "decision_reason": "SYNTHETIC_TEST_ONLY_NO_PIT_NO_OPERATIONAL_15M",
        "native_paper_intent": intent,
        "native_position_ledger_invoked": True,
        "paper_execution": "NOT_ACTIVATED",
        "work235_actual_route": "NOT_CONNECTED_15M_UNSUPPORTED",
        "paper_authority": "NONE", "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0,
        "paper_position_events": 0, "actual_fills": None,
        "historical_pit": "NOT_ATTESTED",
        "holdout": "SEALED_UNOPENED",
    }, "paper_sha256")
    combined = _sealed_body({
        "schema": BATCH_SCHEMA, "route_id": route_id,
        "decision": "TEST_ONLY_LAB_COMPLETE_PAPER_REJECTED",
        "core_secretary_receipt_sha256": snap["route_receipt_sha256"],
        "strategy_gate_sha256": gate["gate_sha256"],
        "factory_consumer_ack_sha256": factory_ack["consumer_ack_sha256"],
        "lab_sha256": lab["lab_sha256"],
        "isolated_paper_sha256": paper["paper_sha256"],
        "source_zip_sha256": gate["source_zip_sha256"],
        "core_245_price_query_sha256": native_price_query["price_query_sha256"],
        "core_253_query_local_sha256": local_query["query_sha256"],
        "observed_bar_count": 8, "decision_slots": 7,
        "lab_actual_computation": True,
        "paper_native_interface_checked": True,
        "historical_pit": "NOT_ATTESTED",
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "holdout": "SEALED_UNOPENED",
        "paper_execution": "NOT_ACTIVATED",
        "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0, "actual_fills": None,
    }, "batch_sha256")
    return {"secretary": snap, "lab": lab, "paper": paper,
            "batch": combined}
