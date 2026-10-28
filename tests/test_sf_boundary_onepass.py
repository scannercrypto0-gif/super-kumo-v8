"""One batch of falsifiers at the existing synthetic comparison boundary."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from research_wp_r0.factory_exam import FrozenExam, freeze_manifest, freeze_protocol, run_route, compare_routes
from research_wp_r0.factory_exam_example import fixture
from research_wp_r0.frozen_research_plan import commit_research_plan, verify_research_plan
from research_wp_r0.strategy_definition import canonical

ROOT=Path('evidence/factory-consolidated-20261028')


def route(*, unknown=False):
    dna,events,config=fixture()
    if unknown: events[0]['fill_fraction']=None
    m=freeze_manifest(dna,events)
    p=freeze_protocol(m,expected_manifest_digest=m.digest,config=config)
    return run_route(m,p,expected_manifest_digest=m.digest,expected_protocol_digest=p.digest,arm='ALWAYS')


def forged(receipt, change):
    spec=receipt.spec; change(spec); return FrozenExam(canonical(spec))


def test_positive_valid_and_unknown_denominator():
    a=route(); b=route(unknown=True)
    result=compare_routes(a,a).spec
    assert result['left']['scheduled']==8 and result['left']['known']==8
    assert result['conditional_selection_sensitive'] is True
    result=compare_routes(b,b).spec
    assert result['left']['scheduled']==8 and result['left']['unknown']==8
    assert result['left']['ex_ante_policy_mean_per_requested_notional'] is None
    assert result['left']['portfolio']['net_quote'] is None
    assert result['independent_custody']=='NOT_VERIFIED'
    assert result['inference']=='DESCRIPTIVE_SYNTHETIC_NO_P_VALUES_NO_PROMOTION'


@pytest.mark.parametrize('field',['net_quote','net_per_requested_notional','executed_net_return','gross_quote'])
def test_unknown_zero_fill_refused(field):
    a=route(unknown=True)
    bad=forged(a,lambda s:s['outcomes'][0].update({field:0}))
    with pytest.raises(ValueError,match='UNKNOWN'): compare_routes(bad,bad)


@pytest.mark.parametrize('field',['fee_bps','spread_bps','slippage_bps'])
@pytest.mark.parametrize('value',[-1,True,float('nan')])
def test_invalid_cost_at_direct_consumer_refused(field,value):
    a=route()
    # Nonfinite serialization itself must fail; finite bad values reach consumer.
    with pytest.raises(ValueError):
        bad=forged(a,lambda s:s['assumptions'].update({field:value}))
        compare_routes(bad,bad)


@pytest.mark.parametrize('change',[
    lambda s:s['assumptions'].pop('fee_bps'),
    lambda s:s['assumptions'].update(schema='unknown-contract'),
    lambda s:s['assumptions'].update(cost_units='percent-instead-of-bps'),
    lambda s:s['outcomes'].append(deepcopy(s['outcomes'][0])),
    lambda s:s['outcomes'][0].update(status='PENDING'),
    lambda s:s['outcomes'][0].update(status='FAILED'),
    lambda s:s['outcomes'][0].update(status='INVALID'),
    lambda s:s['outcomes'][0].update(status='ABANDONED'),
    lambda s:s['outcomes'][0].update(status='COMPLETE'),
    lambda s:s['outcomes'][0].update(net_per_requested_notional=42),
    lambda s:s['portfolio'].update(unknown_opportunities=1),
    lambda s:s.update(execution='EMPIRICAL_ACCEPTED'),
    lambda s:s.update(independent_custody='VERIFIED'),
    lambda s:s.update(schema='factory-comparison-1'),
    lambda s:s.update(conditional_selection_sensitive=False),
    lambda s:s.update(universe_mean_from_conditional=1),
])
def test_inconsistent_or_promoted_report_refused(change):
    a=route();bad=forged(a,change)
    with pytest.raises(ValueError): compare_routes(bad,bad)


def test_unknown_count_and_halted_coverage_cannot_be_relabelled():
    a=route(unknown=True)
    for change in [lambda s:s['portfolio'].update(unknown_opportunities=0),
                   lambda s:s['portfolio'].update(drawdown_complete=True),
                   lambda s:s['portfolio'].update(final_equity=1000,net_quote=0)]:
        bad=forged(a,change)
        with pytest.raises(ValueError): compare_routes(bad,bad)


def test_unchanged_v1_bytes_hash_and_opaque_rule_is_not_a_route():
    golden=(ROOT/'legacy-plan-v1.json').read_bytes()
    pin=json.loads((ROOT/'legacy-pins.json').read_text())
    assert hashlib.sha256(golden).hexdigest()==pin['plan_sha256']
    plan=verify_research_plan(golden,pin['plan_sha256'])
    raw,h=commit_research_plan(plan['family_id'],[(r['candidate_id'],r['strategy_digest']) for r in plan['candidates']],
        **{k:plan[k] for k in ('protocol_digest','dataset_digest','split_digest','metrics','selection_rule','cost_model','baseline_digest')})
    assert raw==golden and h==pin['plan_sha256']
    assert hashlib.sha256(Path('research_wp_r0/frozen_research_plan.py').read_bytes().replace(b'\r\n',b'\n')).hexdigest()==pin['plan_module_sha256']
    # Legacy opaque selection/cost commitments remain readable, never a ranker.
    with pytest.raises(ValueError): compare_routes(FrozenExam(golden),FrozenExam(golden))


def test_static_inventory_reproduces_pinned_tree():
    from tools.factory_boundary_inventory import inventory
    existing=json.loads((ROOT/'source-inventory.json').read_text())
    assert inventory(existing['commit'])==existing
    assert existing['dynamic_completeness'] is False

def test_overlay_difference_requires_explicit_sensitivity():
    dna, events, config = fixture()
    manifest = freeze_manifest(dna, events)
    left_protocol = freeze_protocol(manifest, expected_manifest_digest=manifest.digest, config=config)
    left = run_route(manifest, left_protocol, expected_manifest_digest=manifest.digest,
                     expected_protocol_digest=left_protocol.digest, arm='ALWAYS')
    right_config = deepcopy(config)
    right_config['overlay'] = {'name': 'MAX_CONCURRENT', 'version': '1', 'max_concurrent': 1}
    right_protocol = freeze_protocol(manifest, expected_manifest_digest=manifest.digest, config=right_config)
    right = run_route(manifest, right_protocol, expected_manifest_digest=manifest.digest,
                      expected_protocol_digest=right_protocol.digest, arm='ALWAYS')
    with pytest.raises(ValueError, match='sensitivity'):
        compare_routes(left, right)
    result = compare_routes(left, right, sensitivity=True).spec
    assert result['comparison_kind'] == 'SENSITIVITY'
    assert result['changed_execution_assumptions'] == ['overlay']
    assert compare_routes(left, left).spec['comparison_kind'] == 'MATCHED_ASSUMPTIONS'
