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
    # Missing post-decision evidence is UNKNOWN, not evidence of NO_FILL.
    return OfflineEvaluationResult({**common, "outcome": "UNRESOLVED",
                                    "reason": "UNKNOWN"})
