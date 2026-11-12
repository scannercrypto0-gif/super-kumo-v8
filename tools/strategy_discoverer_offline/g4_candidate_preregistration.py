"""G4 synthetic-only, preregistered Discoverer candidate proposal for Factory.

Read-only projection of existing Discoverer immutable evidence and durable
attempt census. Factory owns all later paired result/trial events and must
verify the candidate binding itself before running any candidate-origin trial.
No historical/PIT/rights/selection/promotion authority is conferred.
"""
from __future__ import annotations

from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1, NominationEvidenceV1, _digest,
)
from tools.strategy_discoverer_offline.hypotheses import SearchPlan, HypothesisProposal
from tools.strategy_discoverer_offline.validation import ValidationProtocolV1
from tools.strategy_discoverer_offline.ledger import DiscovererLedger
from tools.strategy_discoverer_offline.synthetic_scanner_candidate_bridge import (
    verify_test_only_candidate_binding,
)

SCHEMA = "aql.g4.discoverer.preregistered-candidate-proposal.v1"
HEX = set("0123456789abcdef")
TERMINAL = {"INVALID", "FAILED", "COMPLETE", "ABANDONED"}
STATES = {"REGISTERED", "PENDING", *TERMINAL}


class G4CandidatePreregError(ValueError):
    """Fail-closed preregistration error; no evaluation has started."""


def _need(ok, code):
    if not ok:
        raise G4CandidatePreregError("G4_DISCOVERER_" + code)


def _sha(s):
    return type(s) is str and len(s) == 64 and set(s) <= HEX


def _canonical(value, cls, label):
    _need(type(value) is dict, label + "_TYPE")
    try:
        unpacked = dict(value)
        if cls is SearchPlan:
            unpacked["hypothesis_ids"] = tuple(unpacked["hypothesis_ids"])
        elif cls is HypothesisProposal:
            unpacked["assumptions"] = tuple(unpacked["assumptions"])
        elif cls is ValidationProtocolV1:
            for name in ("comparator_slate", "predeclared_metrics", "evaluation_gates"):
                unpacked[name] = tuple(unpacked[name])
        obj = cls.from_dict(value) if cls is NominationEvidenceV1 else cls(**unpacked)
        actual = obj.to_dict()
    except (TypeError, KeyError, ValueError, AttributeError) as exc:
        raise G4CandidatePreregError("G4_DISCOVERER_" + label + "_INVALID") from exc
    _need(actual == value, label + "_NONCANONICAL")
    return obj


def _census(entries, package, plan, attempt_id, budget):
    _need(type(entries) is list and len(entries) > 0, "LEDGER_ENTRIES")
    try:
        ledger = DiscovererLedger.from_dict_list(entries, max_entries=max(4096, len(entries)))
    except (TypeError, KeyError, ValueError) as exc:
        raise G4CandidatePreregError("G4_DISCOVERER_LEDGER_INVALID") from exc
    _need(ledger.verify_chain(), "LEDGER_CHAIN")
    last = {}
    identifiers = set()
    for entry in ledger.entries():
        _need(entry.state in STATES, "LEDGER_STATE")
        last[entry.attempt_id] = entry
        identifiers.add(entry.attempt_id)
    _need(0 < len(last) <= budget, "SEARCH_BUDGET")
    _need(all(x.search_plan_digest == plan.plan_digest for x in last.values()),
          "FOREIGN_PLAN_ATTEMPT")
    _need(all(x.family_id == package.family_id for x in last.values()),
          "FOREIGN_FAMILY_ATTEMPT")
    _need(attempt_id in last and last[attempt_id].candidate_id == package.candidate_id,
          "SELECTED_ATTEMPT")
    _need(last[attempt_id].strategy_digest == package.strategy_definition_digest and
          last[attempt_id].nomination_digest == package.nomination_evidence_digest,
          "ATTEMPT_IDENTITY")
    counts = {state: sum(x.state == state for x in last.values()) for state in sorted(STATES)}
    counts["total_unique_attempts"] = len(last)
    counts["total_ledger_events"] = len(entries)
    counts["incomplete_attempts"] = sum(x.state not in TERMINAL for x in last.values())
    _need(sum(counts[s] for s in STATES) == len(last), "DENOMINATOR")
    return counts, ledger.head_digest()


def build_g4_synthetic_candidate_proposal(*, candidate_package, synthetic_nomination,
                                          scanner_plugin, scanner_binding,
                                          hypothesis, search_plan, validation_protocol,
                                          durable_checkpoint, ledger_attempt_id,
                                          ledger_reference, baseline_id, trial_family_id,
                                          frozen_trial_budget):
    """Issue one sealed proposed-only receipt from existing durable custody.

    An all-variant Factory registry is still mandatory before evaluation;
    this proposal is not a permit to score, open holdout, or select a winner.
    """
    _need(type(ledger_reference) is str and bool(ledger_reference), "LEDGER_REFERENCE")
    for name, value in (("BASELINE_ID", baseline_id), ("TRIAL_FAMILY_ID", trial_family_id),
                        ("ATTEMPT_ID", ledger_attempt_id)):
        _need(type(value) is str and 0 < len(value) <= 160, name)
    _need(type(frozen_trial_budget) is int and frozen_trial_budget > 0,
          "TRIAL_BUDGET")
    package = _canonical(candidate_package, DiscoveryCandidatePackageV1, "CANDIDATE")
    nomination = _canonical(synthetic_nomination, NominationEvidenceV1, "NOMINATION")
    plan = _canonical(search_plan, SearchPlan, "SEARCH_PLAN")
    proto = _canonical(validation_protocol, ValidationProtocolV1, "PROTOCOL")
    hypo = _canonical(hypothesis, HypothesisProposal, "HYPOTHESIS")
    _need(plan.plan_digest == package.search_plan_digest and
          proto.search_plan_digest == plan.plan_digest and
          proto.family_registry_digest == plan.family_registry_digest and
          hypo.hypothesis_id in plan.hypothesis_ids and
          hypo.family_id == package.family_id and
          hypo.family_version == package.family_version and
          hypo.counterhypothesis_id == package.counterhypothesis_id,
          "PREREG_BINDING")
    _need(proto.holdout_sealed is True and
          proto.protocol_status == "EVALUATION_NOT_AUTHORIZED" and
          hypo.scientific_status == "PROPOSED_RESEARCH_ONLY" and
          plan.total_candidate_budget >= 1, "EVALUATION_AUTHORITY")
    _need(nomination.evidence_class == "TEST_ONLY_SYNTHETIC" and
          nomination.quarantine_status == "TEST_ONLY_SYNTHETIC" and
          nomination.nomination_digest == package.nomination_evidence_digest and
          nomination.source_manifest_sha256 == package.source_manifest_sha256,
          "SOURCE_NOMINATION")
    _need(package.status == "PROPOSED_RESEARCH_ONLY" and
          package.evaluation_status == "NOT_EVALUATED" and
          package.factory_routing == "NOT_CONNECTED", "RESEARCH_ONLY")
    try:
        valid = verify_test_only_candidate_binding(
            candidate_package=candidate_package, synthetic_nomination=synthetic_nomination,
            plugin=scanner_plugin, binding=scanner_binding)
    except (ValueError, TypeError, KeyError) as exc:
        raise G4CandidatePreregError("G4_DISCOVERER_SCANNER_BINDING_INVALID") from exc
    _need(valid is True, "SCANNER_BINDING_INVALID")
    _need(type(scanner_binding) is dict and _sha(scanner_binding.get("binding_sha256")),
          "SCANNER_RECEIPT")
    _need(hasattr(durable_checkpoint, "read_latest_ledger") and
          hasattr(durable_checkpoint, "verify_membership"), "DURABLE_LEDGER_REQUIRED")
    try:
        snapshot = durable_checkpoint.read_latest_ledger()
        membership = durable_checkpoint.verify_membership(
            package=package, ledger_attempt_id=ledger_attempt_id,
            ledger_head_digest=package.attempt_ledger_head,
            ledger_reference=ledger_reference)
    except (ValueError, KeyError, TypeError) as exc:
        raise G4CandidatePreregError("G4_DISCOVERER_DURABLE_MEMBERSHIP_INVALID") from exc
    _need(membership.package_digest == package.package_digest and
          membership.candidate_id == package.candidate_id and
          membership.checkpoint_head == package.attempt_ledger_head and
          membership.ledger_root == snapshot["ledger_head"],
          "MEMBERSHIP_IDENTITY")
    counts, root = _census(snapshot["entries"], package, plan,
                           ledger_attempt_id, plan.total_candidate_budget)
    _need(root == snapshot["ledger_head"] and
          snapshot["checkpoint_sha"] and _sha(snapshot["checkpoint_sha"]),
          "DURABLE_CENSUS_CONFLICT")
    _need(frozen_trial_budget >= counts["total_unique_attempts"],
          "TRIAL_BUDGET_BELOW_ATTEMPTS")
    payload = {
        "schema_version": SCHEMA, "source_class": "TEST_ONLY_SYNTHETIC",
        "proposal_status": "PROPOSED_NOT_EVALUATED",
        "candidate_id": package.candidate_id,
        "candidate_package_sha256": package.package_digest,
        "strategy_definition_sha256": package.strategy_definition_digest,
        "nomination_evidence_sha256": nomination.nomination_digest,
        "source_manifest_sha256": package.source_manifest_sha256,
        "search_plan_sha256": plan.plan_digest,
        "hypothesis_sha256": hypo.hypothesis_digest,
        "protocol_sha256": proto.protocol_digest,
        "candidate_family_id": package.family_id,
        "counterhypothesis_id": package.counterhypothesis_id,
        "scanner_binding_sha256": scanner_binding["binding_sha256"],
        "scanner_plugin_sha256": scanner_binding["scanner_plugin_sha256"],
        "ledger_reference": ledger_reference,
        "ledger_attempt_id": ledger_attempt_id,
        "ledger_checkpoint_sha256": snapshot["checkpoint_sha"],
        "attempt_ledger_head_sha256": snapshot["ledger_head"],
        "membership_sha256": membership.verification_digest,
        "attempt_census": counts,
        "trial_family_id": trial_family_id, "paired_baseline_id": baseline_id,
        "frozen_trial_budget": frozen_trial_budget,
        "multiplicity_plan_sha256": _digest(proto.multiplicity_plan),
        "partition_rules_sha256": _digest(proto.partition_rules),
        "result_selection": "NOT_PERFORMED",
        "oos_status": "SEALED_UNOPENED",
        "historical_pit": "NOT_ATTESTED",
        "source_rights": "NOT_INDEPENDENTLY_VERIFIED",
        "source_ack_sha256": None, "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None, "research_review_ack_sha256": None,
        "trading_authority": "NONE",
        "factory_trial_registry_required": True,
    }
    return {**payload, "proposal_sha256": _digest(payload)}


def verify_g4_synthetic_candidate_proposal(*, proposal, **originals):
    """Rebuild from stored originals and durable ledger; reject substituted fields."""
    _need(type(proposal) is dict and _sha(proposal.get("proposal_sha256")),
          "PROPOSAL_FORMAT")
    expected = build_g4_synthetic_candidate_proposal(**originals)
    _need(proposal == expected, "PROPOSAL_MISMATCH")
    return True
