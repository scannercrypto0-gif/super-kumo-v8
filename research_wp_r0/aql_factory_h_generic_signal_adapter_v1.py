"""Factory H generic research receiver — verified Scanner H signals, NOT F2.

The legacy F2 24-attempt receiver remains untouched. This narrow adapter
consumes Scanner-verified closed-bar signal events and the matching sealed
Core253 receipt, reuses Factory's existing next-open/Decimal cost kernel,
existing scientific Lab consumer and immutable SQLite v2 H table.
No independent Scanner AST re-evaluation, fabricated fills or real execution.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest, ResultsStoreError, audit_store_layout,
)
from research_wp_r0.aql_factory_h_research_package_v1 import _store_package
from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_immutable_ledger
from research_wp_r0.aql_factory_historical_rule_projection import (
    _modeled_trade, _costs, COST_KEYS,
)

SCHEMA="aql.factory.h.generic-signal-input.v1"
COST_SCHEMA="aql.factory.h.generic-cost-policy.v1"
LEDGER_SCHEMA="aql.factory.h.generic-trade-event-ledger.v1"
REPORT_SCHEMA="aql.factory.h.generic-execution-report.v1"
SECRETARY_SCHEMA="aql.factory.h.generic-secretary-review-receipt.v1"
RESULT_SCHEMA="aql.factory.h.generic-research-result.v1"
PACKAGE_SCHEMA="aql.factory.h.generic-immutable-package.v1"
FIELDS={
    "schema","sha256","experiment_id","scanner_signal_batch",
    "strategy_plugin","scanner_signal_policy","core_query",
    "operator_cost_policy","factory_code_sha256",
    "source_query_sha256","source_bytes_sha256",
    "manifest_integrity_sha256","strategy_definition_sha256",
    "strategy_plugin_sha256","config_sha256","scanner_policy_sha256",
    "scanner_evaluator_code_sha256","decision_cutoff_ms",
    "holdout","historical_pit","trading_authority",
    "source_ack_sha256","strategy_approval_sha256",
    "factory_consumer_ack_sha256",
}
COST_FIELDS={
    "schema","costs","market","direction","scenario_class",
    "owner_operator_authorized","fill_semantics","holdout",
    "trading_authority","sha256",
}
HEX=set("0123456789abcdef")
SCENARIOS={
    "SYNTHETIC_TEST_EXPLICIT",
    "OWNER_DECLARED_RESEARCH_SCENARIO",
}


def _need(ok,reason):
    if not ok:
        raise ResultsStoreError("FACTORY_H_GENERIC_"+reason)


def _sha(s):
    return type(s) is str and len(s)==64 and set(s)<=HEX


def _sealed(document,key="sha256"):
    _need(type(document) is dict and _sha(document.get(key)) and
          digest({k:v for k,v in document.items() if k!=key})==
              document[key],"SEAL_"+key)
    return document


def _verified(packet):
    """Consume EXACT actual Scanner verifier; no fork of the signal engine."""
    _need(type(packet) is dict and set(packet)==FIELDS and
          packet.get("schema")==SCHEMA,"PACKET_FIELDS")
    _sealed(packet)
    _need(type(packet["experiment_id"]) is str and
          packet["experiment_id"].startswith("RESEARCH-H-GENERIC-") and
          len(packet["experiment_id"])<=160 and
          all(_sha(packet[k]) for k in (
              "factory_code_sha256","source_query_sha256",
              "source_bytes_sha256","manifest_integrity_sha256",
              "strategy_definition_sha256","strategy_plugin_sha256",
              "config_sha256","scanner_policy_sha256",
              "scanner_evaluator_code_sha256")) and
          all(packet[k] is None for k in (
              "source_ack_sha256","strategy_approval_sha256",
              "factory_consumer_ack_sha256")) and
          packet["trading_authority"]=="NONE" and
          packet["historical_pit"]=="NOT_ATTESTED" and
          packet["holdout"]=="SEALED_UNOPENED",
          "PARENT_AUTHORITY")
    # This import resolves from the separately pinned Scanner #277 overlay.
    # Factory does NOT vendor or duplicate its verifier/indicator evaluation.
    from tools.scanner_strategy_f import research_strategy_plugin as scanner
    from tools.strategy_service_offline.common import Frozen
    from research_wp_r0.strategy_definition import StrategyDefinition
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

    verified=scanner.verify_factory_signal_batch(packet["scanner_signal_batch"])
    batch=verified.data
    plugin=Frozen.restore(packet["strategy_plugin"])
    meta=plugin.data
    signal_policy=Frozen.restore(packet["scanner_signal_policy"])
    scanner._validate_policy(packet["scanner_signal_policy"])
    scanner._validate_query(packet["core_query"])
    query=packet["core_query"]
    _need(set(meta)==scanner.PLUGIN_FIELDS and
          meta.get("schema")==scanner.PLUGIN_SCHEMA and
          meta.get("trading_authority")=="NONE" and
          meta.get("policy_status")=="RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL"
          and meta.get("historical_pit")=="NOT_ATTESTED" and
          all(meta.get(k) is None for k in (
              "source_ack_sha256","strategy_approval_sha256",
              "factory_consumer_ack_sha256")) and
          meta.get("input_origin") in ("MANUAL","DISCOVERER_CANDIDATE")
          and ((meta["input_origin"]=="MANUAL"
                and meta.get("candidate_sha256") is None)
               or (meta["input_origin"]=="DISCOVERER_CANDIDATE"
                   and _sha(meta.get("candidate_sha256")))),
          "PLUGIN_SCOPE")
    definition=StrategyDefinition.from_dict(
        meta["definition"],registry=IndicatorRegistryV2())
    _need(definition.digest==meta["definition_digest"] and
          meta["strategy_id"]==definition.spec["strategy_id"] and
          meta["strategy_version"]==definition.spec["strategy_version"] and
          meta["timing"]==definition.spec["timing"] and
          meta["timing"]=={
              "decision":"CONFIRMED_CLOSE",
              "entry_execution":"NEXT_ELIGIBLE_OPEN",
              "ambiguity":"REJECT",
          } and definition.spec["scope"]=="RESEARCH_ONLY" and
          meta["parameters"]==[
              {"name":r["name"],"indicator_id":r["indicator_id"],
               "version":r["version"],"parameters":r["parameters"]}
              for r in definition.spec["indicators"]],
          "PLUGIN_DEFINITION_DRIFT")
    if meta["source_spec_sha256"] is None:
        _need(meta["config_identity_class"]=="MANUAL_AST_PARAMETERS"
              and meta["config_digest"]==
                  scanner.manual_config_digest(meta["definition"]),
              "MANUAL_CONFIG_DRIFT")
    else:
        known=scanner.FROZEN.get(meta["strategy_id"])
        _need(known is not None and
              meta["source_spec_sha256"]==known["spec_sha256"] and
              meta["config_digest"]==known["config_digest"] and
              meta["definition_digest"]==known["definition_digest"] and
              meta["config_identity_class"]=="WORK235_FROZEN_TEST_ONLY",
              "FROZEN_CONFIG_DRIFT")
    _need(meta["evaluator_code_sha256"]==scanner._code_sha(),
          "SCANNER_EVALUATOR_CODE_DRIFT")
    _need(batch["strategy_plugin_sha256"]==plugin.sha256==
              packet["strategy_plugin_sha256"] and
          batch["strategy_definition_digest"]==definition.digest==
              packet["strategy_definition_sha256"] and
          batch["config_digest"]==meta["config_digest"]==
              packet["config_sha256"] and
          batch["evaluator_code_sha256"]==meta["evaluator_code_sha256"]==
              packet["scanner_evaluator_code_sha256"] and
          batch["policy_sha256"]==signal_policy.sha256==
              packet["scanner_policy_sha256"] and
          batch["source_class"]==signal_policy.data["source_class"] and
          batch["source_query_sha256"]==query["query_sha256"]==
              packet["source_query_sha256"] and
          batch["source_bytes_sha256"]==query["source_bytes_sha256"]==
              packet["source_bytes_sha256"] and
          batch["manifest_integrity_sha256"]==
              query["manifest_integrity_sha256"]==
              packet["manifest_integrity_sha256"] and
          batch["dataset_id"]==query["dataset_id"] and
          batch["decision_cutoff_ms"]==query["decision_cutoff_ms"]==
              packet["decision_cutoff_ms"] and
          batch["start_ms"]==query["start_ms"] and
          batch["end_exclusive_ms"]==query["end_exclusive_ms"] and
          batch["coverage"]==query["coverage"] and
          batch["expected_bar_count"]==query["required_bar_count"] and
          batch["observed_bar_count"]==query["available_bar_count"] and
          batch["missing_bar_count"]==len(query["missing_bar_opens"]),
          "CROSS_OWNER_SOURCE_QUERY_IDENTITY")
    policy=_sealed(packet["operator_cost_policy"])
    _need(set(policy)==COST_FIELDS and policy["schema"]==COST_SCHEMA and
          policy["scenario_class"] in SCENARIOS and
          type(policy["owner_operator_authorized"]) is bool and
          policy["owner_operator_authorized"] is
              (policy["scenario_class"]==
               "OWNER_DECLARED_RESEARCH_SCENARIO") and
          policy["fill_semantics"]==
              "NEXT_ELIGIBLE_OPEN_UNKNOWN_ON_INTRABAR_TOUCH" and
          policy["direction"]=="LONG" and policy["market"]=="SPOT" and
          policy["holdout"]=="SEALED_UNOPENED" and
          policy["trading_authority"]=="NONE" and
          type(policy["costs"]) is dict and
          set(policy["costs"])==set(COST_KEYS) and
          all(type(x) is str for x in policy["costs"].values()),
          "EXPLICIT_COST_POLICY_REQUIRED")
    fees=_costs({"costs":policy["costs"],"market":"SPOT"})
    _need(all(x>=0 for x in fees.values()) and
          fees["funding_bps_per_bar"]==Decimal(0),
          "COST_POLICY_SPOT_OR_NEGATIVE")
    return batch,query,definition,fees,policy,verified.sha256


def _execution(batch,query,definition,fees,packet,policy,scanner_sha):
    # Scanner decides signals. Factory sees only validated events and Core
    # original readback prices; neither signal nor indicator AST is rerun.
    price_rows=query["bars"]
    complete=batch["coverage"]=="COMPLETE"
    bars=[
        {"open_ms":b["bar_open_ms"],"open":b["open"],
         "close":b["close"],"high":b["high"],"low":b["low"],
         "close_ms":b["bar_close_ms"]}
        for b in price_rows
    ]
    expected=batch["expected_bar_count"]
    _need(not complete or len(bars)==expected,"COMPLETE_GRID_COUNT")
    risk=definition.spec["risk"]
    decisions=[]
    outcomes=[]
    active=None
    blocked=False
    counts=Counter()
    for i,signal in enumerate(batch["events"]):
        state=signal["signal_state"]
        execution="NO_MODEL_FILL"
        counts[state]+=1
        if not complete:
            _need(state=="UNKNOWN","GAPPED_SOURCE_MUST_QUARANTINE")
            execution="UNKNOWN_SOURCE_GAP_NO_FILLS"
        elif blocked:
            execution="BLOCKED_AFTER_UNOBSERVABLE_OUTCOME"
        elif active is None:
            if state=="ENTRY_SIGNAL":
                if i+1<len(bars):
                    _need(signal["next_eligible_open_ms"]==
                          bars[i+1]["open_ms"] and
                          bars[i+1]["close_ms"]<
                          batch["decision_cutoff_ms"],
                          "ENTRY_FUTURE_NEXT_OPEN")
                    active=i+1
                    execution="MODELED_ENTRY_AT_NEXT_OBSERVED_OPEN"
                else:
                    execution="UNKNOWN_NEXT_OPEN_NOT_OBSERVED"
            elif state=="UNKNOWN":
                execution="UNKNOWN_SIGNAL_NO_TRADE"
        else:
            entry=bars[active]
            current=bars[i]
            entry_price=Decimal(str(entry["open"]))
            stop=entry_price*(Decimal(1)-Decimal(str(risk["stop_fraction"])))
            target=entry_price*(Decimal(1)+Decimal(str(risk["target_fraction"])))
            touched=(Decimal(str(current["low"]))<=stop or
                     Decimal(str(current["high"]))>=target)
            if touched:
                execution="UNKNOWN_INTRABAR_STOP_TARGET"
                outcomes.append({
                    "status":"UNKNOWN_INTRABAR_STOP_TARGET",
                    "entry_open_ms":entry["open_ms"],"exit_open_ms":None,
                    "modeled_gross_return":None,"modeled_net_return":None,
                    "total_cost_bps":None,
                    "reason":"STOP_OR_TARGET_OHLCV_CHRONOLOGY_UNKNOWN"})
                blocked=True
                active=None
            elif state=="UNKNOWN":
                execution="UNKNOWN_EXIT_RULE"
                outcomes.append({
                    "status":"UNKNOWN_EXIT_RULE",
                    "entry_open_ms":entry["open_ms"],"exit_open_ms":None,
                    "modeled_gross_return":None,"modeled_net_return":None,
                    "total_cost_bps":None,
                    "reason":"SCANNER_EXIT_SIGNAL_UNOBSERVABLE"})
                blocked=True
                active=None
            elif state=="EXIT_SIGNAL" or i+1-active>=risk["holding_bars"]:
                if i+1>=len(bars):
                    execution="UNKNOWN_END_OF_DATA"
                    outcomes.append({
                        "status":"UNKNOWN_END_OF_DATA",
                        "entry_open_ms":entry["open_ms"],"exit_open_ms":None,
                        "modeled_gross_return":None,
                        "modeled_net_return":None,
                        "total_cost_bps":None,
                        "reason":"NO_ELIGIBLE_NEXT_OPEN"})
                    blocked=True
                    active=None
                else:
                    _need(bars[i+1]["open_ms"]==
                          signal["bar_close_ms"]+1 and
                          bars[i+1]["close_ms"]<
                          batch["decision_cutoff_ms"],
                          "EXIT_FUTURE_NEXT_OPEN")
                    trade=_modeled_trade(bars,active,i+1,"LONG",fees,"SPOT")
                    outcomes.append({**trade,"status":"MODEL_ONLY",
                                     "reason":("SCANNER_EXIT_SIGNAL" if
                                               state=="EXIT_SIGNAL"
                                               else "STRATEGY_HOLDING_CAP")})
                    execution="MODELED_EXIT_AT_NEXT_OBSERVED_OPEN"
                    active=None
            else:
                execution="POSITION_HELD_NO_EXIT_SIGNAL"
        decisions.append({
            "bar_open_ms":signal["bar_open_ms"],
            "decision_cutoff_ms":signal["research_asof_ms"],
            "scanner_event_sha256":signal["event_sha256"],
            "signal_state":state,
            "execution_state":execution,
            "source_observed":signal["source_observed"],
        })
    if active is not None:
        outcomes.append({
            "status":"UNKNOWN_END_OF_DATA",
            "entry_open_ms":bars[active]["open_ms"],
            "exit_open_ms":None,
            "modeled_gross_return":None,"modeled_net_return":None,
            "total_cost_bps":None,
            "reason":"NO_CLOSED_EXIT_BEFORE_RANGE_END"})
    _need(counts==Counter(batch["signal_counts"]) and
          len(decisions)==expected and
          len({x["bar_open_ms"] for x in decisions})==expected,
          "SIGNAL_DENOMINATOR_RECONCILIATION")
    n_modeled=sum(x["status"]=="MODEL_ONLY" for x in outcomes)
    n_unknown=len(outcomes)-n_modeled
    economic="DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED" if all(
        v==0 for v in fees.values()) else (
        "EXPLICIT_DECLARED_COST_SCENARIO_NOT_INDEPENDENTLY_ATTESTED")
    body={
        "schema":LEDGER_SCHEMA,
        "input_sha256":packet["sha256"],
        "scanner_receipt_sha256":scanner_sha,
        "scanner_policy_sha256":packet["scanner_policy_sha256"],
        "scanner_plugin_sha256":packet["strategy_plugin_sha256"],
        "source_query_sha256":packet["source_query_sha256"],
        "source_graph_sha256":digest({
            "source_query_sha256":query["query_sha256"],
            "source_bytes_sha256":query["source_bytes_sha256"],
            "manifest_integrity_sha256":query["manifest_integrity_sha256"],
            "decision_cutoff_ms":query["decision_cutoff_ms"],
        }),
        "source_month":"GENERIC_RANGE",
        "source_bytes_sha256":query["source_bytes_sha256"],
        "strategy_digest":packet["strategy_definition_sha256"],
        "config_sha256":packet["config_sha256"],
        "code_sha256":packet["factory_code_sha256"],
        "policy_sha256":policy["sha256"],
        "fill_contract":"NEXT_ELIGIBLE_OPEN_RESEARCH_ONLY",
        "cohort":{
            "cohort_class":"GENERIC_SCANNER_H",
            "coverage":batch["coverage"],
            "expected_bars":expected,
            "observed_bars":batch["observed_bar_count"],
            "missing_bars":batch["missing_bar_count"],
            "decision_slots":expected,
            "focus_bar_count":batch["observed_bar_count"],
            "signal_unknown":counts["UNKNOWN"],
            "entry_signals":counts["ENTRY_SIGNAL"],
            "exit_signals":counts["EXIT_SIGNAL"],
            "no_signal_bars":counts["NO_SIGNAL"],
            "modeled_trades":n_modeled,
            "unknown_trades":n_unknown,
        },
        "decision_counts":dict(sorted(counts.items())),
        "events":decisions,
        "outcomes":outcomes,
        "economic_policy_class":economic,
        "source_class":batch["source_class"],
        "historical_pit":"NOT_ATTESTED",
        "holdout":"SEALED_UNOPENED",
        "execution_status":"NOT_OBSERVED",
        "trading_authority":"NONE",
    }
    return {**body,"sha256":digest(body)}


def _secretary(packet,ledger,lab,factory_result):
    """Research review pointer only. Existing F2→Core Secretary bridge untouched."""
    _need(lab["ledger_sha256"]==ledger["sha256"] and
          factory_result["lab_sha256"]==lab["sha256"] and
          factory_result["ledger_sha256"]==ledger["sha256"],
          "SECRETARY_PARENT_DRIFT")
    body={
        "schema":SECRETARY_SCHEMA,
        "state":"RESEARCH_RESULT_READY_FOR_REVIEW_NOT_ACK",
        "source_query_sha256":packet["source_query_sha256"],
        "source_bytes_sha256":packet["source_bytes_sha256"],
        "manifest_integrity_sha256":packet["manifest_integrity_sha256"],
        "strategy_definition_sha256":packet["strategy_definition_sha256"],
        "strategy_plugin_sha256":packet["strategy_plugin_sha256"],
        "config_sha256":packet["config_sha256"],
        "scanner_evaluator_code_sha256":packet["scanner_evaluator_code_sha256"],
        "factory_code_sha256":packet["factory_code_sha256"],
        "scanner_signal_policy_sha256":packet["scanner_policy_sha256"],
        "cost_policy_sha256":ledger["policy_sha256"],
        "decision_cutoff_ms":packet["decision_cutoff_ms"],
        "experiment_input_sha256":packet["sha256"],
        "experiment_sha256":factory_result["experiment_sha256"],
        "result_sha256":factory_result["result_sha256"],
        "lab_sha256":lab["sha256"],
        "ledger_sha256":ledger["sha256"],
        "uncertainty_sha256":digest(lab["uncertainty"]),
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "trading_authority":"NONE",
        "paper":"NOT_ACTIVATED",
        "holdout":"SEALED_UNOPENED",
        "historical_pit":"NOT_ATTESTED",
    }
    return {**body,"sha256":digest(body)}


def run_factory_h_generic_research(packet,store_path):
    """Return status-bound report; SQLite layout-v2 preexists outside RAW."""
    batch,query,definition,fees,policy,scanner_sha=_verified(packet)
    path=Path(store_path)
    _need(path.is_file() and path.suffix==".sqlite" and
          audit_store_layout(path)["layout_version"]==2,
          "ISOLATED_EXISTING_SQLITE_V2_REQUIRED")
    ledger=_execution(batch,query,definition,fees,packet,policy,scanner_sha)
    lab=evaluate_immutable_ledger(ledger)
    experiment_sha=digest({
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "strategy_digest":definition.digest,
        "source_query_sha256":query["query_sha256"],
        "scanner_batch_sha256":scanner_sha,
        "cost_policy_sha256":policy["sha256"],
    })
    result_sha=digest({
        "experiment_sha256":experiment_sha,
        "ledger_sha256":ledger["sha256"],
        "lab_sha256":lab["sha256"],
        "execution_status":"NOT_OBSERVED",
        "trading_authority":"NONE",
    })
    factory_body={
        "schema":REPORT_SCHEMA,
        "input_sha256":packet["sha256"],
        "experiment_sha256":experiment_sha,
        "result_sha256":result_sha,
        "ledger_sha256":ledger["sha256"],
        "lab_sha256":lab["sha256"],
        "scanner_batch_sha256":scanner_sha,
        "source_query_sha256":packet["source_query_sha256"],
        "source_bytes_sha256":packet["source_bytes_sha256"],
        "strategy_definition_sha256":definition.digest,
        "config_sha256":packet["config_sha256"],
        "factory_code_sha256":packet["factory_code_sha256"],
        "cost_policy_sha256":policy["sha256"],
        "decision_cutoff_ms":packet["decision_cutoff_ms"],
        "economic_class":ledger["economic_policy_class"],
        "historical_pit":"NOT_ATTESTED",
        "holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "paper":"NOT_ACTIVATED",
        "f5":"BLOCKED_EXTERNAL_INPUT",
    }
    factory={**factory_body,"sha256":digest(factory_body)}
    secretary=_secretary(packet,ledger,lab,factory)
    package={
        "schema":PACKAGE_SCHEMA,
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "factory_report":factory,
        "trade_event_ledger":ledger,
        "scientific_lab":lab,
        "secretary_research_receipt":secretary,
        "economic_class":ledger["economic_policy_class"],
        "holdout":"SEALED_UNOPENED",
        "historical_pit":"NOT_ATTESTED",
        "f5":"BLOCKED_EXTERNAL_INPUT",
        "trading_authority":"NONE",
    }
    package_sha,status=_store_package(path,package)
    outer={
        "schema":RESULT_SCHEMA,
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "package_sha256":package_sha,
        "factory_report_sha256":factory["sha256"],
        "trade_ledger_sha256":ledger["sha256"],
        "scientific_lab_sha256":lab["sha256"],
        "secretary_receipt_sha256":secretary["sha256"],
        "experiment_sha256":experiment_sha,
        "result_sha256":result_sha,
        "scanner_batch_sha256":scanner_sha,
        "cost_policy_sha256":policy["sha256"],
        "economic_class":ledger["economic_policy_class"],
        "store_status":status,
        "f5":"BLOCKED_EXTERNAL_INPUT",
        "trading_authority":"NONE",
        "paper":"NOT_ACTIVATED",
        "holdout":"SEALED_UNOPENED",
    }
    return {**outer,"receipt_sha256":digest(outer)}
