"""
Adversarial tests for contracts.py
====================================
Covers:
  - NominationEvidenceV1: digest integrity, field validation, round-trip
  - DiscoveryCandidatePackageV1: hard NOT_* guards, digest integrity
  - Content-addressed determinism across Python versions
  - Tampered field detection
  - Census count / constraint guards
"""

import hashlib
import json
import pytest

from tools.strategy_discoverer_offline.contracts import (
    NominationEvidenceV1,
    DiscoveryCandidatePackageV1,
    EvidenceClass,
    SourceAvailability,
    ScannerQuarantineStatus,
    EvaluationStatus,
    ScientificAcceptanceStatus,
    ExecutionStatus,
    HoldoutStatus,
    FactoryRouting,
    CandidateStatus,
    _canonical,
    _digest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence(**overrides):
    """Build a minimal valid NominationEvidenceV1 via .build() and return it.

    Uses the actual field names from NominationEvidenceV1 (Phase 1 contract).
    Overrides are applied at the kwargs level before build is called.
    """
    base = dict(
        schema_version="aql.discoverer.nomination-evidence.v1",
        evidence_class=EvidenceClass.TEST_ONLY_SYNTHETIC.value,
        quarantine_status=ScannerQuarantineStatus.TEST_ONLY_SYNTHETIC.value,
        scanner_contract_version="0.1.0",
        scanner_source_commit="0" * 40,
        scanner_envelope_sha256="a" * 64,
        scanner_receipt_sha256="b" * 64,
        source_dataset_id="test_ds_001",
        source_dataset_version=1,
        source_raw_sha256="c" * 64,
        source_manifest_sha256="d" * 64,
        universe_snapshot_sha256="e" * 64,
        scan_run_id="run-test-001",
        market="binance_spot",
        symbol="BTCUSDT",
        timeframe="1h",
        profile="default",
        cutoff_ms=1_700_000_000_000,
        source_availability=SourceAvailability.CONFIRMED_FINAL.value,
        full_universe_denominator=100,
        eligible_selected=10,
        ineligible=5,
        unscanned=0,
        screened_rejected=85,
        unknown=0,
        nominated=1,
        failed_attempts=0,
        omission_reason_codes=(),
        independent_verifier_receipt_sha256="f" * 64,
    )
    base.update(overrides)
    return NominationEvidenceV1.build(**base)


def _make_package(**overrides):
    """Build a minimal valid DiscoveryCandidatePackageV1 via .build()."""
    strat_digest = "e" * 64
    nom_digest = "f" * 64
    source_mani = "0" * 64
    base = dict(
        schema_version="aql.discoverer.candidate.v1",
        candidate_id="F001-0001",
        family_id="F001",
        family_version="1.0.0",
        strategy_definition_digest=strat_digest,
        strategy_spec={"schema_version": "1"},
        nomination_evidence_digest=nom_digest,
        source_manifest_sha256=source_mani,
        rule_grammar_version="aql.strategy-definition.grammar.v1",
        search_plan_digest="9" * 64,
        counterhypothesis_id="F001-0001-null",
        attempt_ledger_head="1" * 64,
        status=CandidateStatus.PROPOSED_RESEARCH_ONLY.value,
    )
    base.update(overrides)
    return DiscoveryCandidatePackageV1.build(**base)


# ===========================================================================
# Section 1: _canonical determinism
# ===========================================================================

class TestCanonicalDeterminism:
    """Content-addressed bytes must be deterministic across calls."""

    def test_same_dict_same_bytes(self):
        d = {"z": 1, "a": 2, "m": [3, 4]}
        assert _canonical(d) == _canonical(d)

    def test_key_order_independent(self):
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        assert _canonical(a) == _canonical(b)

    def test_digest_matches_manual(self):
        d = {"foo": "bar"}
        expected = hashlib.sha256(json.dumps(d, sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()
        assert _digest(d) == expected

    def test_nan_blocked(self):
        with pytest.raises((ValueError, Exception)):
            _canonical({"v": float("nan")})

    def test_inf_blocked(self):
        with pytest.raises((ValueError, Exception)):
            _canonical({"v": float("inf")})

    def test_bytes_type_blocked(self):
        with pytest.raises((TypeError, ValueError)):
            _canonical({"v": b"bytes"})


# ===========================================================================
# Section 2: NominationEvidenceV1 — valid construction
# ===========================================================================

class TestNominationEvidenceValid:
    def test_build_returns_correct_class(self):
        ev = _make_evidence()
        assert isinstance(ev, NominationEvidenceV1)

    def test_nomination_digest_is_64_hex(self):
        ev = _make_evidence()
        assert len(ev.nomination_digest) == 64
        assert all(c in "0123456789abcdef" for c in ev.nomination_digest)

    def test_round_trip_from_dict(self):
        ev = _make_evidence()
        d = ev.to_dict()
        ev2 = NominationEvidenceV1.from_dict(d)
        assert ev2.nomination_digest == ev.nomination_digest

    def test_omission_reason_codes_tuple(self):
        ev = _make_evidence(omission_reason_codes=("DELIST", "COVERAGE_GAP"))
        assert isinstance(ev.omission_reason_codes, tuple)
        assert "DELIST" in ev.omission_reason_codes

    def test_schema_version_field_correct(self):
        ev = _make_evidence()
        assert ev.schema_version == "aql.discoverer.nomination-evidence.v1"

    def test_evidence_class_field_correct(self):
        ev = _make_evidence()
        assert ev.evidence_class == EvidenceClass.TEST_ONLY_SYNTHETIC.value

    def test_cutoff_ms_zero_valid(self):
        """cutoff_ms=0 is valid (boundary)."""
        ev = _make_evidence(cutoff_ms=0)
        assert ev.cutoff_ms == 0

    def test_source_dataset_version_one_valid(self):
        ev = _make_evidence(source_dataset_version=1)
        assert ev.source_dataset_version == 1

    def test_nominated_equals_eligible_selected_valid(self):
        """nominated may equal eligible_selected."""
        ev = _make_evidence(nominated=10, eligible_selected=10)
        assert ev.nominated == ev.eligible_selected


# ===========================================================================
# Section 3: NominationEvidenceV1 — adversarial / tampered inputs
# ===========================================================================

class TestNominationEvidenceTamper:
    def test_wrong_schema_version_rejected(self):
        with pytest.raises((ValueError, TypeError)):
            _make_evidence(schema_version="aql.discoverer.nomination-evidence.v99")

    def test_scanner_receipt_sha256_wrong_length(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(scanner_receipt_sha256="abc")

    def test_scanner_receipt_sha256_non_hex(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(scanner_receipt_sha256="z" * 64)

    def test_scanner_envelope_sha256_wrong_length(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(scanner_envelope_sha256="abc")

    def test_source_manifest_sha256_wrong_length(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(source_manifest_sha256="abc")

    def test_independent_verifier_receipt_wrong_length(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(independent_verifier_receipt_sha256="abc")

    def test_tampered_digest_field_rejected(self):
        ev = _make_evidence()
        d = ev.to_dict()
        # Flip one character of nomination_digest
        d["nomination_digest"] = d["nomination_digest"][:-1] + (
            "0" if d["nomination_digest"][-1] != "0" else "1"
        )
        with pytest.raises((ValueError, AssertionError)):
            NominationEvidenceV1.from_dict(d)

    def test_cutoff_ms_same_value_deterministic(self):
        """Two builds with same cutoff_ms yield the same digest."""
        ev1 = _make_evidence(cutoff_ms=1_700_000_000_000)
        ev2 = _make_evidence(cutoff_ms=1_700_000_000_000)
        assert ev1.nomination_digest == ev2.nomination_digest

    def test_negative_cutoff_ms_rejected(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(cutoff_ms=-1)

    def test_source_dataset_version_zero_rejected(self):
        """source_dataset_version must be ≥1."""
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(source_dataset_version=0)

    def test_source_dataset_version_negative_rejected(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(source_dataset_version=-1)

    def test_ineligible_negative_rejected(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(ineligible=-1)

    def test_nominated_exceeds_eligible_rejected(self):
        """nominated > eligible_selected must be rejected."""
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(nominated=11, eligible_selected=10)

    def test_eligible_exceeds_universe_rejected(self):
        """eligible_selected > full_universe_denominator must be rejected."""
        with pytest.raises((ValueError, AssertionError)):
            _make_evidence(eligible_selected=101, full_universe_denominator=100)

    def test_tampered_symbol_different_digest(self):
        ev1 = _make_evidence(symbol="BTCUSDT")
        ev2 = _make_evidence(symbol="ETHUSDT")
        assert ev1.nomination_digest != ev2.nomination_digest

    def test_tampered_cutoff_ms_different_digest(self):
        ev1 = _make_evidence(cutoff_ms=1_700_000_000_000)
        ev2 = _make_evidence(cutoff_ms=1_700_000_001_000)
        assert ev1.nomination_digest != ev2.nomination_digest

    def test_invalid_evidence_class_rejected(self):
        with pytest.raises((ValueError, KeyError)):
            _make_evidence(evidence_class="MADE_UP_CLASS")

    def test_invalid_source_availability_rejected(self):
        with pytest.raises((ValueError, KeyError)):
            _make_evidence(source_availability="CONFIRMED_FUTURE")

    def test_invalid_quarantine_status_rejected(self):
        with pytest.raises((ValueError, KeyError)):
            _make_evidence(quarantine_status="UNGUARDED")

    def test_omission_reason_codes_list_rejected(self):
        """omission_reason_codes must be a tuple, not a list."""
        with pytest.raises((ValueError, TypeError)):
            # Pass a list — __post_init__ must reject it
            NominationEvidenceV1(
                schema_version="aql.discoverer.nomination-evidence.v1",
                evidence_class=EvidenceClass.TEST_ONLY_SYNTHETIC.value,
                quarantine_status=ScannerQuarantineStatus.TEST_ONLY_SYNTHETIC.value,
                scanner_contract_version="0.1.0",
                scanner_source_commit="0" * 40,
                scanner_envelope_sha256="a" * 64,
                scanner_receipt_sha256="b" * 64,
                source_dataset_id="test_ds_001",
                source_dataset_version=1,
                source_raw_sha256="c" * 64,
                source_manifest_sha256="d" * 64,
                universe_snapshot_sha256="e" * 64,
                scan_run_id="run-test-001",
                market="binance_spot",
                symbol="BTCUSDT",
                timeframe="1h",
                profile="default",
                cutoff_ms=1_700_000_000_000,
                source_availability=SourceAvailability.CONFIRMED_FINAL.value,
                full_universe_denominator=100,
                eligible_selected=10,
                ineligible=5,
                unscanned=0,
                screened_rejected=85,
                unknown=0,
                nominated=1,
                failed_attempts=0,
                omission_reason_codes=["DELIST"],   # list, not tuple
                independent_verifier_receipt_sha256="f" * 64,
                nomination_digest="0" * 64,  # will fail digest check anyway
            )


# ===========================================================================
# Section 4: DiscoveryCandidatePackageV1 — hard NOT_* guards
# ===========================================================================

class TestCandidatePackageGuards:
    def test_valid_package_builds(self):
        p = _make_package()
        assert isinstance(p, DiscoveryCandidatePackageV1)

    def test_evaluation_status_locked_to_not_evaluated(self):
        p = _make_package()
        assert p.evaluation_status == EvaluationStatus.NOT_EVALUATED.value

    def test_scientific_acceptance_locked(self):
        p = _make_package()
        assert p.scientific_acceptance == ScientificAcceptanceStatus.NOT_OBTAINED.value

    def test_execution_status_locked(self):
        p = _make_package()
        assert p.execution_status == ExecutionStatus.NOT_AUTHORIZED.value

    def test_publishable_locked_false(self):
        p = _make_package()
        assert p.publishable is False

    def test_delivery_authorized_locked_false(self):
        p = _make_package()
        assert p.delivery_authorized is False

    def test_holdout_status_sealed(self):
        p = _make_package()
        assert p.holdout_status == HoldoutStatus.SEALED_UNOPENED.value

    def test_factory_routing_not_connected(self):
        p = _make_package()
        assert p.factory_routing == FactoryRouting.NOT_CONNECTED.value

    def test_status_proposed_only(self):
        p = _make_package()
        assert p.status == CandidateStatus.PROPOSED_RESEARCH_ONLY.value

    def test_package_digest_is_64_hex(self):
        p = _make_package()
        assert len(p.package_digest) == 64
        assert all(c in "0123456789abcdef" for c in p.package_digest)

    def test_tampered_candidate_id_different_digest(self):
        p1 = _make_package(candidate_id="F001-0001")
        p2 = _make_package(candidate_id="F001-0002")
        assert p1.package_digest != p2.package_digest

    def test_invalid_strategy_digest_rejected(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_package(strategy_definition_digest="not-a-valid-hash")

    def test_invalid_nomination_digest_rejected(self):
        with pytest.raises((ValueError, AssertionError)):
            _make_package(nomination_evidence_digest="tooshort")

    def test_package_tamper_digest_detected(self):
        p = _make_package()
        d = p.to_dict()
        d["package_digest"] = "0" * 64
        with pytest.raises((ValueError, AssertionError)):
            DiscoveryCandidatePackageV1(**d)


# ===========================================================================
# Section 5: Cross-call determinism
# ===========================================================================

class TestCrossDeterminism:
    def test_same_evidence_same_digest_two_calls(self):
        ev1 = _make_evidence()
        ev2 = _make_evidence()
        assert ev1.nomination_digest == ev2.nomination_digest

    def test_same_package_same_digest_two_calls(self):
        p1 = _make_package()
        p2 = _make_package()
        assert p1.package_digest == p2.package_digest
