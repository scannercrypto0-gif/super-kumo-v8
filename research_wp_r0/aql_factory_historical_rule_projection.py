"""Factory #246: frozen StrategyDefinition rule triggers over a pinned price grid.

This is a *bounded retrospective decision/cost projection*, not an execution
engine. Reuses the merged AQL StrategyDefinition grammar and indicator kernels
and Factory's established Decimal cost helper. Does not confer source/PIT,
independent universe, OOS or scientific acceptance to self-asserted receipts.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from types import SimpleNamespace
import math

from research_wp_r0.aql_factory_authentic_research_admission import (
    ResearchAdmissionError, _check_seal, _digest, _hash, _require, seal,
)
from research_wp_r0.aql_p2_factory_real_development import dec
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

SCHEMA = "aql.factory.historical-rule-projection.v1"
REPORT = "aql.factory.historical-rule-report.v1"
TRIAL_STATES = frozenset(("PROPOSED", "INVALID", "DUPLICATE", "FAILED",
                          "REJECTED", "UNKNOWN", "BUDGET_EXHAUSTED"))
OPPORTUNITY_STATES = frozenset(("NOMINATED", "REJECTED", "UNSCANNED",
                                "UNKNOWN", "INELIGIBLE"))
COST_KEYS = ("fee_entry_bps", "fee_exit_bps", "spread_entry_bps",
             "spread_exit_bps", "slippage_entry_bps", "slippage_exit_bps",
             "funding_bps_per_bar")


def _decimal(value, name):
    _require(type(value) is str, "COST_" + name.upper())
    try:
        result = dec(value)
    except ValueError as exc:
        raise ResearchAdmissionError("FACTORY_AUTHENTIC_COST_" + name.upper()) from exc
    _require(Decimal(0) <= result <= Decimal(1000), "COST_RANGE_" + name.upper())
    return result


def _validate_population(packet):
    trials = packet.get("trials")
    _require(type(packet.get("trial_budget")) is int
             and packet["trial_budget"] == 53, "FROZEN_53_TRIAL_BUDGET")
    _require(type(trials) is list and len(trials) == 53, "TRIAL_DENOMINATOR")
    ids, prior = set(), set()
    selected = []
    for trial in trials:
        _require(type(trial) is dict and set(trial) == {
            "attempt_id", "candidate_digest", "plan_digest", "state",
            "duplicate_of"}, "TRIAL_SHAPE")
        aid = trial["attempt_id"]
        _require(type(aid) is str and bool(aid) and aid not in ids,
                 "TRIAL_ID_DUPLICATE")
        ids.add(aid)
        _require(_hash(trial["candidate_digest"])
                 and trial["plan_digest"] == packet["plan_digest"]
                 and trial["state"] in TRIAL_STATES, "TRIAL_PROVENANCE")
        duplicate = trial["state"] == "DUPLICATE"
        _require((type(trial["duplicate_of"]) is str and
                  trial["duplicate_of"] in prior) if duplicate
                 else trial["duplicate_of"] is None, "TRIAL_DUPLICATE_PARENT")
        prior.add(aid)
        if aid == packet["selected_attempt_id"]:
            selected.append(trial)
    _require(len(selected) == 1 and selected[0]["state"] == "PROPOSED",
             "SELECTED_ATTEMPT_STATUS")
    census = packet.get("universe")
    _require(type(census) is dict and set(census) == {
        "full", "eligible", "ineligible", "unscanned", "rejected",
        "unknown", "nominated", "source_coverage"}, "UNIVERSE_SHAPE")
    _require(all(type(census[k]) is int and census[k] >= 0
                 for k in ("full", "eligible", "ineligible", "unscanned",
                           "rejected", "unknown", "nominated")),
             "UNIVERSE_COUNTS")
    _require(census["full"] == census["eligible"] + census["ineligible"]
             and census["eligible"] == (
                census["unscanned"] + census["rejected"] +
                census["unknown"] + census["nominated"]),
             "UNIVERSE_CONSERVATION")
    _require(census["source_coverage"] == "NOT_INDEPENDENTLY_ATTESTED",
             "UNIVERSE_FALSE_ATTESTATION")
    opportunities = packet.get("opportunities")
    _require(type(packet.get("opportunity_count")) is int
             and packet["opportunity_count"] >= 0
             and type(opportunities) is list
             and len(opportunities) == packet["opportunity_count"],
             "OPPORTUNITY_DENOMINATOR")
    seen, arms = set(), 0
    for opportunity in opportunities:
        _require(type(opportunity) is dict and set(opportunity) == {
            "opportunity_id", "bar_open_ms", "status", "arms"},
            "OPPORTUNITY_SHAPE")
        oid = opportunity["opportunity_id"]
        _require(type(oid) is str and bool(oid) and oid not in seen,
                 "OPPORTUNITY_ID")
        seen.add(oid)
        _require(type(opportunity["bar_open_ms"]) is int
                 and opportunity["status"] in OPPORTUNITY_STATES,
                 "OPPORTUNITY_STATUS")
        pair = opportunity["arms"]
        _require(type(pair) is list and len(pair) == 2
                 and {a.get("arm") for a in pair if type(a) is dict} ==
                 {"BASE", "SHADOW"}, "PAIR_ARMS")
        _require(all(type(a) is dict and set(a) == {"arm", "status"}
                     and a["status"] in ("UNKNOWN", "NOT_EVALUATED")
                     for a in pair), "PAIR_PREMATURE_PROMOTION")
        arms += 2
    return selected[0], Counter(t["state"] for t in trials), arms


def _validate_bars(packet):
    width = packet.get("width_ms")
    bars = packet.get("bars")
    _require(type(width) is int and width in (60_000, 900_000, 3_600_000),
             "BAR_WIDTH")
    _require(type(bars) is list and 2 <= len(bars) <= 100_000,
             "BAR_DENOMINATOR")
    first = None
    retrospective = False
    for index, bar in enumerate(bars):
        _require(type(bar) is dict and set(bar) == {
            "open_ms", "close_ms", "open", "high", "low", "close",
            "volume", "known_at_ms", "quality", "bar_sha256"},
            "BAR_SHAPE")
        _check_seal({**{k: v for k, v in bar.items()
                        if k != "bar_sha256"},
                     "artifact_sha256": bar["bar_sha256"]},
                    "artifact_sha256")
        start = bar["open_ms"]
        _require(type(start) is int and start >= 0
                 and type(bar["close_ms"]) is int
                 and bar["close_ms"] == start + width - 1
                 and start % width == 0, "BAR_GRID")
        if first is None:
            first = start
        _require(start == first + index * width, "MISSING_OR_DUPLICATE_BAR")
        _require(bar["quality"] == "FINAL", "UNFINAL_BAR")
        o, h, l, c, v = (bar[k] for k in ("open", "high", "low", "close", "volume"))
        _require(all(type(x) in (int, float) and math.isfinite(x)
                     for x in (o, h, l, c, v))
                 and 0 < l <= o <= h and l <= c <= h and v >= 0,
                 "BAD_OHLCV")
        known = bar["known_at_ms"]
        if known is None:
            retrospective = True
        else:
            _require(type(known) is int
                     and bar["close_ms"] < known <= start + width,
                     "FUTURE_OR_INVALID_AVAILABILITY")
    return bars, retrospective


def _vectors(definition, bars):
    """Invoke existing AQL indicator kernels; do not reimplement indicators.

    Existing kernels are forward-recursive, and each decision reads only
    values indexed <= its own closed bar. This offline path never invokes
    custody's confirmed-only PIT API on retrospective data.
    """
    registry = IndicatorRegistryV2()
    values = {}
    source_bars = [SimpleNamespace(**bar) for bar in bars]
    for ref in definition.spec["indicators"]:
        indicator = registry.get(ref["indicator_id"], **ref["parameters"])
        outputs = {}
        if hasattr(indicator, "_values"):
            for index, vals in indicator._values(source_bars):
                _require(type(index) is int and index >= 0 and index < len(bars)
                         and len(vals) == len(indicator.output_fields),
                         "INDICATOR_VECTOR_SHAPE")
                outputs[index] = dict(zip(indicator.output_fields, vals))
        else:
            raw = indicator._compute_values([b["close"] for b in bars], source_bars)
            _require(len(raw) == len(bars), "INDICATOR_LENGTH")
            for index in range(indicator.min_warmup_bars, len(bars)):
                if raw[index] is not None:
                    outputs[index] = {"value": raw[index]}
        _require(all(all(type(v) in (int, float) and math.isfinite(v)
                         for v in row.values()) for row in outputs.values()),
                 "NONFINITE_INDICATOR")
        values[ref["name"]] = outputs
    return values


def _expression(node, index, values):
    op = node["op"]
    if op == "constant":
        return node["value"]
    if op == "indicator":
        prior = index - node["lag"]
        if prior < 0:
            return None
        return values[node["name"]].get(prior, {}).get(node["field"])
    if op in ("gt", "ge", "lt", "le", "eq"):
        left = _expression(node["left"], index, values)
        right = _expression(node["right"], index, values)
        if left is None or right is None:
            return None
        return {"gt": lambda: left > right, "ge": lambda: left >= right,
                "lt": lambda: left < right, "le": lambda: left <= right,
                "eq": lambda: left == right}[op]()
    if op == "not":
        x = _expression(node["arg"], index, values)
        return None if x is None else not x
    terms = [_expression(x, index, values) for x in node["args"]]
    if op == "all":
        return False if False in terms else None if None in terms else True
    if op == "any":
        return True if True in terms else None if None in terms else False
    _require(False, "UNSUPPORTED_RULE_AST")


def _costs(packet):
    costs = packet.get("costs")
    _require(type(costs) is dict and set(costs) == set(COST_KEYS),
             "COST_SHAPE")
    values = {k: _decimal(costs[k], k) for k in COST_KEYS}
    if packet["market"] == "SPOT":
        _require(values["funding_bps_per_bar"] == 0, "SPOT_FUNDING")
    return values


def _modeled_trade(bars, entry_index, exit_index, direction, fees, market):
    entry = Decimal(str(bars[entry_index]["open"]))
    exit_ = Decimal(str(bars[exit_index]["open"]))
    _require(entry > 0 and exit_ > 0, "TRADE_PRICE")
    holding = exit_index - entry_index
    _require(holding > 0, "TRADE_HOLDING")
    # Stop/target may have been touched intrabar before the modeled exit.
    # Without execution chronology their order/price is not observable.
    sign = Decimal(1) if direction == "LONG" else Decimal(-1)
    gross = sign * (exit_ / entry - Decimal(1))
    leg_cost = sum((fees[k] for k in COST_KEYS if k != "funding_bps_per_bar"),
                   Decimal(0))
    funding = fees["funding_bps_per_bar"] * holding if market == "PERP" else Decimal(0)
    net = gross - (leg_cost + funding) / Decimal(10_000)
    return {
        "entry_open_ms": bars[entry_index]["open_ms"],
        "exit_open_ms": bars[exit_index]["open_ms"],
        "holding_bars": holding,
        "modeled_entry_open": str(entry),
        "modeled_exit_open": str(exit_),
        "modeled_gross_return": str(gross),
        "modeled_net_return": str(net),
        "total_cost_bps": str(leg_cost + funding),
        "cost_class": "ASSUMPTION_ONLY_NOT_EXECUTABLE_FILL",
        "market": market,
        "direction": direction,
    }


def evaluate_historical_rules(packet):
    """Produce TEST_ONLY/RETROSPECTIVE projection with sealed trial denominator.

    Market prices may originate from retained originals, but their SHA and
    caller-declared known-at values alone never prove source/PIT chronology.
    """
    _check_seal(packet, "artifact_sha256")
    _require(packet.get("schema") == SCHEMA
             and packet.get("source_kind") in ("TEST_ONLY", "ORIGINAL_UNVERIFIED")
             and packet.get("market") in ("SPOT", "PERP")
             and packet.get("holdout") == "SEALED_UNOPENED"
             and packet.get("execution_authority") == "NONE",
             "AUTHORITY_OR_SCHEMA")
    _require(packet.get("availability") == (
        "SYNTHETIC_TEST" if packet["source_kind"] == "TEST_ONLY"
        else "RETROSPECTIVE_NON_PIT"), "AVAILABILITY_CLASS")
    _require(type(packet.get("dataset_id")) is str and bool(packet["dataset_id"])
             and type(packet.get("dataset_version")) is int
             and packet["dataset_version"] >= 1
             and _hash(packet.get("source_bytes_sha256"))
             and _hash(packet.get("source_manifest_sha256"))
             and _hash(packet.get("plan_digest")), "DATASET_SOURCE_PIN")
    selected, attempt_counts, arm_count = _validate_population(packet)
    _require(type(packet.get("strategy")) is dict, "STRATEGY_DEFINITION")
    try:
        definition = StrategyDefinition.from_dict(
            packet["strategy"], registry=IndicatorRegistryV2())
    except (ValueError, TypeError, KeyError) as exc:
        raise ResearchAdmissionError("FACTORY_AUTHENTIC_INVALID_STRATEGY") from exc
    _require(selected["candidate_digest"] == definition.digest,
             "CANDIDATE_DEFINITION_DRIFT")
    bars, retrospective = _validate_bars(packet)
    fees = _costs(packet)
    risk = definition.spec["risk"]
    direction = packet.get("direction")
    _require(direction in ("LONG", "SHORT")
             and (packet["market"] != "SPOT" or direction == "LONG"),
             "DIRECTION_MARKET")
    # Only next-open, rule/holding exits. Stop/target touch is intentionally
    # UNKNOWN, not a fabricated deterministic fill or lucky intrabar ordering.
    values = _vectors(definition, bars)
    decisions, modeled, unknown = [], [], 0
    active = None
    blocked = False
    for i in range(len(bars)-1):
        cutoff = bars[i]["close_ms"] + 1
        if bars[i]["known_at_ms"] is not None:
            _require(bars[i]["known_at_ms"] <= cutoff,
                     "FEATURE_NOT_AVAILABLE_AT_DECISION")
        if blocked:
            state = "UNKNOWN_PATH_AFTER_BARRIER"
        elif active is None:
            flag = _expression(definition.spec["entry"], i, values)
            state = ("WARMUP_UNKNOWN" if flag is None
                     else "NO_SIGNAL" if not flag else "ENTRY_TRIGGERED")
            if flag is True:
                active = {"entry": i + 1, "decision": i}
        else:
            entry = active["entry"]
            entry_price = bars[entry]["open"]
            stop = (entry_price * (1 - risk["stop_fraction"])
                    if direction == "LONG" else
                    entry_price * (1 + risk["stop_fraction"]))
            target = (entry_price * (1 + risk["target_fraction"])
                      if direction == "LONG" else
                      entry_price * (1 - risk["target_fraction"]))
            # The decision bar is fully observed at next-open execution. If
            # any stop/target was touched since entry, intrabar fill sequencing
            # cannot be reconstructed from OHLCV.
            touches = any((bars[j]["low"] <= stop or bars[j]["high"] >= target)
                          if direction == "LONG"
                          else (bars[j]["high"] >= stop or bars[j]["low"] <= target)
                          for j in range(entry, i+1))
            if touches:
                unknown += 1
                modeled.append({
                    "entry_open_ms": bars[entry]["open_ms"],
                    "exit_open_ms": None, "modeled_net_return": None,
                    "status": "UNKNOWN_INTRABAR_STOP_TARGET",
                })
                blocked = True
                active = None
                state = "UNKNOWN_INTRABAR_STOP_TARGET"
            else:
                signal = _expression(definition.spec["exit"], i, values)
                holding_cap = i + 1 - entry >= risk["holding_bars"]
                if signal is None:
                    unknown += 1
                    state = "UNKNOWN_EXIT_RULE"
                    modeled.append({
                        "entry_open_ms": bars[entry]["open_ms"],
                        "exit_open_ms": None, "modeled_net_return": None,
                        "status": "UNKNOWN_EXIT_RULE",
                    })
                    blocked = True
                    active = None
                elif signal or holding_cap:
                    record = _modeled_trade(bars, entry, i+1, direction,
                                            fees, packet["market"])
                    record["status"] = "MODEL_ONLY"
                    record["exit_reason"] = ("EXIT_RULE" if signal else
                                             "HOLDING_CAP")
                    modeled.append(record)
                    active = None
                    state = "EXIT_TRIGGERED"
                else:
                    state = "IN_POSITION"
        decisions.append({
            "bar_open_ms": bars[i]["open_ms"], "decision_cutoff_ms": cutoff,
            "state": state,
        })
    if active is not None:
        modeled.append({
            "entry_open_ms": bars[active["entry"]]["open_ms"],
            "exit_open_ms": None, "modeled_net_return": None,
            "status": "UNKNOWN_END_OF_DATA",
        })
        unknown += 1
    status_counts = Counter(row["state"] for row in decisions)
    output = {
        "schema": REPORT, "input_sha256": packet["artifact_sha256"],
        "strategy_digest": definition.digest,
        "selected_attempt_id": packet["selected_attempt_id"],
        "plan_digest": packet["plan_digest"],
        "source_bytes_sha256": packet["source_bytes_sha256"],
        "source_manifest_sha256": packet["source_manifest_sha256"],
        "dataset_id": packet["dataset_id"],
        "dataset_version": packet["dataset_version"],
        "source_class": packet["source_kind"],
        "trial_budget": packet["trial_budget"],
        "trial_state_counts": {s: attempt_counts[s] for s in sorted(TRIAL_STATES)},
        "full_universe": packet["universe"]["full"],
        "universe_independently_attested": False,
        "opportunity_count": packet["opportunity_count"],
        "arm_slots": arm_count,
        "bar_count": len(bars),
        "decision_slots": len(decisions),
        "decision_counts": dict(sorted(status_counts.items())),
        "decisions": decisions,
        "modeled_outcomes": modeled,
        "unknown_outcomes": unknown,
        "model_class": "TEST_ONLY" if packet["source_kind"] == "TEST_ONLY"
                       else "RETROSPECTIVE_ONLY_UNVERIFIED",
        "indicator_kernel": "EXISTING_AQL_V1_V2_UNVERIFIED_OFFLINE_VECTORS",
        "source_original_bytes_verified": False,
        "historical_pit_verified": False,
        "unverified_known_at_count": sum(b["known_at_ms"] is None for b in bars),
        "any_unverified_asof": retrospective,
        "costs": packet["costs"],
        "stop_target_semantics": "UNKNOWN_ON_ANY_INTRABAR_TOUCH",
        "execution_status": "NOT_OBSERVED",
        "scoring_acceptance": "INSUFFICIENT_EVIDENCE",
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "holdout": "SEALED_UNOPENED", "trading_authority": "NONE",
    }
    output["artifact_sha256"] = _digest(output)
    return output
