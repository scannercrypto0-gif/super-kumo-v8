"""Versioned, deterministic *result contract* for future offline evaluation.

No fills are calculated here; no COMPLETE ledger event or custody claim.
"""
from dataclasses import dataclass
import json
import re

from .strategy_definition import canonical, digest, keys, integer, number

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OUTCOMES = frozenset({"NO_SIGNAL", "NO_FILL", "UNRESOLVED", "SIMULATED_CLOSED"})
_REASONS = frozenset({
    "NONE", "NO_SIGNAL", "TTL_EXPIRED", "NO_ELIGIBLE_BAR",
    "SAME_BAR_AMBIGUITY", "DATA_GAP", "DELISTING", "UNKNOWN",
})


@dataclass(frozen=True, init=False)
class OfflineEvaluationResult:
    """A validated proposed result; not evidence that simulation was run."""

    payload: bytes

    def __init__(self, value):
        keys(value, "schema_version inputs_digest strategy_digest protocol_digest "
             "outcome reason decision_cutoff_ms entry_bar_open_ms exit_bar_open_ms "
             "gross_return_bps fee_bps slippage_bps net_return_bps "
             "independent_custody")
        if value["schema_version"] != "research-eval-result-1":
            raise ValueError("Unsupported result schema")
        for field in ("inputs_digest", "strategy_digest", "protocol_digest"):
            if type(value[field]) is not str or not _SHA.fullmatch(value[field]):
                raise ValueError("Invalid result commitment: " + field)
        outcome, reason = value["outcome"], value["reason"]
        if outcome not in _OUTCOMES or reason not in _REASONS:
            raise ValueError("Invalid result outcome/reason")
        if value["independent_custody"] != "NOT_VERIFIED":
            raise ValueError("Result cannot self-attest custody")
        integer(value["decision_cutoff_ms"], 0, 2**53 - 1)
        entry, exit_ = value["entry_bar_open_ms"], value["exit_bar_open_ms"]
        if outcome == "SIMULATED_CLOSED":
            if reason != "NONE":
                raise ValueError("Closed simulation must have NONE reason")
            integer(entry, 0, 2**53 - 1)
            integer(exit_, 0, 2**53 - 1)
            if not (value["decision_cutoff_ms"] < entry < exit_):
                raise ValueError("Execution must occur strictly after decision")
            for field in ("gross_return_bps", "fee_bps", "slippage_bps", "net_return_bps"):
                number(value[field], -1000000 if field in ("gross_return_bps", "net_return_bps") else 0,
                       1000000)
            if abs(value["net_return_bps"] - (value["gross_return_bps"] -
                       value["fee_bps"] - value["slippage_bps"])) > 1e-8:
                raise ValueError("Net return must include both-side costs")
        else:
            if entry is not None or exit_ is not None:
                raise ValueError("Unexecuted or unresolved result cannot claim fills")
            if any(value[field] is not None for field in
                   ("gross_return_bps", "fee_bps", "slippage_bps", "net_return_bps")):
                raise ValueError("Unknown/unexecuted outcome cannot claim PnL")
            expected = {"NO_SIGNAL": {"NO_SIGNAL"}, "NO_FILL": {"TTL_EXPIRED", "NO_ELIGIBLE_BAR"},
                        "UNRESOLVED": {"SAME_BAR_AMBIGUITY", "DATA_GAP", "DELISTING", "UNKNOWN"}}
            if reason not in expected[outcome]:
                raise ValueError("Incompatible outcome/reason")
        object.__setattr__(self, "payload", canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return digest(self.spec)
