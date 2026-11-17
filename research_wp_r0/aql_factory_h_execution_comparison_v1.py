"""Bounded synthetic execution/exit comparison for the existing Factory H Lab.

This is a scenario extension of Factory's Decimal return/cost kernel, not a
signal generator, optimizer, historical backtester or order dispatcher. Every
entry and attempted candidate is supplied in a sealed, predeclared fixture.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, _attempts, audit_store_layout, digest,
)
from research_wp_r0.aql_factory_historical_rule_projection import (
    COST_KEYS, _costs, _modeled_trade,
)

SCHEMA = "aql.factory.h.execution-exit-fixture.v1"
REPORT = "aql.factory.h.execution-exit-comparison.v1"
MIN_EMBARGO_MS = 259200000
POLICIES = {
    "A": "SINGLE_FINAL_TARGET_FIXED_STOP",
    "B": "THREE_TARGETS_FIXED_STOP",
    "C": "THREE_TARGETS_STOP_TO_ENTRY_FROM_NEXT_BAR_AFTER_TARGET_1",
}
SCENARIOS = ("TAKER", "PASSIVE_ENTRY_MARKET_EXIT", "STRESS_TAKER")
HEX = set("0123456789abcdef")


def _need(ok, reason):
    if not ok:
        raise ResultsStoreError("FACTORY_H_EXEC_" + reason)


def _sha(value):
    return type(value) is str and len(value) == 64 and set(value) <= HEX


def _number(value, *, positive=False):
    _need(type(value) is str and 0 < len(value) <= 64, "DECIMAL_STRING")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ResultsStoreError("FACTORY_H_EXEC_DECIMAL") from exc
    _need(result.is_finite() and (result > 0 if positive else result >= 0),
          "DECIMAL_RANGE")
    return result


def _validate(packet):
    fields = {
        "schema", "experiment_id", "sha256", "source_class", "market",
        "direction", "trading_authority", "holdout", "historical_pit",
        "frozen_at_ms", "train_end_ms", "embargo_ms", "evaluation_start_ms",
        "strategy_sha256", "scanner_entry_batch_sha256", "baseline_sha256",
        "null_method", "cost_convention", "costs", "stop_order", "attempts",
        "entries", "null_entries", "allocations", "target_r_multiples",
        "initial_risk_fraction", "selection", "cost_provenance", "generation_states",
    }
    _need(type(packet) is dict and set(packet) == fields and
          packet.get("schema") == SCHEMA, "PACKET_FIELDS")
    _need(_sha(packet["sha256"]) and packet["sha256"] == digest(
        {k: v for k, v in packet.items() if k != "sha256"}), "PACKET_SEAL")
    _need(packet["source_class"] == "SYNTHETIC_FIXTURE_ONLY" and
          packet["market"] == "SPOT" and packet["direction"] == "LONG" and
          packet["trading_authority"] == "NONE" and
          packet["holdout"] == "SEALED_UNOPENED" and
          packet["historical_pit"] == "NOT_ATTESTED" and
          packet["selection"] == "PREDECLARED_ALL_VARIANTS_NO_WINNER" and
          packet["stop_order"] in ("STOP_MARKET", "STOP_LIMIT"), "AUTHORITY")
    _need(type(packet["experiment_id"]) is str and
          packet["experiment_id"].startswith("RESEARCH-H-EXEC-CMP-") and
          len(packet["experiment_id"]) <= 160 and
          all(_sha(packet[k]) for k in (
              "strategy_sha256", "scanner_entry_batch_sha256", "baseline_sha256")),
          "IDENTITY")
    _need(all(type(packet[k]) is int and packet[k] >= 0 for k in (
        "frozen_at_ms", "train_end_ms", "embargo_ms", "evaluation_start_ms")) and
        packet["embargo_ms"] >= MIN_EMBARGO_MS and
        packet["evaluation_start_ms"] >= packet["train_end_ms"] +
            packet["embargo_ms"] and
        packet["frozen_at_ms"] < packet["evaluation_start_ms"], "CHRONOLOGY")
    _need(packet["null_method"] == "INDEPENDENT_PREDECLARED_SYNTHETIC_ENTRIES" and
          packet["cost_convention"] ==
          "HALF_SPREAD_PER_LEG_SLIPPAGE_EXCLUDES_SPREAD" and
          packet["cost_provenance"] == "SYNTHETIC_ASSUMPTION_NOT_ATTESTED",
          "COST_OR_NULL_CONVENTION")
    _need(type(packet["costs"]) is dict and
          set(packet["costs"]) == set(SCENARIOS), "SCENARIO_COSTS")
    fees = {}
    for name in SCENARIOS:
        values = packet["costs"][name]
        _need(type(values) is dict and set(values) == set(COST_KEYS) and
              all(type(x) is str for x in values.values()), "EXPLICIT_COSTS")
        fees[name] = _costs({"costs": values, "market": "SPOT"})
    _need(all(fees["STRESS_TAKER"][k] >= fees["TAKER"][k]
              for k in COST_KEYS), "STRESS_CANNOT_IMPROVE_COSTS")
    _attempts(packet["attempts"])
    attempts = {a["attempt_id"]: a for a in packet["attempts"]}
    generation = packet["generation_states"]
    _need(type(generation) is dict and set(generation) == set(attempts) and
          all(state in ("GENERATED", "FAILED_TO_GENERATE", "UNSCANNED")
              for state in generation.values()) and
          all((a["state"] != "SELECTED" or generation[k] == "GENERATED") and
              ((a["state"] == "UNSCANNED") == (generation[k] == "UNSCANNED"))
              for k, a in attempts.items()), "GENERATION_DENOMINATOR")
    risk = _number(packet["initial_risk_fraction"], positive=True)
    _need(risk < 1 and type(packet["target_r_multiples"]) is list and
          len(packet["target_r_multiples"]) == 3 and
          type(packet["allocations"]) is list and
          len(packet["allocations"]) == 3, "RISK_POLICY")
    targets = [_number(x, positive=True) for x in packet["target_r_multiples"]]
    allocation = [_number(x, positive=True) for x in packet["allocations"]]
    _need(targets[0] < targets[1] < targets[2] and
          sum(allocation, Decimal(0)) == 1, "TARGET_OR_ALLOCATION")
    ids = set()
    candidate_attempts = set()
    for key in ("entries", "null_entries"):
        entries = packet[key]
        _need(type(entries) is list and 0 < len(entries) <= 1000,
              "ENTRY_DENOMINATOR")
        previous_close = None
        for row in entries:
            _need(type(row) is dict and set(row) == {
                "entry_id", "attempt_id", "signal_ms", "entry_ms",
                "entry_price", "bars", "maker_state", "maker_fill_fraction"},
                "ENTRY_SHAPE")
            _need(type(row["entry_id"]) is str and row["entry_id"] and
                  row["entry_id"] not in ids and
                  row["attempt_id"] in attempts and
                  attempts[row["attempt_id"]]["state"] == "SELECTED",
                  "ENTRY_ID_OR_ATTEMPT")
            ids.add(row["entry_id"])
            if key == "entries":
                candidate_attempts.add(row["attempt_id"])
            _need(type(row["signal_ms"]) is int and
                  type(row["entry_ms"]) is int and
                  packet["evaluation_start_ms"] <= row["signal_ms"] <
                  row["entry_ms"], "CAUSAL_ENTRY")
            _need(previous_close is None or row["entry_ms"] > previous_close,
                  "ENTRY_SEQUENCE_OR_OVERLAP")
            price = _number(row["entry_price"], positive=True)
            state = row["maker_state"]
            fraction = row["maker_fill_fraction"]
            _need(state in ("UNKNOWN", "NONFILL", "PARTIAL", "FILLED"),
                  "MAKER_STATE")
            if state == "UNKNOWN":
                _need(fraction is None, "UNKNOWN_FILL_FRACTION")
            else:
                fraction = _number(fraction)
                _need((state == "NONFILL" and fraction == 0) or
                      (state == "PARTIAL" and 0 < fraction < 1) or
                      (state == "FILLED" and fraction == 1), "FILL_FRACTION")
            bars = row["bars"]
            _need(type(bars) is list and 0 < len(bars) <= 10000, "BARS")
            prior_close = None
            for bar in bars:
                _need(type(bar) is dict and set(bar) == {
                    "open_ms", "close_ms", "open", "high", "low", "close"},
                    "BAR_SHAPE")
                _need(type(bar["open_ms"]) is int and
                      type(bar["close_ms"]) is int and
                      row["entry_ms"] <= bar["open_ms"] < bar["close_ms"] and
                      (prior_close is None or bar["open_ms"] > prior_close),
                      "BAR_CHRONOLOGY")
                o, h, l, c = (_number(bar[k], positive=True)
                              for k in ("open", "high", "low", "close"))
                _need(l <= min(o, c) <= max(o, c) <= h, "OHLC")
                prior_close = bar["close_ms"]
            _need(bars[0]["open_ms"] == row["entry_ms"] and
                  _number(bars[0]["open"], positive=True) == price,
                  "NEXT_OPEN_PRICE")
            previous_close = bars[-1]["close_ms"]
    _need(candidate_attempts == {k for k, a in attempts.items()
                                if a["state"] == "SELECTED"},
          "SELECTED_ATTEMPT_MISSING")
    _need(digest(packet["entries"]) != digest(packet["null_entries"]),
          "NULL_ALIASES_CANDIDATE")
    return fees, risk, targets, allocation


def _leg(entry, bar, exit_price, fraction, fees, reason):
    # Reuse the established Factory Decimal price-return and bps accounting.
    # These two synthetic accounting marks are NOT observed execution times.
    marks = [{"open_ms": entry["entry_ms"], "open": entry["entry_price"]},
             {"open_ms": bar["close_ms"] + 1, "open": str(exit_price)}]
    kernel = _modeled_trade(marks, 0, 1, "LONG", fees, "SPOT")
    return {
        "reason": reason, "exit_bar_open_ms": bar["open_ms"],
        "accounting_asof_ms": bar["close_ms"] + 1,
        "price": str(exit_price), "fraction_of_initial_notional": str(fraction),
        "gross_return": str(fraction * Decimal(kernel["modeled_gross_return"])),
        "net_return": str(fraction * Decimal(kernel["modeled_net_return"])),
        "cost_components_bps": {k: str(fraction * fees[k]) for k in COST_KEYS},
        "total_cost_bps": str(fraction * Decimal(kernel["total_cost_bps"])),
        "cost_class": kernel["cost_class"],
    }


def _path(entry, name, fees, policy, risk, target_rs, allocation, stop_order):
    maker = name == "PASSIVE_ENTRY_MARKET_EXIT"
    state = entry["maker_state"] if maker else "FILLED"
    fraction = (None if state == "UNKNOWN" else
                _number(entry["maker_fill_fraction"]) if maker else Decimal(1))
    row = {"entry_id": entry["entry_id"], "attempt_id": entry["attempt_id"],
           "policy": policy, "scenario": name, "entry_fill_state": state,
           "filled_fraction": None if fraction is None else str(fraction),
           "unfilled_fraction": None if fraction is None else str(1 - fraction),
           "exit_model": "TARGET_MARKET_AND_" + stop_order,
           "execution_evidence": "SYNTHETIC_ASSUMPTION_NOT_ATTESTED",
           "legs": [], "gross_return": None, "net_return": None,
           "total_cost_bps": None, "r_multiple": None}
    if state == "UNKNOWN":
        return {**row, "status": "UNKNOWN_FILL"}
    if state == "NONFILL":
        return {**row, "status": "NONFILL", "gross_return": "0",
                "net_return": "0", "total_cost_bps": "0", "r_multiple": "0"}
    price = _number(entry["entry_price"], positive=True)
    stop = price * (1 - risk)
    targets = [price * (1 + risk * r) for r in target_rs]
    indexes = [2] if policy == "A" else [0, 1, 2]
    remaining = fraction
    legs = []
    advance = False
    for bar in entry["bars"]:
        if advance:
            stop = price
            advance = False
        low, high, opening = (_number(bar[k], positive=True)
                              for k in ("low", "high", "open"))
        stop_hit = low <= stop
        target_hit = bool(indexes) and high >= targets[indexes[0]]
        if stop_hit and target_hit:
            return {**row, "legs": legs, "status": "UNKNOWN_INTRABAR_STOP_TARGET"}
        if stop_hit:
            if stop_order == "STOP_LIMIT":
                return {**row, "legs": legs, "status": "UNKNOWN_STOP_LIMIT_FILL"}
            legs.append(_leg(entry, bar, min(opening, stop), remaining, fees,
                             "STOP_MARKET_MODEL"))
            remaining = Decimal(0)
        else:
            while indexes and high >= targets[indexes[0]]:
                i = indexes.pop(0)
                size = fraction if policy == "A" else fraction * allocation[i]
                legs.append(_leg(entry, bar, max(opening, targets[i]), size, fees,
                                 "TARGET_%d_MARKET_MODEL" % (i + 1)))
                remaining -= size
                if policy == "C" and i == 0:
                    advance = True  # exact rule: cannot move stop inside this bar
        if remaining == 0:
            gross = sum((Decimal(x["gross_return"]) for x in legs), Decimal(0))
            net = sum((Decimal(x["net_return"]) for x in legs), Decimal(0))
            costs = sum((Decimal(x["total_cost_bps"]) for x in legs), Decimal(0))
            return {**row, "status": "MODEL_ONLY", "legs": legs,
                    "gross_return": str(gross), "net_return": str(net),
                    "total_cost_bps": str(costs), "r_multiple": str(net / risk)}
    return {**row, "legs": legs, "status": "UNKNOWN_END_OF_DATA"}


def _summarize(rows):
    status = Counter(r["status"] for r in rows)
    modeled = [r for r in rows if r["status"] == "MODEL_ONLY"]
    unknown = sum(n for s, n in status.items() if s.startswith("UNKNOWN"))
    # Do not promote a favorable subset when unknown entries remain.
    comparable = not unknown
    net = [Decimal(r["net_return"]) for r in modeled]
    equity, peak, drawdown = Decimal(1), Decimal(1), Decimal(0)
    for value in net:
        equity *= 1 + value
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    return {
        "attempted_entry_count": len(rows), "status_counts": dict(sorted(status.items())),
        "modeled_trade_count": len(modeled), "unknown_count": unknown,
        "nonfill_count": status["NONFILL"],
        "partial_entry_count": sum(r["entry_fill_state"] == "PARTIAL" for r in rows),
        "modeled_exit_order_count": sum(len(r["legs"]) for r in rows),
        "gross_return_sum": str(sum((Decimal(r["gross_return"]) for r in modeled),
                                    Decimal(0))) if comparable else None,
        "net_return_sum": str(sum(net, Decimal(0))) if comparable else None,
        "expected_r_per_attempted_entry": str(sum(
            (Decimal(r["r_multiple"]) for r in modeled), Decimal(0)) / len(rows))
            if comparable else None,
        "max_drawdown_trade_close_only": str(drawdown) if comparable else None,
        "worst_modeled_net_return": str(min(net)) if net and comparable else None,
        "comparison_status": "COMPLETE_MODEL_ONLY" if comparable else
            "INCOMPLETE_UNKNOWN_NO_AGGREGATE_PROMOTION",
    }


def evaluate_execution_exit_comparison(packet):
    """Evaluate all predeclared variants; no ranking, refitting or OOS opening."""
    with localcontext() as context:
        context.prec = 40
        fees, risk, targets, allocation = _validate(packet)
        rows = []
        summaries = {}
        for cohort, key in (("CANDIDATE", "entries"), ("NULL_PLACEBO", "null_entries")):
            for scenario in SCENARIOS:
                for policy in POLICIES:
                    subset = [{**_path(e, scenario, fees[scenario], policy, risk,
                                      targets, allocation, packet["stop_order"]),
                               "cohort": cohort} for e in packet[key]]
                    rows.extend(subset)
                    summaries[cohort + ":" + scenario + ":" + policy] = _summarize(subset)
        census = Counter(a["state"] for a in packet["attempts"])
        root = Path(__file__).resolve().parent
        source_hashes = {name: sha256((root / name).read_text(
                             encoding="utf-8").encode("utf-8")).hexdigest()
                         for name in (
                             "aql_factory_h_execution_comparison_v1.py",
                             "aql_factory_h_scientific_lab_v1.py",
                             "aql_factory_historical_rule_projection.py",
                             "aql_factory_e_research_results_store_v1.py",
                             "aql_factory_h_research_package_v1.py")}
        body = {
            "schema": REPORT, "experiment_id": packet["experiment_id"],
            "input_sha256": packet["sha256"],
            "kernel": "aql_factory_historical_rule_projection._modeled_trade",
            "strategy_sha256": packet["strategy_sha256"],
            "scanner_entry_batch_sha256": packet["scanner_entry_batch_sha256"],
            "baseline_sha256": packet["baseline_sha256"],
            "implementation_sources": source_hashes,
            "code_sha256": digest(source_hashes),
            "frozen_plan_sha256": digest({k: packet[k] for k in (
                "frozen_at_ms", "train_end_ms", "embargo_ms", "evaluation_start_ms",
                "costs", "initial_risk_fraction", "allocations", "target_r_multiples",
                "stop_order", "selection", "null_method")}),
            "policies": POLICIES, "scenarios": list(SCENARIOS),
            "attempts": packet["attempts"],
            "generation_states": packet["generation_states"],
            "denominators": {"total_attempted": len(packet["attempts"]),
                "generated": sum(s == "GENERATED" for s in packet["generation_states"].values()),
                "failed_to_generate": sum(s == "FAILED_TO_GENERATE"
                                          for s in packet["generation_states"].values()),
                "failed": census["FAILED"], "attempt_state_counts": dict(sorted(census.items())),
                "candidate_entries": len(packet["entries"]),
                "null_entries": len(packet["null_entries"]),
                "variants_per_cohort": 9, "total_variant_rows": len(rows)},
            "outcomes": rows, "comparisons": summaries,
            "coverage": {
                "gross_and_taker_costs": "SYNTHETIC_MODEL_ONLY",
                "spread_slippage": packet["cost_convention"],
                "maker_entry": "EXPLICIT_SYNTHETIC_NONFILL_PARTIAL_UNKNOWN_NO_TOUCH_FILL",
                "maker_exit": "MARKET_EXIT_ONLY_NO_PASSIVE_EXIT_FILL_CLAIM",
                "stop_limit": "UNKNOWN_FILL_NO_QUEUE_MODEL",
                "queue_priority_adverse_selection_cancel_reprice_fallback": "UNSUPPORTED",
                "market_impact_latency_liquidity": "UNSUPPORTED_COST_SENSITIVITY_ONLY",
                "fixed_ticket_fees_perp_funding_short": "UNSUPPORTED",
                "continuous_trailing_stop": "UNSUPPORTED_C_IS_NEXT_BAR_BREAKEVEN_ONLY",
                "intrabar_chronology": "UNKNOWN_ON_STOP_AND_TARGET_SAME_BAR",
                "null": "SEPARATE_PREDECLARED_FIXTURE_NOT_SCIENTIFIC_INDEPENDENCE_PROOF",
                "drawdown_tails": "TRADE_CLOSE_DESCRIPTIVE_ONLY_NOT_PORTFOLIO_PATH",
                "oos_robustness_multiple_testing": "NOT_ATTESTED_NO_VARIANT_SELECTION",
            },
            "source_class": "SYNTHETIC_FIXTURE_ONLY", "historical_pit": "NOT_ATTESTED",
            "holdout": "SEALED_UNOPENED", "paper": "NOT_ACTIVATED",
            "trading_authority": "NONE", "orders_created": 0, "actual_fills": None,
            "winner": None, "assessment": "SYNTHETIC_ENGINEERING_ONLY_NO_ALPHA_CLAIM",
        }
        return {**body, "sha256": digest(body)}


def run_factory_h_execution_comparison(packet, store_path):
    """Persist/replay the report through the existing Factory H immutable store."""
    report = evaluate_execution_exit_comparison(packet)
    path = Path(store_path)
    _need(path.is_file() and path.suffix == ".sqlite" and
          audit_store_layout(path)["layout_version"] == 2, "EXISTING_STORE_V2")
    from research_wp_r0.aql_factory_h_research_package_v1 import _store_package
    body = {"schema": "aql.factory.h.execution-comparison-package.v1",
            "experiment_id": packet["experiment_id"],
            "input_sha256": packet["sha256"], "comparison": report,
            "holdout": "SEALED_UNOPENED", "trading_authority": "NONE"}
    package_sha, status = _store_package(path, body)
    receipt = {"schema": "aql.factory.h.execution-comparison-receipt.v1",
               "input_sha256": packet["sha256"], "report_sha256": report["sha256"],
               "package_sha256": package_sha, "store_status": status,
               "code_sha256": report["code_sha256"],
               "trading_authority": "NONE", "assessment": report["assessment"]}
    return {**receipt, "receipt_sha256": digest(receipt)}
