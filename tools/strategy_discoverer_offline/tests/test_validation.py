"""
Tests for validation.py (Phase 6 — Validation Protocol)
=========================================================
Covers:
  - ValidationProtocolV1 builds correctly
  - protocol_status is always EVALUATION_NOT_AUTHORIZED
  - holdout_sealed is always True
  - protocol_digest verifies
  - Comparator slate fully populated
  - All predeclared metrics present
  - Evaluation gates are declared
  - Tampered protocol_digest detected
  - Cross-call determinism
"""

import pytest

from tools.strategy_discoverer_offline.validation import (
    ValidationProtocolV1,
    ProtocolStatus,
    COMPARATOR_SLATE_V1,
    PREDECLARED_METRICS_V1,
    PARTITION_RULES_V1,
    MULTIPLICITY_PLAN_V1,
)
from tools.strategy_discoverer_offline.families import family_registry_digest


def _make_protocol(**overrides):
    base = dict(
        protocol_id="vp-test-001",
        family_registry_digest=family_registry_digest(),
        search_plan_digest="a" * 64,
    )
    base.update(overrides)
    return ValidationProtocolV1.build(**base)


class TestValidationProtocolBuild:
    def test_builds_correctly(self):
        p = _make_protocol()
        assert isinstance(p, ValidationProtocolV1)

    def test_schema_version_correct(self):
        p = _make_protocol()
        assert p.schema_version == "aql.discoverer.validation-protocol.v1"

    def test_protocol_status_evaluation_not_authorized(self):
        p = _make_protocol()
        assert p.protocol_status == ProtocolStatus.EVALUATION_NOT_AUTHORIZED.value

    def test_holdout_sealed_true(self):
        p = _make_protocol()
        assert p.holdout_sealed is True

    def test_protocol_digest_is_64_hex(self):
        p = _make_protocol()
        assert len(p.protocol_digest) == 64
        assert all(c in "0123456789abcdef" for c in p.protocol_digest)

    def test_evaluation_gates_populated(self):
        p = _make_protocol()
        assert len(p.evaluation_gates) >= 4
        # Must include all four GATE_A through GATE_D
        gates_str = " ".join(p.evaluation_gates)
        for gate in ("GATE_A", "GATE_B", "GATE_C", "GATE_D"):
            assert gate in gates_str

    def test_comparator_slate_populated(self):
        p = _make_protocol()
        assert len(p.comparator_slate) >= 7
        # Check RANDOM_BASELINE is present
        assert any("RANDOM_BASELINE" in s for s in p.comparator_slate)

    def test_predeclared_metrics_populated(self):
        p = _make_protocol()
        assert len(p.predeclared_metrics) >= 10
        assert "precision_at_k" in p.predeclared_metrics
        assert "recall_at_k" in p.predeclared_metrics
        assert "pr_auc" in p.predeclared_metrics

    def test_partition_rules_present(self):
        p = _make_protocol()
        assert "type" in p.partition_rules
        assert p.partition_rules["type"] == "chronological_walkforward"

    def test_multiplicity_plan_present(self):
        p = _make_protocol()
        assert "approach" in p.multiplicity_plan
        assert "White_Reality_Check" in p.multiplicity_plan["methods"]


class TestValidationProtocolIntegrity:
    def test_cross_call_determinism(self):
        p1 = _make_protocol()
        p2 = _make_protocol()
        assert p1.protocol_digest == p2.protocol_digest

    def test_different_protocol_id_different_digest(self):
        p1 = _make_protocol(protocol_id="vp-001")
        p2 = _make_protocol(protocol_id="vp-002")
        assert p1.protocol_digest != p2.protocol_digest

    def test_tampered_digest_rejected_on_init(self):
        """Directly constructing with wrong digest must be caught by __post_init__."""
        p = _make_protocol()
        # Attempt to create with tampered digest — this bypasses .build()
        with pytest.raises((ValueError, AssertionError, TypeError)):
            ValidationProtocolV1(
                schema_version=p.schema_version,
                protocol_id=p.protocol_id,
                family_registry_digest=p.family_registry_digest,
                search_plan_digest=p.search_plan_digest,
                comparator_slate=p.comparator_slate,
                predeclared_metrics=p.predeclared_metrics,
                partition_rules=p.partition_rules,
                multiplicity_plan=p.multiplicity_plan,
                protocol_status=p.protocol_status,
                holdout_sealed=p.holdout_sealed,
                evaluation_gates=p.evaluation_gates,
                protocol_digest="0" * 64,  # <-- tampered
            )

    def test_wrong_schema_version_rejected(self):
        p = _make_protocol()
        with pytest.raises((ValueError, AssertionError, TypeError)):
            ValidationProtocolV1(
                schema_version="aql.discoverer.validation-protocol.v999",
                protocol_id=p.protocol_id,
                family_registry_digest=p.family_registry_digest,
                search_plan_digest=p.search_plan_digest,
                comparator_slate=p.comparator_slate,
                predeclared_metrics=p.predeclared_metrics,
                partition_rules=p.partition_rules,
                multiplicity_plan=p.multiplicity_plan,
                protocol_status=p.protocol_status,
                holdout_sealed=p.holdout_sealed,
                evaluation_gates=p.evaluation_gates,
                protocol_digest=p.protocol_digest,
            )

    def test_holdout_unsealed_rejected(self):
        """holdout_sealed=False must be rejected at init."""
        p = _make_protocol()
        with pytest.raises((ValueError, AssertionError, TypeError)):
            ValidationProtocolV1(
                schema_version=p.schema_version,
                protocol_id=p.protocol_id,
                family_registry_digest=p.family_registry_digest,
                search_plan_digest=p.search_plan_digest,
                comparator_slate=p.comparator_slate,
                predeclared_metrics=p.predeclared_metrics,
                partition_rules=p.partition_rules,
                multiplicity_plan=p.multiplicity_plan,
                protocol_status=p.protocol_status,
                holdout_sealed=False,  # <-- must be rejected
                evaluation_gates=p.evaluation_gates,
                protocol_digest=p.protocol_digest,
            )

    def test_to_dict_round_trips(self):
        p = _make_protocol()
        d = p.to_dict()
        assert d["protocol_digest"] == p.protocol_digest
        assert d["schema_version"] == p.schema_version
        assert d["holdout_sealed"] is True


class TestComparatorSlate:
    def test_comparator_slate_module_constant(self):
        assert len(COMPARATOR_SLATE_V1) >= 7
        ids = {c["id"] for c in COMPARATOR_SLATE_V1}
        assert "RANDOM_BASELINE" in ids
        assert "VOLUME_ONLY" in ids
        assert "SIMPLE_MOMENTUM" in ids
        assert "RVOL_ONLY" in ids

    def test_predeclared_metrics_module_constant(self):
        assert "precision_at_k" in PREDECLARED_METRICS_V1
        assert "missingness_failure_rate" in PREDECLARED_METRICS_V1
        assert "regime_strata_breakdown" in PREDECLARED_METRICS_V1
