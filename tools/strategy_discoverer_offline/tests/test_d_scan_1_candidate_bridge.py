"""D-SCAN-1: synthetic contract-only candidate projection and adversarial tests."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import StrategyDefinition
from tools.scanner_strategy_f.research_strategy_plugin import (
    register_strategy_plugin, manual_config_digest,
)
from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1,
)
from tools.strategy_discoverer_offline.synthetic_scanner_candidate_bridge import (
    CandidateBridgeError, project_test_only_candidate, verify_test_only_candidate_binding,
)
from tools.strategy_discoverer_offline.tests.test_factory_lab_bridge import (
    _make_evidence, _make_package,
)


def case():
    nomination = _make_evidence()
    original = _make_package(nomination)
    from tools.strategy_service_offline.run import FIXTURES
    import json
    fixture = json.loads((FIXTURES / "strategies.json").read_text())[0]
    d = deepcopy(fixture["payload"]["definition"]["definition"])
    d["strategy_id"] = "d_scan_1_synthetic_test"
    definition = StrategyDefinition(d, registry=IndicatorRegistryV2())
    package = DiscoveryCandidatePackageV1.build(**{
        **{k: v for k, v in original._fields_for_digest().items()
           if k not in ("evaluation_status", "scientific_acceptance",
                        "execution_status", "publishable",
                        "delivery_authorized", "holdout_status",
                        "factory_routing")},
        "strategy_spec": definition.to_dict(),
        "strategy_definition_digest": definition.digest,
    })
    return package.to_dict(), nomination.to_dict()


def project(p=None, n=None, **kwargs):
    package, nomination = case()
    if p is not None:
        package = p
    if n is not None:
        nomination = n
    return project_test_only_candidate(
        candidate_package=package, synthetic_nomination=nomination, **kwargs)


def test_synthetic_candidate_to_real_scanner_registry_roundtrip():
    p,n=case()
    plugin,binding=project(p,n)
    assert binding["candidate_package_sha256"]==p["package_digest"]
    assert binding["strategy_definition_sha256"]==p["strategy_definition_digest"]
    assert binding["scanner_plugin_sha256"]==plugin["sha256"]
    assert verify_test_only_candidate_binding(
        candidate_package=p,synthetic_nomination=n,plugin=plugin,binding=binding)
    assert plugin["payload"]["input_origin"]=="DISCOVERER_CANDIDATE"
    assert plugin["payload"]["candidate_sha256"]==p["package_digest"]
    assert plugin["payload"]["policy_status"]=="RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL"
    assert plugin["payload"]["historical_pit"]=="NOT_ATTESTED"
    assert all(plugin["payload"][k] is None for k in (
        "source_ack_sha256","strategy_approval_sha256","factory_consumer_ack_sha256"))
    assert plugin["payload"]["trading_authority"]=="NONE"
    assert binding["f4_historical_connected"] is False
    assert binding["selected"] is False


def test_original_old_simplified_candidate_spec_fails_closed():
    n=_make_evidence()
    p=_make_package(n)
    with pytest.raises(CandidateBridgeError,match="strategy_spec"):
        project(p.to_dict(),n.to_dict())


def test_tampered_candidate_spec_and_resealed_digest_substitution_rejected():
    p,n=case()
    bad=deepcopy(p)
    bad["strategy_spec"]["definition"]["strategy_id"]="hijacked"
    with pytest.raises(CandidateBridgeError,match="sealed"):
        project(bad,n)
    bad=deepcopy(p)
    bad["strategy_definition_digest"]="f"*64
    bad["package_digest"]=__import__("tools.strategy_discoverer_offline.contracts",fromlist=["_digest"])._digest({
        k:v for k,v in bad.items() if k!="package_digest"})
    with pytest.raises(CandidateBridgeError,match="strategy_definition_digest"):
        project(bad,n)


def test_unrelated_candidate_digest_and_unrelated_scanner_receipt_rejected():
    p,n=case()
    plugin,binding=project(p,n)
    wrong=deepcopy(plugin)
    wrong["payload"]["candidate_sha256"]="a"*64
    from tools.strategy_service_offline.common import Frozen
    wrong=Frozen.build(wrong["payload"]).receipt()
    with pytest.raises(CandidateBridgeError,match="binding"):
        verify_test_only_candidate_binding(
            candidate_package=p,synthetic_nomination=n,plugin=wrong,binding=binding)
    other=deepcopy(p)
    other["candidate_id"]="different"
    from tools.strategy_discoverer_offline.contracts import _digest
    other["package_digest"]=_digest({k:v for k,v in other.items() if k!="package_digest"})
    with pytest.raises(CandidateBridgeError,match="binding"):
        verify_test_only_candidate_binding(
            candidate_package=other,synthetic_nomination=n,plugin=plugin,binding=binding)


def test_wrong_nomination_or_historical_evidence_cannot_enter_test_only():
    p,n=case()
    n2=deepcopy(n)
    n2["evidence_class"]="RETROSPECTIVE_NON_PIT_VERIFIED"
    from tools.strategy_discoverer_offline.contracts import _digest
    n2["nomination_digest"]=_digest({k:v for k,v in n2.items() if k!="nomination_digest"})
    with pytest.raises(CandidateBridgeError,match="nomination"):
        project(p,n2)
    with pytest.raises(CandidateBridgeError,match="context"):
        project(p,n,research_context="F4_SIGNED_V2")
    with pytest.raises(CandidateBridgeError,match="context"):
        project(p,n,research_context="OWNER_LOCAL_RECOVERY_DIAGNOSTIC")


def test_unsafe_candidate_flags_holdout_or_source_routing_rejected():
    p,n=case()
    for field,value in (
        ("execution_status","AUTHORIZED"),("holdout_status","OPEN"),
        ("factory_routing","CONNECTED"),("publishable",True),
        ("status","INVALID"),
    ):
        b=deepcopy(p)
        b[field]=value
        from tools.strategy_discoverer_offline.contracts import _digest
        b["package_digest"]=_digest({k:v for k,v in b.items() if k!="package_digest"})
        with pytest.raises(CandidateBridgeError):
            project(b,n)


def test_unverified_registry_indicator_and_changed_definition_source_denied():
    p,n=case()
    invalid=deepcopy(p)
    invalid["strategy_spec"]["definition"]["indicators"][0]["indicator_id"]="NO_SUCH_INDICATOR"
    from tools.strategy_discoverer_offline.contracts import _digest
    invalid["strategy_spec"]["digest"]=_digest(invalid["strategy_spec"]["definition"])
    invalid["strategy_definition_digest"]=invalid["strategy_spec"]["digest"]
    invalid["package_digest"]=_digest({k:v for k,v in invalid.items() if k!="package_digest"})
    with pytest.raises(CandidateBridgeError,match="AST/indicator registry"):
        project(invalid,n)
    plugin,binding=project(p,n)
    b=deepcopy(binding)
    b["source_ack_sha256"]="a"*64
    b["binding_sha256"]=_digest({k:v for k,v in b.items() if k!="binding_sha256"})
    with pytest.raises(CandidateBridgeError,match="binding"):
        verify_test_only_candidate_binding(
            candidate_package=p,synthetic_nomination=n,plugin=plugin,binding=b)


def test_scanner_research_plugin_is_unapproved_without_f4():
    p,n=case()
    plugin,binding=project(p,n)
    definition=p["strategy_spec"]
    unrelated=register_strategy_plugin(
        definition,config_digest=manual_config_digest(definition),
        origin="MANUAL")
    assert unrelated["payload"]["candidate_sha256"] is None
    assert unrelated["payload"]["input_origin"]=="MANUAL"
    assert plugin["payload"]["candidate_sha256"]==p["package_digest"]
    assert binding["holdout_status"]=="SEALED_UNOPENED"
