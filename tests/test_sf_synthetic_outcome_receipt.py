"""NO_FILL and REGIME_ABSTAIN distinct from UNKNOWN under fixed universe."""
import copy
from research_wp_r0.factory_exam_example import fixture
from research_wp_r0.synthetic_outcome_receipt import evaluate_synthetic_outcomes

def test_no_fill_abstain_and_unknown_are_distinct_and_denominator_retained():
    dna, events, cfg = fixture()
    events=copy.deepcopy(events)
    events[0]["fill_fraction"]=0
    events[1]["features"]=None
    receipt=evaluate_synthetic_outcomes(dna,events,cfg)
    assert receipt["scheduled"]==len(events)==8
    a=receipt["always"]["outcomes"]
    b=receipt["regime"]["outcomes"]
    assert len(a)==len(b)==8
    assert a[0]["status"]=="NO_FILL"
    assert a[1]["status"]=="UNKNOWN" and a[1]["reason"]=="NOT_SUPPLIED"
    assert b[1]["status"]=="UNKNOWN"
    assert any(x["reason"]=="REGIME_ABSTAIN" for x in b)
    assert receipt["comparison"]["left"]["scheduled"]==8
    assert receipt["comparison"]["right"]["scheduled"]==8
