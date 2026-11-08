"""F-LAB-2: verified Generic H decisions to existing Core-style P2 paired Lab.

No second evaluator/backtester. Market window observations are explicit
synthetic research observations, NOT actual fills. Source and time metadata
must be pinned; no missing outcome may be converted to a positive return.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError,digest)
from research_wp_r0.aql_factory_lab_experiment_index_v1 import (
    get_experiment_link, require as checked)
from research_wp_r0.aql_p2_factory_lab import (
    validate_schedule,build_lab,HORIZONS)

SCHEMA="aql.factory.lab.h.paired-observation.v1"
RECEIPT="aql.factory.lab.h.paired-observation-report.v1"
STEP=900000
HOUR=3600000
MAPPING={"ENTRY_SIGNAL":"TRIGGERED","EXIT_SIGNAL":"REJECTED",
         "NO_SIGNAL":"NO_SIGNAL","UNKNOWN":"UNKNOWN"}


def need(ok,reason):
    if not ok:
        raise ResultsStoreError("FACTORY_LAB_2_"+reason)


def _sha(v):
    return type(v) is str and len(v)==64 and set(v)<=set("0123456789abcdef")


def _sealed(x):
    need(type(x) is dict and
         _sha(x.get("sha256")) and
         digest({k:v for k,v in x.items() if k!="sha256"})==x["sha256"],
         "SEALED_INPUT")
    return x


def build_generic_paired_lab(*,store_path,secretary_root,experiment_id,
                             packet,package,base_result,
                             observation_windows,comparison_definition_sha256,
                             protocol_sha256,evaluation_asof_ms,
                             embargo_ms=259200000):
    """Use real Generic H ledger, deterministic paired IDs, *actual* P2 Lab.

    `observation_windows` is a list with exact horizon/decision market
    observations supplied independently, never inferred from incomplete
    original/cutoff-constrained H bars. A future observation may be provided
    only when explicitly visible by `evaluation_asof_ms` and strictly before
    declared sealed holdout. For synthetic tests all numbers are TEST_ONLY.
    """
    index=get_experiment_link(store_path,experiment_id,
                              secretary_root=secretary_root)
    need(index["status"]=="VERIFIED_WAIT","UNREGISTERED_EXPERIMENT")
    link=index["link"]
    _sealed(packet)
    _sealed(package)
    need(type(base_result) is dict and _sha(base_result.get("receipt_sha256")) and
         digest({k:v for k,v in base_result.items()
                 if k!="receipt_sha256"})==base_result["receipt_sha256"],
         "RESULT_SEAL")
    need(packet["experiment_id"]==experiment_id and
         package["experiment_id"]==experiment_id and
         base_result["experiment_id"]==experiment_id and
         packet["sha256"]==link["input_sha256"] and
         package["sha256"]==link["package_sha256"] and
         base_result["receipt_sha256"]==digest({
             k:v for k,v in base_result.items() if k!="receipt_sha256"}) and
         base_result["result_sha256"]==link["result_sha256"] and
         package["trade_event_ledger"]["sha256"]==
             package["scientific_lab"]["ledger_sha256"] and
         packet["source_bytes_sha256"]==link["source_bytes_sha256"] and
         packet["source_query_sha256"]==link["source_query_sha256"] and
         packet["config_sha256"]==link["config_sha256"] and
         packet["operator_cost_policy"]["sha256"]==
             link["cost_policy_sha256"] and
         packet["strategy_definition_sha256"]==
             link["strategy_definition_sha256"] and
         _sha(comparison_definition_sha256) and
         _sha(protocol_sha256) and
         type(embargo_ms) is int and embargo_ms>=259200000,
         "CROSS_PARENT_COMPARISON_DRIFT")
    led=package["trade_event_ledger"]
    events=led["events"]
    need(len(events)==link["expected_bars"] and
         all(type(e["bar_open_ms"]) is int for e in events) and
         all(events[i]["bar_open_ms"]<events[i+1]["bar_open_ms"]
             for i in range(len(events)-1)),
         "ORIGINAL_DECISION_CENSUS")
    query=packet["core_query"]
    source_start=query["start_ms"]
    train_end=query["end_exclusive_ms"]
    eval_asof=evaluation_asof_ms
    need(query["source_bytes_sha256"]==link["source_bytes_sha256"] and
         query["query_sha256"]==link["source_query_sha256"] and
         type(train_end) is int and train_end>source_start and
         type(eval_asof) is int and
         eval_asof>query["decision_cutoff_ms"] and
         eval_asof<train_end+embargo_ms and
         eval_asof>=train_end,
         "SOURCE_CUTOFF")
    # Research windows require a later, *explicitly observed* as-of time;
    # no implicit immediate horizon results at the signal cutoff.
    need(type(observation_windows) is list and
         len(observation_windows)==len(events)*len(HORIZONS),
         "WINDOW_DENOMINATOR")
    windows={}
    allowed_open_ms={e["bar_open_ms"] for e in events}
    for w in observation_windows:
        need(type(w) is dict and set(w)=={
            "bar_open_ms","horizon_hours","availability",
            "availability_reason","market_metrics","observed_at_ms",
            "source_query_sha256","source_bytes_sha256",
            "experiment_id","strategy_definition_sha256",
            "cost_policy_sha256"},"WINDOW_SHAPE")
        key=(w["bar_open_ms"],w["horizon_hours"])
        need(key not in windows and w["bar_open_ms"] in
             allowed_open_ms and
             w["horizon_hours"] in HORIZONS and
             w["experiment_id"]==experiment_id and
             w["source_query_sha256"]==link["source_query_sha256"] and
             w["source_bytes_sha256"]==link["source_bytes_sha256"] and
             w["strategy_definition_sha256"]==
                 link["strategy_definition_sha256"] and
             w["cost_policy_sha256"]==link["cost_policy_sha256"] and
             type(w["observed_at_ms"]) is int,
             "WINDOW_IDENTITY")
        due=w["bar_open_ms"]+(w["horizon_hours"]*HOUR)
        need(w["observed_at_ms"]>=query["decision_cutoff_ms"] and
             w["observed_at_ms"]<=eval_asof and
             w["availability"] in ("COMPLETE","CENSORED","UNKNOWN") and
             (w["availability"]!="COMPLETE" or
              (w["observed_at_ms"]>=due and
               type(w["market_metrics"]) is dict)) and
             (w["availability"]=="COMPLETE" or
              (w["market_metrics"] is None and
               type(w["availability_reason"]) is str and
               bool(w["availability_reason"]))),
             "WINDOW_FUTURE_OR_NOT_OBSERVED")
        windows[key]=w
    # The retrospective research evaluation asof is independent of initial
    # signal cutoff; later outcomes are not eligible before this timestamp.
    need(len(windows)==len(observation_windows),"WINDOW_DUPLICATION")
    source_package_sha=digest({
        "source_query_sha256":link["source_query_sha256"],
        "source_bytes_sha256":link["source_bytes_sha256"],
        "manifest_integrity_sha256":link["manifest_integrity_sha256"],
        "factory_package_sha256":link["package_sha256"],
    })
    source_id="CORE253:"+link["source_query_sha256"]
    protocol={
        "trial_id":experiment_id,
        "protocol_sha256":protocol_sha256,
        "base_definition_sha256":link["strategy_definition_sha256"],
        "shadow_definition_sha256":comparison_definition_sha256,
        "embargo_ms":embargo_ms,
        "train_end_exclusive_ms":train_end,
        "holdout_start_ms":train_end+embargo_ms,
        "holdout_end_exclusive_ms":train_end+embargo_ms+HOUR,
    }
    source={"source_id":source_id,
            "source_package_sha256":source_package_sha}
    pairs=[]
    observations=[]
    for e in events:
        state=e["signal_state"]
        need(state in MAPPING and
             e["decision_cutoff_ms"]<=query["decision_cutoff_ms"] and
             e["bar_open_ms"]<train_end,
             "SIGNAL_TIME_OR_STATE")
        opid=digest({"experiment_id":experiment_id,
                     "scanner_event_sha256":e["scanner_event_sha256"],
                     "bar_open_ms":e["bar_open_ms"]})
        pair_id=digest({"protocol_sha256":protocol_sha256,
                        "trial_id":experiment_id,
                        "opportunity_id":opid})
        opp={
            "trial_id":experiment_id,
            "source_id":source_id,
            "source_package_sha256":source_package_sha,
            "opportunity_id":opid,
            "decision_cutoff_ms":e["decision_cutoff_ms"],
            "decision_ms":e["decision_cutoff_ms"],
            "disposition":MAPPING[state],
            "evidence_class":"RETROSPECTIVE_NON_PIT",
            "direction":None,"direction_evidence_ref":None,
            "regime":None,"regime_source_sha256":None,
        }
        pairs.append({
            "pair_id":pair_id,"opportunity":opp,
            "arms":[
                {"arm":"BASE",
                 "definition_sha256":link["strategy_definition_sha256"]},
                {"arm":"SHADOW",
                 "definition_sha256":comparison_definition_sha256}
            ]})
        for h in HORIZONS:
            window=windows[(e["bar_open_ms"],h)]
            for arm in ("BASE","SHADOW"):
                observations.append({
                    "pair_id":pair_id,"arm":arm,"horizon_hours":h,
                    "availability":window["availability"],
                    "availability_reason":window["availability_reason"],
                    "market_metrics":window["market_metrics"],
                    "directional_metrics":None,
                    "execution_status":"NOT_OBSERVED",
                })
    schedule={
        "schema":"aql.p2.core.paired-schedule.v1",
        "test_only":True,"evidence_class":"RETROSPECTIVE_NON_PIT",
        "holdout_status":"SEALED_UNOPENED",
        "outcome_evaluation":"NOT_PERFORMED",
        "execution_status":"NOT_OBSERVED",
        "protocol":protocol,"source":source,
        "scheduled_total":len(pairs),
        "pairs":pairs,
    }
    schedule["artifact_sha256"]=digest(schedule)
    validate_schedule(schedule)
    report=build_lab(schedule,observations,test_only=True)
    expected={k:sum(e["signal_state"]==k for e in events) for k in MAPPING}
    need(report["scheduled_opportunities"]==len(events) and
         report["observation_slots"]==len(events)*2*len(HORIZONS) and
         sum(expected.values())==len(events),
         "PAIRED_DENOMINATORS")
    body={
        "schema":RECEIPT,"experiment_id":experiment_id,
        "index_sha256":link["sha256"],
        "factory_package_sha256":link["package_sha256"],
        "scientific_lab_sha256":link["lab_sha256"],
        "secretary_wait_sha256":link["secretary_expected_sha256"],
        "source_query_sha256":link["source_query_sha256"],
        "strategy_definition_sha256":link["strategy_definition_sha256"],
        "shadow_definition_sha256":comparison_definition_sha256,
        "cost_policy_sha256":link["cost_policy_sha256"],
        "decision_counts":expected,
        "paired_schedule_sha256":schedule["artifact_sha256"],
        "paired_lab_sha256":report["artifact_sha256"],
        "horizon_coverage":report["market_coverage_by_horizon"],
        "observation_asof_ms":eval_asof,
        "observed_outcome_scope":"TEST_ONLY_DESCRIPTIVE_NO_ALPHA",
        "trading_authority":"NONE",
    }
    return {**body,"sha256":digest(body)}
