"""Secretary-only G2 read-only receipt. No Factory H2 route or approval authority.

Consumes a Core-verified immutable G2 observation export; emits a deterministic
SHA-sealed TEST_ONLY receipt. Neither source DB nor Secretary storage is mutated.
"""
from __future__ import annotations

from aql.observation.contracts import HORIZONS_MS, digest
from aql.observation.durable_bridge_v1 import sha

EXPORT_SCHEMA = "aql.core.g1-g2.verified-opportunity-read.v1"
RECEIPT_SCHEMA = "aql.secretary.g1-g2.observation-readonly-receipt.v1"
ACK_FIELDS = (
    "source_ack_sha256", "strategy_approval_sha256",
    "factory_consumer_ack_sha256", "research_review_ack_sha256",
)
EXPORT_FIELDS = frozenset((
    "schema", "snapshot_id", "snapshot", "g1_content_sha256",
    "g1_receipt_sha256", "scanner_opportunity_sha256",
    "scanner_decision_sha256", "scanner_policy_sha256",
    "strategy_definition_sha256", "strategy_config_sha256",
    "scanner_evaluator_sha256", "commit_return_ms", "as_of_ms",
    "horizons", "event_chain_tail_sha256", "test_only",
    "historical_pit", "trading_authority", "orders_enabled", "sha256",
))


class SecretaryReadStop(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise SecretaryReadStop(reason)


def consume_verified_opportunity(export):
    """Strict, pure deterministic consumer of genuine Core read-only export."""
    need(type(export) is dict and set(export) == EXPORT_FIELDS and
         export.get("schema") == EXPORT_SCHEMA and
         sha(export.get("sha256")) and
         export["sha256"] == digest({
             k: v for k, v in export.items() if k != "sha256"
         }), "EXPORT_CANONICAL_SEAL")
    need(export["test_only"] is True and
         export["historical_pit"] == "NOT_ATTESTED" and
         export["trading_authority"] == "NONE" and
         export["orders_enabled"] is False, "NO_AUTHORITY")
    pins = ("snapshot_id","g1_content_sha256","g1_receipt_sha256",
            "scanner_opportunity_sha256","scanner_decision_sha256",
            "scanner_policy_sha256","strategy_definition_sha256",
            "strategy_config_sha256","scanner_evaluator_sha256",
            "event_chain_tail_sha256")
    need(all(sha(export.get(k)) for k in pins), "PARENT_SHA")
    snap = export.get("snapshot")
    need(type(snap) is dict and
         snap.get("snapshot_id") == export["snapshot_id"] and
         snap["snapshot_id"] == digest({
             k: v for k, v in snap.items() if k != "snapshot_id"
         }) and
         type(export["as_of_ms"]) is int and
         type(export["commit_return_ms"]) is int and
         type(snap.get("decision_ms")) is int and
         type(snap.get("receipt_ms")) is int and
         export["commit_return_ms"] == snap["receipt_ms"] and
         export["commit_return_ms"] <= snap["decision_ms"] <=
             export["as_of_ms"] and
         snap.get("source") == "aql.scanner.g1-g2.test-only-opportunity.v1",
         "SNAPSHOT_TIME_OR_ID")
    horizon_records = export.get("horizons")
    need(type(horizon_records) is list and
         len(horizon_records) == len(HORIZONS_MS), "THREE_HORIZONS_REQUIRED")
    summary = []
    for expected_h, entry in zip(HORIZONS_MS, horizon_records):
        need(type(entry) is dict and set(entry) ==
             {"horizon_ms","identity","due_ms","state","observation"} and
             type(entry["horizon_ms"]) is int and
             entry["horizon_ms"] == expected_h and
             entry["identity"] == f'{export["snapshot_id"]}:{expected_h}' and
             type(entry["due_ms"]) is int and
             entry["due_ms"] == snap["decision_ms"] + expected_h,
             "HORIZON_IDENTITY_OR_ORDER")
        state, observation, due = (
            entry["state"],entry["observation"],entry["due_ms"])
        need(state in ("pending","mature","missing","UNKNOWN"),
             "HORIZON_STATE")
        if state in ("pending","UNKNOWN"):
            need(observation is None and
                 ((state == "pending" and export["as_of_ms"] < due) or
                  (state == "UNKNOWN" and export["as_of_ms"] >= due)),
                 "UNOBSERVED_TIME_OR_FABRICATION")
        else:
            need(type(observation) is dict and set(observation) == {
                "snapshot_id","horizon_ms","observed_ms","received_ms",
                "source","evidence_id","value","missing_reason"
            }, "OBSERVATION_SCHEMA")
            need(observation["snapshot_id"] == export["snapshot_id"] and
                 type(observation["horizon_ms"]) is int and
                 observation["horizon_ms"] == expected_h and
                 type(observation["observed_ms"]) is int and
                 type(observation["received_ms"]) is int and
                 due <= observation["observed_ms"] <=
                     observation["received_ms"] <= export["as_of_ms"] and
                 type(observation["source"]) is str and
                 bool(observation["source"]) and
                 type(observation["evidence_id"]) is str and
                 bool(observation["evidence_id"]), "OBSERVATION_PARENT_OR_TIME")
            if state == "mature":
                need(type(observation["value"]) is str and
                     bool(observation["value"]) and
                     observation["missing_reason"] is None,
                     "FABRICATED_MATURE")
            else:
                need(observation["value"] is None and
                     type(observation["missing_reason"]) is str and
                     bool(observation["missing_reason"]),
                     "FABRICATED_MISSING")
        summary.append(dict(horizon_ms=expected_h,state=state,
                            evidence_sha256=(digest(observation)
                                if observation is not None else None)))
    receipt = dict(schema=RECEIPT_SCHEMA,source_schema=EXPORT_SCHEMA,
        core_export_sha256=export["sha256"],
        event_chain_tail_sha256=export["event_chain_tail_sha256"],
        snapshot_id=export["snapshot_id"],
        scanner_opportunity_sha256=export["scanner_opportunity_sha256"],
        scanner_decision_sha256=export["scanner_decision_sha256"],
        g1_receipt_sha256=export["g1_receipt_sha256"],
        as_of_ms=export["as_of_ms"],horizons=summary,
        state="READ_ONLY_OBSERVATION_RECEIVED",test_only=True,
        historical_pit="NOT_ATTESTED",trading_authority="NONE",
        orders_enabled=False,orders=0,fills=0,
        **{k:None for k in ACK_FIELDS})
    return {**receipt,"receipt_sha256":digest(receipt)}


def read_secretary_receipt(bridge, snapshot_id, *, as_of_ms):
    """Read Core G2 directly; no Secretary state writes or implicit approvals."""
    return consume_verified_opportunity(
        bridge.read_verified_opportunity(snapshot_id,as_of_ms=as_of_ms))
