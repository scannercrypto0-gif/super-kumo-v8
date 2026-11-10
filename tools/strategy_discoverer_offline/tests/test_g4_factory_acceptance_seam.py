"""Focused G4 prereg -> real Factory E durable registry integration; synthetic only."""
from copy import deepcopy

import pytest

from tools.strategy_discoverer_offline.g4_candidate_preregistration import (
    build_g4_synthetic_candidate_proposal, G4CandidatePreregError,
)
from tools.strategy_discoverer_offline.g4_factory_acceptance_seam import (
    build_g4_factory_research_attempt_join,
)
from tools.strategy_discoverer_offline.tests.test_g4_candidate_preregistration import setup
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    read_experiment, ResultsStoreError,
)


def context(tmp_path):
    inputs=setup(tmp_path)
    proposal=build_g4_synthetic_candidate_proposal(**inputs)
    kw=dict(proposal=proposal, originals=inputs,
            factory_store_path=tmp_path/"factory-g4.sqlite",
            experiment_id="G4-DISCOVERER-SYNTHETIC-001",
            config_sha256="a"*64,
            source_query_245_sha256="b"*64,
            source_query_253_sha256="c"*64,
            code_sha256="d"*64,environment_sha256="e"*64)
    return kw


def test_verified_discoverer_proposal_is_stored_in_actual_factory_registry(tmp_path):
    args=context(tmp_path)
    receipt=build_g4_factory_research_attempt_join(**args)
    stored=read_experiment(args["factory_store_path"],args["experiment_id"])
    assert stored["lane"]=="DISCOVERER"
    assert stored["attempt_count"]==3
    assert stored["parent_receipt_sha256"]==args["proposal"]["proposal_sha256"]
    assert stored["strategy_definition_sha256"]==args["proposal"]["strategy_definition_sha256"]
    assert [x["state"] for x in stored["attempts"]]==["FAILED","REJECTED","SELECTED"]
    assert receipt["factory_attempt_count"]==3
    assert receipt["discoverer_attempt_census"]["INVALID"]==1
    assert receipt["discoverer_attempt_census"]["FAILED"]==1
    assert receipt["discoverer_attempt_census"]["COMPLETE"]==1
    assert receipt["factory_comparison_trials_status"]=="NOT_PERFORMED"
    assert stored["strategy_performance_accepted"] is False
    assert stored["actual_fills"] is None
    assert receipt["trading_authority"]=="NONE"
    assert build_g4_factory_research_attempt_join(**args)["factory_write_status"]=="REPLAY_IDENTICAL"


def test_swapped_candidate_proposal_does_not_enter_factory(tmp_path):
    args=context(tmp_path)
    fake=deepcopy(args["proposal"])
    fake["candidate_package_sha256"]="f"*64
    from tools.strategy_discoverer_offline.contracts import _digest
    fake["proposal_sha256"]=_digest({k:v for k,v in fake.items() if k!="proposal_sha256"})
    with pytest.raises(G4CandidatePreregError):
        build_g4_factory_research_attempt_join(**{**args,"proposal":fake})
    assert not args["factory_store_path"].exists()


def test_missing_failed_attempt_or_modified_durable_checkpoint_is_rejected(tmp_path):
    args=context(tmp_path)
    fake=deepcopy(args["proposal"])
    fake["attempt_census"]["FAILED"]=0
    from tools.strategy_discoverer_offline.contracts import _digest
    fake["proposal_sha256"]=_digest({k:v for k,v in fake.items() if k!="proposal_sha256"})
    with pytest.raises(G4CandidatePreregError):
        build_g4_factory_research_attempt_join(**{**args,"proposal":fake})


def test_same_experiment_id_cannot_rewrite_different_immutable_parents(tmp_path):
    args=context(tmp_path)
    build_g4_factory_research_attempt_join(**args)
    args["environment_sha256"]="0"*64
    with pytest.raises(ResultsStoreError,match="IMMUTABLE_IDEMPOTENCY_CONFLICT"):
        build_g4_factory_research_attempt_join(**args)


def test_unknown_and_incomplete_generation_attempts_are_not_silently_selected(tmp_path):
    args=context(tmp_path)
    assert args["proposal"]["attempt_census"]["incomplete_attempts"]==0
    assert args["proposal"]["result_selection"]=="NOT_PERFORMED"
    assert args["proposal"]["oos_status"]=="SEALED_UNOPENED"
    assert args["proposal"]["historical_pit"]=="NOT_ATTESTED"


def test_no_fake_paired_result_or_research_authority(tmp_path):
    args=context(tmp_path)
    receipt=build_g4_factory_research_attempt_join(**args)
    assert receipt["factory_paired_results_status"]=="NOT_PERFORMED"
    assert receipt["factory_comparison_trials_status"]=="NOT_PERFORMED"
    assert receipt["research_authority"]=="NONE"
    assert receipt["historical_pit"]=="NOT_ATTESTED"
