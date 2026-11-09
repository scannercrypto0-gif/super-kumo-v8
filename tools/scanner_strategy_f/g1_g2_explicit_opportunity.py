"""Scanner B: bounded TEST_ONLY G1-final → explicit opportunity issuer.

This is a narrow source/strategy decision adapter, NOT the historical H2
plugin, not a live scanner, not a G2 ledger and never trading authority.
Only an independently verified G1 Journal COMMIT-return receipt and a
matching explicit research decision can create an opportunity.
"""
from __future__ import annotations

import re

from src.aql.g1_integrity import content as bar_content, fingerprint
from src.aql.models.bar import MarketBar
from src.aql.observation.contracts import digest as g2_digest

SCHEMA = "aql.scanner.g1-g2.test-only-opportunity.v1"
DECISION_SCHEMA = "aql.scanner.g1-g2.explicit-test-decision.v1"
POLICY_SCHEMA = "aql.scanner.g1-g2.test-only-policy.v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
DECISION_STATES = ("ENTRY_SIGNAL", "EXIT_SIGNAL")
ALLOWED_POLICY = "TEST_ONLY_SYNTHETIC_OPPORTUNITY"
OPPORTUNITY_FIELDS = frozenset((
    "schema", "opportunity_key", "symbol", "interval", "source",
    "source_bar_open_ms", "source_bar_close_ms", "bar_checksum",
    "g1_stable_key", "g1_content_digest", "g1_receipt_sha256",
    "g1_receipt_ms", "decision_cutoff_ms", "decision_ms",
    "strategy_id", "strategy_version", "strategy_definition_sha256",
    "strategy_config_sha256", "strategy_evaluator_sha256",
    "strategy_decision_sha256", "decision_state", "policy_sha256",
    "source_availability", "test_only", "historical_pit",
    "source_ack_sha256", "strategy_approval_sha256",
    "factory_consumer_ack_sha256", "trading_authority",
    "orders_enabled", "sha256",
))
DECISION_FIELDS = frozenset((
    "schema", "strategy_id", "strategy_version",
    "strategy_definition_sha256", "strategy_config_sha256",
    "strategy_evaluator_sha256", "symbol", "interval",
    "bar_close_ms", "decision_cutoff_ms", "decision_state",
    "test_only", "sha256",
))
POLICY_FIELDS = frozenset((
    "schema", "policy_class", "test_only", "trading_authority",
    "strategy_approval_sha256", "sha256",
))


class OpportunityRejected(ValueError):
    """No eligible opportunity may be published."""


def need(condition, reason):
    if not condition:
        raise OpportunityRejected("SCANNER_G1_G2_" + reason)


def _sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _seal(payload):
    need(type(payload) is dict and "sha256" not in payload, "SEAL_FIELDS")
    return {**payload, "sha256": g2_digest(payload)}


def _verify(receipt, fields, schema):
    need(type(receipt) is dict and set(receipt) == fields
         and receipt.get("schema") == schema
         and _sha(receipt.get("sha256"))
         and receipt["sha256"] == g2_digest({
             k: v for k, v in receipt.items() if k != "sha256"
         }), "RECEIPT_SEAL_OR_SCHEMA")
    return receipt


def test_only_policy():
    """Inert policy receipt; no strategy approval or live entitlement."""
    return _seal({
        "schema": POLICY_SCHEMA,
        "policy_class": ALLOWED_POLICY,
        "test_only": True,
        "trading_authority": "NONE",
        "strategy_approval_sha256": None,
    })


def explicit_test_decision(
    *, symbol, interval, bar_close_ms, decision_cutoff_ms,
    strategy_id, strategy_version, strategy_definition_sha256,
    strategy_config_sha256, strategy_evaluator_sha256, decision_state,
):
    """Synthetic fixture decision provided by caller, never inferred per bar."""
    need(decision_state in DECISION_STATES, "NO_EXPLICIT_ACTION_SIGNAL")
    need(type(symbol) is str and bool(symbol)
         and type(interval) is str and bool(interval)
         and type(strategy_id) is str and bool(strategy_id)
         and type(strategy_version) is str and bool(strategy_version)
         and all(_sha(x) for x in (
             strategy_definition_sha256, strategy_config_sha256,
             strategy_evaluator_sha256,
         )) and type(bar_close_ms) is int and bar_close_ms >= 0
         and type(decision_cutoff_ms) is int
         and bar_close_ms < decision_cutoff_ms,
         "DECISION_SOURCE_OR_TEMPORAL_IDENTITY")
    return _seal({
        "schema": DECISION_SCHEMA,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "strategy_definition_sha256": strategy_definition_sha256,
        "strategy_config_sha256": strategy_config_sha256,
        "strategy_evaluator_sha256": strategy_evaluator_sha256,
        "symbol": symbol,
        "interval": interval,
        "bar_close_ms": bar_close_ms,
        "decision_cutoff_ms": decision_cutoff_ms,
        "decision_state": decision_state,
        "test_only": True,
    })


def verify_opportunity(receipt):
    x = _verify(receipt, OPPORTUNITY_FIELDS, SCHEMA)
    need(x["test_only"] is True
         and x["source_availability"] == "G1_COMMIT_RECEIPT_OBSERVED_TEST_ONLY"
         and x["historical_pit"] == "NOT_ATTESTED"
         and x["trading_authority"] == "NONE"
         and x["orders_enabled"] is False
         and all(x[k] is None for k in (
             "source_ack_sha256", "strategy_approval_sha256",
             "factory_consumer_ack_sha256",
         )), "AUTHORITY_MUST_BE_DENIED")
    need(type(x["symbol"]) is str and bool(x["symbol"])
         and type(x["interval"]) is str and bool(x["interval"])
         and x["source"] == "binance_ws"
         and type(x["source_bar_open_ms"]) is int
         and type(x["source_bar_close_ms"]) is int
         and type(x["g1_receipt_ms"]) is int
         and type(x["decision_cutoff_ms"]) is int
         and type(x["decision_ms"]) is int
         and x["source_bar_open_ms"] < x["source_bar_close_ms"]
         and x["source_bar_close_ms"] < x["g1_receipt_ms"]
         and x["g1_receipt_ms"] <= x["decision_ms"]
         and x["decision_ms"] == x["decision_cutoff_ms"]
         and type(x["strategy_id"]) is str and bool(x["strategy_id"])
         and type(x["strategy_version"]) is str
         and x["decision_state"] in DECISION_STATES
         and x["g1_stable_key"] ==
             f'{x["symbol"]}:{x["interval"]}:{x["source_bar_open_ms"]}'
         and all(_sha(x[k]) for k in (
             "bar_checksum", "g1_content_digest", "g1_receipt_sha256",
             "strategy_definition_sha256", "strategy_config_sha256",
             "strategy_evaluator_sha256", "strategy_decision_sha256",
             "policy_sha256", "opportunity_key",
         )), "OPPORTUNITY_FIELDS_OR_TIME")
    key_material = {
        "schema": SCHEMA,
        "g1_stable_key": x["g1_stable_key"],
        "strategy_id": x["strategy_id"],
        "strategy_version": x["strategy_version"],
        "strategy_definition_sha256": x["strategy_definition_sha256"],
        "strategy_config_sha256": x["strategy_config_sha256"],
        "strategy_evaluator_sha256": x["strategy_evaluator_sha256"],
        "policy_sha256": x["policy_sha256"],
    }
    need(x["opportunity_key"] == g2_digest(key_material),
         "OPPORTUNITY_IDENTITY_DRIFT")
    return x


def emit_explicit_opportunity(
    *, bar, journal, store, decision, policy, decision_ms,
    existing=None,
):
    """Read back *actual* G1 journal/store and independently supplied decision.

    Idempotent public synthetic issuance only. Caller/Core G2 owns any
    durable opportunity/observation index; existing is a comparison receipt
    and does not enable authorization or state mutation.
    """
    p = _verify(policy, POLICY_FIELDS, POLICY_SCHEMA)
    d = _verify(decision, DECISION_FIELDS, DECISION_SCHEMA)
    need(p["policy_class"] == ALLOWED_POLICY and p["test_only"] is True
         and p["trading_authority"] == "NONE"
         and p["strategy_approval_sha256"] is None,
         "UNKNOWN_POLICY")
    need(d["test_only"] is True and d["decision_state"] in DECISION_STATES
         and type(decision_ms) is int and decision_ms >= 0
         and d["decision_cutoff_ms"] == decision_ms,
         "EXPLICIT_DECISION_REQUIRED")
    need(type(bar) is MarketBar and bar.is_final is True
         and bar.source == "binance_ws"
         and bar.state.value in ("LOCAL_COMMITTED", "PERSISTED")
         and bar.ingested_at >= bar.bar_close + 1
         and bar.ingested_at <= decision_ms
         and bar.bar_close < decision_ms
         and bar.bar_open < bar.bar_close
         and bar.checksum == bar.compute_checksum()
         and d["symbol"] == bar.symbol and d["interval"] == bar.interval
         and d["bar_close_ms"] == bar.bar_close
         and all(_sha(d[k]) for k in (
             "strategy_definition_sha256", "strategy_config_sha256",
             "strategy_evaluator_sha256",
         )), "BAR_NOT_FINAL_OR_DECISION_MISMATCH")
    # G1 G0 temporal eligibility: source receipt cannot be forged from the
    # caller's bar or a pre-COMMIT MarketBar.committed_at field.
    try:
        journal.require_eligible(bar.stable_key())
        store.require_eligible(bar.stable_key())
        committed = journal.commit_receipt(bar.stable_key())
        with store._connect() as conn:
            row = conn.execute(
                "SELECT * FROM market_bars WHERE symbol=? AND interval=? "
                "AND bar_open=? AND NOT EXISTS ("
                "SELECT 1 FROM g1_integrity_events e "
                "WHERE e.stable_key=market_bars.symbol || ':' || "
                "market_bars.interval || ':' || market_bars.bar_open)",
                (bar.symbol, bar.interval, bar.bar_open),
            ).fetchone()
            stored = None
            if row is not None:
                fields = dict(row)
                fields.pop("id")
                fields["is_final"] = bool(fields["is_final"])
                stored = MarketBar.from_dict(fields)
        original = next((item for item in journal.replay(
            symbol=bar.symbol, interval=bar.interval, final_only=True,
        ) if item.stable_key() == bar.stable_key()), None)
    except Exception as exc:
        raise OpportunityRejected(
            "SCANNER_G1_G2_G1_REPLAY_UNAVAILABLE"
        ) from exc
    need(stored is not None and original is not None
         and bar_content(original) == bar_content(stored)
         and bar_content(original) == bar_content(bar)
         and stored.source == "binance_ws"
         and stored.checksum == stored.compute_checksum()
         and original.checksum == original.compute_checksum(),
         "G1_SOURCE_OR_STORE_DRIFT")
    expected = fingerprint(bar_content(original))
    need(committed.get("version") == 1
         and committed.get("status") == "SQLITE_COMMIT_RETURN_OBSERVED"
         and committed.get("content_digest") == expected
         and committed.get("record_contract_version") == 1
         and committed.get("physical_fsync_or_powerloss_verified") is False
         and type(committed.get("commit_return_observed_at_ms")) is int
         and bar.bar_close < committed["commit_return_observed_at_ms"]
         and committed["commit_return_observed_at_ms"] <= decision_ms,
         "G1_COMPLETION_RECEIPT_NOT_ELIGIBLE")
    committed_sha = g2_digest(committed)
    identity = {
        "schema": SCHEMA,
        "g1_stable_key": bar.stable_key(),
        "strategy_id": d["strategy_id"],
        "strategy_version": d["strategy_version"],
        "strategy_definition_sha256": d["strategy_definition_sha256"],
        "strategy_config_sha256": d["strategy_config_sha256"],
        "strategy_evaluator_sha256": d["strategy_evaluator_sha256"],
        "policy_sha256": p["sha256"],
    }
    key = g2_digest(identity)
    receipt = _seal({
        "schema": SCHEMA,
        "opportunity_key": key,
        "symbol": bar.symbol,
        "interval": bar.interval,
        "source": bar.source,
        "source_bar_open_ms": bar.bar_open,
        "source_bar_close_ms": bar.bar_close,
        "bar_checksum": bar.checksum,
        "g1_stable_key": bar.stable_key(),
        "g1_content_digest": expected,
        "g1_receipt_sha256": committed_sha,
        "g1_receipt_ms": committed["commit_return_observed_at_ms"],
        "decision_cutoff_ms": decision_ms,
        "decision_ms": decision_ms,
        "strategy_id": d["strategy_id"],
        "strategy_version": d["strategy_version"],
        "strategy_definition_sha256": d["strategy_definition_sha256"],
        "strategy_config_sha256": d["strategy_config_sha256"],
        "strategy_evaluator_sha256": d["strategy_evaluator_sha256"],
        "strategy_decision_sha256": d["sha256"],
        "decision_state": d["decision_state"],
        "policy_sha256": p["sha256"],
        "source_availability": "G1_COMMIT_RECEIPT_OBSERVED_TEST_ONLY",
        "test_only": True,
        "historical_pit": "NOT_ATTESTED",
        "source_ack_sha256": None,
        "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        "trading_authority": "NONE",
        "orders_enabled": False,
    })
    verify_opportunity(receipt)
    if existing is not None:
        verify_opportunity(existing)
        need(existing["opportunity_key"] == receipt["opportunity_key"]
             and existing == receipt, "DUPLICATE_CONFLICT")
    return receipt
