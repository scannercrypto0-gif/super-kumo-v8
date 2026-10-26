"""SF-BREAKOUT-PILOT-01: deterministic SYNTHETIC integration demonstration.

No historical market data, PIT evidence, OOS, paper/live orders or strategy
promotion. Separate BASE/SHADOW evaluation on one 15-minute bar stream.
"""
from dataclasses import dataclass
import math

from .strategy_definition import canonical, digest
from .synthetic_execution import account_long_prices

DELTA_MS = 15 * 60 * 1000
COSTS = {"BASE_COST": {"fee_bps": 10, "slippage_bps": 5},
         "STRESS_COST": {"fee_bps": 20, "slippage_bps": 10}}
SPEC = {"schema": "sf-breakout-pilot-01", "purpose": "SYNTHETIC_INTEGRATION_ONLY",
        "symbol": "BTCUSDT", "market": "SPOT", "interval_ms": DELTA_MS,
        "bars": 500, "entry_lookback": 20, "exit_lookback": 10,
        "entry_rule": "CLOSE_GT_PREVIOUS_20_HIGH_RISING_EDGE",
        "exit_rule": "CLOSE_LT_PREVIOUS_10_LOW",
        "shadow_volume_rule": "CANDLE_VOLUME_GT_1_2_TIMES_PRIOR_20_MEAN",
        "timing": "ASSUMED_CLOSE_PLUS_ONE_MS_GUARD_ONE_INTERVAL",
        "capital": 100000, "max_quantity_btc": 1,
        "costs": COSTS, "oos": "NEVER_OPENED"}


@dataclass(frozen=True)
class PilotPlan:
    payload: bytes

    def __init__(self, definition):
        if canonical(definition) != canonical(SPEC):
            raise ValueError("Pilot contract cannot be optimized or altered")
        object.__setattr__(self, "payload", canonical(definition))

    @property
    def digest(self):
        import hashlib
        return hashlib.sha256(self.payload).hexdigest()


def synthetic_fixture():
    """Exactly 500 generated 15m bars; artificial waves, never market evidence."""
    rows = []
    previous = 100.0
    for i in range(500):
        j = i % 100
        if j < 24:
            close = 100.0
        elif j < 45:
            close = 100.0 + (j - 23) * 1.4
        elif j < 70:
            close = 129.4 - (j - 44) * 1.7
        else:
            close = 92.5 + (j - 69) * .25
        vol = 150.0 if j == 24 and (i // 100) % 2 == 0 else 80.0
        start = 1704067200000 + i * DELTA_MS
        rows.append((start, start + DELTA_MS - 1, previous,
                     max(previous, close) + .2,
                     min(previous, close) - .2, close, vol))
        previous = close
    return tuple(rows)


def _validate(rows):
    if type(rows) not in (list, tuple) or len(rows) != 500:
        raise ValueError("Exact 500-bar synthetic fixture scope required")
    validated = []
    for i, row in enumerate(rows):
        if type(row) not in (list, tuple) or len(row) != 7:
            raise ValueError("OHLCV row required")
        op_ms, cl_ms, opening, high, low, closing, volume = row
        if (type(op_ms) is not int or type(cl_ms) is not int
                or op_ms % DELTA_MS or cl_ms != op_ms + DELTA_MS - 1
                or (i and op_ms != validated[-1][0] + DELTA_MS)):
            raise ValueError("Missing/nonfinal/off-grid essential 15m candle")
        vals = (opening, high, low, closing)
        if (not all(type(v) in (float, int) and math.isfinite(v) and v > 0 for v in vals)
                or low > min(opening, closing) or high < max(opening, closing)):
            raise ValueError("Invalid essential OHLC candle")
        if volume is not None and (type(volume) not in (int, float)
                                   or not math.isfinite(volume) or volume < 0):
            raise ValueError("Invalid volume, never assume a favorable reading")
        validated.append(tuple(row))
    return tuple(validated)


def _version_events(rows, *, shadow):
    """One set of cost-independent opportunities and hypothetical actions."""
    events, trades = [], []
    position = None
    pending = None
    # Stress-cash envelope prevents cost-driven candidate cherry-picking.
    stress_cash = 100000.0
    for i, row in enumerate(rows):
        if pending is not None and pending["at"] == i:
            price = row[2]
            if pending["kind"] == "ENTRY":
                debit = price * 1.001 * 1.002
                if debit <= stress_cash:
                    stress_cash -= debit
                    position = {"index": i, "price": price}
                    events.append({"index": i, "kind": "SIMULATED_ENTRY",
                                   "basis_decision_index": pending["from"]})
                else:
                    events.append({"index": i, "kind": "REJECTED_CAPITAL",
                                   "basis_decision_index": pending["from"]})
            else:
                entry = position
                assert entry is not None
                stress_cash += price * .999 * .998
                trades.append({"entry_index": entry["index"], "entry_price": entry["price"],
                               "exit_index": i, "exit_price": price})
                position = None
                events.append({"index": i, "kind": "SIMULATED_EXIT",
                               "basis_decision_index": pending["from"]})
            pending = None
        if i < 21:
            continue
        # All reference values are from completed PRIOR candles, never current/future.
        entry_level = max(r[3] for r in rows[i-20:i])
        prior_level = max(r[3] for r in rows[i-21:i-1])
        exit_level = min(r[4] for r in rows[i-10:i])
        breakout = row[5] > entry_level and rows[i-1][5] <= prior_level
        exit_signal = row[5] < exit_level
        if pending is not None:
            continue
        if position is not None:
            if exit_signal:
                _schedule(events, i, "EXIT", len(rows))
                if i+2 < len(rows):
                    pending = {"kind": "EXIT", "at": i+2, "from": i}
        elif breakout:
            if shadow:
                current_volume = row[6]
                previous_volumes = [r[6] for r in rows[i-20:i]]
                if current_volume is None or any(v is None for v in previous_volumes):
                    events.append({"index": i, "kind": "BLOCKED_MISSING_REQUIRED_DATA",
                                   "input": "volume", "value": "UNKNOWN"})
                    continue
                if not current_volume > 1.2 * (math.fsum(previous_volumes) / 20):
                    events.append({"index": i, "kind": "SHADOW_VOLUME_VETO"})
                    continue
            _schedule(events, i, "ENTRY", len(rows))
            if i+2 < len(rows):
                pending = {"kind": "ENTRY", "at": i+2, "from": i}
    return {"events": events, "trades": trades, "open_position": position,
            "pending_action": pending}


def _schedule(events, index, kind, length):
    # Candle i closes at index i+1 grid; unverified guard one MORE full 15m.
    candidate = index + 2
    events.append({"index": index, "kind": kind + "_SIGNAL",
                   "hypothetical_eligible_index": candidate,
                   "status": "SCHEDULED" if candidate < length else "UNRESOLVED_BOUNDARY"})
    

def _account(version, rows, costs):
    result = {}
    for label, config in costs.items():
        fee = config["fee_bps"] / 10000
        slip = config["slippage_bps"] / 10000
        realized = 0.0
        cash = 100000.0
        booked = []
        for t in version["trades"]:
            pair = account_long_prices(t["entry_price"], t["exit_price"],
                                       fee_bps=config["fee_bps"],
                                       slippage_bps=config["slippage_bps"])
            debit = pair["entry_execution_price"] * (1 + fee)
            credit = pair["exit_execution_price"] * (1 - fee)
            net = credit - debit
            cash += net
            realized += net
            booked.append({**t, "net_quote": net})
        open_position = version["open_position"]
        mark = None
        if open_position is not None:
            price = open_position["price"]
            debit = price * (1 + slip) * (1 + fee)
            cash -= debit
            mark = rows[-1][5] * (1 - slip) * (1 - fee)
        result[label] = {"trades": booked, "realized_pnl_quote": realized,
                         "terminal_equity_quote": cash + (mark or 0),
                         "open_position_mark_quote": mark,
                         "open_position_unrealized": open_position is not None}
    return result


def run_pilot(rows, *, plan, expected_plan_digest, expected_data_digest):
    """DEVELOPMENT-only synthetic proof; digest must be retained independently."""
    if not isinstance(plan, PilotPlan) or plan.digest != expected_plan_digest:
        raise ValueError("Frozen pilot plan mismatch")
    records = _validate(rows)
    if digest(records) != expected_data_digest:
        raise ValueError("Frozen synthetic data mismatch")
    versions = {}
    for name in ("BASE", "SHADOW"):
        path = _version_events(records, shadow=name == "SHADOW")
        versions[name] = {**path, "accounting": _account(path, records, COSTS),
                          "version": "BREAKOUT_20_10_" + name + "_v1"}
    output = {"schema": "sf-breakout-pilot-result-1", "phase": "SYNTHETIC_INTEGRATION_ONLY",
              "plan_digest": plan.digest, "data_digest": expected_data_digest,
              "actual_fills": "NOT_OBSERVED", "oos": "NOT_OPENED",
              "paper": "NOT_STARTED", "versions": versions}
    output["result_digest"] = digest(output)
    return output
