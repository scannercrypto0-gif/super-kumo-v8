"""D-SCAN-1: verified, synthetic-only Discoverer -> existing Scanner H plugin.

No F4 historical authority, no Factory enqueue, no approved strategies.
Package integrity and Scanner canonical AST are independently recomputed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1, NominationEvidenceV1, _digest,
)

SCHEMA = "aql.discoverer.h.synthetic-scanner-candidate-binding.v1"
CONTEXT = "TEST_ONLY"
HEX = set("0123456789abcdef")


class CandidateBridgeError(ValueError):
    pass


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in HEX for c in value):
        raise CandidateBridgeError(name + ": invalid sha256")
    return value


def _package(value: Any) -> DiscoveryCandidatePackageV1:
    if type(value) is not dict:
        raise CandidateBridgeError("candidate: canonical dictionary required")
    if value.get("schema_version") != "aql.discoverer.candidate.v1":
        raise CandidateBridgeError("candidate: unexpected schema")
    try:
        package = DiscoveryCandidatePackageV1.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise CandidateBridgeError("candidate: invalid sealed package") from exc
    if package.to_dict() != value:
        raise CandidateBridgeError("candidate: noncanonical fields")
    if package.status != "PROPOSED_RESEARCH_ONLY":
        raise CandidateBridgeError("candidate: not a proposed research candidate")
    if (package.evaluation_status != "NOT_EVALUATED"
        or package.scientific_acceptance != "NOT_OBTAINED"
        or package.execution_status != "NOT_AUTHORIZED"
        or package.publishable is not False
        or package.delivery_authorized is not False
        or package.holdout_status != "SEALED_UNOPENED"
        or package.factory_routing != "NOT_CONNECTED"):
        raise CandidateBridgeError("candidate: authority flags forbidden")
    return package


def _nomination(value: Any, package: DiscoveryCandidatePackageV1) -> None:
    if type(value) is not dict:
        raise CandidateBridgeError("nomination: required for synthetic binding")
    try:
        n = NominationEvidenceV1.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise CandidateBridgeError("nomination: invalid sealed evidence") from exc
    if (n.to_dict() != value or n.nomination_digest != package.nomination_evidence_digest
        or n.source_manifest_sha256 != package.source_manifest_sha256
        or n.evidence_class != "TEST_ONLY_SYNTHETIC"
        or n.quarantine_status != "TEST_ONLY_SYNTHETIC"):
        raise CandidateBridgeError("nomination: TEST_ONLY synthetic/source binding required")


def _definition(package: DiscoveryCandidatePackageV1):
    try:
        from research_wp_r0.strategy_definition import StrategyDefinition
        from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
        spec = package.strategy_spec
        if type(spec) is not dict or set(spec) != {"definition", "digest"}:
            raise CandidateBridgeError(
                "strategy_spec: exact StrategyDefinition.to_dict() fields required")
        definition = StrategyDefinition.from_dict(spec, registry=IndicatorRegistryV2())
        if (definition.to_dict() != spec
            or definition.digest != package.strategy_definition_digest):
            raise CandidateBridgeError("strategy_definition_digest: canonical mismatch")
        return definition
    except CandidateBridgeError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise CandidateBridgeError("strategy_spec: Scanner AST/indicator registry incompatible") from exc


def _bind(package: DiscoveryCandidatePackageV1, nomination: dict, plugin: dict) -> dict:
    from tools.strategy_service_offline.common import Frozen
    from tools.scanner_strategy_f.research_strategy_plugin import PLUGIN_SCHEMA
    p = Frozen.restore(plugin).data
    if (p.get("schema") != PLUGIN_SCHEMA
        or p.get("input_origin") != "DISCOVERER_CANDIDATE"
        or p.get("candidate_sha256") != package.package_digest
        or p.get("definition_digest") != package.strategy_definition_digest
        or p.get("definition") != package.strategy_spec
        or p.get("config_identity_class") != "MANUAL_AST_PARAMETERS"
        or p.get("policy_status") != "RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL"
        or p.get("historical_pit") != "NOT_ATTESTED"
        or p.get("source_ack_sha256") is not None
        or p.get("strategy_approval_sha256") is not None
        or p.get("factory_consumer_ack_sha256") is not None
        or p.get("trading_authority") != "NONE"):
        raise CandidateBridgeError("Scanner: candidate identity/authority mismatch")
    return {
        "schema_version": SCHEMA,
        "source_class": CONTEXT,
        "candidate_id": package.candidate_id,
        "candidate_package_sha256": package.package_digest,
        "nomination_evidence_sha256": nomination["nomination_digest"],
        "strategy_definition_sha256": package.strategy_definition_digest,
        "scanner_plugin_sha256": _sha(plugin["sha256"], "Scanner plugin"),
        "scanner_plugin_schema": PLUGIN_SCHEMA,
        "research_scope": "SYNTHETIC_RESEARCH_ONLY",
        "historical_pit": "NOT_ATTESTED",
        "status": "RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL",
        "f4_historical_connected": False,
        "selected": False,
        "source_ack_sha256": None,
        "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        "holdout_status": "SEALED_UNOPENED",
        "trading_authority": "NONE",
    }


def project_test_only_candidate(*, candidate_package: dict, synthetic_nomination: dict,
                                research_context: str = CONTEXT) -> tuple[dict, dict]:
    """Return (Scanner's existing plugin receipt, sealed Discoverer binding).

    No historical source/provenance inferred from synthetic nomination or sha.
    """
    if research_context != CONTEXT:
        raise CandidateBridgeError("context: TEST_ONLY required")
    p = _package(candidate_package)
    _nomination(synthetic_nomination, p)
    _definition(p)

    from tools.scanner_strategy_f.research_strategy_plugin import (
        manual_config_digest, register_strategy_plugin,
    )
    config = manual_config_digest(p.strategy_spec)
    plugin = register_strategy_plugin(
        p.strategy_spec, config_digest=config, origin="DISCOVERER_CANDIDATE",
        candidate_sha256=p.package_digest,
    )
    payload = _bind(p, synthetic_nomination, plugin)
    return plugin, {**payload, "binding_sha256": _digest(payload)}


def verify_test_only_candidate_binding(*, candidate_package: dict,
                                       synthetic_nomination: dict,
                                       plugin: dict, binding: dict) -> bool:
    """Independently recompute the full binding, including Scanner's own seal."""
    if type(binding) is not dict or set(binding) != {
        "schema_version", "source_class", "candidate_id",
        "candidate_package_sha256", "nomination_evidence_sha256",
        "strategy_definition_sha256", "scanner_plugin_sha256",
        "scanner_plugin_schema", "research_scope", "historical_pit",
        "status", "f4_historical_connected", "selected",
        "source_ack_sha256", "strategy_approval_sha256",
        "factory_consumer_ack_sha256", "holdout_status",
        "trading_authority", "binding_sha256",
    }:
        raise CandidateBridgeError("binding: exact schema required")
    if binding.get("binding_sha256") != _digest({
        k: v for k, v in binding.items() if k != "binding_sha256"
    }):
        raise CandidateBridgeError("binding: digest mismatch")
    expected_plugin, expected = project_test_only_candidate(
        candidate_package=candidate_package,
        synthetic_nomination=synthetic_nomination,
        research_context=CONTEXT,
    )
    if plugin != expected_plugin or binding != expected:
        raise CandidateBridgeError("binding: candidate/Scanner receipt mismatch")
    return True
