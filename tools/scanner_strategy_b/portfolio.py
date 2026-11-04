"""Multi-timeframe strategy portfolio orchestrator over existing Work #235.

No new scanner engine, indicator library, evaluator, journal or trading stack.
Each distinct declared (market,timeframe) receives its own source, membership,
cutoff, config, and full denominator. Native 15m is the new TEST_ONLY adapter;
existing 5m/30m/1h/4h/1d reuses Work235.scan unmodified.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen, digest, require
from tools.strategy_service_offline.screening import StrategyScreeningSpec, scan as work235_scan, TF
from .native15m import native_15m_policy, scan_native15m


class PinnedNativeScannerWorker:
    """Reuse Work #235 existing Worker→Scanner #227 native admission port."""
    def call(self, component, action, body):
        require(component == "scanner" and action == "admit",
                "UNAUTHORIZED_DEPENDENCY_CALL")
        from tools.strategy_service_offline.worker import call
        return call(component, action, body)


def scan_strategy_groups(groups):
    """Run heterogeneous explicit source/timeframe groups deterministically.

    groups is a list of source-bounded dicts:
      {work235_specs, raw, manifest, universe, cutoff_ms, symbol_budget}
    Each spec is the complete existing Work #235 Frozen receipt. NO automatic
    resampling or cross-market feature cache; native15m policies are explicit.
    """
    require(type(groups) is list and 0 < len(groups) <= 16,
            "PORTFOLIO_GROUP_BUDGET")
    seen = set()
    outputs = []
    total = 0
    for group in groups:
        require(type(group) is dict and set(group) == {
            "work235_specs", "raw", "manifest", "universe", "cutoff_ms",
            "symbol_budget"}, "PORTFOLIO_GROUP_SCHEMA")
        work_specs = group["work235_specs"]
        require(type(work_specs) is list and 0 < len(work_specs) <= 16,
                "PORTFOLIO_STRATEGY_BUDGET")
        specs = [StrategyScreeningSpec.restore_spec(x) for x in work_specs]
        tf = group["manifest"].get("timeframe")
        market = group["manifest"].get("market")
        require(type(tf) is str and tf in set(TF) | {"15m"}
                and type(market) is str and bool(market),
                "PORTFOLIO_SOURCE_SCOPE")
        require(all(s.data["market"] == market for s in specs),
                "PORTFOLIO_MARKET_CONFIG")
        for spec in specs:
            identity = (spec.data["strategy_id"], spec.data["strategy_version"],
                        spec.data["config_digest"], market, tf)
            require(identity not in seen, "DUPLICATE_PORTFOLIO_STRATEGY_SOURCE")
            seen.add(identity)
        if tf == "15m":
            policies = [native_15m_policy(x).receipt() for x in work_specs]
            result = scan_native15m(
                policies, work_specs, group["raw"], group["manifest"],
                group["universe"], cutoff_ms=group["cutoff_ms"],
                symbol_budget=group["symbol_budget"])
            adapter = "SCANNER_NATIVE_15M_TEST_ONLY"
        else:
            require(all(s.data["timeframe"] == tf for s in specs),
                    "PORTFOLIO_TIMEFRAME_CONFIG_MISMATCH")
            result = work235_scan(
                specs, group["raw"], group["manifest"], group["universe"],
                cutoff_ms=group["cutoff_ms"], symbol_budget=group["symbol_budget"],
                deps=PinnedNativeScannerWorker())
            adapter = "EXISTING_WORK235_SCANNER227"
        r = result.data
        require(len(r["nominations"]) == len(specs)*len(group["universe"]["members"]),
                "PORTFOLIO_SILENT_DENOMINATOR_LOSS")
        for nomination in r["nominations"]:
            n = Frozen.restore(nomination).data
            require(n["timeframe"] == tf and n["market"] == market
                    and n["source_raw_sha256"] == group["manifest"]["raw_sha256"]
                    and n["status"] in ("SELECTED", "REJECTED", "UNKNOWN",
                                       "UNSCANNED", "INELIGIBLE", "FAILED")
                    and n["trading_authority"] == "NONE"
                    and n["publishable"] is False
                    and n["delivery_authorized"] is False,
                    "PORTFOLIO_CROSS_SOURCE_OR_AUTHORITY")
        total += len(r["nominations"])
        outputs.append({
            "timeframe": tf, "market": market, "adapter": adapter,
            "result": result.receipt(),
            "strategy_count": len(specs),
            "universe_denominator": len(group["universe"]["members"]),
            "strategy_symbol_attempts": len(r["nominations"]),
            "source_manifest_sha256": digest(group["manifest"]),
        })
    return Frozen.build({
        "schema": "aql.scanner-b.portfolio-research-run.v1",
        "groups": outputs, "group_count": len(outputs),
        "total_strategy_symbol_attempts": total,
        "denominator": sum(g["strategy_symbol_attempts"] for g in outputs),
        "no_cross_timeframe_resampling": True,
        "discoverer_dependency": "OPTIONAL",
        "historical_scanner_upgrade": "FORBIDDEN",
        "paper_execution": "NOT_ACTIVATED", "trading_authority": "NONE",
        "operational_work235_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
    })
