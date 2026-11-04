"""Single TEST_ONLY cross-owner contract gate; NO unmerged runtime imports.

Fixtures conform to Core #226 query and Discoverer #230 candidate/evidence
field shapes, then invoke the ACTUAL existing Factory descriptive evaluator.
"""
from __future__ import annotations
import copy
import unittest
from test_aql_factory_research_consumer_seam import integration_fixture
from research_wp_r0.aql_factory_research_consumer_seam import digest, seal
from research_wp_r0.aql_factory_cross_owner_compatibility import (
    build_compatibility_report, validate_core_query, validate_discoverer,
)
from research_wp_r0.aql_p2_factory_lab import LabContractError

CORE_HEAD = "6c4ddfe481b89f6fbdc79d1a31a664f65a5fdc54"
DISCOVERER_HEAD = "f2006c0e431690ccea8b0532095bf4f2a2dc88ba"


def fixture():
    schedule, envelope, observations = integration_fixture()
    selected = next(x for x in envelope["rows"] if x["status"] == "NOMINATED")
    definition = "c" * 64
    for row in envelope["rows"]:
        row["strategy_version"] = definition
    envelope["strategy_version"] = definition
    envelope = seal({k: v for k, v in envelope.items() if k != "artifact_sha256"})
    cutoff = selected["decision_cutoff_ms"]
    request = {
        "schema": "aql.core-research.custody-query.v1",
        "dataset_id": "TEST_ONLY_SOURCE",
        "version": 1, "start_ms": 899880000,
        "end_exclusive_ms": 899940000, "decision_cutoff_ms": cutoff,
        "require_complete": True, "confirmed_only": False,
    }
    core_result = {
        "schema": "aql.bridge.custody-range.v1",
        "dataset_id": request["dataset_id"], "version": 1,
        "manifest_integrity_sha256": "f" * 64,
        "source_bytes_sha256": schedule["source"]["source_package_sha256"],
        "decision_cutoff_ms": cutoff,
        "status": "COMPLETE", "available_bar_count": 1,
        "required_bar_count": 1, "missing_bar_opens": [],
        "availability_class": "SYNTHETIC_TEST",
        "source_confidence": "LOCAL_CHECKSUM_AND_PIN_ONLY",
        "bars": [{
            "bar_open": 899880000, "bar_close": 899939999,
            "checksum": "a" * 64,
            "observation_cutoff_ms": 899940000,
            "availability_kind": "RETROSPECTIVE",
        }],
        "research_evaluation": "NOT_PERFORMED",
    }
    response = {
        "schema": "aql.core-research.custody-query-result.v1",
        "status": "OK", "error": None, "result": core_result,
        "evidence_class": "SYNTHETIC_TEST",
    }
    evidence = {
        "schema_version": "aql.discoverer.nomination-evidence.v1",
        "evidence_class": "TEST_ONLY_SYNTHETIC",
        "quarantine_status": "TEST_ONLY_SYNTHETIC",
        "scanner_contract_version": "TEST_ONLY.0.1.0",
        "scanner_source_commit": "0"*40,
        "scanner_envelope_sha256": "a"*64,
        "scanner_receipt_sha256": "b"*64,
        "source_dataset_id": "TEST_ONLY_SOURCE",
        "source_dataset_version": 1,
        "source_raw_sha256": schedule["source"]["source_package_sha256"],
        "source_manifest_sha256": "f"*64,
        "universe_snapshot_sha256": "e"*64,
        "scan_run_id": "TEST_ONLY_RUN_1",
        "market": "BINANCE_SPOT", "symbol": "BTCUSDT", "timeframe": "1m",
        "profile": "TEST_ONLY", "cutoff_ms": cutoff,
        "source_availability": "UNKNOWN",
        "full_universe_denominator": 4,
        "eligible_selected": 3, "ineligible": 1, "unscanned": 1,
        "screened_rejected": 1, "unknown": 0, "nominated": 1,
        "failed_attempts": 0, "omission_reason_codes": ["TEST_ONLY_UNSCANNED"],
        "independent_verifier_receipt_sha256": "0"*64,
    }
    evidence["nomination_digest"] = digest(evidence)
    candidate = {
        "schema_version": "aql.discoverer.candidate.v1",
        "candidate_id": "TEST_ONLY_CANDIDATE",
        "family_id": "TEST_FAMILY", "family_version": "v1",
        "strategy_definition_digest": definition,
        "strategy_spec": {"fixture": "NOT_A_REAL_STRATEGY"},
        "nomination_evidence_digest": evidence["nomination_digest"],
        "source_manifest_sha256": evidence["source_manifest_sha256"],
        "rule_grammar_version": "aql.strategy-definition.grammar.v1",
        "search_plan_digest": "a"*64,
        "counterhypothesis_id": "TEST_ONLY_NULL",
        "attempt_ledger_head": "b"*64,
        "status": "PROPOSED_RESEARCH_ONLY",
        "evaluation_status": "NOT_EVALUATED",
        "scientific_acceptance": "NOT_OBTAINED",
        "execution_status": "NOT_AUTHORIZED",
        "publishable": False, "delivery_authorized": False,
        "holdout_status": "SEALED_UNOPENED",
        "factory_routing": "NOT_CONNECTED",
    }
    candidate["package_digest"] = digest(candidate)
    binding = {
        "pair_id": selected["pair_id"], "arm": selected["arm"],
        "attempt_id": selected["attempt_id"],
        "candidate_id": candidate["candidate_id"],
    }
    return schedule, envelope, observations, request, response, evidence, candidate, binding


def repin_evidence(spec):
    spec["nomination_digest"] = digest({
        k: v for k, v in spec.items() if k != "nomination_digest"
    })


def repin_package(spec):
    spec["package_digest"] = digest({
        k: v for k, v in spec.items() if k != "package_digest"
    })


class TestCrossOwnerCompatibility(unittest.TestCase):
    def test_one_consolidated_query_candidate_factory_report(self):
        args = fixture()
        original = copy.deepcopy(args)
        a = build_compatibility_report(*args)
        b = build_compatibility_report(*args)
        self.assertEqual(a, b)
        self.assertEqual(args, original)
        self.assertEqual(a["factory_arm_slots"], 8)
        self.assertEqual(a["factory_observation_slots"], 24)
        self.assertEqual(sum(a["factory_status_counts"].values()), 8)
        self.assertEqual(a["discoverer_census"]["unscanned"], 1)
        self.assertEqual(a["scanner_nomination"], "TEST_ONLY_QUARANTINED")
        self.assertEqual(a["authentic_core_discoverer_connection"], "NOT_CONNECTED")
        self.assertEqual(a["modeled_trades"], "NOT_EVALUATED")
        self.assertEqual(a["trading_authority"], "NONE")
        self.assertEqual(a["artifact_sha256"], digest({
            k: v for k, v in a.items() if k != "artifact_sha256"
        }))
        print("FACTORY_CROSS_OWNER_TEST_ONLY_RECEIPT", a["artifact_sha256"])

    def test_read_only_core_and_discoverer_negative_matrix(self):
        cases = [
            ("core-missing", lambda x: x[4]["result"].update(missing_bar_opens=[899880000])),
            ("core-partial", lambda x: x[4]["result"].update(status="PARTIAL")),
            ("core-future", lambda x: x[4]["result"]["bars"][0].update(observation_cutoff_ms=900000001)),
            ("core-grid", lambda x: x[4]["result"]["bars"][0].update(bar_open=899880001)),
            ("core-source", lambda x: x[4]["result"].update(source_bytes_sha256="9"*64)),
            ("core-real-claim", lambda x: x[4].update(evidence_class="CONFIRMED_ONLY_QUERY_NOT_ATTESTATION")),
            ("core-errored", lambda x: x[4].update(status="ERROR", result=None)),
            ("core-request-future", lambda x: x[3].update(decision_cutoff_ms=899800000)),
            ("discovery-fake-digest", lambda x: x[5].update(cutoff_ms=1)),
            ("discovery-census", lambda x: x[5].update(nominated=2)),
            ("discovery-unscanned", lambda x: x[5].update(omission_reason_codes=[])),
            ("discovery-quarantine", lambda x: x[5].update(quarantine_status="UNKNOWN_DEFERRED")),
            ("discovery-pit", lambda x: x[5].update(evidence_class="RETROSPECTIVE_NON_PIT_VERIFIED")),
            ("package-nested-tamper", lambda x: x[6]["strategy_spec"].update(fixture="CHANGED")),
            ("package-authority", lambda x: x[6].update(factory_routing="CONNECTED")),
            ("package-fill", lambda x: x[6].update(evaluation_status="EVALUATED")),
            ("package-nomination-link", lambda x: x[6].update(nomination_evidence_digest="8"*64)),
            ("factory-wrong-version", lambda x: x[1].update(strategy_version="NOT_PINNED")),
            ("factory-missing-denominator", lambda x: x[1]["rows"].pop()),
            ("factory-null-to-zero", lambda x: x[1]["rows"][-1].update(**{"return":0})),
            ("selected-pair-wrong", lambda x: x[7].update(pair_id="0"*64)),
            ("selected-cutoff-wrong", lambda x: x[5].update(cutoff_ms=9)),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                args = list(fixture())
                mutate(args)
                # Honest malicious-attempt test: valid upstream self-digests
                # still cannot bypass the independent Factory join/checks.
                if label not in ("discovery-fake-digest", "package-nested-tamper"):
                    repin_evidence(args[5])
                    args[6]["nomination_evidence_digest"] = args[5]["nomination_digest"]
                    repin_package(args[6])
                if label.startswith("factory-"):
                    env = args[1]
                    args[1] = seal({k:v for k,v in env.items()
                                    if k != "artifact_sha256"})
                with self.assertRaises(LabContractError):
                    build_compatibility_report(*args)


if __name__ == "__main__":
    unittest.main()
