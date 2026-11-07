"""Package H research-only scientific assessment of an immutable Factory ledger.

Consumes Factory's SHA-sealed derived trade/event ledger, never OHLCV bars or
recomputed signals. Statistical estimates are explicitly descriptive and
sample-dependent, not proof of historical PIT, OOS alpha or real fills.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, localcontext
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest,ResultsStoreError,
)

SCHEMA="aql.factory.h.scientific-lab-report.v1"
RECEIPT="aql.factory.h.secretary-research-result-ready.v1"
MIN_WIN_RATE_N=10
MIN_RISK_N=30


def _need(ok,reason):
    if not ok:
        raise ResultsStoreError("FACTORY_H_LAB_"+reason)


def _d(s):
    return Decimal(str(s))


def _ratio(top,bottom):
    return str(top/bottom) if bottom else None


def _dd(sequence):
    equity=Decimal(1)
    peak=equity
    dd=Decimal(0)
    for value in sequence:
        equity*=Decimal(1)+value
        peak=max(peak,equity)
        dd=max(dd,(peak-equity)/peak)
    return dd


def evaluate_immutable_ledger(ledger, *, comparison=None):
    """Descriptive comparable research statistics, not a profitable strategy claim."""
    _need(type(ledger) is dict and ledger.get("schema")==
          "aql.factory.h.trade-event-ledger.v1" and
          ledger.get("sha256")==digest({k:v for k,v in ledger.items()
                                       if k!="sha256"}) and
          ledger.get("trading_authority")=="NONE" and
          ledger.get("historical_pit")=="NOT_ATTESTED" and
          ledger.get("holdout")=="SEALED_UNOPENED",
          "PARENT_SEAL_OR_AUTHORITY")
    cohort=ledger["cohort"]
    outcomes=ledger["outcomes"]
    _need(type(outcomes) is list and type(cohort) is dict and
          cohort["attempts"]==24 and cohort["evaluated"]==20 and
          cohort["inventory_unknown"]==4 and
          cohort["source_months"]==10 and cohort["original_bars"]==29376
          and cohort["decision_slots"]>0 and
          cohort["focus_bar_count"]==cohort["decision_slots"]+1
          and len(ledger["events"])>=cohort["decision_slots"],
          "DENOMINATOR_OR_SCOPE")
    count=Counter(r["status"] for r in outcomes)
    _need(count["MODEL_ONLY"]==cohort["modeled_trades"] and
          sum(v for k,v in count.items() if k!="MODEL_ONLY")==
          cohort["unknown_trades"] and
          set(count)<= {"MODEL_ONLY","UNKNOWN_INTRABAR_STOP_TARGET",
                        "UNKNOWN_EXIT_RULE","UNKNOWN_END_OF_DATA"},
          "OUTCOME_DENOMINATOR")
    with localcontext() as ctx:
        ctx.prec=40
        modeled=[x for x in outcomes if x["status"]=="MODEL_ONLY"]
        returns=[_d(x["modeled_net_return"]) for x in modeled]
        gross=[_d(x["modeled_gross_return"]) for x in modeled]
        costs=[_d(x["total_cost_bps"]) for x in modeled]
        holding=[int(x["holding_bars"]) for x in modeled]
        _need(all(Decimal("-1")<=v for v in returns) and
              all(h>0 for h in holding),"INVALID_TRADE_RETURN")
        n=len(returns)
        winners=sum(r>0 for r in returns)
        losses=sum(r<0 for r in returns)
        pos=sum((r for r in returns if r>0),Decimal(0))
        neg=-sum((r for r in returns if r<0),Decimal(0))
        net_total=Decimal(1)
        gross_total=Decimal(1)
        for v in returns:
            net_total*=Decimal(1)+v
        for v in gross:
            gross_total*=Decimal(1)+v
        decision_slots=cohort["decision_slots"]
        exposure=Decimal(sum(holding))/Decimal(decision_slots) if decision_slots else None
        _need(exposure is None or exposure<=1,"EXPOSURE_OVERLAP")
        # Conservative: no annualization or observed-fill inference.
        if n>=MIN_RISK_N and not cohort["unknown_trades"]:
            mean=sum(returns,Decimal(0))/Decimal(n)
            variance=sum(((v-mean)**2 for v in returns),Decimal(0))/Decimal(n-1)
            sd=variance.sqrt()
            sharpe=_ratio(mean,sd)
        else:
            sharpe=None
        comparable={"strategy_digest":ledger["strategy_digest"],
                    "month":ledger["source_month"],
                    "source_sha256":ledger["source_bytes_sha256"],
                    "policy_sha256":ledger["policy_sha256"],
                    "decision_slots":decision_slots,
                    "unknown_trades":cohort["unknown_trades"],
                    "modeled_trades":n}
        if comparison is not None:
            _need(type(comparison) is dict and
                  comparison.get("source_month")==ledger["source_month"] and
                  comparison.get("source_bytes_sha256")==ledger[
                      "source_bytes_sha256"] and
                  comparison.get("cohort",{}).get("decision_slots")==
                      decision_slots and
                  comparison.get("historical_pit")=="NOT_ATTESTED",
                  "NONCOMPARABLE_COHORT")
            comparable["comparison_input_sha256"]=comparison.get("sha256")
        metrics={
            "modeled_trade_count":n,
            "gross_compounded_return":str(gross_total-1) if n else None,
            "net_compounded_return":str(net_total-1) if n else None,
            "cost_bps_total":str(sum(costs,Decimal(0))) if n else None,
            "fee_spread_slippage_bps_per_trade":(
                str(sum(costs,Decimal(0))/n) if n else None),
            "gross_return_arithmetic_sum":str(sum(gross,Decimal(0))) if n else None,
            "net_return_arithmetic_sum":str(sum(returns,Decimal(0))) if n else None,
            "exposure_bar_fraction":str(exposure) if n else None,
            "turnover_round_trip_proxy":n if n else None,
            "max_drawdown_trade_close_only":str(_dd(returns)) if n else None,
            "win_rate":str(Decimal(winners)/n) if n>=MIN_WIN_RATE_N and
                        not cohort["unknown_trades"] else None,
            "profit_factor":_ratio(pos,neg) if neg>0 and
                           n>=MIN_WIN_RATE_N and
                           not cohort["unknown_trades"] else None,
            "sharpe_per_trade_unannualized":sharpe,
            "unknown_outcomes":cohort["unknown_trades"],
            "insufficient_sample":n<MIN_WIN_RATE_N,
        }
    # Sensitivity only on the SAME immutable outcomes; no optimization,
    # parameter re-evaluation or fake robustness inference.
    adjusted={}
    for extra_bps in ("0","5","10"):
        offset=Decimal(extra_bps)/Decimal(10000)
        equity=Decimal(1)
        for net in returns:
            equity*=Decimal(1)+net-offset
        adjusted[extra_bps]=str(equity-1) if returns else None
    body={
        "schema":SCHEMA,"ledger_sha256":ledger["sha256"],
        "experiment_input_sha256":ledger["input_sha256"],
        "strategy_digest":ledger["strategy_digest"],
        "source_sha256":ledger["source_bytes_sha256"],
        "policy_sha256":ledger["policy_sha256"],
        "config_sha256":ledger["config_sha256"],
        "code_sha256":ledger["code_sha256"],
        "scanner_receipt_sha256":ledger["scanner_receipt_sha256"],
        "cohort":cohort,"comparable":comparable,
        "metrics":metrics,
        "sensitivity":{"cost_extra_bps_round_trip":adjusted,
                       "parameter_change":"NOT_EVALUATED_NO_REOPTIMIZATION"},
        "uncertainty":{"unknown_outcomes":cohort["unknown_trades"],
                       "incomplete_months":["2024-02","2024-08"],
                       "in_sample_only":True,
                       "holdout_opened":False,
                       "historical_pit":"NOT_ATTESTED",
                       "independent_source_rights":"NOT_ATTESTED",
                       "economic_claim":"NOT_ATTESTED"},
        "economic_class":ledger["economic_policy_class"],
        "assessment":"DESCRIPTIVE_RESEARCH_ONLY_NO_ALPHA_CLAIM",
        "research_ready_for_review":True,
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
    }
    return {**body,"sha256":digest(body)}


def secretary_research_receipt(*, packet, factory_report, ledger, lab):
    """Sealed research result for Secretary REVIEW/WAIT only, never ACK."""
    _need(type(packet) is dict and packet.get("sha256")==
          digest({k:v for k,v in packet.items() if k!="sha256"}),
          "UNSEALED_INPUT")
    _need(type(factory_report) is dict and factory_report.get(
          "receipt_sha256")==digest({k:v for k,v in factory_report.items()
                                     if k!="receipt_sha256"}) and
          factory_report.get("trading_authority")=="NONE" and
          factory_report.get("original_f2_report_sha256") is None,
          "UNSEALED_FACTORY")
    _need(type(lab) is dict and lab.get("sha256")==
          digest({k:v for k,v in lab.items() if k!="sha256"}) and
          lab["ledger_sha256"]==ledger["sha256"] and
          lab["experiment_input_sha256"]==packet["sha256"],
          "LAB_PARENT_DRIFT")
    _need(ledger["sha256"]==digest({k:v for k,v in ledger.items()
                                   if k!="sha256"}) and
          ledger["input_sha256"]==packet["sha256"] and
          factory_report["input_sha256"]==packet["sha256"],
          "LEDGER_FACTORY_PARENT_DRIFT")
    body={
        "schema":RECEIPT,
        "state":"RESEARCH_RESULT_READY_FOR_REVIEW_NOT_ACK",
        "factory_report_receipt_sha256":factory_report["receipt_sha256"],
        "source_graph_sha256":ledger["source_graph_sha256"],
        "source_sha256":ledger["source_bytes_sha256"],
        "strategy_definition_sha256":ledger["strategy_digest"],
        "config_sha256":packet["config_sha256"],
        "policy_sha256":ledger["policy_sha256"],
        "code_sha256":packet["code_sha256"],
        "experiment_sha256":factory_report["experiment_sha256"],
        "lab_sha256":lab["sha256"],
        "result_sha256":factory_report["result_sha256"],
        "experiment_input_sha256":packet["sha256"],
        "scope":"RESEARCH_ONLY_RETROSPECTIVE_NON_PIT",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "holdout":"SEALED_UNOPENED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
        "uncertainty_sha256":digest(lab["uncertainty"]),
    }
    return {**body,"sha256":digest(body)}
