"""Factory F4/F5: bounded PRIVATE source-backed retrospective research command.

Real positive execution is not implied by self-declared SHAs: the caller must
supply a trusted, separately pinned external attestation of Core's actual F2
run, Scanner owner policy approval, source ACK and StrategyApproval. This
module checks file bytes and the graph against that trusted pin. No network,
broker, holdout, OHLCV upload or Paper is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, build_experiment, register_experiment, read_experiment,
    digest, _sha,
)
from research_wp_r0.aql_factory_authentic_research_admission import seal
from research_wp_r0.aql_factory_historical_rule_projection import (
    evaluate_historical_rules,
)
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

SCHEMA="aql.factory.f.private-original-cohort-input.v1"
TRUST="aql.factory.f.external-independent-trust-witness.v1"
OUTPUT="aql.factory.f.private-original-cohort-result.v1"
MAX_INPUT_BYTES=50_000_000
MAX_BARS=40000
MAX_ATTEMPTS=10000
REQUIRED_PARENTS=(
    "core_f2_report_sha256","source_ack_sha256",
    "independent_policy_approval_sha256","strategy_approval_sha256",
    "core_245_query_sha256","core_253_query_sha256",
)


def need(ok,code):
    if not ok:
        raise ResultsStoreError("FACTORY_F_PRIVATE_"+code)


def _load(path,limit):
    p=Path(path)
    need(p.is_file() and not p.is_symlink()
         and 0<p.stat().st_size<=limit,"BOUNDED_FILE")
    return json.loads(p.read_text(encoding="utf-8"))


def _exact(doc,keys,name):
    need(type(doc) is dict and set(doc)==set(keys),name)


def _witness(packet,witness,witness_sha):
    """Verify independently pinned TRUST CHANNEL, not just a self SHA seal.

    Operator must pin witness_sha OUT OF BAND from independent authorized
    custody/policy/Secretary approver. This code cannot authenticate whoever
    issued the out-of-band reference on its own.
    """
    _exact(witness,("schema","factory_input_sha256","trust_class",
                    "core_f2_report_sha256","source_ack_sha256",
                    "independent_policy_approval_sha256",
                    "strategy_approval_sha256","core_245_query_sha256",
                    "core_253_query_sha256","issuer_reference",
                    "authorization_reference","approved_months"),
           "WITNESS_SHAPE")
    need(witness["schema"]==TRUST and witness["trust_class"]
         =="OUT_OF_BAND_INDEPENDENT_APPROVER",
         "INDEPENDENT_WITNESS_REQUIRED")
    need(_sha(witness_sha) and digest(witness)==witness_sha
         and witness["factory_input_sha256"]==packet["sha256"],
         "WITNESS_INDEPENDENT_PIN")
    for name in REQUIRED_PARENTS:
        need(_sha(witness[name]) and witness[name]==packet[name],
             "TRUSTED_PARENT_"+name.upper())
    need(witness["core_245_query_sha256"] != witness["core_253_query_sha256"],
         "DUAL_QUERY_DISTINCT")
    authority_ids=(witness["core_f2_report_sha256"],witness["source_ack_sha256"],
                   witness["independent_policy_approval_sha256"],
                   witness["strategy_approval_sha256"])
    need(len(set(authority_ids))==len(authority_ids),
         "DISTINCT_SOURCE_POLICY_STRATEGY_ACK")
    need(type(witness["issuer_reference"]) is str
         and len(witness["issuer_reference"])>=8
         and type(witness["authorization_reference"]) is str
         and len(witness["authorization_reference"])>=8,
         "EXTERNAL_APPROVER_REFERENCE")
    need(witness["approved_months"]==packet["admitted_months"],
         "MONTH_AUTHORITY_SCOPE")


def validate_input(packet,witness,witness_sha):
    _exact(packet,("schema","experiment_id","batch_id","market",
                   "symbol","timeframe","policy_id","policy_draft_sha256",
                   "core_f2_report","core_f2_report_sha256",
                   "source_ack_sha256","independent_policy_approval_sha256",
                   "strategy_approval_sha256","core_245_query_sha256",
                   "core_253_query_sha256","source_manifest_sha256",
                   "admitted_months","strategy","strategy_definition_sha256",
                   "config_sha256","code_sha256","environment_sha256",
                   "attempts","trial_packet","sha256"),"INPUT_SHAPE")
    need(packet["schema"]==SCHEMA and _sha(packet.get("sha256"))
         and digest({k:v for k,v in packet.items() if k!="sha256"})
         ==packet["sha256"],"INPUT_CANONICAL_SEAL")
    need(packet["market"]=="BINANCE:SPOT:USDT"
         and packet["symbol"]=="BTCUSDT" and packet["timeframe"]=="15m"
         and packet["policy_id"]=="btc-spot-15m-retrospective-non-pit-v1"
         and _sha(packet["policy_draft_sha256"])
         and type(packet["batch_id"]) is str
         and type(packet["experiment_id"]) is str,
         "SCOPE")
    report=packet["core_f2_report"]
    need(type(report) is dict and report.get("schema")
         =="aql.core.f.private-raw-warehouse-dual-query-report.v1"
         and _sha(report.get("report_sha256"))
         and digest({k:v for k,v in report.items()
                     if k!="report_sha256"})==report["report_sha256"]
         and packet["core_f2_report_sha256"]==report["report_sha256"],
         "CORE_F2_REPORT")
    need(report["manifest_sha256"]==packet["source_manifest_sha256"]
         and report["f2_new_admitted_count"]==len(report["entries"])==10
         and report["f2_previous_retained_inventory_only_count"]==2
         and report["factory_consumer_ack"] is None
         and report["secretary_historical_strategy_route"]=="NOT_AUTHORIZED"
         and report["strategy_policy_approval"]=="NOT_ATTESTED_BY_CORE"
         and report["historical_pit"]=="NOT_ATTESTED"
         and report["trading_authority"]=="NONE",
         "CORE_F2_CANNOT_ISSUE_STRATEGY_ACK")
    months=[]
    entries_by_month={}
    for entry in report["entries"]:
        need(type(entry) is dict and
             set(entry)=={"month","state","source_sha256",
                          "checksum_file_sha256","csv_member_sha256",
                          "warehouse_receipt_sha256",
                          "core_245_native_price_query_sha256",
                          "core_253_local_query_sha256","dual_query_map_sha256",
                          "bars","historical_pit"},
             "CORE_F2_ENTRY_SHAPE")
        m=entry["month"]
        need(type(m) is str and m.startswith("2024-") and m[-2:].isdigit()
             and 1<=int(m[-2:])<=12 and m not in ("2024-02","2024-08")
             and m not in entries_by_month
             and entry["state"]=="RAW_AND_DUAL_QUERY_READBACK"
             and entry["historical_pit"]=="NOT_ATTESTED"
             and all(_sha(entry[k]) for k in (
                  "source_sha256","checksum_file_sha256",
                  "csv_member_sha256","warehouse_receipt_sha256",
                  "core_245_native_price_query_sha256",
                  "core_253_local_query_sha256","dual_query_map_sha256"))
             and entry["core_245_native_price_query_sha256"] !=
                  entry["core_253_local_query_sha256"]
             and type(entry["bars"]) is int and entry["bars"]>0,
             "CORE_F2_ENTRY_UNVERIFIED")
        from calendar import monthrange
        yy,mm=map(int,m.split("-"))
        need(entry["bars"]==monthrange(yy,mm)[1]*96,
             "CORE_F2_MONTH_BAR_CENSUS")
        entries_by_month[m]=entry
        months.append(m)
    expected_new_months=[f"2024-{i:02d}" for i in range(1,13)
                         if i not in (2,8)]
    need(type(packet["admitted_months"]) is list
         and packet["admitted_months"]==expected_new_months
         and packet["admitted_months"]==sorted(months)
         and packet["admitted_months"]
         and report["authorization_document_sha256"] is not None
         and _sha(report["authorization_document_sha256"]),
         "AUTHORIZED_COHORT")
    # Cohort query identities must not be inferred by copying one month SHA.
    # They are committed to the exact ordered (month,query) graph.
    native=digest([[m,entries_by_month[m][
        "core_245_native_price_query_sha256"]] for m in sorted(months)])
    local=digest([[m,entries_by_month[m][
        "core_253_local_query_sha256"]] for m in sorted(months)])
    need(packet["core_245_query_sha256"]==native
         and packet["core_253_query_sha256"]==local
         and native!=local,"BULK_DUAL_QUERY_GRAPH")
    need(len(packet["attempts"])>0 and
         len(packet["attempts"])<=MAX_ATTEMPTS,"ATTEMPT_DENOMINATOR")
    expected=set()
    states={"SELECTED","REJECTED","UNKNOWN","QUARANTINED","INELIGIBLE"}
    for trial in packet["attempts"]:
        _exact(trial,("attempt_id","candidate_id","month","state",
                       "source_receipt_sha256"),"ATTEMPT_SHAPE")
        need(type(trial["attempt_id"]) is str
             and 0<len(trial["attempt_id"])<=160
             and trial["attempt_id"] not in expected
             and trial["state"] in states
             and trial["month"] in packet["admitted_months"]
             and trial["source_receipt_sha256"]==
                entries_by_month[trial["month"]]["source_sha256"],
             "ATTEMPT_SOURCE_IDENTITY")
        expected.add(trial["attempt_id"])
    # A real F2 admission contains 10 authenticated months, but a positive
    # research execution cannot silently omit the other eligible candidates.
    # Preserve the exact 2 frozen scanner strategy × 10 admitted-month
    # denominator. February/August remain in the earlier WAIT 12-month census.
    need(len(packet["attempts"])==20
         and all(sum(row["month"]==m for row in packet["attempts"])==2
                 for m in packet["admitted_months"])
         and len({row["candidate_id"] for row in packet["attempts"]})==2
         and all(len({row["candidate_id"] for row in packet["attempts"]
                      if row["month"]==m})==2
                 for m in packet["admitted_months"]),
         "TEN_MONTH_FULL_STRATEGY_CENSUS")
    # A Scanner strategy signal is a proposal, not authority. Positive
    # selection is allowed only via a separately authenticated Secretary
    # strategy approval bound to the full selected source/strategy identity.
    need(sum(x["state"]=="SELECTED" for x in packet["attempts"])==1,
         "EXACTLY_ONE_SOURCE_BOUND_SELECTED_TRIAL")
    # Factory never promotes a self-issued selected row: the independently
    # witnessed authorization MUST bind the exact complete attempt census.
    # The current trust-v1 witness pins the entire Factory input digest; its
    # external approver is responsible for full strategy/selection identity.
    need(all(_sha(packet[name]) for name in ("strategy_definition_sha256",
                                           "config_sha256","code_sha256",
                                           "environment_sha256")),
         "STRATEGY_CONFIG_CODE_ENV_IDENTITY")
    definition=StrategyDefinition.from_dict(packet["strategy"],
                                              registry=IndicatorRegistryV2())
    need(definition.digest==packet["strategy_definition_sha256"],
         "STRATEGY_DEFINITION_DRIFT")
    trial=packet["trial_packet"]
    need(type(trial) is dict and trial.get("schema")
         =="aql.factory.historical-rule-projection.v1"
         and trial.get("source_kind")=="ORIGINAL_UNVERIFIED"
         and trial.get("availability")=="RETROSPECTIVE_NON_PIT"
         and trial.get("source_manifest_sha256")==report["manifest_sha256"]
         and trial.get("strategy")==packet["strategy"]
         and trial.get("market")=="SPOT"
         and trial.get("width_ms")==900000
         and trial.get("holdout")=="SEALED_UNOPENED"
         and trial.get("execution_authority")=="NONE"
         and trial.get("source_bytes_sha256")==entries_by_month[
             next(x["month"] for x in packet["attempts"]
                  if x["state"]=="SELECTED")]["source_sha256"],
         "REAL_LAB_PACKET_PARENT_DRIFT")
    need(type(trial.get("bars")) is list
         and 2<=len(trial["bars"])<=MAX_BARS
         and all(type(bar) is dict and bar.get("known_at_ms") is None
                 for bar in trial["bars"]),
         "NO_SYNTHETIC_KNOWN_AT")
    need(all(type(x.get("bar_sha256")) is str and
             x["bar_sha256"]==digest({k:v for k,v in x.items()
                                    if k!="bar_sha256"})
             for x in trial["bars"]),
         "BAR_SHA")
    sel=next(x for x in packet["attempts"] if x["state"]=="SELECTED")
    month_prefix=sel["month"]
    # Hard-bind each private bar to the exact Core F2 monthly source range.
    # Native 15m bars from other months are forbidden in a one-month run.
    from datetime import datetime, timezone
    from calendar import monthrange
    yy,mm=map(int,month_prefix.split("-"))
    first=int(datetime(yy,mm,1,tzinfo=timezone.utc).timestamp()*1000)
    last=int(datetime(yy,mm,monthrange(yy,mm)[1],tzinfo=timezone.utc).timestamp()*1000)+86400000
    need(all(first<=bar["open_ms"] and bar["close_ms"]<last
             for bar in trial["bars"]), "MONTH_GRID_SOURCE_SWAP")
    need(trial.get("selected_attempt_id")==
         sel["attempt_id"],"SELECTED_ATTEMPT_PLAN")
    need(type(trial.get("trials")) is list
         and any(t.get("attempt_id")==sel["attempt_id"] and
                 t.get("candidate_digest")==definition.digest and
                 t.get("state")=="PROPOSED" for t in trial["trials"]),
         "TRIAL_SELECTED_DEFINITION_PARENT")
    need(len(trial["bars"])<=MAX_BARS
         and all(type(x["open_ms"]) is int
                 and x["open_ms"]%900000==0 for x in trial["bars"]),
         "NATIVE_GRID")
    need(type(trial["research_window"]) is dict
         and trial["bars"][-1]["close_ms"]<
             trial["research_window"]["train_end_exclusive_ms"],
         "NO_HOLDOUT_BAR_ACCESS")
    _witness(packet,witness,witness_sha)
    return definition,sel,entries_by_month


def run_private_cohort(packet,witness,witness_sha,store_path):
    definition,selected,entries=validate_input(
        packet,witness,witness_sha)
    # Factory consumer ACK is distinct from Source ACK and StrategyApproval;
    # it binds exactly the independently approved source/policy/strategy/input
    # graph *before* the Lab executes. Lab result SHA is a separate child.
    ack_body={
        "schema":"aql.factory.f.consumer-ack.v1",
        "core_source_ack_sha256":packet["source_ack_sha256"],
        "independent_policy_approval_sha256":
             packet["independent_policy_approval_sha256"],
        "strategy_approval_sha256":packet["strategy_approval_sha256"],
        "source_manifest_sha256":packet["source_manifest_sha256"],
        "core_f2_report_sha256":packet["core_f2_report_sha256"],
        "core_245_query_sha256":packet["core_245_query_sha256"],
        "core_253_query_sha256":packet["core_253_query_sha256"],
        "factory_input_sha256":packet["sha256"],
        "historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }
    factory_consumer_ack=digest(ack_body)
    # The outer positive decision is permitted only after the independently
    # trusted witness is verified. The underlying reusable kernel deliberately
    # keeps retrospective original-source status unverified/PIT NOT_ATTESTED.
    lab=evaluate_historical_rules(seal(packet["trial_packet"]))
    need(lab["source_class"]=="ORIGINAL_UNVERIFIED"
         and lab["historical_pit_verified"] is False
         and lab["trading_authority"]=="NONE"
         and lab["execution_status"]=="NOT_OBSERVED",
         "LAB_AUTHORITY_BOUNDARY")
    lab_sha=lab["artifact_sha256"]
    body={
        "schema":OUTPUT,"experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "source_ack_sha256":packet["source_ack_sha256"],
        "independent_policy_approval_sha256":
             packet["independent_policy_approval_sha256"],
        "strategy_approval_sha256":packet["strategy_approval_sha256"],
        "factory_consumer_ack_sha256":factory_consumer_ack,
        "core_f2_report_sha256":packet["core_f2_report_sha256"],
        "lab_receipt_sha256":lab_sha,
        "unknown_outcomes":lab["unknown_outcomes"],
        "modeled_outcomes_count":len(lab["modeled_outcomes"]),
        "costs":lab["costs"],
        "research_class":"RETROSPECTIVE_NON_PIT",
        "source_issuer_pit":"NOT_ATTESTED",
        "paper":"NOT_ACTIVATED","orders_created":0,
        "positions":0,"actual_fills":None,
        "trading_authority":"NONE","holdout":"SEALED_UNOPENED",
        "scientific_acceptance":"INSUFFICIENT_EVIDENCE"}
    result_sha=digest(body)
    immutable=build_experiment(
        experiment_id=packet["experiment_id"],lane="SCANNER",
        source_status="RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT",
        source_sha256=selected["source_receipt_sha256"],
        source_query_245_sha256=entries[selected["month"]][
            "core_245_native_price_query_sha256"],
        source_query_253_sha256=entries[selected["month"]][
            "core_253_local_query_sha256"],
        strategy_definition_sha256=definition.digest,
        config_sha256=packet["config_sha256"],
        code_sha256=packet["code_sha256"],
        environment_sha256=packet["environment_sha256"],
        parent_receipt_sha256=packet["strategy_approval_sha256"],
        attempts=[{"attempt_id":x["attempt_id"],
                   "candidate_id":x["candidate_id"],
                   "state":x["state"],
                   "source_receipt_sha256":x["source_receipt_sha256"]}
                  for x in packet["attempts"]],
        lab_receipt_sha256=lab_sha,
        result_sha256=result_sha,
        evidence_class="RETROSPECTIVE_NON_PIT")
    # Preserve Feb/Aug as four immutable UNKNOWN rows in the same final
    # experiment; the evaluated census remains the original full 24 attempts.
    # These source-month rows explicitly have no authentic source receipt.
    from research_wp_r0.aql_factory_e_research_results_store_v1 import _seal
    retained=[]
    for month in ("2024-02","2024-08"):
        for candidate in sorted({x["candidate_id"] for x in packet["attempts"]}):
            retained.append({"attempt_id":f"RETAINED-{month}-{candidate}",
                "candidate_id":candidate,"state":"UNKNOWN",
                "source_receipt_sha256":digest({
                    "schema":"aql.factory.f.retained-inventory-only.v1",
                    "month":month,"candidate_id":candidate,
                    "status":"INVENTORY_ONLY_NOT_READBACK",
                    "core_f2_report_sha256":packet["core_f2_report_sha256"]})})
    need(len(retained)==4, "RETAINED_FEB_AUG_CENSUS")
    # Rebuild the immutable E experiment with all 20 authenticated-month
    # attempts plus exactly four unevaluated inventory-only rows.
    kwargs=dict(
        experiment_id=packet["experiment_id"],lane="SCANNER",
        source_status="RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT",
        source_sha256=selected["source_receipt_sha256"],
        source_query_245_sha256=entries[selected["month"]]["core_245_native_price_query_sha256"],
        source_query_253_sha256=entries[selected["month"]]["core_253_local_query_sha256"],
        strategy_definition_sha256=definition.digest,
        config_sha256=packet["config_sha256"],code_sha256=packet["code_sha256"],
        environment_sha256=packet["environment_sha256"],
        parent_receipt_sha256=packet["strategy_approval_sha256"],
        attempts=[{"attempt_id":x["attempt_id"],"candidate_id":x["candidate_id"],
                   "state":x["state"],"source_receipt_sha256":x["source_receipt_sha256"]}
                  for x in packet["attempts"]]+retained,
        lab_receipt_sha256=lab_sha,result_sha256=result_sha,
        evidence_class="RETROSPECTIVE_NON_PIT")
    immutable=build_experiment(**kwargs)
    need(immutable["attempt_count"]==24 and
         immutable["attempt_states"]["UNKNOWN"]>=4, "FULL_24_ATTEMPT_CENSUS")
    registered=register_experiment(store_path,immutable)
    reread=read_experiment(store_path,packet["experiment_id"])
    need(reread==immutable,"RESULT_REPLAY_DRIFT")
    output={**body,
            "result_sha256":result_sha,
            "experiment_sha256":immutable["sha256"],
            "store_status":registered["status"]}
    return {**output,"receipt_sha256":digest(output)}


def main():
    parser=argparse.ArgumentParser(description="Owner-private F4 real cohort, no broker/no PIT")
    parser.add_argument("--input-json",required=True)
    parser.add_argument("--trusted-witness-json",required=True)
    parser.add_argument("--trusted-witness-sha256",required=True)
    parser.add_argument("--results-store",required=True)
    parser.add_argument("--sanitized-out",required=True)
    args=parser.parse_args()
    try:
        packet=_load(args.input_json,MAX_INPUT_BYTES)
        witness=_load(args.trusted_witness_json,50_000)
        out=run_private_cohort(packet,witness,args.trusted_witness_sha256,
                               args.results_store)
        destination=Path(args.sanitized_out)
        need(destination.parent.is_dir() and not destination.is_symlink(),
             "SANITIZED_OUTPUT_PATH")
        destination.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps(out,sort_keys=True))
    except (ResultsStoreError,ValueError,KeyError,TypeError) as exc:
        raise SystemExit("FACTORY_F_PRIVATE_BLOCKED: "+str(exc))


if __name__=="__main__":
    main()
