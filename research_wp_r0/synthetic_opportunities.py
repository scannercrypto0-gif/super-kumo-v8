"""Synthetic-only portfolio opportunity recorder.

Single-position policy: never invent a simultaneous fill. No profitability
claim, independent custody attestation, or historical/live order routing.
"""
from .strategy_definition import digest, integer
from .synthetic_execution import execute_synthetic_long


def run_synthetic_opportunities(bars, decision_indices, *, stop_fraction,
                                target_fraction, ttl_bars, holding_bars,
                                fee_bps, slippage_bps):
    if type(decision_indices) is not list or len(decision_indices) > 10000:
        raise ValueError("Bounded decision list required")
    previous = -1
    blocked_until = -1
    records = []
    for index in decision_indices:
        integer(index, 0, len(bars) - 1)
        if index <= previous:
            raise ValueError("Decision indices must be strictly increasing")
        previous = index
        if index <= blocked_until:
            record = {"decision_bar_index": index, "status": "NO_SIGNAL_EXECUTION",
                      "reason": "POSITION_ALREADY_ACTIVE"}
        else:
            result = execute_synthetic_long(
                bars, index, stop_fraction=stop_fraction,
                target_fraction=target_fraction, ttl_bars=ttl_bars,
                holding_bars=holding_bars, fee_bps=fee_bps,
                slippage_bps=slippage_bps)
            record = {"decision_bar_index": index, "status": result["status"],
                      "execution": result}
            if result["status"].startswith("RESOLVED_"):
                blocked_until = result["details"]["exit_bar_index"]
            elif result["status"] == "UNRESOLVED":
                # Unknown exposure cannot be assumed flat. Conservative quarantine
                # until the end of the available observation horizon.
                blocked_until = len(bars) - 1
        records.append(record)
    output = {"schema": "synthetic-opportunities-1", "synthetic_only": True,
              "independent_custody_verified": False, "records": records}
    output["receipt_hash"] = digest(output)
    return output
