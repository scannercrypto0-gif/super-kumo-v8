"""Affected native consumer seam only; never rerun accepted G4 producers."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from tools.research_evidence_gateway.gateway import build, sha, EvidenceStop

FIXTURE = Path(__file__).parent/'fixtures/native-current'
ANCHOR = (FIXTURE/'manifest.sha256').read_text().strip()


def mutable(tmp_path):
    dest=tmp_path/'native';shutil.copytree(FIXTURE,dest);return dest


def sealed(obj,key='sha256'):
    obj[key]=sha({k:v for k,v in obj.items() if k!=key})


def update(root,name,fn):
    manifest=json.loads((root/'manifest.json').read_text())
    path=root/name
    obj=json.loads(path.read_text());fn(obj)
    if name=='source.json':
        for row in obj['rows']:
            row['decision_sha256']=sha(row['decision'])
        obj['visible_sha256']=sha(obj['rows']);sealed(obj)
    if name=='g4_current_head/closeout.json':
        sealed(obj['generation'],'receipt_sha256')
        sealed(obj['trial']);obj['variant_registry']['result_sha256']=obj['trial']['sha256']
        sealed(obj['variant_registry']);sealed(obj)
    if name=='g4_current_head/frozen-v2/proposal.json':sealed(obj,'proposal_sha256')
    if name=='g4_current_head/frozen-v2/registration.json':sealed(obj)
    path.write_text(json.dumps(obj),encoding='utf-8')
    if name.startswith('g4_current_head/'):
        manifest['research']['files'][name[len('g4_current_head/'):]]=sha(obj)
    else:manifest['files'][name]=sha(obj)
    (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return sha(manifest)


def mature(source):
    return next(h for row in source['rows'] for h in row['horizons'] if h['state']=='mature')


def test_actual_current_native_export_and_persisted_accepted_join():
    report=build(FIXTURE,ANCHOR)
    assert report['status']=='PASS_READ_ONLY_EVIDENCE_INTEGRATION'
    assert report['mature_g2_consumer_seam']=='MATURE_G2_CONSUMER_SEAM_PASS'
    assert report['horizon_counts']=={'mature':4,'UNKNOWN':1,'pending':58,'NOT_AVAILABLE':0}
    assert report['decision_counts']=={'UNKNOWN':3,'ENTRY_SIGNAL':21}
    assert report['denominators']==dict(scanner_decisions=24,scanner_signals=21,modeled_results=1,
                                       discoverer_attempts=3,factory_trials=1,factory_variants=10)
    r=report['research']
    assert r['status']=='RESEARCH_JOIN_PASS'
    assert r['generation_states']=={'INVALID':1,'FAILED':1,'COMPLETE':1}
    assert (r['modeled_trade_outcomes'],r['unknown_signal_slots'],r['unknown_trade_outcomes'])==(45,91,9)
    assert r['source_commit']=='7b6c8d82ca8111f5fa15dee5e6823bc39289b48c'
    assert r['scientific_acceptance']=='NOT_GRANTED' and r['actual_fills'] is None
    assert report['evidence_boundary']['actual_fills'] is None
    assert sum(x.get('modeled_fill_count',0) for x in report['objects'])==2


def test_missing_native_state_keeps_none_value_and_distinct_status(tmp_path):
    root=mutable(tmp_path)
    def missing(s):
        h=mature(s);p=s['rows'][-1]['decision']['parent']
        assert p['close_ms']>=h['due_ms']+900000
        h.update(state='missing');h['evidence'].update(state='missing',value=None,parent=deepcopy(p),recorded_ms=s['as_of_ms'])
    anchor=update(root,'source.json',missing)
    r=build(root,anchor)
    assert r['horizon_counts']['missing']==1 and r['horizon_counts']['mature']==3
    assert any(o['record_type']=='horizon' and o['status']=='missing' and o['g1_receipt_sha256'] for o in r['objects'])


def test_late_native_status_is_not_silently_mature_or_unknown(tmp_path):
    root=mutable(tmp_path)
    # A targeted helper test avoids rewriting unrelated opportunity population;
    # the new late parent must still be an independently supplied source parent.
    from tools.research_evidence_gateway.gateway import native_horizon
    s=json.loads((root/'source.json').read_text());h=mature(s)
    d=next(r['decision'] for r in s['rows'] if r['decision']['opportunity_id']==h['evidence']['opportunity_id'])
    h['state']='late';h['evidence']['state']='late';h['evidence']['value']=None
    p=h['evidence']['parent'];p['commit_ms']=p['close_ms']+5001
    h['evidence']['recorded_ms']=p['commit_ms']
    assert native_horizon(h,d,s['run'],s['as_of_ms'],{p['key']:p})=='late'


@pytest.mark.parametrize('mutation',[
    lambda h:h['evidence']['run'].update(evaluator_sha256='0'*64),
    lambda h:h['evidence'].update(decision_key='BTCUSDT:15m:0'),
    lambda h:h['evidence'].update(opportunity_id='0'*64),
    lambda h:h['evidence'].update(horizon_ms=86400000),
    lambda h:h['evidence'].update(due_ms=0),
    lambda h:h['evidence'].update(recorded_ms=999999999),
    lambda h:h['evidence'].update(recorded_ms=0),
    lambda h:h['evidence']['parent'].update(g1_receipt_sha256='0'*64),
    lambda h:h['evidence']['parent'].update(content_sha256='0'*64),
    lambda h:h['evidence']['parent'].update(bar_checksum='0'*64),
    lambda h:h['evidence']['parent'].update(is_final=False),
    lambda h:h['evidence']['parent'].update(close_ms=True),
    lambda h:h['evidence']['parent'].update(open_ms=1),
    lambda h:h['evidence'].update(value=None),
    lambda h:h['evidence'].update(value='NaN'),
    lambda h:h['evidence'].update(value='0'),
    lambda h:h['evidence'].update(value='Infinity'),
    lambda h:h.update(state='missing'),
    lambda h:(h.update(state='missing'),h['evidence'].update(state='missing',value=None)),
    lambda h:h.update(state='UNKNOWN'),
    lambda h:h.update(state='pending'),
    lambda h:h['evidence'].update(source_ack_sha256='0'*64),
    lambda h:h['evidence'].update(trading_authority='LIVE'),
    lambda h:h['evidence'].update(historical_pit='VERIFIED'),
])
def test_resealed_native_semantic_swaps_rejected(tmp_path,mutation):
    root=mutable(tmp_path);anchor=update(root,'source.json',lambda s:mutation(mature(s)))
    with pytest.raises(EvidenceStop):build(root,anchor)


@pytest.mark.parametrize('mutation',[
    lambda c:c['trial']['records'].pop(next(iter(c['trial']['records']))),
    lambda c:c['variant_registry']['attempts'].pop(),
    lambda c:c['variant_registry']['attempts'].append(deepcopy(c['variant_registry']['attempts'][0])),
    lambda c:c['variant_registry'].update(parent_receipt_sha256='0'*64),
    lambda c:c['generation'].update(candidate_proposal_sha256='0'*64),
    lambda c:c['generation'].update(candidate_package_sha256='0'*64),
    lambda c:c['generation'].update(discoverer_checkpoint_sha256='0'*64),
    lambda c:c['generation']['discoverer_attempt_census'].update(FAILED=0),
    lambda c:c['generation']['factory_attempt_states'].update(FAILED=0),
    lambda c:c['variant_registry']['attempts'][0].update(source_receipt_sha256='0'*64),
    lambda c:c['trial']['records'][next(iter(c['trial']['records']))].update(attempt='different-trial'),
    lambda c:c['trial']['registry'].update(head_digest='0'*64),
    lambda c:c['trial']['registry']['by_state'].update(FAILED=1),
    lambda c:c['trial']['records'][next(iter(c['trial']['records']))]['hashes'].pop('result_sha256'),
    lambda c:c['trial']['paired']['train'].update(paired_modeled_outcomes=999),
    lambda c:c['variant_registry'].update(actual_fills=1),
    lambda c:c['variant_registry'].update(strategy_performance_accepted=True),
    lambda c:c['variant_registry'].update(source_ack_sha256='0'*64),
])
def test_resealed_research_semantic_missing_duplicate_parent_authority(tmp_path,mutation):
    root=mutable(tmp_path);anchor=update(root,'g4_current_head/closeout.json',mutation)
    with pytest.raises(EvidenceStop):build(root,anchor)


@pytest.mark.parametrize('name,mutation',[
    ('frozen-v2/proposal.json',lambda d:d.update(candidate_id='foreign-candidate')),
    ('frozen-v2/proposal.json',lambda d:d.update(strategy_definition_sha256='0'*64)),
    ('frozen-v2/registration.json',lambda d:d['dependency_heads'].update(discoverer='0'*40)),
    ('frozen-v2/checkpoint.json',lambda d:d['entries'].pop()),
    ('registry.json',lambda d:d.pop()),
    ('registry.json',lambda d:d.append(deepcopy(d[-1]))),
    ('frozen-v2/originals.json',lambda d:d['search_plan'].update(plan_digest='0'*64)),
])
def test_native_persisted_research_parent_swaps(tmp_path,name,mutation):
    root=mutable(tmp_path);anchor=update(root,'g4_current_head/'+name,mutation)
    with pytest.raises(EvidenceStop):build(root,anchor)


def test_research_absence_does_not_reopen_mature_defect(tmp_path):
    root=mutable(tmp_path);m=json.loads((root/'manifest.json').read_text());m.pop('research')
    (root/'manifest.json').write_text(json.dumps(m))
    r=build(root,sha(m))
    assert r['mature_g2_consumer_seam']=='MATURE_G2_CONSUMER_SEAM_PASS'
    assert r['research']['blocker']=='PERSISTED_DISCOVERER_FACTORY_JOIN_NOT_AVAILABLE'
    assert r['denominators']['discoverer_attempts'] is None


def test_claimed_research_bundle_with_missing_bytes_rejects(tmp_path):
    root=mutable(tmp_path);(root/'g4_current_head/frozen-v2/checkpoint.json').unlink()
    with pytest.raises(EvidenceStop,match='MISSING_OR_LINKED_ARTIFACT'):build(root,ANCHOR)


def test_native_join_two_fresh_processes_deterministic_and_byte_isolated(tmp_path):
    before={p.relative_to(FIXTURE).as_posix():p.read_bytes() for p in FIXTURE.rglob('*') if p.is_file()}
    args=[sys.executable,'-B','-m','tools.research_evidence_gateway.gateway','--inputs',str(FIXTURE),
          '--manifest-sha256',ANCHOR]
    a,b=tmp_path/'native-a.json',tmp_path/'native-b.json'
    for output in (a,b):subprocess.run(args+['--output',str(output)],capture_output=True,check=True)
    assert a.read_bytes()==b.read_bytes()
    assert before=={p.relative_to(FIXTURE).as_posix():p.read_bytes() for p in FIXTURE.rglob('*') if p.is_file()}


@pytest.mark.parametrize('mutation',[
    lambda r:r[0].update(net_pnl='999'),
    lambda r:r[0].update(cash='999'),
    lambda r:r[0].update(fees='0'),
    lambda r:r[0]['fills'].append(deepcopy(r[0]['fills'][0])),
    lambda r:r[0]['fills'][0].update(qty='NaN'),
    lambda r:r[0]['fills'][0].update(received_ms=999999999),
    lambda r:r[0]['fills'][0].update(execution_ms=None),
    lambda r:r[0]['fills'][0].update(assumed_execution_window=[0,0]),
    lambda r:r[0].update(updated_ms=999999999),
    lambda r:r[0].update(phase='ARMED'),
])
def test_resealed_fake_modeled_accounting_and_future_fills(tmp_path,mutation):
    root=mutable(tmp_path);anchor=update(root,'results.json',mutation)
    with pytest.raises(EvidenceStop):build(root,anchor)
