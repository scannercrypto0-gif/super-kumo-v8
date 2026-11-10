"""Scanner C native15m strategy-aware service, reuse Work235 and Scanner B.

One immutable strategy config across explicit policy/approval/route receipts.
No real market or historical PIT source is allowed to become SELECTED.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_b.native15m import native_15m_policy, scan_native15m
from .approval_route import (
    explicit_test_only_approval, seal_strategy_route_request,
)


def scan_and_prepare_test_only_routes(
    work235_specs, raw, manifest, universe, *, cutoff_ms, symbol_budget,
    governance_actions, core_query_pins,
):
    """One native source, full strategy×symbol denominator and explicit actions.

    governance_actions is keyed by (strategy_id, strategy_version) and must
    contain explicit action, approver_id, governance_policy_id, approval_nonce.
    The new Core C strategy-level durable route remains a separate integration.
    """
    require(type(work235_specs) is list and 0 < len(work235_specs) <= 16,
            "C_STRATEGY_BUDGET")
    require(type(governance_actions) is dict and type(core_query_pins) is dict,
            "C_GOVERNANCE_AND_PINS_REQUIRED")
    policies = [native_15m_policy(w).receipt() for w in work235_specs]
    identities = {(p["payload"]["strategy_id"], p["payload"]["strategy_version"])
                  for p in policies}
    require(len(identities) == len(policies)
            and set(governance_actions) == identities,
            "C_EXACT_GOVERNANCE_ACTION_SET")
    require(set(core_query_pins) == {
        "source_custody_receipt_sha256", "core245_price_query_sha256",
        "core253_query_local_sha256", "source_zip_sha256",
        "source_custody_status",
    }, "C_CORE_QUERY_PIN_SCHEMA")
    run = scan_native15m(
        policies, work235_specs, raw, manifest, universe,
        cutoff_ms=cutoff_ms, symbol_budget=symbol_budget)
    approvals = {}
    for work, policy in zip(work235_specs, policies):
        key = (policy["payload"]["strategy_id"], policy["payload"]["strategy_version"])
        args = governance_actions[key]
        require(type(args) is dict and set(args) == {
            "action", "approver_id", "governance_policy_id", "approval_nonce",
        }, "C_EXPLICIT_APPROVAL_ARGUMENTS")
        approvals[key] = explicit_test_only_approval(
            work, policy, **args).receipt()
    routes = []
    for n in run.data["nominations"]:
        identity = (n["payload"]["strategy_id"], n["payload"]["strategy_version"])
        i = next(i for i, p in enumerate(policies)
                 if (p["payload"]["strategy_id"], p["payload"]["strategy_version"]) == identity)
        route = seal_strategy_route_request(
            work235_specs[i], policies[i], approvals[identity], run.receipt(), n,
            **core_query_pins)
        routes.append(route.receipt())
    require(len(routes) == len(work235_specs)*len(universe["members"]),
            "C_SILENT_SYMBOL_DENOMINATOR_LOSS")
    require(all(Frozen.restore(route).data["trading_authority"] == "NONE"
                for route in routes), "C_TRADING_AUTHORITY")
    return Frozen.build({
        "schema": "aql.scanner-c.shared-native15m-service.v1",
        "scanner_run": run.receipt(),
        "native15m_policies": policies,
        "strategy_approvals": [
            approvals[(p["payload"]["strategy_id"], p["payload"]["strategy_version"])]
            for p in policies],
        "strategy_route_requests": routes,
        "source_status": run.data["source_status"],
        "symbol_denominator": len(universe["members"]),
        "strategy_count": len(policies),
        "total_attempts": len(routes),
        "strategy_secretary_integration": "NOT_CONNECTED_CORE_C_REQUIRED",
        "factory_strategy_consumer": "NOT_CONNECTED_FACTORY_C_REQUIRED",
        "operational_paper": "NOT_CONNECTED",
        "trading_authority": "NONE",
    })
