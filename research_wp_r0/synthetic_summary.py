"""Synthetic-only outcome counts; unresolved exposure never scored as zero PnL."""
from .strategy_definition import digest, keys


def summarize_synthetic_opportunities(ledger):
    keys(ledger, "schema synthetic_only independent_custody_verified records receipt_hash")
    if ledger["schema"] != "synthetic-opportunities-1" or ledger["synthetic_only"] is not True or ledger["independent_custody_verified"] is not False:
        raise ValueError("Not a synthetic opportunity ledger")
    if digest({k: v for k, v in ledger.items() if k != "receipt_hash"}) != ledger["receipt_hash"]:
        raise ValueError("Ledger receipt mismatch")
    counts = {"RESOLVED_TARGET": 0, "RESOLVED_STOP": 0, "UNRESOLVED": 0,
              "NO_FILL": 0, "NO_SIGNAL_EXECUTION": 0}
    net_returns = []
    if type(ledger["records"]) is not list:
        raise ValueError("Invalid records")
    previous_decision = -1
    for record in ledger["records"]:
        keys(record, "decision_bar_index status execution" if "execution" in record else "decision_bar_index status reason")
        decision = record["decision_bar_index"]
        if type(decision) is not int or decision <= previous_decision:
            raise ValueError("Decision order invalid")
        previous_decision = decision
        status = record["status"]
        if status not in counts:
            raise ValueError("Unknown opportunity status")
        if status == "NO_SIGNAL_EXECUTION":
            if record.get("reason") != "POSITION_ALREADY_ACTIVE" or "execution" in record:
                raise ValueError("Invalid blocked opportunity")
        else:
            execution = record.get("execution")
            if type(execution) is not dict or execution.get("status") != status:
                raise ValueError("Opportunity and execution status mismatch")
            if (execution.get("schema") != "synthetic-execution-1"
                    or execution.get("synthetic_only") is not True
                    or execution.get("independent_custody_verified") is not False
                    or digest({k: v for k, v in execution.items() if k != "receipt_hash"}) != execution.get("receipt_hash")):
                raise ValueError("Invalid nested execution receipt")
        counts[status] += 1
        if status.startswith("RESOLVED_"):
            execution = record["execution"]
            if (execution["status"] != status or "net_return" not in execution["details"] or
                    execution.get("synthetic_only") is not True or
                    digest({k: v for k, v in execution.items() if k != "receipt_hash"}) != execution.get("receipt_hash")):
                raise ValueError("Missing resolved execution evidence")
            net_returns.append(execution["details"]["net_return"])
        elif "execution" in record and "net_return" in record["execution"].get("details", {}):
            raise ValueError("Non-resolved outcome must not contain a scored return")
    result = {"schema": "synthetic-summary-1", "synthetic_only": True,
              "counts": counts, "total_opportunities": len(ledger["records"]),
              "resolved_trades": len(net_returns),
              "sum_resolved_net_returns": sum(net_returns),
              "mean_resolved_net_return": (sum(net_returns) / len(net_returns)
                                           if net_returns else None),
              "profitability_claim": False}
    result["receipt_hash"] = digest(result)
    return result
