"""Isolated owner-private RESEARCH_E2E_DIAGNOSTIC (never F5 approval).

Local SHA-pinned source and a declared read-only replay allow limited
engineering diagnostics of genuine operator-owned original bars. They are
not issuer authentication, independent policy approval or a Secretary ACK.
Uses existing AQL causal rule/cost engine and immutable v2 Results Store;
this module does NOT import the signed F5 execution gateway.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path

from research_wp_r0.aql_factory_authentic_research_admission import seal
from research_wp_r0.aql_factory_historical_rule_projection import evaluate_historical_rules
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError,build_experiment,register_experiment,read_experiment,
    audit_store_layout,digest,_sha
)
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

SCHEMA="aql.factory.f.research-e2e-diagnostic-input.v1"
OUTPUT="aql.factory.f.research-e2e-diagnostic-report.v1"
MAX_BYTES=50_000_000
MONTHS=[f"2024-{x:02d}" for x in range(1,13) if x not in (2,8)]


def need(condition,reason):
    if not condition:
        raise ResultsStoreError("FACTORY_DIAGNOSTIC_"+reason)


def load_json(path):
    p=Path(path)
    need(p.is_file() and not p.is_symlink()
         and 0<p.stat().st_size<=MAX_BYTES,"PRIVATE_FILE_PATH")
    return json.loads(p.read_text(encoding="utf-8"))


def _month_boundaries(month):
    y,m=map(int,month.split("-"))
    start=int(datetime(y,m,1,tzinfo=timezone.utc).timestamp()*1000)
    end=int(datetime(y+1,1,1,tzinfo=timezone.utc).timestamp()*1000) if m==12 else int(
        datetime(y,m+1,1,tzinfo=timezone.utc).timestamp()*1000)
    return start,end


def validate_diagnostic_input(packet):
    need(type(packet) is dict and packet.get("schema")==SCHEMA
         and _sha(packet.get("sha256"))
         and digest({k:v for k,v in packet.items() if k!="sha256"})
              ==packet["sha256"],"INPUT_SEAL")
    need(set(packet)=={
        "schema","sha256","experiment_id","local_source_mode",
        "core_f2_report_sha256","source_manifest_sha256",
        "core_245_query_sha256","core_253_query_sha256",
        "operator_local_source_readback_sha256","strategy_definition_sha256",
        "config_sha256","code_sha256","environment_sha256",
        "strategy","admitted_months","attempts","trial_packet",
        "source_coverage","market","symbol","timeframe","purpose"},
        "INPUT_FIELDS")
    need(packet["purpose"]=="RESEARCH_E2E_DIAGNOSTIC"
         and packet["local_source_mode"]=="OWNER_PRIVATE_READ_ONLY"
         and packet["market"]=="BINANCE:SPOT:USDT"
         and packet["symbol"]=="BTCUSDT" and packet["timeframe"]=="15m"
         and type(packet["experiment_id"]) is str
         and packet["experiment_id"].startswith("DIAG-F4-")
         and 0<len(packet["experiment_id"])<=160
         and type(packet["source_coverage"]) is dict,
         "DIAGNOSTIC_SCOPE")
    need(all(_sha(packet[name]) for name in (
        "core_f2_report_sha256","source_manifest_sha256",
        "core_245_query_sha256","core_253_query_sha256",
        "operator_local_source_readback_sha256",
        "strategy_definition_sha256","config_sha256","code_sha256",
        "environment_sha256")),"PARENTS")
    need(packet["core_245_query_sha256"]!=packet["core_253_query_sha256"],
         "ALIAS_DUAL_QUERY")
    need(packet["admitted_months"]==MONTHS,"EXACT_10_MONTHS")
    coverage=packet["source_coverage"]
    need(set(coverage)=={"new_admitted_months","new_admitted_bars",
                         "retained_inventory_months","retained_inventory_status",
                         "historical_pit","source_rights_assurance"},
         "COVERAGE_FIELDS")
    need(coverage["new_admitted_months"]==10
         and coverage["new_admitted_bars"]==29376
         and coverage["retained_inventory_months"]==["2024-02","2024-08"]
         and coverage["retained_inventory_status"]=="INVENTORY_ONLY_NOT_READBACK"
         and coverage["historical_pit"]=="NOT_ATTESTED"
         and coverage["source_rights_assurance"]=="LOCAL_OPERATOR_DECLARED_NOT_INDEPENDENT",
         "COVERAGE_PROMOTION")
    need(type(packet["attempts"]) is list and len(packet["attempts"])==24,
         "ATTEMPT_DENOMINATOR")
    seen=set()
    admitted_counts={m:0 for m in MONTHS}
    retained_counts={"2024-02":0,"2024-08":0}
    attempts=[]
    candidates=set()
    for row in packet["attempts"]:
        need(type(row) is dict and set(row)=={
            "attempt_id","candidate_id","month","state",
            "source_receipt_sha256"},"ATTEMPT_FIELDS")
        need(type(row["attempt_id"]) is str and 0<len(row["attempt_id"])<=160
             and row["attempt_id"] not in seen
             and type(row["candidate_id"]) is str and 0<len(row["candidate_id"])<=160
             and _sha(row["source_receipt_sha256"]),"ATTEMPT_IDENTITY")
        seen.add(row["attempt_id"])
        candidates.add(row["candidate_id"])
        m=row["month"]
        if m in admitted_counts:
            admitted_counts[m]+=1
            need(row["state"] in ("UNKNOWN","REJECTED"),
                 "NO_REAL_SELECTED_PROMOTION")
        else:
            need(m in retained_counts and row["state"]=="UNKNOWN",
                 "RETAINED_MONTH_NOT_UNKNOWN")
            retained_counts[m]+=1
        attempts.append({k:row[k] for k in (
            "attempt_id","candidate_id","state","source_receipt_sha256")})
    need(len(candidates)==2 and all(x==2 for x in admitted_counts.values())
         and all(x==2 for x in retained_counts.values()),
         "MISSING_STRATEGY_MONTH_DENOMINATOR")
    packet_trial=packet["trial_packet"]
    need(type(packet_trial) is dict and packet_trial.get("schema")
         =="aql.factory.historical-rule-projection.v1"
         and packet_trial.get("source_kind")=="ORIGINAL_UNVERIFIED"
         and packet_trial.get("availability")=="RETROSPECTIVE_NON_PIT"
         and packet_trial.get("holdout")=="SEALED_UNOPENED"
         and packet_trial.get("execution_authority")=="NONE"
         and packet_trial.get("market")=="SPOT"
         and packet_trial.get("width_ms")==900000
         and packet_trial.get("source_manifest_sha256")==packet["source_manifest_sha256"]
         and packet_trial.get("strategy")==packet["strategy"]
         and packet_trial.get("source_bytes_sha256")==packet[
             "operator_local_source_readback_sha256"],
         "SOURCE_RULE_PARENT")
    need(type(packet_trial.get("bars")) is list
         and 2<=len(packet_trial["bars"])<=35000
         and all(bar.get("known_at_ms") is None
                 for bar in packet_trial["bars"]),"BARS_UNKNOWN_ISSUER_PIT")
    month=packet_trial.get("diagnostic_month")
    need(month in MONTHS,"EVALUATED_MONTH_ADMITTED")
    first,last=_month_boundaries(month)
    need(all(type(bar.get("open_ms")) is int
             and type(bar.get("close_ms")) is int
             and first<=bar["open_ms"] and bar["close_ms"]<last
             for bar in packet_trial["bars"]),"CROSS_MONTH_SOURCE_ACCESS")
    need(packet_trial["bars"][-1]["close_ms"]<
         packet_trial["research_window"]["train_end_exclusive_ms"],
         "FUTURE_BAR_BLOCK")
    definition=StrategyDefinition.from_dict(packet["strategy"],
                                             registry=IndicatorRegistryV2())
    need(definition.digest==packet["strategy_definition_sha256"],
         "STRATEGY_DEFINITION")
    need(packet_trial.get("strategy_definition_sha256") in
         (None,definition.digest),"STRATEGY_PARENT")
    need(packet_trial.get("selected_attempt_id") in seen,
         "RULE_TRIAL_NOT_IN_CENSUS")
    need(any(r["attempt_id"]==packet_trial["selected_attempt_id"] and
             r["month"]==month for r in packet["attempts"]),
         "RULE_MONTH_IDENTITY")
    return definition,attempts


def run_diagnostic(packet,store_path):
    definition,attempts=validate_diagnostic_input(packet)
    # A selected rule projection target is only a diagnostic computational
    # focus, NEVER a historical strategy selection/authorization.
    trial=dict(packet["trial_packet"])
    trial.pop("diagnostic_month")
    lab=evaluate_historical_rules(seal(trial))
    need(lab["trading_authority"]=="NONE"
         and lab["historical_pit_verified"] is False
         and lab["source_class"]=="ORIGINAL_UNVERIFIED"
         and lab["execution_status"]=="NOT_OBSERVED","LAB_AUTHORITY")
    lab_sha=lab["artifact_sha256"]
    result_body={
        "schema":"aql.factory.f.research-e2e-diagnostic-evaluation.v1",
        "input_sha256":packet["sha256"],"lab_sha256":lab_sha,
        "core_f2_report_sha256":packet["core_f2_report_sha256"],
        "local_source_readback_sha256":packet["operator_local_source_readback_sha256"],
        "research_class":"RETROSPECTIVE_NON_PIT",
        "not_authority":"NOT_F5_APPROVAL_OR_FACTORY_CONSUMER_ACK",
        "modeled_count":len(lab["modeled_outcomes"]),
        "unknown_count":lab["unknown_outcomes"],
        "costs":lab["costs"],"trading_authority":"NONE"}
    result_sha=digest(result_body)
    record=build_experiment(
        experiment_id=packet["experiment_id"],lane="SCANNER",
        source_status="RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT",
        source_sha256=packet["operator_local_source_readback_sha256"],
        source_query_245_sha256=packet["core_245_query_sha256"],
        source_query_253_sha256=packet["core_253_query_sha256"],
        strategy_definition_sha256=definition.digest,
        config_sha256=packet["config_sha256"],
        code_sha256=packet["code_sha256"],
        environment_sha256=packet["environment_sha256"],
        parent_receipt_sha256=packet["sha256"],
        attempts=attempts,lab_receipt_sha256=lab_sha,
        result_sha256=result_sha,evidence_class="RETROSPECTIVE_NON_PIT")
    saved=register_experiment(store_path,record)
    need(read_experiment(store_path,packet["experiment_id"])==record,
         "IMMUTABLE_READBACK")
    summary=audit_store_layout(store_path)
    need(summary["experiment_count"]>=1,"LAYOUT_READBACK")
    output={
        "schema":OUTPUT,"status":"DIAGNOSTIC_ONLY_NOT_F5",
        "input_sha256":packet["sha256"],
        "experiment_id":packet["experiment_id"],
        "experiment_sha256":record["sha256"],
        "result_sha256":result_sha,"lab_sha256":lab_sha,
        "core_f2_report_sha256":packet["core_f2_report_sha256"],
        "operator_local_source_readback_sha256":
            packet["operator_local_source_readback_sha256"],
        "attempt_count":record["attempt_count"],
        "attempt_states":record["attempt_states"],
        "feb_aug_inventory_unknown":4,
        "modeled_count":len(lab["modeled_outcomes"]),
        "unknown_count":lab["unknown_outcomes"],
        "costs":lab["costs"],
        "store_status":saved["status"],
        "layout_version":summary["layout_version"],
        "factory_consumer_ack_sha256":None,
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "independent_policy_approval_sha256":None,
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
        "paper":"NOT_ACTIVATED","orders_created":0,
        "positions":0,"actual_fills":None,"holdout":"SEALED_UNOPENED"}
    return {**output,"receipt_sha256":digest(output)}


def main():
    p=argparse.ArgumentParser(description="AQL diagnostic only, not signed F5")
    p.add_argument("--private-input-json",required=True)
    p.add_argument("--diagnostic-store",required=True)
    p.add_argument("--sanitized-out-json",required=True)
    a=p.parse_args()
    try:
        inp=load_json(a.private_input_json)
        out=run_diagnostic(inp,a.diagnostic_store)
        path=Path(a.sanitized_out_json)
        need(path.parent.is_dir() and not path.is_symlink(),
             "OUTPUT_PATH")
        path.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",
                        encoding="utf-8")
        print(json.dumps(out,sort_keys=True))
    except (ResultsStoreError,ValueError,TypeError,KeyError) as exc:
        raise SystemExit("PRIVATE_DIAGNOSTIC_WAIT: "+str(exc))


if __name__=="__main__":
    main()
