"""ATLAS C shared strategy identity, explicitly governed TEST_ONLY approval.

No approved operational policy registry is connected; approval is a distinct
offline engineering action, not a Scanner SELECTED or Core Secretary source ACK.
The canonical seal uses Work #235 Frozen SHA semantics. A validated native15m
policy from Scanner B is required; production/PIT authority cannot be minted.
"""
from __future__ import annotations

import re

from tools.strategy_service_offline.common import Frozen, digest, require
from tools.strategy_service_offline.screening import StrategyScreeningSpec
from tools.scanner_strategy_b.native15m import native_15m_policy, verify_policy

HEX64 = re.compile(r"^[a-f0-9]{64}$")
APPROVAL_SCHEMA = "aql.scanner-c.strategy-approval.v1"
REQUEST_SCHEMA = "aql.scanner-c.strategy-route-request.v1"
OFFLINE_AUTHORITY = "NONE"


def _sha(value, name):
    require(type(value) is str and HEX64.fullmatch(value) is not None, name)


def _identity(work_spec, native_policy):
    work = StrategyScreeningSpec.restore_spec(work_spec)
    policy = verify_policy(native_policy, work_spec)
    p, w = policy.data, work.data
    require(w["scope"] == "TEST_ONLY_UNAPPROVED_POLICY"
            and w["paper_approval"] == "NOT_FOUND"
            and p["trading_authority"] == OFFLINE_AUTHORITY
            and p["approved_paper_registry"] == "NOT_CONNECTED"
            and p["timeframe"] == "15m"
            and p["operational_work235_15m"] == "NOT_CONNECTED_15M_UNSUPPORTED",
            "STRATEGY_15M_POLICY_SCOPE")
    return {
        "strategy_id": p["strategy_id"],
        "strategy_version": p["strategy_version"],
        "config_digest": p["config_digest"],
        "work235_config_digest": w["config_digest"],
        "definition_digest": p["definition"]["digest"],
        "dna_digest": p["dna"]["digest"],
        "work235_spec_sha256": work.sha256,
        "native15m_policy_sha256": policy.sha256,
        "market": p["market"], "timeframe": "15m",
    }


def explicit_test_only_approval(work_spec_receipt, native_policy_receipt, *,
                                action, governance_policy_id, approver_id,
                                approval_nonce):
    """Only an explicit caller action can issue a sealed engineering approval.

    A selected nomination or Core ACK are intentionally NOT accepted as inputs.
    This call creates no persistent approval registry, no broker/Paper access.
    Repeated identical inputs produce the same seal (no implicit wall clock).
    """
    identity = _identity(work_spec_receipt, native_policy_receipt)
    require(action in ("APPROVE_TEST_ONLY", "DENY_TEST_ONLY"),
            "EXPLICIT_GOVERNANCE_ACTION_REQUIRED")
    require(all(type(v) is str and 1 <= len(v) <= 96 and
                re.fullmatch(r"[a-zA-Z0-9_.:-]+", v) is not None
                for v in (governance_policy_id, approver_id, approval_nonce)),
            "GOVERNANCE_ACTION_IDENTITY_REQUIRED")
    decision = "APPROVED_TEST_ONLY" if action == "APPROVE_TEST_ONLY" else "DENIED_TEST_ONLY"
    return Frozen.build({
        "schema": APPROVAL_SCHEMA, **identity,
        "decision": decision, "governance_action": action,
        "governance_policy_id": governance_policy_id,
        "approver_id": approver_id, "approval_nonce": approval_nonce,
        "source_custody_status": "NOT_ATTESTED_BY_APPROVAL",
        "scanner_nomination_status": "NOT_ATTESTED_BY_APPROVAL",
        "strategy_governance_status": decision,
        "scope": "SYNTHETIC_OFFLINE_ENGINEERING_ONLY",
        "historical_pit_authority": "NOT_ATTESTED",
        "operational_work235_native15m": "NOT_CONNECTED_15M_UNSUPPORTED",
        "operational_paper_authority": "NONE",
        "trading_authority": OFFLINE_AUTHORITY,
        "paper_execution": "NOT_ACTIVATED",
    })


def verify_test_only_approval(approval_receipt, work_spec_receipt, native_policy_receipt):
    """Verify policy and explicit action; never infer approval from source ACK."""
    r = Frozen.restore(approval_receipt)
    d = r.data
    identity = _identity(work_spec_receipt, native_policy_receipt)
    require(d.get("schema") == APPROVAL_SCHEMA and all(d.get(k) == v for k, v in identity.items()),
            "APPROVAL_STRATEGY_POLICY_DRIFT")
    require(d.get("governance_action") in ("APPROVE_TEST_ONLY", "DENY_TEST_ONLY")
            and d.get("decision") == (
                "APPROVED_TEST_ONLY" if d["governance_action"] == "APPROVE_TEST_ONLY"
                else "DENIED_TEST_ONLY")
            and d.get("strategy_governance_status") == d["decision"],
            "APPROVAL_ACTION_SEAL_DRIFT")
    expected = explicit_test_only_approval(
        work_spec_receipt, native_policy_receipt,
        action=d["governance_action"], governance_policy_id=d["governance_policy_id"],
        approver_id=d["approver_id"], approval_nonce=d["approval_nonce"])
    require(expected.data == d, "APPROVAL_SCOPE_OR_FIELD_DRIFT")
    return r


def _verify_scan_parent(scan_run_receipt, nomination_receipt, policy):
    run, nomination = Frozen.restore(scan_run_receipt), Frozen.restore(nomination_receipt)
    x, n = run.data, nomination.data
    require(x.get("schema") == "aql.scanner.strategy-native15m-test-only.v1"
            and x.get("operational_scanner_status") == "UNKNOWN"
            and x.get("work235_native_15m") == "NOT_CONNECTED_15M_UNSUPPORTED"
            and x.get("source_status") == "SYNTHETIC_TEST_ONLY_NATIVE_15M"
            and x.get("trading_authority") == "NONE",
            "SCANNER_C_SYNTHETIC_SOURCE_REQUIRED")
    require(type(x.get("nominations")) is list
            and sum(1 for q in x["nominations"] if Frozen.restore(q).sha256 == nomination.sha256) == 1,
            "SCANNER_C_NOMINATION_PARENT_MISSING_OR_DUPLICATE")
    require(n.get("schema") == "aql.scanner.native15m-strategy-nomination.v1"
            and n.get("run_id") == x["run_id"]
            and n.get("strategy_id") == policy["strategy_id"]
            and n.get("strategy_version") == policy["strategy_version"]
            and n.get("config_digest") == policy["config_digest"]
            and n.get("strategy_definition_digest") == policy["definition_digest"]
            and n.get("market") == policy["market"]
            and n.get("timeframe") == "15m"
            and n.get("evidence_class") == "TEST_ONLY"
            and n.get("operational_scanner_status") == "UNKNOWN"
            and n.get("trading_authority") == "NONE"
            and n.get("publishable") is False
            and n.get("delivery_authorized") is False
            and n.get("feature_snapshot_sha256") == digest(n["feature_evidence"]),
            "SCANNER_C_NOMINATION_IDENTITY_OR_AUTHORITY")
    source_identity = {(Frozen.restore(q).data["source_raw_sha256"],
                        Frozen.restore(q).data["source_manifest_sha256"],
                        Frozen.restore(q).data["universe_sha256"],
                        Frozen.restore(q).data["cutoff_ms"])
                       for q in x["nominations"]}
    require(len(source_identity) == 1
            and (n["source_raw_sha256"], n["source_manifest_sha256"],
                 n["universe_sha256"], n["cutoff_ms"]) in source_identity,
            "SCANNER_C_SOURCE_CUTOFF_DRIFT")
    strategy_rows = [Frozen.restore(q).data for q in x["nominations"]
                     if Frozen.restore(q).data["config_digest"] == policy["config_digest"]]
    require(len(strategy_rows) == n.get("denominator")
            and len({z["symbol"] for z in strategy_rows}) == len(strategy_rows)
            and n.get("strategy_census") == {
                name.lower(): sum(z["status"] == name for z in strategy_rows)
                for name in ("SELECTED", "REJECTED", "UNKNOWN", "UNSCANNED", "INELIGIBLE", "FAILED")},
            "SCANNER_C_STRATEGY_DENOMINATOR")
    return run, nomination


def seal_strategy_route_request(work_spec_receipt, native_policy_receipt,
                                approval_receipt, scan_run_receipt, nomination_receipt,
                                *, source_custody_receipt_sha256, core245_price_query_sha256,
                                core253_query_local_sha256, source_zip_sha256,
                                historical_known_at_ms=None, source_custody_status="TEST_ONLY_ATTESTED",
                                strategy_secretary_status="NOT_ENQUEUED"):
    """Build a deterministic sealed route proposal; NEVER performs Core enqueue.

    Synthetic Scanner raw-source SHA and separately pinned historical source
    ZIP SHA are *not* presumed equal or same-origin. The genuine Core
    Secretary strategy-level durable queue must be supplied by Core C later.
    """
    identity = _identity(work_spec_receipt, native_policy_receipt)
    approval = verify_test_only_approval(
        approval_receipt, work_spec_receipt, native_policy_receipt)
    run, nomination = _verify_scan_parent(scan_run_receipt, nomination_receipt, identity)
    n = nomination.data
    for label, value in (
        ("SOURCE_CUSTODY_RECEIPT_SHA", source_custody_receipt_sha256),
        ("CORE245_PRICE_QUERY_SHA", core245_price_query_sha256),
        ("CORE253_QUERY_LOCAL_SHA", core253_query_local_sha256),
        ("SOURCE_ZIP_SHA", source_zip_sha256),
        ("SCANNER_SOURCE_SHA", n["source_raw_sha256"]),
        ("SCANNER_MANIFEST_SHA", n["source_manifest_sha256"])):
        _sha(value, label)
    require(core245_price_query_sha256 != core253_query_local_sha256,
            "CORE_QUERY_SHA_DOMAINS_ALIASED")
    require(historical_known_at_ms is None, "HISTORICAL_KNOWN_AT_NOT_ATTESTED")
    require(source_custody_status in ("TEST_ONLY_ATTESTED", "RETROSPECTIVE_NON_PIT")
            and strategy_secretary_status == "NOT_ENQUEUED",
            "SOURCE_OR_SECRETARY_STATUS_AUTHORITY")
    eligible = (
        approval.data["decision"] == "APPROVED_TEST_ONLY"
        and n["status"] == "SELECTED"
        and source_custody_status == "TEST_ONLY_ATTESTED"
    )
    decision = "ROUTE_CANDIDATE_TEST_ONLY" if eligible else "WAIT"
    return Frozen.build({
        "schema": REQUEST_SCHEMA, **identity,
        "strategy_approval_sha256": approval.sha256,
        "strategy_governance_status": approval.data["decision"],
        "governance_policy_id": approval.data["governance_policy_id"],
        "scanner_run_sha256": run.sha256,
        "scanner_nomination_sha256": nomination.sha256,
        "scanner_nomination_status": n["status"],
        "scanner_operational_status": "UNKNOWN",
        "scanner_attempt_id": n["attempt_id"],
        "scanner_symbol": n["symbol"],
        "symbol": n["symbol"], "cutoff_ms": n["cutoff_ms"],
        "source_raw_sha256": n["source_raw_sha256"],
        "source_manifest_sha256": n["source_manifest_sha256"],
        "universe_sha256": n["universe_sha256"],
        "denominator": n["denominator"],
        "strategy_census": n["strategy_census"],
        "source_custody_status": source_custody_status,
        "source_custody_receipt_sha256": source_custody_receipt_sha256,
        "source_zip_sha256": source_zip_sha256,
        "core245_price_query_sha256": core245_price_query_sha256,
        "core253_query_local_sha256": core253_query_local_sha256,
        "historical_known_at_ms": None,
        "strategy_secretary_status": strategy_secretary_status,
        "source_secretary_ack_is_strategy_approval": False,
        "strategy_route_status": decision,
        "approval_is_synthetic_test_only": True,
        "paper_authority": "NONE",
        "trading_authority": "NONE",
        "paper_execution": "NOT_ACTIVATED", "orders_created": 0,
        "paper_positions": 0, "actual_fills": None,
        "work235_operational_15m_status": "NOT_CONNECTED_15M_UNSUPPORTED",
        "g0_status": "NOT_APPROVED",
    })


def verify_strategy_route_request(route_receipt, work_spec_receipt, native_policy_receipt,
                                  approval_receipt, scan_run_receipt, nomination_receipt,
                                  *, source_custody_receipt_sha256, core245_price_query_sha256,
                                  core253_query_local_sha256, source_zip_sha256):
    """Recompute a complete immutable proposal from its exact nested parents."""
    route = Frozen.restore(route_receipt)
    expected = seal_strategy_route_request(
        work_spec_receipt, native_policy_receipt, approval_receipt, scan_run_receipt,
        nomination_receipt,
        source_custody_receipt_sha256=source_custody_receipt_sha256,
        core245_price_query_sha256=core245_price_query_sha256,
        core253_query_local_sha256=core253_query_local_sha256,
        source_zip_sha256=source_zip_sha256)
    require(route.data == expected.data, "STRATEGY_ROUTE_PARENT_DRIFT")
    return route


def no_operational_paper(route_request_receipt):
    """Pure boundary: even APPROVED_TEST_ONLY is not Paper trading approval."""
    r = Frozen.restore(route_request_receipt)
    require(r.data.get("schema") == REQUEST_SCHEMA
            and r.data.get("paper_authority") == "NONE"
            and r.data.get("trading_authority") == "NONE",
            "STRATEGY_ROUTE_PAPER_AUTHORITY")
    return Frozen.build({
        "schema": "aql.scanner-c.paper-boundary.v1",
        "strategy_route_request_sha256": r.sha256,
        "decision": "WAIT",
        "reason": "OPERATIONAL_STRATEGY_SECRETARY_AND_PAPER_NOT_CONNECTED",
        "paper_execution": "NOT_ACTIVATED", "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0, "actual_fills": None,
    })
