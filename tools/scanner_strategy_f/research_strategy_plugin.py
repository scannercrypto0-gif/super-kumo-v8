"""Package H Scanner: versioned, research-only strategy plug-in and causal signals.

Adapter over the existing StrategyDefinition / Factory indicator kernels.
It does NOT simulate fills, costs, PnL, approvals, or a second warehouse.
Core #253 immutable query is re-read and compared before any signal release.
"""
from __future__ import annotations

from collections import Counter
import math
import re

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import StrategyDefinition
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_f.frozen_diagnostic_contracts import FROZEN
from tools.scanner_strategy_f.research_e2e_diagnostic import (
    STEP, _code_sha, _eval_strategy,
)

PLUGIN_SCHEMA="aql.scanner.h.strategy-plugin.v1"
BATCH_SCHEMA="aql.scanner.h.causal-signal-batch.v1"
EVENT_SCHEMA="aql.scanner.h.closed-bar-signal-event.v1"
POLICY_SCHEMA="aql.scanner.h.research-signal-policy.v1"
CORE_SCHEMA="aql.core.local-history-query.v1"
HEX=re.compile(r"[0-9a-f]{64}\Z")
STATES=frozenset(("ENTRY_SIGNAL","EXIT_SIGNAL","NO_SIGNAL","UNKNOWN"))
CORE_FIELDS=frozenset((
    "schema","dataset_id","version","source_bytes_sha256",
    "manifest_integrity_sha256","start_ms","end_exclusive_ms",
    "decision_cutoff_ms","coverage","missing_bar_opens",
    "required_bar_count","available_bar_count","bars",
    "source_availability","historical_pit","universe","query_sha256",
))
MAX_BARS=4096
EVENT_FIELDS=frozenset((
    "schema","sequence","bar_open_ms","bar_close_ms","research_asof_ms",
    "historical_known_at_ms","historical_pit","signal_state",
    "source_observed","next_eligible_open_ms","next_open_is_fill",
    "cost_or_pnl_computed","source_query_sha256","strategy_plugin_sha256",
    "evaluator_code_sha256","decision_cutoff_ms","event_sha256",
))


def _hex(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _definition(receipt):
    require(type(receipt) is dict
            and set(receipt)=={"definition","digest"},
            "H_PLUGIN_DEFINITION_RECEIPT_SHAPE")
    return StrategyDefinition.from_dict(receipt,registry=IndicatorRegistryV2())


def manual_config_digest(definition_receipt):
    """Bind manual AST indicators, risk and timing to the config identity."""
    spec=_definition(definition_receipt).spec
    return digest({"indicators":spec["indicators"],
                   "risk":spec["risk"],"timing":spec["timing"]})


def register_strategy_plugin(
    definition_receipt, *, config_digest, source_spec_receipt=None,
    origin="MANUAL", candidate_sha256=None,
):
    """Pin AST, version, parameters, actual evaluator code and optional Work235.

    An optional Discoverer identity is an input reference, NOT signed F4.
    Neither a supplied config digest nor source spec implies approval.
    """
    definition=_definition(definition_receipt)
    require(_hex(config_digest),"H_PLUGIN_CONFIG_SHA")
    if source_spec_receipt is None:
        require(config_digest==manual_config_digest(definition_receipt),
                "H_PLUGIN_MANUAL_CONFIG_DRIFT")
    require(origin in ("MANUAL","DISCOVERER_CANDIDATE")
            and ((origin=="MANUAL" and candidate_sha256 is None)
                 or (origin=="DISCOVERER_CANDIDATE"
                     and _hex(candidate_sha256))),
            "H_PLUGIN_DISCOVERER_NOT_APPROVAL")
    source_sha=None
    if source_spec_receipt is not None:
        spec=Frozen.restore(source_spec_receipt)
        payload=spec.data
        require(payload.get("strategy_id")==definition.spec["strategy_id"]
                and payload.get("strategy_version")==definition.spec["strategy_version"]
                and payload.get("definition")==definition_receipt
                and payload.get("config_digest")==config_digest
                and payload.get("scope")=="TEST_ONLY_UNAPPROVED_POLICY"
                and payload.get("paper_approval")=="NOT_FOUND",
                "H_PLUGIN_WORK235_SOURCE_DRIFT")
        known=FROZEN.get(definition.spec["strategy_id"])
        require(known is not None
                and spec.sha256==known["spec_sha256"]
                and config_digest==known["config_digest"]
                and definition.digest==known["definition_digest"],
                "H_PLUGIN_WORK235_PIN_DRIFT")
        source_sha=spec.sha256
    parameters=[
        {"name":ref["name"],"indicator_id":ref["indicator_id"],
         "version":ref["version"],"parameters":ref["parameters"]}
        for ref in definition.spec["indicators"]
    ]
    return Frozen.build({
        "schema":PLUGIN_SCHEMA,
        "strategy_id":definition.spec["strategy_id"],
        "strategy_version":definition.spec["strategy_version"],
        "config_digest":config_digest,
        "definition":definition.to_dict(),
        "definition_digest":definition.digest,
        "parameters":parameters,
        "evaluator_code_sha256":_code_sha(),
        "source_spec_sha256":source_sha,
        "config_identity_class":(
            "WORK235_FROZEN_TEST_ONLY" if source_sha is not None
            else "MANUAL_AST_PARAMETERS"),
        "input_origin":origin,
        "candidate_sha256":candidate_sha256,
        "timing":definition.spec["timing"],
        "policy_status":"RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL",
        "historical_pit":"NOT_ATTESTED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "trading_authority":"NONE",
    }).receipt()


def research_signal_policy(*, source_class="TEST_ONLY"):
    """Explicit unsigned research scope. Cost policy lives in Factory."""
    require(source_class in ("TEST_ONLY","OWNER_LOCAL_RECOVERY_DIAGNOSTIC"),
            "H_POLICY_SOURCE_CLASS")
    return Frozen.build({
        "schema":POLICY_SCHEMA,
        "source_class":source_class,
        "research_scope":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "policy_status":"DRAFT_RESEARCH_ONLY",
        "independent_owner_approval_sha256":None,
        "holdout":"SEALED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "economic_attestation":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }).receipt()


def _validate_policy(policy):
    p=Frozen.restore(policy).data
    require(set(p)=={
        "schema","source_class","research_scope","historical_pit",
        "policy_status","independent_owner_approval_sha256","holdout",
        "source_ack_sha256","strategy_approval_sha256",
        "factory_consumer_ack_sha256","economic_attestation",
        "trading_authority",
    } and p["schema"]==POLICY_SCHEMA
        and p["source_class"] in ("TEST_ONLY","OWNER_LOCAL_RECOVERY_DIAGNOSTIC")
        and p["research_scope"]=="RETROSPECTIVE_NON_PIT"
        and p["historical_pit"]=="NOT_ATTESTED"
        and p["policy_status"]=="DRAFT_RESEARCH_ONLY"
        and p["independent_owner_approval_sha256"] is None
        and p["holdout"]=="SEALED"
        and p["source_ack_sha256"] is None
        and p["strategy_approval_sha256"] is None
        and p["factory_consumer_ack_sha256"] is None
        and p["economic_attestation"]=="NOT_ATTESTED"
        and p["trading_authority"]=="NONE",
        "H_POLICY_APPROVAL_OR_PIT_FORGED")
    return p


def _validate_query(query):
    require(type(query) is dict and set(query)==CORE_FIELDS
            and query.get("schema")==CORE_SCHEMA
            and _hex(query.get("query_sha256"))
            and digest({k:v for k,v in query.items()
                        if k!="query_sha256"})==query["query_sha256"]
            and _hex(query.get("source_bytes_sha256"))
            and _hex(query.get("manifest_integrity_sha256"))
            and type(query.get("dataset_id")) is str
            and type(query.get("version")) is int
            and query["version"]>0
            and query.get("source_availability")=="RETROSPECTIVE_NON_PIT"
            and query.get("historical_pit")=="NOT_ATTESTED"
            and query.get("universe")=="NOT_ATTESTED",
            "H_CORE_QUERY_PARENT_OR_SCOPE")
    begin=query["start_ms"]
    end=query["end_exclusive_ms"]
    cutoff=query["decision_cutoff_ms"]
    require(all(type(v) is int and 0<=v<=2**53-1
                for v in (begin,end,cutoff))
            and 0<=begin<end<=cutoff
            and begin%STEP==0 and end%STEP==0
            and (end-begin)//STEP<=MAX_BARS,
            "H_CORE_CUTOFF_OR_RANGE")
    expected=list(range(begin,end,STEP))
    bars=query["bars"]
    missing=query["missing_bar_opens"]
    require(type(bars) is list and type(missing) is list
            and all(type(v) is int for v in missing)
            and len(set(missing))==len(missing)
            and type(query["available_bar_count"]) is int
            and type(query["required_bar_count"]) is int
            and query["required_bar_count"]==len(expected)
            and query["available_bar_count"]==len(bars)
            and len(bars)+len(missing)==len(expected),
            "H_CORE_DENOMINATOR_DRIFT")
    actual=[]
    for bar in bars:
        require(type(bar) is dict and set(bar)=={
            "bar_open_ms","bar_close_ms","open","high","low","close",
            "volume","bar_checksum","observation_lower_bound_ms",
            "historical_known_at_ms",
        }, "H_BAR_SHAPE")
        t=bar["bar_open_ms"]
        o,h,l,c,v=(bar[k] for k in ("open","high","low","close","volume"))
        require(type(t) is int and t in expected
                and type(bar["bar_close_ms"]) is int
                and bar["bar_close_ms"]==t+STEP-1
                and bar["bar_close_ms"]<cutoff
                and bar["historical_known_at_ms"] is None
                and type(bar["observation_lower_bound_ms"]) is int
                and bar["observation_lower_bound_ms"]>=bar["bar_close_ms"]+1
                and _hex(bar["bar_checksum"])
                and all(type(x) in (int,float) and math.isfinite(x)
                        for x in (o,h,l,c,v))
                and 0<l<=o<=h and l<=c<=h and v>=0,
                "H_BAR_FUTURE_OR_GRID_OR_VALUES")
        actual.append(t)
    require(actual==sorted(set(actual))
            and set(actual).isdisjoint(missing)
            and set(actual)|set(missing)==set(expected),
            "H_BAR_DUPLICATE_MISSING_OR_FUTURE")
    require((query["coverage"]=="COMPLETE" and not missing)
            or (query["coverage"]=="PARTIAL" and bool(bars) and bool(missing))
            or (query["coverage"]=="UNKNOWN" and not bars),
            "H_CORE_COVERAGE_DRIFT")
    return expected


def _event(batch_identity, index, start, state, has_observation, cutoff):
    end=start+STEP-1
    data={
        "schema":EVENT_SCHEMA,
        "sequence":index,
        "bar_open_ms":start,
        "bar_close_ms":end,
        "research_asof_ms":end+1,
        "historical_known_at_ms":None,
        "historical_pit":"NOT_ATTESTED",
        "signal_state":state,
        "source_observed":has_observation,
        "next_eligible_open_ms":end+1 if state in
            ("ENTRY_SIGNAL","EXIT_SIGNAL") else None,
        "next_open_is_fill":False,
        "cost_or_pnl_computed":False,
        "source_query_sha256":batch_identity["source_query_sha256"],
        "strategy_plugin_sha256":batch_identity["strategy_plugin_sha256"],
        "evaluator_code_sha256":batch_identity["evaluator_code_sha256"],
        "decision_cutoff_ms":cutoff,
    }
    return {**data,"event_sha256":digest(data)}


def evaluate_strategy_plugin(
    plugin, core_query, *,warehouse_root,policy,
):
    """Causal Scanner signal trace, immutable warehouse replay; Factory fills.

    PARTIAL/UNKNOWN inputs are entirely quarantined to UNKNOWN: no indicator
    warmup across missing bars, no fake NO_SIGNAL denominator.
    """
    obj=Frozen.restore(plugin)
    data=obj.data
    require(data.get("schema")==PLUGIN_SCHEMA
            and data.get("policy_status")=="RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL"
            and data.get("trading_authority")=="NONE"
            and data.get("historical_pit")=="NOT_ATTESTED"
            and data.get("source_ack_sha256") is None
            and data.get("strategy_approval_sha256") is None
            and data.get("factory_consumer_ack_sha256") is None
            and data.get("evaluator_code_sha256")==_code_sha(),
            "H_PLUGIN_CODE_OR_AUTHORITY_DRIFT")
    definition=_definition(data["definition"])
    require(definition.digest==data["definition_digest"]
            and definition.spec["strategy_id"]==data["strategy_id"]
            and definition.spec["strategy_version"]==data["strategy_version"]
            and data["timing"]==definition.spec["timing"]
            and data["parameters"]==[
                {"name":ref["name"],"indicator_id":ref["indicator_id"],
                 "version":ref["version"],"parameters":ref["parameters"]}
                for ref in definition.spec["indicators"]],
            "H_PLUGIN_DEFINITION_OR_PARAMS_DRIFT")
    source_sha=data.get("source_spec_sha256")
    if source_sha is not None:
        frozen=FROZEN.get(data["strategy_id"])
        require(frozen is not None
                and source_sha==frozen["spec_sha256"]
                and data["config_digest"]==frozen["config_digest"]
                and definition.digest==frozen["definition_digest"]
                and data.get("config_identity_class")=="WORK235_FROZEN_TEST_ONLY",
                "H_PLUGIN_WORK235_CONFIG_IDENTITY_DRIFT")
    else:
        require(data.get("config_identity_class")=="MANUAL_AST_PARAMETERS"
                and data["config_digest"]==
                    manual_config_digest(data["definition"]),
                "H_PLUGIN_MANUAL_CONFIG_DRIFT")
    source=_validate_policy(policy)
    expected=_validate_query(core_query)
    actual=query_local(
        warehouse_root,core_query["dataset_id"],core_query["version"],
        core_query["start_ms"],core_query["end_exclusive_ms"],
        core_query["decision_cutoff_ms"],
        required_source_sha256=core_query["source_bytes_sha256"],
        require_complete=False,sqlite_immutable=True,
    )
    require(actual==core_query,"H_CORE_IMMUTABLE_REPLAY_DRIFT")
    if core_query["coverage"]=="COMPLETE":
        signals=_eval_strategy(definition,core_query["bars"])
        require(len(signals)==len(expected)
                and all(type(item) is list and len(item)==2
                        and item[0]==start+STEP-1 and item[1] in STATES
                        for item,start in zip(signals,expected)),
                "H_FACTORY_KERNEL_SIGNAL_SHAPE")
        states=[item[1] for item in signals]
    else:
        states=["UNKNOWN"]*len(expected)
    require(len(states)==len(expected),"H_EVENT_DENOMINATOR")
    identity={
        "source_query_sha256":core_query["query_sha256"],
        "strategy_plugin_sha256":obj.sha256,
        "evaluator_code_sha256":data["evaluator_code_sha256"],
    }
    events=[
        _event(identity,i,start,states[i],
               core_query["coverage"]=="COMPLETE",
               core_query["decision_cutoff_ms"])
        for i,start in enumerate(expected)
    ]
    counts=Counter(states)
    return Frozen.build({
        "schema":BATCH_SCHEMA,
        "source_class":source["source_class"],
        "strategy_id":data["strategy_id"],
        "strategy_version":data["strategy_version"],
        "strategy_plugin_sha256":obj.sha256,
        "strategy_definition_digest":definition.digest,
        "config_digest":data["config_digest"],
        "evaluator_code_sha256":data["evaluator_code_sha256"],
        "source_query_sha256":core_query["query_sha256"],
        "source_bytes_sha256":core_query["source_bytes_sha256"],
        "manifest_integrity_sha256":core_query["manifest_integrity_sha256"],
        "dataset_id":core_query["dataset_id"],
        "policy_sha256":Frozen.restore(policy).sha256,
        "decision_cutoff_ms":core_query["decision_cutoff_ms"],
        "start_ms":core_query["start_ms"],
        "end_exclusive_ms":core_query["end_exclusive_ms"],
        "coverage":core_query["coverage"],
        "expected_bar_count":len(expected),
        "observed_bar_count":len(core_query["bars"]),
        "missing_bar_count":len(core_query["missing_bar_opens"]),
        "signal_counts":{s:counts[s] for s in
                         ("ENTRY_SIGNAL","EXIT_SIGNAL","NO_SIGNAL","UNKNOWN")},
        "event_count":len(events),
        "events":events,
        "quarantine":("NONE" if core_query["coverage"]=="COMPLETE"
                      else "ALL_EVENTS_UNKNOWN_SOURCE_GAP"),
        "research_asof_basis":"HYPOTHETICAL_CLOSED_BAR_NOT_HISTORICAL_PIT",
        "factory_interface":"SIGNAL_ONLY_NEXT_ELIGIBLE_OPEN_NO_FILLS",
        "cost_or_pnl_computed":False,
        "economic_attestation":"NOT_ATTESTED",
        "historical_pit":"NOT_ATTESTED",
        "independent_policy_approval_sha256":None,
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "selected":False,
        "holdout":"SEALED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
    }).receipt()


def verify_factory_signal_batch(batch):
    """Verify deterministic event identity and invariants; NOT price replay."""
    obj=Frozen.restore(batch)
    x=obj.data
    require(x.get("schema")==BATCH_SCHEMA
            and x.get("factory_interface")=="SIGNAL_ONLY_NEXT_ELIGIBLE_OPEN_NO_FILLS"
            and x.get("cost_or_pnl_computed") is False
            and x.get("historical_pit")=="NOT_ATTESTED"
            and x.get("trading_authority")=="NONE"
            and x.get("selected") is False
            and x.get("holdout")=="SEALED"
            and x.get("paper")=="NOT_ACTIVATED"
            and x.get("independent_policy_approval_sha256") is None
            and x.get("source_ack_sha256") is None
            and x.get("strategy_approval_sha256") is None
            and x.get("factory_consumer_ack_sha256") is None
            and x.get("economic_attestation")=="NOT_ATTESTED",
            "H_FACTORY_AUTHORITY_OR_INTERFACE")
    require(all(_hex(x.get(k)) for k in (
        "source_query_sha256","strategy_plugin_sha256",
        "evaluator_code_sha256","config_digest",
        "strategy_definition_digest","policy_sha256"))
        and type(x.get("event_count")) is int
        and type(x.get("events")) is list
        and len(x["events"])==x["event_count"]
        and type(x.get("expected_bar_count")) is int
        and x["event_count"]==x["expected_bar_count"]
        and x["event_count"]<=MAX_BARS
        and type(x.get("signal_counts")) is dict
        and set(x["signal_counts"])==STATES
        and sum(x["signal_counts"].values())==x["event_count"],
        "H_FACTORY_DENOMINATOR")
    seen=set()
    counts=Counter()
    for i,e in enumerate(x["events"]):
        require(type(e) is dict and e.get("schema")==EVENT_SCHEMA
                and e.get("sequence")==i
                and type(e.get("bar_open_ms")) is int
                and e["bar_open_ms"]%STEP==0
                and e["bar_open_ms"] not in seen
                and e.get("bar_close_ms")==e["bar_open_ms"]+STEP-1
                and e.get("research_asof_ms")==e["bar_close_ms"]+1
                and e["bar_close_ms"]<x["decision_cutoff_ms"]
                and e.get("decision_cutoff_ms")==x["decision_cutoff_ms"]
                and e.get("signal_state") in STATES
                and e.get("source_observed") is
                    (x["coverage"]=="COMPLETE")
                and e.get("historical_known_at_ms") is None
                and e.get("historical_pit")=="NOT_ATTESTED"
                and e.get("cost_or_pnl_computed") is False
                and e.get("next_open_is_fill") is False
                and e.get("next_eligible_open_ms")==(
                    e["bar_close_ms"]+1 if e["signal_state"] in
                    ("ENTRY_SIGNAL","EXIT_SIGNAL") else None)
                and e.get("source_query_sha256")==x["source_query_sha256"]
                and e.get("strategy_plugin_sha256")==x["strategy_plugin_sha256"]
                and e.get("evaluator_code_sha256")==x["evaluator_code_sha256"]
                and e.get("event_sha256")==digest({
                    k:v for k,v in e.items() if k!="event_sha256"}),
                "H_FACTORY_DUPLICATE_OR_EVENT_DRIFT")
        if i:
            require(e["bar_open_ms"]==x["events"][i-1]["bar_open_ms"]+STEP,
                    "H_FACTORY_EVENT_GRID_DRIFT")
        seen.add(e["bar_open_ms"])
        counts[e["signal_state"]]+=1
    require(all(counts[k]==x["signal_counts"][k] for k in STATES)
            and (x["coverage"]=="COMPLETE"
                 or (x["quarantine"]=="ALL_EVENTS_UNKNOWN_SOURCE_GAP"
                     and counts["UNKNOWN"]==x["event_count"]))
            and (x["coverage"]!="COMPLETE"
                 or x["quarantine"]=="NONE")
            and type(x["observed_bar_count"]) is int
            and type(x["missing_bar_count"]) is int
            and x["observed_bar_count"]+x["missing_bar_count"]
                ==x["expected_bar_count"],
            "H_FACTORY_COUNTS_OR_QUARANTINE_DRIFT")
    return obj
