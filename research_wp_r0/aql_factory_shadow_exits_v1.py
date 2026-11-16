"""Four frozen, long Spot counterfactuals using the Factory H cost kernel."""
from collections import Counter
from decimal import Decimal, InvalidOperation

from .aql_factory_e_research_results_store_v1 import ResultsStoreError
from .aql_factory_historical_rule_projection import COST_KEYS, _costs, _modeled_trade


FAMILIES = ("SINGLE_FIXED", "SINGLE_TRAILING", "MULTI_FIXED", "MULTI_TRAILING")
COST_CASES = ("TAKER", "PASSIVE_ENTRY_MARKET_EXIT", "STRESS_TAKER")


def need(condition, reason):
    if not condition:
        raise ResultsStoreError("SHADOW_" + reason)


def number(value):
    need(type(value) is str and 0 < len(value) <= 48, "DECIMAL")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ResultsStoreError("SHADOW_DECIMAL") from exc
    need(result.is_finite() and (result == 0 or -18 <= result.adjusted() <= 18), "DECIMAL")
    return result


def validate_costs(cases):
    need(type(cases) is dict and set(cases) == set(COST_CASES), "COST_CASES")
    for costs in cases.values():
        need(type(costs) is dict and set(costs) == set(COST_KEYS)
             and all(0 <= number(value) < 10000 for value in costs.values()), "COST_FIELDS")
        _costs({"costs": costs, "market": "SPOT"})
    need(all(number(cases["STRESS_TAKER"][key]) >= number(cases["TAKER"][key])
             for key in COST_KEYS), "STRESS_COST")


def validate_family(name, spec):
    need(type(spec) is dict and set(spec) == {
        "applicable", "reason", "risk", "targets", "allocations", "trail", "stop"
    } and type(spec["applicable"]) is bool, "FAMILY_SHAPE")
    if not spec["applicable"]:
        need(type(spec["reason"]) is str and 0 < len(spec["reason"]) <= 240
             and all(spec[k] is None for k in ("risk", "targets", "allocations", "trail", "stop")),
             "EXCLUSION_REASON")
        return
    count = 1 if name.startswith("SINGLE") else None
    targets, allocations = spec["targets"], spec["allocations"]
    need(spec["reason"] is None and spec["stop"] in ("STOP_MARKET", "STOP_LIMIT")
         and type(targets) is list and type(allocations) is list
         and len(targets) == len(allocations) and
         (len(targets) == count if count else 2 <= len(targets) <= 8), "FAMILY_TARGET_COUNT")
    values = [number(t) for t in targets]
    fractions = [number(a) for a in allocations]
    need(0 < number(spec["risk"]) < 1 and values[0] > 0
         and values == sorted(set(values)) and min(fractions) > 0
         and sum(fractions) == 1, "FAMILY_TARGETS")
    if name.endswith("TRAILING"):
        need(0 < number(spec["trail"]) < 1, "TRAIL_FRACTION")
    else:
        need(spec["trail"] is None, "FIXED_STOP_TRAIL")


def compare(entry, spec, cost_case, costs, step, end):
    """Bar-close ratchet takes effect next bar. No intrabar path inference."""
    maker = cost_case == "PASSIVE_ENTRY_MARKET_EXIT"
    fraction = entry["maker_fraction"] if maker else "1"
    result = {
        "opportunity_id": entry["id"], "cost_case": cost_case,
        "filled_fraction": fraction, "status": "UNKNOWN_FILL", "legs": [],
        "gross": None, "net": None, "cost_bps": None,
        "provenance": "COUNTERFACTUAL_MODEL_ONLY",
    }
    if fraction is None:
        return result
    fraction = number(fraction)
    if fraction == 0:
        return {**result, "status": "NONFILL", "gross": "0", "net": "0", "cost_bps": "0"}
    price = number(entry["price"])
    risk = number(spec["risk"])
    stop = price * (1 - risk)
    trail = number(spec["trail"]) if spec["trail"] is not None else None
    targets = [price * (1 + risk * number(t)) for t in spec["targets"]]
    weights = iter(number(w) for w in spec["allocations"])
    fees = _costs({"market": "SPOT", "costs": costs})
    remaining = fraction
    target_index = 0
    expected = entry["entry_at"]
    legs = result["legs"]

    def account(bar_open, exit_price, quantity, reason):
        marks = [{"open_ms": entry["entry_at"], "open": entry["price"]},
                 {"open_ms": bar_open + step, "open": str(exit_price)}]
        modeled = _modeled_trade(marks, 0, 1, "LONG", fees, "SPOT")
        legs.append({
            "bar_open": bar_open, "price": str(exit_price), "fraction": str(quantity),
            "reason": reason, "gross": str(quantity * Decimal(modeled["modeled_gross_return"])),
            "net": str(quantity * Decimal(modeled["modeled_net_return"])),
            "cost_bps": str(quantity * Decimal(modeled["total_cost_bps"])),
            "components_bps": {key: str(quantity * fees[key]) for key in COST_KEYS},
        })

    for bar in entry["bars"]:
        if bar["at"] != expected:
            return {**result, "status": "UNKNOWN_GAP"}
        if expected + step > end:
            return {**result, "status": "UNKNOWN_SEALED_BOUNDARY"}
        opening, high, low = (number(bar[key]) for key in ("open", "high", "low"))
        target_hit = high >= targets[target_index]
        if low <= stop:
            if target_hit:
                return {**result, "status": "UNKNOWN_INTRABAR"}
            if spec["stop"] == "STOP_LIMIT":
                return {**result, "status": "UNKNOWN_STOP_LIMIT_FILL"}
            account(expected, min(opening, stop), remaining, "STOP_MARKET")
            remaining = Decimal(0)
        else:
            while target_index < len(targets) and high >= targets[target_index]:
                quantity = fraction * next(weights)
                account(expected, max(opening, targets[target_index]), quantity, "TARGET_MARKET")
                remaining -= quantity
                target_index += 1
        if not remaining:
            return {**result, "status": "MODEL_ONLY", **{
                field: str(sum((Decimal(leg[field]) for leg in legs), Decimal(0)))
                for field in ("gross", "net", "cost_bps")
            }}
        if trail is not None:
            stop = max(stop, high * (1 - trail))
        expected += step
    return {**result, "status": "UNKNOWN_END_OF_DATA"}


def summarize(rows):
    counts = Counter(row["status"] for row in rows)
    complete = bool(rows) and all(row["net"] is not None for row in rows)
    equity = peak = Decimal(1)
    drawdown = Decimal(0)
    if complete:
        for row in rows:
            equity *= max(Decimal(0), 1 + Decimal(row["net"]))
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak - equity) / peak)
    return {
        "opportunities": len(rows), "states": dict(sorted(counts.items())),
        "partial_entry_count": sum(row["filled_fraction"] not in (None, "0", "1") for row in rows),
        "gross": str(sum((Decimal(row["gross"]) for row in rows), Decimal(0))) if complete else None,
        "net": str(sum((Decimal(row["net"]) for row in rows), Decimal(0))) if complete else None,
        "max_drawdown_trade_close_only": str(drawdown) if complete else None,
    }
