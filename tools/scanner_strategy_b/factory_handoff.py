"""Scanner-owned immutable handoff bundle for Factory's ONE new-delta software gate.

Receipts are verification anchors, not instructions to Factory/Paper. This
module never mutates Core Secretary, Factory Lab, or broker state. It binds
the independently obtained Scanner strategy census and source-only
Core/Secretary receipts without converting historical UNKNOWN to SELECTED.
"""
from __future__ import annotations

from collections import Counter

from tools.strategy_service_offline.common import Frozen, digest, require

SCHEMA = "aql.scanner-b.factory-handoff.v1"
STATES = ("SELECTED", "REJECTED", "UNKNOWN", "UNSCANNED", "INELIGIBLE", "FAILED")


def prepare_factory_handoff(native_run_receipt, source_route_receipt, ack_check_receipt,
                            *, expected_source_zip_sha256, expected_core245_sha256,
                            expected_core253_sha256):
    """Bind tested synthetic Scanner census + *separate* original source route.

    Synthetic test-only strategy results MUST NOT inherit historical authority
    from the separate Core original RAW/warehouse receipt. No same-source
    authentic strategy-evaluation assertion is made.
    """
    run = Frozen.restore(native_run_receipt)
    source = Frozen.restore(source_route_receipt)
    ack = Frozen.restore(ack_check_receipt)
    scan, route, check = run.data, source.data, ack.data
    require(scan.get("schema") == "aql.scanner.strategy-native15m-test-only.v1"
            and scan.get("operational_scanner_status") == "UNKNOWN"
            and scan.get("work235_native_15m") == "NOT_CONNECTED_15M_UNSUPPORTED"
            and scan.get("paper_execution") == "NOT_ACTIVATED"
            and scan.get("trading_authority") == "NONE",
            "FACTORY_HANDOFF_SCANNER_SCOPE")
    require(route.get("schema") == "aql.scanner-b.core-secretary-source-route.v1"
            and route.get("operational_scanner_status") == "UNKNOWN"
            and route.get("strategy_decision") == "NOT_PERFORMED"
            and route.get("historical_known_at_ms") is None
            and route.get("trading_authority") == "NONE"
            and route.get("source_zip_sha256") == expected_source_zip_sha256
            and route.get("core_245_price_query_sha256") == expected_core245_sha256
            and route.get("core_253_query_local_sha256") == expected_core253_sha256,
            "FACTORY_HANDOFF_SOURCE_QUERY_DOMAIN")
    require(check.get("schema") == "aql.scanner-b.secretary-ack-check.v1"
            and check.get("source_route_sha256") == source.sha256
            and check.get("state") in ("WAIT", "ACKED_SOURCE_ONLY")
            and check.get("paper_execution") == "NOT_ACTIVATED"
            and check.get("trading_authority") == "NONE",
            "FACTORY_HANDOFF_ACK_CONTRACT")
    if check["state"] == "WAIT":
        require(check.get("reason") in ("MISSING_SECRETARY_ACK", "QUARANTINED_NOMINATION")
                and check.get("factory_consumer_receipt_sha256") is None,
                "FACTORY_HANDOFF_WAIT_REASON")
    else:
        require(type(check.get("core_ack_receipt_sha256")) is str
                and len(check["core_ack_receipt_sha256"]) == 64
                and type(check.get("factory_consumer_receipt_sha256")) is str
                and len(check["factory_consumer_receipt_sha256"]) == 64
                and check.get("strategy_decision") == "NOT_PERFORMED",
                "FACTORY_HANDOFF_SOURCE_ACK_NOT_STRATEGY")
    require(type(expected_source_zip_sha256) is str
            and type(expected_core245_sha256) is str
            and type(expected_core253_sha256) is str
            and all(len(x) == 64 for x in (
                expected_source_zip_sha256, expected_core245_sha256, expected_core253_sha256)),
            "FACTORY_HANDOFF_SHA_PIN")
    names = set()
    attempts = []
    census_by_strategy = {}
    require(type(scan.get("nominations")) is list,
            "FACTORY_HANDOFF_NOMINATIONS_MISSING")
    for receipt in scan["nominations"]:
        item = Frozen.restore(receipt)
        n = item.data
        identity = (n.get("strategy_id"), n.get("strategy_version"),
                    n.get("config_digest"), n.get("symbol"))
        require(identity not in names and all(type(x) is str and bool(x) for x in identity),
                "FACTORY_HANDOFF_DUPLICATE_STRATEGY_SYMBOL")
        names.add(identity)
        require(n.get("schema") == "aql.scanner.native15m-strategy-nomination.v1"
                and n.get("run_id") == scan.get("run_id")
                and n.get("timeframe") == "15m"
                and n.get("status") in STATES
                and n.get("trading_authority") == "NONE"
                and n.get("publishable") is False
                and n.get("delivery_authorized") is False
                and n.get("operational_scanner_status") == "UNKNOWN"
                and n.get("feature_snapshot_sha256") == digest(n["feature_evidence"]),
                "FACTORY_HANDOFF_NOMINATION_IDENTITY_OR_AUTHORITY")
        key = (n["strategy_id"], n["strategy_version"], n["config_digest"])
        census_by_strategy.setdefault(key, []).append(n)
        attempts.append({
            "strategy_id": n["strategy_id"], "strategy_version": n["strategy_version"],
            "config_digest": n["config_digest"],
            "strategy_definition_digest": n["strategy_definition_digest"],
            "symbol": n["symbol"], "timeframe": "15m",
            "attempt_id": n["attempt_id"], "status": n["status"],
            "nomination_sha256": item.sha256,
            "source_manifest_sha256": n["source_manifest_sha256"],
            "source_raw_sha256": n["source_raw_sha256"],
            "cutoff_ms": n["cutoff_ms"],
        })
    require(len(attempts) > 0, "FACTORY_HANDOFF_NO_NOMINATIONS")
    require(scan.get("source_status") == "SYNTHETIC_TEST_ONLY_NATIVE_15M"
            or all(n["status"] not in ("SELECTED", "REJECTED")
                   for rows in census_by_strategy.values() for n in rows),
            "FACTORY_HANDOFF_NON_PIT_SELECTION")
    require(all(n["source_raw_sha256"] == attempts[0]["source_raw_sha256"]
                and n["source_manifest_sha256"] == attempts[0]["source_manifest_sha256"]
                and n["cutoff_ms"] == attempts[0]["cutoff_ms"]
                for n in attempts), "FACTORY_HANDOFF_CROSS_SOURCE_CUTOFF")
    totals = []
    for identity, rows in sorted(census_by_strategy.items()):
        state_counts = Counter(n["status"] for n in rows)
        counted = {state.lower(): state_counts[state] for state in STATES}
        require(len(rows) == rows[0].get("denominator")
                and all(n.get("denominator") == len(rows)
                        and n.get("strategy_census") == counted for n in rows),
                "FACTORY_HANDOFF_DENOMINATOR_DRIFT")
        totals.append({"strategy_id": identity[0], "strategy_version": identity[1],
                       "config_digest": identity[2], "denominator": len(rows),
                       "census": counted})
    require(sum(x["denominator"] for x in totals) == len(attempts),
            "FACTORY_HANDOFF_TOTAL_DENOMINATOR")
    policy_config = {a["config_digest"] for a in attempts}
    require(route["work235_config_digest"] not in policy_config,
            "FACTORY_HANDOFF_SYNTHETIC_AND_HISTORICAL_CONFIG_ALIAS")
    return Frozen.build({
        "schema": SCHEMA, "scanner_run_sha256": run.sha256,
        "source_route_sha256": source.sha256, "secretary_ack_check_sha256": ack.sha256,
        "source_zip_sha256": expected_source_zip_sha256,
        "core_245_price_query_sha256": expected_core245_sha256,
        "core_253_query_local_sha256": expected_core253_sha256,
        "synthetic_native15m_strategy_attempts": attempts,
        "synthetic_native15m_strategy_census": totals,
        "synthetic_attempt_denominator": len(attempts),
        "secretary_source_only_state": check["state"],
        "secretary_source_only_ack_sha256": check.get("core_ack_receipt_sha256"),
        "strategy_to_original_source": "NOT_CONNECTED_NO_PIT_PROMOTION",
        "source_only_is_strategy_selection": False,
        "discoverer_dependency": "OPTIONAL",
        "operational_scanner_status": "UNKNOWN",
        "work235_native_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
        "factory_lab_activation": "NOT_AUTHORIZED_BY_SCANNER",
        "paper_execution": "NOT_ACTIVATED", "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0, "actual_fills": None,
    })
