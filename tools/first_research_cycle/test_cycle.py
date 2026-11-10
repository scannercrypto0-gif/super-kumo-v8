"""New intake seam only. No accepted G4 or market-data evaluation rerun."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pytest
from aql.models.bar import MarketBar
from tools.first_research_cycle.cycle import assess,inspect_actual,read,sha,Stop

DESIGN=read(Path(__file__).with_name('design.json'))


def simulated_input(root):
    """Contract test bytes, NEVER a real-market evidence fixture/substitution."""
    root.mkdir()
    bars=[MarketBar('TEST','15m',i*900000,i*900000+899999,100.,102.,99.,101.,4.,True,
                    'SIMULATED_INTAKE_TEST',i*900000+900000).with_checksum().to_dict() for i in range(4)]
    (root/'bars.json').write_text(json.dumps(bars));(root/'terms.txt').write_text('SIMULATED TEST TERMS; not real provider rights')
    source=dict(schema='aql.first-cycle.source-export.v1',evidence_class='ACTUAL_MARKET',cohort='SIMULATED_INTAKE_TEST',
        market='SPOT',symbol='TEST',interval='15m',step_ms=900000,source_label='SIMULATED_INTAKE_TEST',
        trading_authority='NONE',actual_fills=None,ack=None,historical_pit='NOT_ATTESTED',real_oos='NOT_ATTESTED',
        rights=dict(authorized_research_use=True,reference='TEST_ONLY',terms_sha256=hashlib.sha256((root/'terms.txt').read_bytes()).hexdigest()),
        bars_sha256=sha(bars),first_open_ms=0,last_open_ms=2700000,expected_bars=4,
        prefreeze_ms=0,evaluation_read_at_ms=1,plan_frozen_before_evaluation=True,
        first_outcome_available_ms=900000,train_end_ms=900000,validation_end_ms=1800000,
        holdout_start_ms=261000000,holdout_end_ms=262000000,as_of_ms=3600000)
    return source,bars


def save(root,source,bars):
    source['bars_sha256']=sha(bars)
    (root/'bars.json').write_text(json.dumps(bars));(root/'source.json').write_text(json.dumps(source))
    return sha(source)


def test_missing_data_does_not_become_engineering_pass():
    result=assess(DESIGN)
    assert result['status']=='BLOCKED_EXACT_DATA_RUNTIME_DEPENDENCY'
    assert result['blocker']=='AUTHORIZED_NEW_ACTUAL_MARKET_BUNDLE'
    assert result['gates']['F2']['status']==result['gates']['F3']['status']==result['gates']['F4']['status']=='NOT_RUN'
    assert all(v is None for v in result['populations'].values())
    assert not result['actual_market_cycle_executed']


def test_native_structure_and_plan_is_not_actual_execution(tmp_path):
    root=tmp_path/'input';s,b=simulated_input(root);anchor=save(root,s,b)
    before={p.name:p.read_bytes() for p in root.iterdir()}
    r=assess(DESIGN,source=root,anchor=anchor)
    assert r['source']['bars']==4
    assert r['source']['status']=='STRUCTURAL_CHECK_ONLY_NOT_AUTHENTICATED'
    assert r['status']=='BLOCKED_EXACT_DATA_RUNTIME_DEPENDENCY'
    assert r['blocker']=='ACTUAL_MARKET_RUNTIME_ADAPTER_NOT_YET_PROVED'
    assert before=={p.name:p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize('mutate',[
    lambda s,b:s.update(evidence_class='SYNTHETIC_TESTED'),
    lambda s,b:s['rights'].update(authorized_research_use=False),
    lambda s,b:s['rights'].update(terms_sha256='0'*64),
    lambda s,b:s.update(plan_frozen_before_evaluation=False),
    lambda s,b:s.update(holdout_start_ms=1800001),
    lambda s,b:s.update(real_oos='VERIFIED'),
    lambda s,b:s.update(historical_pit='PIT'),
    lambda s,b:s.update(actual_fills=1),
    lambda s,b:s.update(ack='ACCEPTED'),
    lambda s,b:s.update(trading_authority='LIVE'),
    lambda s,b:b.pop(),
    lambda s,b:b.append(deepcopy(b[0])),
    lambda s,b:b[1].update(bar_open=0),
    lambda s,b:b[0].update(is_final=False),
    lambda s,b:b[0].update(high=999),
    lambda s,b:b[0].update(symbol='SWAPPED'),
    lambda s,b:s.update(as_of_ms=1),
    lambda s,b:s.update(last_open_ms=10**30),
])
def test_adversarial_input_rejected(tmp_path,mutate):
    root=tmp_path/'input';s,b=simulated_input(root);mutate(s,b);anchor=save(root,s,b)
    with pytest.raises((Stop,ValueError)):inspect_actual(root,anchor,DESIGN)


def test_source_anchor_tamper(tmp_path):
    root=tmp_path/'input';s,b=simulated_input(root);save(root,s,b)
    with pytest.raises(Stop,match='SOURCE_TRUST_ANCHOR'):inspect_actual(root,'0'*64,DESIGN)


def test_adaptive_plan_change_rejected():
    d=deepcopy(DESIGN);d['strategy_sha256']='0'*64
    with pytest.raises(Stop,match='FROZEN_DESIGN_PIN'):assess(d)


def test_owner_override_is_required_for_accepted_cohort(tmp_path):
    root=tmp_path/'input';s,b=simulated_input(root);s['cohort']='MARCH_2024';anchor=save(root,s,b)
    prior=deepcopy(DESIGN);prior.pop('accepted_period_reuse')
    with pytest.raises(Stop,match='ACCEPTED_COHORT_WITHOUT_OWNER_OVERRIDE'):inspect_actual(root,anchor,prior)
    # Only structural test, no original market bytes or previous suite executed.
    assert inspect_actual(root,anchor,DESIGN)['status']=='STRUCTURAL_CHECK_ONLY_NOT_AUTHENTICATED'


@pytest.mark.parametrize('raw',['{','{"a":1,"a":2}','NaN'])
def test_corruption(tmp_path,raw):
    path=tmp_path/'bad.json';path.write_text(raw)
    with pytest.raises(Stop):read(path)


def test_fresh_process_and_restart_exclusive_write(tmp_path):
    cmd=[sys.executable,'-B','-m','tools.first_research_cycle.cycle','--output']
    a,b=tmp_path/'a.json',tmp_path/'b.json'
    for p in (a,b):subprocess.run(cmd+[str(p)],check=True,capture_output=True)
    assert a.read_bytes()==b.read_bytes()
    # Simulates interrupted caller before ACK: retry cannot replace committed receipt.
    before=a.read_bytes()
    assert subprocess.run(cmd+[str(a)],capture_output=True).returncode==2
    assert a.read_bytes()==before
