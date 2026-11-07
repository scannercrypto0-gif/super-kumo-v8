"""Factory Package H: deterministic research-only trade/event ledger.

Consumes the existing Factory recovery v2 *causal focus* kernels; does not
reimplement indicator AST or source custody and does not dispatch orders.
The immutable event ledger is a sealed derived view of one focus-month run.
"""
from __future__ import annotations
from collections import Counter
from decimal import Decimal

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest, ResultsStoreError
from research_wp_r0.aql_factory_f_f2_recovery_research_v2 import (
    validate_recovery_research_input, _policy, _causal_focus,
)
from research_wp_r0.aql_factory_historical_rule_projection import (
    _vectors, _expression, _modeled_trade,
)

SCHEMA="aql.factory.h.trade-event-ledger.v1"
FILL="NEXT_ELIGIBLE_OPEN_RESEARCH_ONLY"
OUTCOMES=("MODEL_ONLY","UNKNOWN_INTRABAR_STOP_TARGET",
          "UNKNOWN_EXIT_RULE","UNKNOWN_END_OF_DATA")
EXPECTED={"modeled_gross_return","modeled_net_return","total_cost_bps"}


def _need(ok,reason):
    if not ok:
        raise ResultsStoreError("FACTORY_H_"+reason)


def _close(parent):
    _need(type(parent) is dict and type(parent.get("sha256")) is str
          and digest({k:v for k,v in parent.items() if k!="sha256"})
              == parent["sha256"],"SEALED_PARENT")


def build_trade_event_ledger(packet):
    """Return versioned causal events from existing Factory v2 conventions.

    This ledger never invents a fill for ambiguous stop/target chronology.
    Each period has a distinct decision/bar denominator, even without trades.
    """
    definitions,parents=validate_recovery_research_input(packet)
    trial=packet["trial_packet"]
    policy=packet["operator_policy"]
    definition=definitions[trial["strategy_id"]]
    bars=trial["bars"]
    fees=_policy(policy)
    values=_vectors(definition,bars)
    risk=definition.spec["risk"]
    events=[]
    outcomes=[]
    decisions=Counter()
    active=None
    blocked=False
    for index in range(len(bars)-1):
        bar=bars[index]
        cutoff=bar["close_ms"]+1
        if blocked:
            state="UNKNOWN_PATH_AFTER_BARRIER"
        elif active is None:
            signal=_expression(definition.spec["entry"],index,values)
            state=("WARMUP_UNKNOWN" if signal is None else
                   "NO_SIGNAL" if signal is False else "ENTRY_TRIGGERED")
            if signal is True:
                active={"entry_index":index+1,"decision_index":index}
                events.append({"event":"ENTRY_SIGNAL","decision_cutoff_ms":cutoff,
                               "next_eligible_open_ms":bars[index+1]["open_ms"],
                               "strategy_id":trial["strategy_id"]})
        else:
            entry=active["entry_index"]
            start=bars[entry]
            price=Decimal(str(start["open"]))
            stop=price*(Decimal(1)-Decimal(str(risk["stop_fraction"])))
            target=price*(Decimal(1)+Decimal(str(risk["target_fraction"])))
            low=Decimal(str(bar["low"]))
            high=Decimal(str(bar["high"]))
            if low<=stop or high>=target:
                state="UNKNOWN_INTRABAR_STOP_TARGET"
                outcomes.append({
                    "status":state,"entry_open_ms":start["open_ms"],
                    "exit_open_ms":None,"modeled_gross_return":None,
                    "modeled_net_return":None,"total_cost_bps":None,
                    "reason":"INTRABAR_CHRONOLOGY_NOT_OBSERVABLE"})
                blocked=True
                active=None
            else:
                signal=_expression(definition.spec["exit"],index,values)
                if signal is None:
                    state="UNKNOWN_EXIT_RULE"
                    outcomes.append({
                        "status":state,"entry_open_ms":start["open_ms"],
                        "exit_open_ms":None,"modeled_gross_return":None,
                        "modeled_net_return":None,"total_cost_bps":None,
                        "reason":"EXIT_SIGNAL_UNOBSERVABLE"})
                    blocked=True
                    active=None
                elif signal or index+1-entry>=risk["holding_bars"]:
                    state="EXIT_TRIGGERED"
                    row=_modeled_trade(bars,entry,index+1,"LONG",fees,"SPOT")
                    outcomes.append({**row,"status":"MODEL_ONLY",
                                     "reason":("EXIT_RULE" if signal
                                               else "HOLDING_CAP")})
                    active=None
                else:
                    state="IN_POSITION"
        decisions[state]+=1
        events.append({"event":"DECISION","bar_open_ms":bar["open_ms"],
                       "cutoff_ms":cutoff,"state":state})
    if active is not None:
        outcomes.append({
            "status":"UNKNOWN_END_OF_DATA",
            "entry_open_ms":bars[active["entry_index"]]["open_ms"],
            "exit_open_ms":None,"modeled_gross_return":None,
            "modeled_net_return":None,"total_cost_bps":None,
            "reason":"NO_CLOSED_ELIGIBLE_EXIT"})
    for row in outcomes:
        _need(row["status"] in OUTCOMES and set(row)>=EXPECTED,
              "OUTCOME_SHAPE")
    # Compare the event ledger against original existing Factory v2 kernel.
    baseline=_causal_focus(trial,definition,policy)
    counts=Counter(x["status"] for x in outcomes)
    _need(counts["MODEL_ONLY"]==baseline["modeled_count"] and
          sum(counts[s] for s in OUTCOMES if s!="MODEL_ONLY")
          ==baseline["unknown_count"] and
          len(events)>=baseline["decision_count"],
          "CAUSAL_KERNEL_DIVERGENCE")
    body={
        "schema":SCHEMA,"input_sha256":packet["sha256"],
        "strategy_digest":definition.digest,
        "scanner_receipt_sha256":packet["scanner_receipt_sha256"],
        "source_graph_sha256":digest(parents),
        "source_month":trial["diagnostic_month"],
        "source_bytes_sha256":trial["source_bytes_sha256"],
        "config_sha256":packet["config_sha256"],
        "code_sha256":packet["code_sha256"],
        "policy_sha256":digest(policy),
        "fill_contract":FILL,
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
        "holdout":"SEALED_UNOPENED",
        "cohort":{"source_months":10,"original_bars":29376,
                  "attempts":24,"evaluated":20,
                  "inventory_unknown":4,
                  "focus_bar_count":len(bars),
                  "decision_slots":len(bars)-1,
                  "modeled_trades":counts["MODEL_ONLY"],
                  "unknown_trades":sum(counts[s] for s in OUTCOMES
                                       if s!="MODEL_ONLY"),
                  "no_signal_bars":decisions["NO_SIGNAL"]},
        "decision_counts":dict(sorted(decisions.items())),
        "events":events,
        "outcomes":outcomes,
        "economic_policy_class":"OWNER_EXPLICIT_SCENARIO_NOT_INDEPENDENTLY_ATTESTED",
        "source_class":"RETROSPECTIVE_NON_PIT",
        "execution_status":"NOT_OBSERVED",
    }
    return {**body,"sha256":digest(body)}


def verify_trade_event_ledger(packet, ledger):
    expected=build_trade_event_ledger(packet)
    _need(type(ledger) is dict and expected==ledger,"SEALED_LEDGER_REPLAY_DRIFT")
    return ledger
