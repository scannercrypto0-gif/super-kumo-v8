"""Separate post-decision execution bars from immutable decision-time inputs.

This contract verifies internal ordering/commitments only. It does not attest
exchange provenance, market completeness, or historical execution.
"""
from dataclasses import dataclass
import json
import re

from .strategy_definition import canonical, digest, integer, keys, number

_SHA = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, init=False)
class FutureBarEvidence:
    payload: bytes

    def __init__(self, value):
        keys(value, "schema_version inputs_digest decision_cutoff_ms symbol "
             "interval_ms bars independent_custody")
        if value["schema_version"] != "research-future-bars-1":
            raise ValueError("Unsupported future bar evidence schema")
        if type(value["inputs_digest"]) is not str or not _SHA.fullmatch(value["inputs_digest"]):
            raise ValueError("Invalid decision input commitment")
        integer(value["decision_cutoff_ms"], 0, 2**53-1)
        integer(value["interval_ms"], 1, 2**53-1)
        if type(value["symbol"]) is not str or not value["symbol"].strip():
            raise ValueError("Explicit symbol required")
        if value["independent_custody"] != "NOT_VERIFIED":
            raise ValueError("Cannot self-attest future evidence")
        bars = value["bars"]
        if type(bars) is not list or not 1 <= len(bars) <= 10000:
            raise ValueError("Bounded future bar evidence required")
        previous = None
        for bar in bars:
            keys(bar, "open_ms close_ms open high low close volume observed_at_ms")
            for field in ("open_ms", "close_ms", "observed_at_ms"):
                integer(bar[field], 0, 2**53-1)
            for field in ("open", "high", "low", "close"):
                number(bar[field], 0, 1e15)
                if bar[field] <= 0:
                    raise ValueError("Positive prices required")
            number(bar["volume"], 0, 1e18)
            if (bar["open_ms"] <= value["decision_cutoff_ms"] or
                bar["close_ms"] != bar["open_ms"] + value["interval_ms"] - 1 or
                bar["observed_at_ms"] <= bar["close_ms"] or
                bar["high"] < max(bar["open"], bar["close"], bar["low"]) or
                bar["low"] > min(bar["open"], bar["close"])):
                raise ValueError("Invalid post-decision OHLCV evidence")
            if previous is not None and bar["open_ms"] != previous + value["interval_ms"]:
                raise ValueError("Gap or duplicate future bar")
            previous = bar["open_ms"]
        object.__setattr__(self, "payload", canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return digest(self.spec)
