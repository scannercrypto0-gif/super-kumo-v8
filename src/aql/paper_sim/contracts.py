"""Frozen synthetic simulation contracts; decimal quantities are JSON strings."""
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re


def need(ok, reason):
    if not ok:
        raise ValueError("PAPER_SIM_" + reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def dec(value, *, zero=False):
    need(type(value) is str and len(value) <= 64, "DECIMAL_STRING_REQUIRED")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("PAPER_SIM_INVALID_DECIMAL") from None
    need(result.is_finite() and len(result.as_tuple().digits) <= 28 and (result >= 0 if zero else result > 0)
         and abs(result.adjusted()) <= 18, "DECIMAL_RANGE")
    return result


def ms(value):
    need(type(value) is int and 0 <= value <= 2**53-1, "INVALID_TIME")
    return value


@dataclass(frozen=True)
class Policy:
    """Every number is a declared assumption, not a venue fee/depth observation.

    Fees and adverse selection use each fill's quote notional. Spread is a
    per-side half spread. Maker volume/depth supplied on each bar are explicit
    synthetic assumptions; OHLC touch alone never establishes queue fills.
    """
    version: int = 1
    taker_fee_bps: str = "10"
    maker_fee_bps: str = "2"
    half_spread_bps: str = "1"
    slippage_bps: str = "2"
    maker_adverse_bps: str = "1"
    capital: str = "10000"
    max_notional: str = "1000"
    allow_fallback: bool = False

    def __post_init__(self):
        need(type(self.version) is int and self.version == 1, "POLICY_VERSION")
        need(type(self.allow_fallback) is bool, "FALLBACK_FLAG")
        for name in ("taker_fee_bps", "maker_fee_bps", "half_spread_bps", "slippage_bps", "maker_adverse_bps"):
            need(dec(getattr(self, name), zero=True) <= 1000, "COST_RANGE")
        need(dec(self.max_notional) <= dec(self.capital), "RISK_BUDGET")


def signal(value):
    keys = {"schema", "signal_id", "strategy_id", "strategy_version", "definition_sha256",
            "config_sha256", "evaluator_sha256", "source_sha256", "symbol", "interval_ms",
            "decision_ms", "source_close_ms", "available_ms", "evidence_mode", "trading_authority"}
    need(type(value) is dict and set(value) == keys, "SIGNAL_FIELDS")
    need(value["schema"] == "aql.paper-sim.signal.v1" and value["evidence_mode"] == "SYNTHETIC_TESTED"
         and value["trading_authority"] == "NONE", "OFFLINE_ONLY")
    for key in ("signal_id", "definition_sha256", "config_sha256", "evaluator_sha256", "source_sha256"):
        need(sha(value[key]), "SIGNAL_DIGEST")
    for key in ("strategy_id", "strategy_version", "symbol"):
        need(type(value[key]) is str and 0 < len(value[key]) <= 128, "SIGNAL_IDENTITY")
    need(type(value["interval_ms"]) is int and 0 < value["interval_ms"] <= 86400000, "INTERVAL")
    need(ms(value["source_close_ms"]) < ms(value["available_ms"]) <= ms(value["decision_ms"]), "SIGNAL_ASOF")
    return json.loads(canonical(value))


def bar(value, *, as_of_ms):
    fields = {"symbol", "open_ms", "close_ms", "received_ms", "open", "high", "low", "close",
              "final", "clock_verified", "synthetic", "taker_qty", "maker_volume"}
    need(type(value) is dict and set(value) == fields, "BAR_FIELDS")
    need(value["final"] is True and value["clock_verified"] is True and value["synthetic"] is True,
         "BAR_FINAL_CLOCK_SYNTHETIC")
    need(ms(value["open_ms"]) <= ms(value["close_ms"]) < ms(value["received_ms"]) <= ms(as_of_ms), "BAR_ASOF")
    o, h, l, c = [dec(value[k]) for k in ("open", "high", "low", "close")]
    need(l <= min(o, c) <= max(o, c) <= h, "OHLC")
    for name in ("taker_qty", "maker_volume"):
        if value[name] is not None:
            dec(value[name], zero=True)
    return json.loads(canonical(value))
