"""G4 focused synthetic cross-owner acceptance: Discoverer proposal -> Factory E registry.

Uses *real* existing Factory E immutable research experiment store API.  This
additive read/verify seam is not a new Factory trial registry, does not fabricate
performance, and does not authorize the generic H result/paired lab.
"""
from __future__ import annotations

from tools.strategy_discoverer_offline.contracts import _digest
from tools.strategy_discoverer_offline.g4_candidate_preregistration import (
    verify_g4_synthetic_candidate_proposal, G4CandidatePreregError,
)

SCHEMA = "aql.g4.discoverer.factory-existing-registry-join.v1"
CROSS_STATES = {
    "INVALID": "REJECTED", "FAILED": "FAILED", "COMPLETE": "SELECTED",
    "ABANDONED": "QUARANTINED", "PENDING": "UNKNOWN", "REGISTERED": "UNSCANNED",
}


def _need(ok, tag):
    if not ok:
        raise G4CandidatePreregError("G4_FACTORY_JOIN_" + tag)


def _rows(snapshot):
    from tools.strategy_discoverer_offline.ledger import DiscovererLedger
    entries=snapshot["entries"]
    try:
        ledger=DiscovererLedger.from_dict_list(entries,max_entries=max(4096,len(entries)))
    except (ValueError, TypeError, KeyError) as exc:
        raise G4CandidatePreregError("G4_FACTORY_JOIN_LEDGER_INVALID") from exc
    _need(ledger.verify_chain() and ledger.head_digest()==snapshot["ledger_head"],
          "LEDGER_CHAIN")
    last={}
    for entry in ledger.entries():
        last[entry.attempt_id]=entry
    return last


def build_g4_factory_research_attempt_join(*, proposal, originals, factory_store_path,
                                           experiment_id, config_sha256,
                                           source_query_245_sha256,
                                           source_query_253_sha256,
                                           code_sha256, environment_sha256):
    """Persist and independently re-read ALL candidate-generation attempts in Factory E.

    The Discoverer numerator and Factory trial/decision denominator are kept
    separate, as they count different things. Factory WP02 must subsequently
    register every BASE/SHADOW/placebo variant; this joins candidate admission.
    """
    from research_wp_r0.aql_factory_e_research_results_store_v1 import (
        build_experiment, register_experiment, read_experiment, digest,
    )
    _need(type(originals) is dict and verify_g4_synthetic_candidate_proposal(
        proposal=proposal, **originals), "PROPOSAL")
    custody=originals["durable_checkpoint"]
    snapshot=custody.read_latest_ledger()
    last=_rows(snapshot)
    census=proposal["attempt_census"]
    _need(len(last)==census["total_unique_attempts"] and
          sum(v.state==s for v in last.values() for s in ("INVALID","FAILED",
          "COMPLETE","ABANDONED","PENDING","REGISTERED"))==len(last),
          "ATTEMPT_CENSUS")
    expected=[
        {"attempt_id":entry.attempt_id,"candidate_id":entry.candidate_id,
         "state":CROSS_STATES[entry.state],
         "source_receipt_sha256":proposal["proposal_sha256"]}
        for _,entry in sorted(last.items())
    ]
    _need(len(expected)<=proposal["frozen_trial_budget"],
          "BUDGET")
    for key in ("experiment_id","config_sha256","source_query_245_sha256",
                "source_query_253_sha256","code_sha256","environment_sha256"):
        _need(type(locals()[key]) is str and bool(locals()[key]),"INPUT_"+key)
    _need(source_query_245_sha256!=source_query_253_sha256,"SOURCE_QUERY_ALIAS")
    factory=build_experiment(
        experiment_id=experiment_id, lane="DISCOVERER",
        source_status="SYNTHETIC_ENGINEERING_PASS",
        source_sha256=proposal["source_manifest_sha256"],
        source_query_245_sha256=source_query_245_sha256,
        source_query_253_sha256=source_query_253_sha256,
        strategy_definition_sha256=proposal["strategy_definition_sha256"],
        config_sha256=config_sha256, code_sha256=code_sha256,
        environment_sha256=environment_sha256,
        parent_receipt_sha256=proposal["proposal_sha256"],
        attempts=expected, evidence_class="TEST_ONLY",
        historical_pit="NOT_ATTESTED",holdout="SEALED_UNOPENED",
        trading_authority="NONE",
    )
    write=register_experiment(factory_store_path,factory)
    fresh=read_experiment(factory_store_path,experiment_id)
    _need(fresh==factory and fresh["attempts"]==expected and
          fresh["attempt_count"]==len(last) and
          fresh["parent_receipt_sha256"]==proposal["proposal_sha256"] and
          fresh["strategy_definition_sha256"]==proposal["strategy_definition_sha256"] and
          fresh["trading_authority"]=="NONE" and
          fresh["strategy_performance_accepted"] is False and
          fresh["actual_fills"] is None,"REGISTRY_READBACK")
    receipt={
        "schema_version":SCHEMA,
        "source_class":"TEST_ONLY_SYNTHETIC",
        "candidate_proposal_sha256":proposal["proposal_sha256"],
        "candidate_package_sha256":proposal["candidate_package_sha256"],
        "scanner_binding_sha256":proposal["scanner_binding_sha256"],
        "scanner_plugin_sha256":proposal["scanner_plugin_sha256"],
        "search_plan_sha256":proposal["search_plan_sha256"],
        "trial_family_id":proposal["trial_family_id"],
        "paired_baseline_id":proposal["paired_baseline_id"],
        "discoverer_ledger_head_sha256":proposal["attempt_ledger_head_sha256"],
        "discoverer_checkpoint_sha256":proposal["ledger_checkpoint_sha256"],
        "discoverer_attempt_census":census,
        "factory_experiment_id":experiment_id,
        "factory_experiment_sha256":fresh["sha256"],
        "factory_attempt_count":fresh["attempt_count"],
        "factory_attempt_states":fresh["attempt_states"],
        "factory_write_status":write["status"],
        "factory_comparison_trials_status":"NOT_PERFORMED",
        "factory_paired_results_status":"NOT_PERFORMED",
        "research_authority":"NONE",
        "historical_pit":"NOT_ATTESTED",
        "holdout_status":"SEALED_UNOPENED",
        "trading_authority":"NONE",
    }
    return {**receipt,"receipt_sha256":_digest(receipt)}
