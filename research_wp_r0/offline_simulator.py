"""Conservative synthetic-only, single-long offline fill demonstrator.

This is NOT a production historical evaluator. Never emits COMPLETE or PnL for
ambiguous, missing, or unconfirmed data. Caller supplies independently audited
input receipt and separately retained digest.
"""
from .offline_input_audit import audit_offline_inputs
from .historical_evaluation_bridge import OfflineInputs
from .offline_evaluation_result import OfflineEvaluationResult


def simulate_single_long(inputs, *, expected_digest, signal, ttl_bars=1):
    """Evaluate one explicitly supplied long signal, not a strategy signal engine.

    Supported: no signal or a market entry at the first eligible next bar open,
    with a conservative exit at the following bar open. No stop/target model.
    Costs are supplied round-trip bps. Synthetic inputs ONLY.
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
    bars = spec["bars"]
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
    # Input receipts are a PIT prefix: no future bars may be present.
    # Therefore this function must not invent a next-bar fill.
    return OfflineEvaluationResult({**common, "outcome": "NO_FILL",
                                    "reason": "NO_ELIGIBLE_BAR"})
