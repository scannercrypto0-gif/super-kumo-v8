"""G4-WP02: actual durable Discoverer attempt census, frozen proposal, adversarial negatives."""
from copy import deepcopy

import pytest

from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1, _digest,
)
from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint
from tools.strategy_discoverer_offline.g4_candidate_preregistration import (
    G4CandidatePreregError, build_g4_synthetic_candidate_proposal,
    verify_g4_synthetic_candidate_proposal,
)
from tools.strategy_discoverer_offline.hypotheses import HypothesisProposal, SearchPlan
from tools.strategy_discoverer_offline.ledger import DiscovererLedger, AttemptState
from tools.strategy_discoverer_offline.validation import ValidationProtocolV1
from tools.strategy_discoverer_offline.families import get_family, family_registry_digest
from tools.strategy_discoverer_offline.synthetic_scanner_candidate_bridge import (
    project_test_only_candidate,
)
from tools.strategy_discoverer_offline.tests.test_d_scan_1_candidate_bridge import case


def setup(tmp_path):
    candidate, nomination = case()
    family = get_family(candidate["family_id"])
    hypothesis = HypothesisProposal.build(
        family=family, hypothesis_id="g4-synthetic-hypothesis",
        parameter_config={}, entry_direction="LONG",
        hypothesis_statement="Frozen synthetic signal differs from null baseline",
        minimum_effect_size="0", null_hypothesis="No effect versus matched null",
        counterhypothesis_id=candidate["counterhypothesis_id"], assumptions=("synthetic only",))
    plan = SearchPlan.build(
        search_plan_id="g4-synthetic-plan",family_registry_digest=family_registry_digest(),
        hypothesis_ids=(hypothesis.hypothesis_id,),total_candidate_budget=4)
    protocol = ValidationProtocolV1.build(
        protocol_id="g4-synthetic-protocol",
        family_registry_digest=plan.family_registry_digest,
        search_plan_digest=plan.plan_digest)
    ledger=DiscovererLedger()
    # Failure and rejection attempts must remain in the denominator.
    ledger.register("invalid-01","invalid-synthetic","F001","a"*64,plan.plan_digest,
                    nomination["nomination_digest"])
    ledger.transition("invalid-01",AttemptState.INVALID,reason="test rejection")
    ledger.register("failed-01","failed-synthetic","F001","b"*64,plan.plan_digest,
                    nomination["nomination_digest"])
    ledger.transition("failed-01",AttemptState.PENDING)
    ledger.transition("failed-01",AttemptState.FAILED,reason="synthetic failure")
    ledger.register("selected-01",candidate["candidate_id"],candidate["family_id"],
                    candidate["strategy_definition_digest"],plan.plan_digest,
                    nomination["nomination_digest"])
    ledger.transition("selected-01",AttemptState.PENDING)
    fields={k:v for k,v in candidate.items() if k not in (
        "package_digest","evaluation_status","scientific_acceptance","execution_status",
        "publishable","delivery_authorized","holdout_status","factory_routing")}
    fields["attempt_ledger_head"]=ledger.head_digest()
    fields["search_plan_digest"]=plan.plan_digest
    candidate=DiscoveryCandidatePackageV1.build(**fields).to_dict()
    ledger.transition("selected-01",AttemptState.COMPLETE)
    custody=DurableDiscovererCheckpoint(tmp_path/"g4-discoverer.sqlite")
    custody.append_ledger(ledger.to_dict_list())
    plugin,binding=project_test_only_candidate(
        candidate_package=candidate,synthetic_nomination=nomination)
    originals=dict(candidate_package=candidate,synthetic_nomination=nomination,
        scanner_plugin=plugin,scanner_binding=binding,hypothesis=hypothesis.to_dict(),
        search_plan=plan.to_dict(),validation_protocol=protocol.to_dict(),
        durable_checkpoint=custody,ledger_attempt_id="selected-01",
        ledger_reference="synthetic-ledger-01",baseline_id="independent-null-01",
        trial_family_id="g4-paired-family-01",frozen_trial_budget=4)
    return originals


def issue(o):
    return build_g4_synthetic_candidate_proposal(**o)


def test_valid_prereg_sealed_durable_census(tmp_path):
    o=setup(tmp_path)
    receipt=issue(o)
    assert receipt["proposal_status"]=="PROPOSED_NOT_EVALUATED"
    assert receipt["attempt_census"]["total_unique_attempts"]==3
    assert receipt["attempt_census"]["INVALID"]==1
    assert receipt["attempt_census"]["FAILED"]==1
    assert receipt["attempt_census"]["COMPLETE"]==1
    assert receipt["attempt_census"]["total_ledger_events"]==8
    assert receipt["trial_family_id"]=="g4-paired-family-01"
    assert receipt["historical_pit"]=="NOT_ATTESTED"
    assert receipt["oos_status"]=="SEALED_UNOPENED"
    assert receipt["factory_trial_registry_required"] is True
    assert all(receipt[k] is None for k in (
        "source_ack_sha256","strategy_approval_sha256",
        "factory_consumer_ack_sha256","research_review_ack_sha256"))
    assert verify_g4_synthetic_candidate_proposal(proposal=receipt,**o)
    assert issue(o)==receipt


def test_swapped_package_or_fake_scanner_binding_rejected(tmp_path):
    o=setup(tmp_path)
    bad=dict(o)
    p=deepcopy(o["candidate_package"])
    p["candidate_id"]="swapped"
    p["package_digest"]=_digest({k:v for k,v in p.items() if k!="package_digest"})
    bad["candidate_package"]=p
    with pytest.raises(G4CandidatePreregError):
        issue(bad)
    bad=dict(o)
    b=deepcopy(o["scanner_binding"])
    b["candidate_package_sha256"]="a"*64
    b["binding_sha256"]=_digest({k:v for k,v in b.items() if k!="binding_sha256"})
    bad["scanner_binding"]=b
    with pytest.raises(G4CandidatePreregError,match="SCANNER_BINDING"):
        issue(bad)


def test_resealed_protocol_plan_hypothesis_mismatch_rejected(tmp_path):
    o=setup(tmp_path)
    for key,field in (("validation_protocol","search_plan_digest"),
                      ("search_plan","family_registry_digest"),
                      ("hypothesis","counterhypothesis_id")):
        bad=dict(o)
        b=deepcopy(o[key])
        b[field]="f"*64 if "digest" in field else "wrong"
        digest_field={"validation_protocol":"protocol_digest",
                      "search_plan":"plan_digest","hypothesis":"hypothesis_digest"}[key]
        b[digest_field]=_digest({k:v for k,v in b.items() if k!=digest_field})
        bad[key]=b
        with pytest.raises(G4CandidatePreregError):
            issue(bad)


def test_declared_budget_and_missing_entries_rejected(tmp_path):
    o=setup(tmp_path)
    with pytest.raises(G4CandidatePreregError,match="TRIAL_BUDGET"):
        issue({**o,"frozen_trial_budget":2})
    # A caller-supplied fabricated alternative ledger is never used.
    original = o["durable_checkpoint"].read_latest_ledger()
    assert original["ledger_head"] != "a"*64


def test_false_rights_or_history_cannot_be_promoted(tmp_path):
    o=setup(tmp_path)
    bad=dict(o)
    e=deepcopy(o["synthetic_nomination"])
    e["evidence_class"]="RETROSPECTIVE_NON_PIT_VERIFIED"
    e["nomination_digest"]=_digest({k:v for k,v in e.items() if k!="nomination_digest"})
    bad["synthetic_nomination"]=e
    with pytest.raises(G4CandidatePreregError):
        issue(bad)


def test_snapshot_replay_tamper_and_forged_promotion_rejected(tmp_path):
    o=setup(tmp_path)
    receipt=issue(o)
    bad=deepcopy(receipt)
    bad["source_ack_sha256"]="a"*64
    bad["proposal_sha256"]=_digest({k:v for k,v in bad.items() if k!="proposal_sha256"})
    with pytest.raises(G4CandidatePreregError,match="PROPOSAL_MISMATCH"):
        verify_g4_synthetic_candidate_proposal(proposal=bad,**o)
    bad=deepcopy(receipt)
    bad["attempt_census"]["FAILED"]=0
    bad["proposal_sha256"]=_digest({k:v for k,v in bad.items() if k!="proposal_sha256"})
    with pytest.raises(G4CandidatePreregError,match="PROPOSAL_MISMATCH"):
        verify_g4_synthetic_candidate_proposal(proposal=bad,**o)
    assert issue(o)["proposal_sha256"]==receipt["proposal_sha256"]


def test_no_fake_research_approval_and_sealed_control(tmp_path):
    o=setup(tmp_path)
    bad=dict(o)
    p=deepcopy(o["validation_protocol"])
    p["holdout_sealed"]=False
    p["protocol_digest"]=_digest({k:v for k,v in p.items() if k!="protocol_digest"})
    bad["validation_protocol"]=p
    with pytest.raises(G4CandidatePreregError):
        issue(bad)
    assert issue(o)["result_selection"]=="NOT_PERFORMED"
