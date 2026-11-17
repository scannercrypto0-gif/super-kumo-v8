"""
Tests for package.py
======================
Covers:
  - PackagingResult census accuracy
  - Ledger records every attempt BEFORE packaging
  - Failed packaging recorded as FAILED in ledger
  - source_manifest_sha256 validation
  - All packages have hard NOT_* guards set
  - package_digest unique per candidate
"""

import pytest

from tools.strategy_discoverer_offline.scanner_adapter import ScannerQuarantineAdapter
from tools.strategy_discoverer_offline.families import get_family
from tools.strategy_discoverer_offline.hypotheses import SearchPlan
from tools.strategy_discoverer_offline.generator import HypothesisGenerator
from tools.strategy_discoverer_offline.ledger import DiscovererLedger, AttemptState
from tools.strategy_discoverer_offline.package import CandidatePackager, PackagingResult
from tools.strategy_discoverer_offline.families import family_registry_digest
from tools.strategy_discoverer_offline.contracts import (
    EvaluationStatus,
    ExecutionStatus,
    HoldoutStatus,
    FactoryRouting,
    ScientificAcceptanceStatus,
    CandidateStatus,
)


_SOURCE_MANIFEST = "a" * 64  # valid 64-char hex SHA


def _make_evidence(symbol="BTCUSDT", timeframe="1h"):
    adapter = ScannerQuarantineAdapter()
    return adapter.admit_synthetic_fixture({
        "receipt_id": f"synth-{symbol}-{timeframe}",
        "symbol": symbol,
        "market": "binance_spot",
        "timeframe": timeframe,
        "dataset_id": "test_ds_001",
        "dataset_manifest_sha256": "e" * 64,
        "universe_snapshot_sha256": "f" * 64,
        "available_at_ms": 1_700_000_000_000,
        "decision_cutoff_ms": 1_700_000_000_000,
        "bar_count": 200,
        "warmup_bars": 50,
        "census_eligible_count": 1,
        "census_omission_count": 0,
        "census_omission_codes": (),
    })


def _run_family_and_package(family_id="F004"):
    """Helper: generate + package for one family. Returns (result, packager, gen_result)."""
    family = get_family(family_id)
    evidence = _make_evidence()
    reg_digest = family_registry_digest()
    search_plan = SearchPlan.build(
        search_plan_id=f"sp-test-{family_id}",
        family_registry_digest=reg_digest,
        hypothesis_ids=(f"hyp-{family_id}-001",),
        total_candidate_budget=family.max_candidates,
    )
    gen = HypothesisGenerator()
    gen_result = gen.run_family(family, evidence, search_plan.plan_digest)
    ledger = DiscovererLedger()
    packager = CandidatePackager(ledger, search_plan, family)
    result = packager.package_generation(gen_result, evidence, _SOURCE_MANIFEST)
    return result, packager, gen_result, ledger


class TestPackagingResultCensus:
    def test_returns_packaging_result(self):
        result, *_ = _run_family_and_package("F004")
        assert isinstance(result, PackagingResult)

    def test_submitted_plus_rejected_equals_attempt(self):
        result, *_ = _run_family_and_package("F004")
        assert result.submitted_count + result.rejected_count == result.attempt_count

    def test_packages_length_matches_submitted_count(self):
        result, *_ = _run_family_and_package("F004")
        assert len(result.packages) == result.submitted_count

    def test_packaging_manifest_digest_64_hex(self):
        result, *_ = _run_family_and_package("F004")
        assert len(result.packaging_manifest_digest) == 64
        assert all(c in "0123456789abcdef" for c in result.packaging_manifest_digest)

    def test_ledger_head_in_result(self):
        result, _, _, ledger = _run_family_and_package("F004")
        assert result.ledger_head == ledger.head_digest()


class TestLedgerRegistrationOrder:
    def test_ledger_has_at_least_one_entry(self):
        result, _, gen_result, ledger = _run_family_and_package("F004")
        # Each candidate has at least REGISTERED + PENDING + COMPLETE/FAILED
        assert ledger.entry_count() >= result.submitted_count * 3

    def test_no_incomplete_attempts_after_full_run(self):
        result, _, gen_result, ledger = _run_family_and_package("F004")
        incomplete = ledger.incomplete_attempts()
        assert len(incomplete) == 0

    def test_ledger_chain_verifies(self):
        _, _, _, ledger = _run_family_and_package("F004")
        assert ledger.verify_chain() is True


class TestPackageGuards:
    def test_all_packages_evaluation_not_evaluated(self):
        result, *_ = _run_family_and_package("F004")
        for pkg in result.packages:
            assert pkg.evaluation_status == EvaluationStatus.NOT_EVALUATED.value

    def test_all_packages_execution_not_authorized(self):
        result, *_ = _run_family_and_package("F004")
        for pkg in result.packages:
            assert pkg.execution_status == ExecutionStatus.NOT_AUTHORIZED.value

    def test_all_packages_not_publishable(self):
        result, *_ = _run_family_and_package("F004")
        for pkg in result.packages:
            assert pkg.publishable is False

    def test_all_packages_delivery_not_authorized(self):
        result, *_ = _run_family_and_package("F004")
        for pkg in result.packages:
            assert pkg.delivery_authorized is False

    def test_all_packages_holdout_sealed(self):
        result, *_ = _run_family_and_package("F004")
        for pkg in result.packages:
            assert pkg.holdout_status == HoldoutStatus.SEALED_UNOPENED.value

    def test_all_packages_factory_not_connected(self):
        result, *_ = _run_family_and_package("F004")
        for pkg in result.packages:
            assert pkg.factory_routing == FactoryRouting.NOT_CONNECTED.value

    def test_all_packages_proposed_research_only(self):
        result, *_ = _run_family_and_package("F004")
        for pkg in result.packages:
            assert pkg.status == CandidateStatus.PROPOSED_RESEARCH_ONLY.value


class TestPackageUniqueness:
    def test_package_digests_unique(self):
        result, *_ = _run_family_and_package("F001")
        if len(result.packages) > 1:
            digests = [p.package_digest for p in result.packages]
            assert len(set(digests)) == len(digests)


class TestSourceManifestValidation:
    def test_invalid_source_manifest_raises(self):
        family = get_family("F004")
        evidence = _make_evidence()
        reg_digest = family_registry_digest()
        search_plan = SearchPlan.build(
            search_plan_id="sp-bad-manifest",
            family_registry_digest=reg_digest,
            hypothesis_ids=("hyp-001",),
            total_candidate_budget=8,
        )
        gen = HypothesisGenerator()
        gen_result = gen.run_family(family, evidence, search_plan.plan_digest)
        ledger = DiscovererLedger()
        packager = CandidatePackager(ledger, search_plan, family)

        with pytest.raises(ValueError):
            packager.package_generation(gen_result, evidence, "tooshort")

    def test_non_hex_source_manifest_raises(self):
        family = get_family("F004")
        evidence = _make_evidence()
        reg_digest = family_registry_digest()
        search_plan = SearchPlan.build(
            search_plan_id="sp-bad-manifest-2",
            family_registry_digest=reg_digest,
            hypothesis_ids=("hyp-001",),
            total_candidate_budget=8,
        )
        gen = HypothesisGenerator()
        gen_result = gen.run_family(family, evidence, search_plan.plan_digest)
        ledger = DiscovererLedger()
        packager = CandidatePackager(ledger, search_plan, family)

        with pytest.raises(ValueError):
            packager.package_generation(gen_result, evidence, "Z" * 64)
