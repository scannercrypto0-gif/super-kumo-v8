"""Off-host forward research adapter using the exact audited historical strategy kernel.

This is engineering-only. It reads verified feed lineage, projects complete 15m
bars into a disposable research store, evaluates one current decision point,
and emits a research receipt. It never invokes historical Core/Factory consumers,
writes to the source feed, runs a Lab, or authorizes orders.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

BASELINE_COMMIT = "eb49308d61ffdfc24ed5032df2cb541f37c48bfe"
WAREHOUSE_COMMIT = "ae60b3e367241fec14753ac78e08147603b7af84"
STRATEGY_DIGEST = "bab9bac7e8cbb6dca5db21ba685a5027d2f197babbc2ec7c60468233a724aabf"
STEP_MS = 900_000
MAX_15M_BARS_PER_READ = 672  # #333's 10,080 one-minute source-window bound.
_HEX = set("0123456789abcdef")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _sha(value):
    return _sha_bytes(_canonical(value))


def _need(ok, code):
    if not ok:
        raise ValueError(code)


def _git_head(root):
    try:
        return subprocess.check_output(
            ["git", "-C", str(Path(root).resolve()), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        raise ValueError("PINNED_CHECKOUT_UNAVAILABLE") from None


def _is_under(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def _load_kernel(baseline_root, dependency_root):
    baseline = Path(baseline_root).resolve()
    deps = Path(dependency_root).resolve()
    _need(_git_head(baseline) == BASELINE_COMMIT, "ANALYZER_BASELINE_COMMIT_MISMATCH")
    _need(deps.is_dir(), "ANALYZER_STAGED_DEPENDENCIES_MISSING")
    plan_path = baseline / "tools" / "first_research_cycle" / "market-plan.json"
    anchor_path = plan_path.with_suffix(".sha256")
    _need(plan_path.is_file() and anchor_path.is_file(), "ANALYZER_BASELINE_PLAN_MISSING")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    _need(_sha(plan) == anchor_path.read_text(encoding="ascii").strip(),
          "ANALYZER_PLAN_PIN_MISMATCH")
    _need(plan.get("strategy", {}).get("digest") == STRATEGY_DIGEST,
          "ANALYZER_STRATEGY_PIN_MISMATCH")
    cycle_path = baseline / "tools" / "first_research_cycle" / "market_cycle.py"
    spec = importlib.util.spec_from_file_location("_aql_pinned_market_cycle", cycle_path)
    _need(spec is not None and spec.loader is not None, "ANALYZER_BASELINE_IMPORT_FAILED")
    cycle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cycle)
    # Reuses #296's exact import-origin and full transitive-file manifest checks.
    cycle.configure(deps, plan)

    factory_root = deps / "factory"
    _need(factory_root.is_dir(), "ANALYZER_FACTORY_DEPENDENCY_MISSING")
    if str(factory_root) not in [str(Path(p).resolve()) for p in sys.path if p]:
        sys.path.insert(0, str(factory_root))
    scanner_tools = deps / "scanner" / "tools"
    import tools
    if str(scanner_tools) not in [str(Path(p).resolve()) for p in tools.__path__]:
        tools.__path__.insert(0, str(scanner_tools))
    from research_wp_r0.strategy_definition import StrategyDefinition
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
    from research_wp_r0.aql_factory_historical_rule_projection import _vectors, _expression
    from tools.scanner_strategy_f.research_e2e_diagnostic import _eval_strategy

    evaluator_path = Path(inspect.getfile(_eval_strategy)).resolve()
    definition_path = Path(inspect.getfile(StrategyDefinition)).resolve()
    projection_path = Path(inspect.getfile(_vectors)).resolve()
    _need(_is_under(evaluator_path, deps / "scanner"), "ANALYZER_EVALUATOR_IMPORT_ORIGIN")
    _need(_is_under(definition_path, deps / "factory"), "ANALYZER_DEFINITION_IMPORT_ORIGIN")
    _need(_is_under(projection_path, deps / "factory"), "ANALYZER_KERNEL_IMPORT_ORIGIN")
    manifest = {item["path"]: item["sha256"] for item in plan["dependency_files"]}
    for path, root, relative in (
        (evaluator_path, deps / "scanner", "scanner/tools/scanner_strategy_f/research_e2e_diagnostic.py"),
        (definition_path, deps / "factory", "factory/research_wp_r0/strategy_definition.py"),
        (projection_path, deps / "factory", "factory/research_wp_r0/aql_factory_historical_rule_projection.py"),
    ):
        _need(relative in manifest, "ANALYZER_TRANSITIVE_FILE_MISSING:" + relative)
        _need(_sha_bytes(path.read_bytes()) == manifest[relative],
              "ANALYZER_TRANSITIVE_FILE_PIN_MISMATCH:" + relative)
    # The accepted reference stores a sealed {definition, digest} envelope.
    definition = StrategyDefinition.from_dict(
        plan["strategy"], registry=IndicatorRegistryV2())
    _need(definition.digest == STRATEGY_DIGEST, "ANALYZER_STRATEGY_PIN_MISMATCH")
    return {
        "plan": plan, "definition": definition, "evaluate": _eval_strategy,
        "vectors": _vectors, "expression": _expression,
        "kernel_identity": {
            "baseline_commit": BASELINE_COMMIT,
            "dependency_heads": dict(plan["dependency_heads"]),
            "dependency_manifest_sha256": _sha(plan["dependency_files"]),
            "scanner_evaluator_sha256": manifest["scanner/tools/scanner_strategy_f/research_e2e_diagnostic.py"],
            "factory_strategy_definition_sha256": manifest["factory/research_wp_r0/strategy_definition.py"],
            "factory_rule_kernel_sha256": manifest["factory/research_wp_r0/aql_factory_historical_rule_projection.py"],
            "strategy_definition_sha256": definition.digest,
        },
    }


def _warehouse_api(warehouse_root):
    root = Path(warehouse_root).resolve()
    _need(_git_head(root) == WAREHOUSE_COMMIT, "WAREHOUSE_COMMIT_MISMATCH")
    src = root / "src"
    _need(src.is_dir(), "WAREHOUSE_SOURCE_MISSING")
    if str(src) not in [str(Path(p).resolve()) for p in sys.path if p]:
        sys.path.insert(0, str(src))
    from aql.research_bar_store import ResearchBarStore
    from aql.research_timeframes import MINUTE, project_finalized_1m
    module_path = Path(inspect.getfile(ResearchBarStore)).resolve()
    timeframe_path = Path(inspect.getfile(project_finalized_1m)).resolve()
    _need(_is_under(module_path, src) and _is_under(timeframe_path, src),
          "WAREHOUSE_IMPORT_ORIGIN_MISMATCH")
    return ResearchBarStore, project_finalized_1m, MINUTE


def _decimal_to_float(text):
    _need(type(text) is str, "ANALYZER_DECIMAL_STRING_REQUIRED")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("ANALYZER_DECIMAL_INVALID") from None
    _need(value.is_finite() and value >= 0, "ANALYZER_DECIMAL_INVALID")
    converted = float(value)
    _need(math.isfinite(converted) and 0 <= converted < 1e100,
          "ANALYZER_NUMERIC_CONVERSION_INVALID")
    return converted


def _validated_config(config, expected_config_sha256, symbol, start_ms, bar_count,
                      adapter_code_sha256):
    required = {"schema", "symbol", "window_start_ms", "bar_count",
                "strategy_definition_sha256", "adapter_code_sha256",
                "max_age_ms", "max_signal_lag_ms"}
    _need(type(config) is dict and set(config) == required,
          "ANALYZER_CONFIG_FIELDS_INVALID")
    _need(config["schema"] == "atlas.realtime-market-feed.forward-analysis-config.v1"
          and config["symbol"] == symbol and config["window_start_ms"] == start_ms
          and config["bar_count"] == bar_count
          and config["strategy_definition_sha256"] == STRATEGY_DIGEST
          and config["adapter_code_sha256"] == adapter_code_sha256,
          "ANALYZER_CONFIG_IDENTITY_MISMATCH")
    _need(type(config["max_age_ms"]) is int and 1 <= config["max_age_ms"] <= 86_400_000
          and type(config["max_signal_lag_ms"]) is int
          and 1 <= config["max_signal_lag_ms"] <= STEP_MS,
          "ANALYZER_CONFIG_FRESHNESS_INVALID")
    _need(type(expected_config_sha256) is str and len(expected_config_sha256) == 64
          and set(expected_config_sha256) <= _HEX
          and _sha(config) == expected_config_sha256,
          "ANALYZER_CONFIG_PIN_MISMATCH")


def analyze_forward_window(feed_database, research_database, *, symbol, start_ms,
                           bar_count, decision_cutoff_ms, clock_evidence, config,
                           expected_config_sha256, expected_ws_producer_code_sha256,
                           expected_rest_producer_code_sha256, baseline_root,
                           dependency_root, warehouse_root,
                           allow_synthetic_fixture=False):
    """Evaluate only the latest finalized 15m decision in a complete bounded window."""
    # Load the pinned Warehouse package before importing its adapter; the adapter
    # imports the native `aql` package and must resolve from this exact checkout.
    ResearchBarStore, project_finalized_1m, minute_ms = _warehouse_api(warehouse_root)
    from tools.realtime_market_feed.atlas_integration import project_feed_window

    _need(type(symbol) is str and symbol.isalnum() and symbol == symbol.upper(),
          "ANALYZER_SYMBOL_INVALID")
    _need(type(start_ms) is int and start_ms >= 0 and start_ms % STEP_MS == 0
          and type(bar_count) is int and 8 <= bar_count <= MAX_15M_BARS_PER_READ,
          "ANALYZER_WINDOW_INVALID")
    _need(type(decision_cutoff_ms) is int and decision_cutoff_ms >= 0,
          "ANALYZER_DECISION_CLOCK_INVALID")
    adapter_code_sha256 = _sha_bytes(Path(__file__).read_bytes())
    _validated_config(config, expected_config_sha256, symbol, start_ms, bar_count,
                      adapter_code_sha256)
    clock_keys = {"schema", "method", "observed_at_ms", "uncertainty_ms"}
    _need(type(clock_evidence) is dict and set(clock_evidence) == clock_keys
          and clock_evidence.get("schema") == "atlas.realtime-market-feed.validated-clock.v1"
          and clock_evidence.get("method") == "WALL_MONOTONIC_BRACKET_V1"
          and type(clock_evidence.get("observed_at_ms")) is int
          and type(clock_evidence.get("uncertainty_ms")) is int
          and 0 <= clock_evidence["uncertainty_ms"] <= 2_000,
          "ANALYZER_CLOCK_EVIDENCE_INVALID")
    now_ms = clock_evidence["observed_at_ms"]
    _need(now_ms <= decision_cutoff_ms <= now_ms + clock_evidence["uncertainty_ms"],
          "ANALYZER_DECISION_CLOCK_UNBOUNDED")
    end_ms = start_ms + bar_count * STEP_MS
    _need(end_ms <= decision_cutoff_ms, "ANALYZER_WINDOW_NOT_CLOSED")
    feed_start = start_ms
    feed_end = end_ms
    feed = project_feed_window(
        feed_database, symbol=symbol, start_ms=feed_start, end_ms=feed_end,
        now_ms=now_ms, max_age_ms=config["max_age_ms"],
        allow_synthetic_fixture=allow_synthetic_fixture,
        expected_producer_code_sha256=expected_ws_producer_code_sha256,
        expected_rest_producer_code_sha256=expected_rest_producer_code_sha256,
        max_bars=bar_count * 15, include_lineage_evidence=True)
    one_minute = feed["bars"]
    lineage = feed["lineage"]
    _need(len(one_minute) == bar_count * 15 and len(lineage) == len(one_minute),
          "ANALYZER_1M_WINDOW_INCOMPLETE")
    _need(all(item["available_at_ms"] <= decision_cutoff_ms
              and item["finality"] == "FINAL" for item in lineage),
          "ANALYZER_INPUT_UNAVAILABLE_AT_CUTOFF")
    _need(_is_under(research_database, tempfile.gettempdir()),
          "ANALYZER_RESEARCH_STORE_MUST_BE_DISPOSABLE")
    _need(Path(feed_database).resolve() != Path(research_database).resolve(),
          "ANALYZER_SOURCE_RESEARCH_STORE_COLLISION")
    kernel = _load_kernel(baseline_root, dependency_root)

    # These writes are restricted to a disposable store. The source feed is read-only.
    with ResearchBarStore(research_database) as store:
        for bar, proof in zip(one_minute, lineage):
            input_bar = {
                "symbol": symbol, "interval": "1m", "open_ms": bar["open_ms"],
                "final": True, "o": bar["o"], "h": bar["h"], "l": bar["l"],
                "c": bar["c"], "v": bar["v"], "source_sha256": proof["receipt_sha256"],
                "available_at_ms": proof["available_at_ms"],
            }
            store.insert_1m(input_bar, source_class="FORWARD_UNQUALIFIED")
        projected = [store.project(symbol, "15m", start_ms + i * STEP_MS)
                     for i in range(bar_count)]
        # Idempotent re-read seals ensure no partial or conflicting timeframe write.
        projected = [store.read(symbol, "15m", row["open_ms"]) for row in projected]
    _need(all(row and row["source_class"] == "FORWARD_UNQUALIFIED"
              and row["trading_authority"] == "NONE" and row["pit_oos"] == "NOT_ATTESTED"
              for row in projected), "ANALYZER_PROJECTED_ROW_INVALID")
    _need(all(row["available_at_ms"] <= decision_cutoff_ms for row in projected),
          "ANALYZER_PROJECTED_ROW_UNAVAILABLE")
    latest = projected[-1]
    _need(decision_cutoff_ms - latest["close_exclusive_ms"]
          <= config["max_signal_lag_ms"], "ANALYZER_SIGNAL_SLOT_STALE")

    kernel_bars = []
    for row in projected:
        open_value = _decimal_to_float(row["o"])
        high_value = _decimal_to_float(row["h"])
        low_value = _decimal_to_float(row["l"])
        close_value = _decimal_to_float(row["c"])
        volume_value = _decimal_to_float(row["v"])
        _need(low_value <= min(open_value, close_value)
              <= max(open_value, close_value) <= high_value,
              "ANALYZER_KERNEL_OHLC_INVALID")
        kernel_bars.append({
            "bar_open_ms": row["open_ms"],
            "bar_close_ms": row["close_exclusive_ms"] - 1,
            "open": open_value, "high": high_value, "low": low_value,
            "close": close_value, "volume": volume_value,
        })
    evaluated = kernel["evaluate"](kernel["definition"], kernel_bars)
    _need(type(evaluated) is list and len(evaluated) == bar_count
          and evaluated[-1][0] == latest["close_exclusive_ms"] - 1
          and evaluated[-1][1] in {"ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL", "UNKNOWN"},
          "ANALYZER_KERNEL_OUTPUT_INVALID")
    latest_lineage = [item for item in lineage
                      if latest["open_ms"] <= item["open_ms"] < latest["close_exclusive_ms"]]
    recovered = [item for item in latest_lineage
                 if item["source_class"] == "BINANCE_SPOT_PUBLIC_REST_MARKET_DATA"]
    state = evaluated[-1][1]
    if recovered:
        state = "UNKNOWN_RECOVERED_INPUT"
    evidence_body = {
        "schema": "atlas.realtime-market-feed.forward-analysis-receipt.v1",
        "status": "FORWARD_RESEARCH_ONLY",
        "source": {
            "venue": "BINANCE", "market": "SPOT", "symbol": symbol,
            "interval": "15m", "source_class": "FORWARD_UNQUALIFIED",
            "source_receipt_sha256": [item["receipt_sha256"] for item in lineage],
            "ws_producer_code_sha256": expected_ws_producer_code_sha256,
            "rest_producer_code_sha256": expected_rest_producer_code_sha256,
            "availability_max_ms": max(item["available_at_ms"] for item in lineage),
            "source_snapshot_sha256": _sha([
                {key: item[key] for key in ("open_ms", "receipt_sha256", "schema",
                                             "source_class", "producer_id",
                                             "producer_code_sha256", "available_at_ms",
                                             "finality", "replay_identity_sha256")}
                for item in lineage]),
            "recovered_constituent_count_window": sum(
                item["source_class"] == "BINANCE_SPOT_PUBLIC_REST_MARKET_DATA"
                for item in lineage),
            "recovered_constituent_count_latest_bar": len(recovered),
        },
        "window": {
            "start_ms": start_ms, "bar_count": bar_count, "end_exclusive_ms": end_ms,
            "projected_bar_sha256": [row["sha256"] for row in projected],
        },
        "decision": {
            "latest_open_ms": latest["open_ms"],
            "latest_close_exclusive_ms": latest["close_exclusive_ms"],
            "available_at_ms": latest["available_at_ms"],
            "decision_cutoff_ms": decision_cutoff_ms,
            "state": state,
            "recovered_latest_bar": bool(recovered),
            "warmup_unknown_count": sum(1 for _, item_state in evaluated if item_state == "UNKNOWN"),
            "signal_scope": "LATEST_CLOSED_SLOT_ONLY",
            "evaluated_slot_count": len(evaluated),
            "state_by_slot": [
                {"close_ms": close_ms, "state": slot_state}
                for close_ms, slot_state in evaluated],
        },
        "strategy": {
            "strategy_id": kernel["definition"].spec["strategy_id"],
            "strategy_version": kernel["definition"].spec["strategy_version"],
            "strategy_definition_sha256": kernel["definition"].digest,
            "evaluation_boundary": "tools.scanner_strategy_f.research_e2e_diagnostic._eval_strategy",
            "availability_claim": "DECISION_AT_CUTOFF_NOT_RETROACTIVE_PIT",
        },
        "pins": {
            **kernel["kernel_identity"],
            "warehouse_commit": WAREHOUSE_COMMIT,
            "config_sha256": expected_config_sha256,
            "adapter_code_sha256": adapter_code_sha256,
        },
        "evidence": {
            "lineage_receipts_verified": len(lineage),
            "finality": "FINAL_ALL_ROWS",
            "missing_1m_rows": 0, "open_gaps": 0, "conflicts": 0,
            "source_feed_mutation": "NONE",
            "disposable_research_store": True,
        },
        "orders": 0, "trading_authority": "NONE",
        "pit_oos": "NOT_ATTESTED", "alpha_claim": "NONE",
    }
    receipt = {**evidence_body, "receipt_sha256": _sha(evidence_body)}
    factory = verify_factory_forward_receipt(
        receipt, expected_adapter_code_sha256=adapter_code_sha256,
        expected_strategy_definition_sha256=kernel["definition"].digest,
        expected_config_sha256=expected_config_sha256,
    )
    return {"receipt": receipt, "factory_forward_intake": factory}


def verify_factory_forward_receipt(receipt, *, expected_adapter_code_sha256,
                                   expected_strategy_definition_sha256,
                                   expected_config_sha256):
    """Separate forward research intake validator; never aliases historical ACK."""
    expected_top = {"schema", "status", "source", "window", "decision", "strategy",
                    "pins", "evidence", "orders", "trading_authority", "pit_oos",
                    "alpha_claim", "receipt_sha256"}
    _need(type(receipt) is dict and set(receipt) == expected_top,
          "FACTORY_FORWARD_RECEIPT_FIELDS_INVALID")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    _need(receipt["receipt_sha256"] == _sha(body), "FACTORY_FORWARD_RECEIPT_SEAL_INVALID")
    _need(receipt["schema"] == "atlas.realtime-market-feed.forward-analysis-receipt.v1"
          and receipt["status"] == "FORWARD_RESEARCH_ONLY"
          and receipt["orders"] == 0 and receipt["trading_authority"] == "NONE"
          and receipt["pit_oos"] == "NOT_ATTESTED" and receipt["alpha_claim"] == "NONE",
          "FACTORY_FORWARD_RECEIPT_SCOPE_INVALID")
    _need(receipt["pins"]["adapter_code_sha256"] == expected_adapter_code_sha256
          and receipt["pins"]["strategy_definition_sha256"] == expected_strategy_definition_sha256
          and receipt["pins"]["config_sha256"] == expected_config_sha256
          and receipt["strategy"]["strategy_definition_sha256"] == expected_strategy_definition_sha256
          and receipt["source"]["source_class"] == "FORWARD_UNQUALIFIED"
          and receipt["evidence"]["source_feed_mutation"] == "NONE"
          and receipt["evidence"]["disposable_research_store"] is True,
          "FACTORY_FORWARD_RECEIPT_PIN_MISMATCH")
    decision = receipt["decision"]
    _need(decision["state"] in {"ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL",
                                 "UNKNOWN", "UNKNOWN_RECOVERED_INPUT"}
          and decision["decision_cutoff_ms"] >= receipt["source"]["availability_max_ms"]
          and decision["latest_close_exclusive_ms"] <= decision["decision_cutoff_ms"],
          "FACTORY_FORWARD_DECISION_CAUSALITY_INVALID")
    # This is a separate forward receipt check, not a Factory historical ACK.
    return {
        "schema": "atlas.factory.forward-research-intake-validation.v1",
        "status": "FORWARD_RECEIPT_VALIDATED_RESEARCH_ONLY",
        "parent_receipt_sha256": receipt["receipt_sha256"],
        "historical_factory_consumer": "NOT_CALLED",
        "lab": "NOT_EVALUATED", "paper": "NOT_ACTIVATED",
        "orders": 0, "trading_authority": "NONE",
    }
