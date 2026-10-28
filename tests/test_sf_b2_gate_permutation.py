"""B2 independent gate-score perturbation, no empirical inference."""
import pytest
from research_wp_r0.factory_b2_counterfactual import FAMILIES,gate_permutation_falsifier

@pytest.mark.parametrize("family",FAMILIES)
def test_invert_gate_changes_policy_not_always_prices_or_manifest_input(family):
    receipt=gate_permutation_falsifier(family)
    assert receipt["design"]=="FIXED_PRICES_INVERT_REGIME_SCORE_ONLY"
    assert receipt["base_manifest"]!=receipt["permuted_manifest"]
    assert receipt["original_always_net"]==receipt["inverted_always_net"]
    assert receipt["regime_net_change"] is not None
    assert abs(receipt["regime_net_change"])>0.01
    assert receipt["original_gate_executed"]==3 if family=="TREND_FOLLOWING" else receipt["original_gate_executed"]==2
    assert receipt["note"]=="SYNTHETIC_SELECTION_SENSITIVITY_ONLY_NOT_PREDICTIVE_SKILL"
