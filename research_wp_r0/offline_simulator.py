"""Conservative synthetic-only, single-long offline fill demonstrator.

This is NOT a production historical evaluator. Never emits COMPLETE or PnL for
ambiguous, missing, or unconfirmed data. Caller supplies independently audited
input receipt and separately retained digest.
"""
from .offline_input_audit import audit_offline_inputs
from .historical_evaluation_bridge import OfflineInputs
from .offline_evaluation_result import OfflineEvaluationResult
from .future_bar_evidence import FutureBarEvidence
from .strategy_definition import number
from .historical_library import _interval_to_ms
import re

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def simulate_single_long(inputs, *, expected_digest, signal, ttl_bars=1,
                         future=None, expected_future_digest=None):
    """Evaluate one explicitly supplied long signal, not a strategy signal engine.

    Supported: zero-exposure NO_SIGNAL or UNKNOWN when post-decision
    execution evidence is absent. Never manufactures fills or no-fill claims.
    Synthetic inputs ONLY.
    """
    audit_offline_inputs(inputs, expected_digest=expected_digest)
    if type(signal) is not bool:
        raise ValueError("Explicit boolean signal required")
    if type(ttl_bars) is not int or ttl_bars != 1:
        raise ValueError("Only one-bar TTL supported")
    spec = inputs.spec
    if spec["protocol"]["data_class"] != "SYNTHETIC_TEST":
        raise ValueError("Historical evaluation not yet admitted")
    decision = spec["binding"]["binding"]["decision_cutoff_ms"]
    common = {
        "schema_version": "research-eval-result-1",
        "inputs_digest": inputs.digest,
        "strategy_digest": spec["strategy"]["digest"],
        "protocol_digest": spec["protocol_digest"],
        "decision_cutoff_ms": decision,
        "entry_bar_open_ms": None,
        "exit_bar_open_ms": None,
        "gross_return_bps": None,
        "fee_bps": None,
        "slippage_bps": None,
        "net_return_bps": None,
        "independent_custody": "NOT_VERIFIED",
    }
    if not signal:
        return OfflineEvaluationResult({**common, "outcome": "NO_SIGNAL",
                                        "reason": "NO_SIGNAL"})
    if future is None:
        if expected_future_digest is not None:
            raise ValueError("Future digest supplied without evidence")
        return OfflineEvaluationResult({**common, "outcome": "UNRESOLVED",
                                        "reason": "UNKNOWN"})
    if not isinstance(future, FutureBarEvidence):
        raise ValueError("Validated future evidence required")
    if (type(expected_future_digest) is not str or
        not _SHA256.fullmatch(expected_future_digest) or
        expected_future_digest != future.digest):
        raise ValueError("Separately retained future evidence digest required")
    evidence = future.spec
    if (evidence["inputs_digest"] != inputs.digest or
        evidence["decision_cutoff_ms"] != decision or
        evidence["symbol"] != spec["dataset_manifest"]["symbol"]):
        raise ValueError("Future evidence identity mismatch")
    interval = _interval_to_ms(spec["dataset_manifest"]["interval"])
    if evidence["interval_ms"] != interval:
        raise ValueError("Future interval does not match audited dataset")
    # The first bar must be the first *eligible* next open on the
    # original dataset grid. Otherwise an unobserved fill may be hidden.
    historical_bars = spec["bars"]
    if not historical_bars:
        raise ValueError("Audited historical bars required for grid binding")
    last_open = historical_bars[-1]["open_ms"]
    expected_open = last_open + ((decision - last_open) // interval + 1) * interval
    if evidence["bars"][0]["open_ms"] != expected_open:
        return OfflineEvaluationResult({**common, "outcome": "UNRESOLVED",
                                        "reason": "DATA_GAP"})
    if len(evidence["bars"]) < 2:
        return OfflineEvaluationResult({**common, "outcome": "UNRESOLVED",
                                        "reason": "UNKNOWN"})
    entry, exit_ = evidence["bars"][:2]
    if entry["open_ms"] <= decision or exit_["open_ms"] <= entry["open_ms"]:
        raise ValueError("Invalid execution chronology")
    # Synthetic market-open entry and next-bar-open exit ONLY.
    # Protocol costs are per-side bps; both sides are charged.
    fee = 2 * number(spec["protocol"]["fee_bps"], 0, 10000)
    slip = 2 * number(spec["protocol"]["slippage_bps"], 0, 10000)
    gross = (exit_["open"] / entry["open"] - 1) * 10000
    net = gross - fee - slip
    return OfflineEvaluationResult({
        **common, "outcome": "SIMULATED_CLOSED", "reason": "NONE",
        "entry_bar_open_ms": entry["open_ms"],
        "exit_bar_open_ms": exit_["open_ms"],
        "gross_return_bps": gross, "fee_bps": fee,
        "slippage_bps": slip, "net_return_bps": net,
    })
