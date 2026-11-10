from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from tools.research_evidence_gateway.gateway import build,sha,EvidenceStop

FIXTURE=Path(__file__).parent/'fixtures'
ANCHOR=(FIXTURE/'manifest.sha256').read_text().strip()


def mutable(tmp_path):
    p=tmp_path/'inputs';shutil.copytree(FIXTURE,p)
    return p


def change(p,name,fn,reseal=False):
    obj=json.loads((p/name).read_text());fn(obj)
    if reseal and name=='source.json':
        for row in obj['rows']:
            row['decision_sha256']=sha(row['decision'])
        obj['visible_sha256']=sha(obj['rows'])
        obj['sha256']=sha({k:v for k,v in obj.items() if k!='sha256'})
    (p/name).write_text(json.dumps(obj))
    m=json.loads((p/'manifest.json').read_text());m['files'][name]=sha(obj)
    (p/'manifest.json').write_text(json.dumps(m))
    return sha(m)


def test_positive_preserves_denominators_and_unknown():
    r=build(FIXTURE,ANCHOR)
    assert r['decision_counts']=={'UNKNOWN':3,'ENTRY_SIGNAL':1}
    assert r['denominators']['scanner_decisions']==4
    assert r['denominators']['discoverer_attempts'] is None
    assert r['horizon_counts']['pending']==3
    assert r['status']=='BLOCKED_ONE_EXACT_SEAM'
    assert r['evidence_boundary']['actual_fills'] is None


def test_missing_horizons_are_explicit(tmp_path):
    p=mutable(tmp_path)
    anchor=change(p,'source.json',lambda s:s['rows'][-1].update(horizons=[]),True)
    assert build(p,anchor)['horizon_counts']['NOT_AVAILABLE']==3


@pytest.mark.parametrize('mutation',[
    lambda r:r.append(deepcopy(r[0])),
    lambda r:r.clear(),
    lambda r:r[0]['signal'].update(source_sha256='0'*64),
    lambda r:r[0]['signal'].update(definition_sha256='0'*64),
    lambda r:r[0]['signal'].update(evaluator_sha256='0'*64),
    lambda r:r[0].update(engine_sha256='0'*64),
    lambda r:r[0].update(source_ack_sha256='0'*64),
    lambda r:r[0].update(actual_fills=2),
    lambda r:r[0].update(historical_pit='VERIFIED'),
    lambda r:r[0]['fills'][0].update(liquidity='REAL_FILL'),
    lambda r:r[0].update(phase='UNKNOWN',net_pnl='9'),
    lambda r:r[0].update(phase='NO_FILL'),
])
def test_negative_result_lineage_and_authority(tmp_path,mutation):
    p=mutable(tmp_path);anchor=change(p,'results.json',mutation)
    with pytest.raises(EvidenceStop):build(p,anchor)


@pytest.mark.parametrize('mutation',[
    lambda s:s['rows'].append(deepcopy(s['rows'][0])),
    lambda s:s['rows'][0]['decision']['parent'].update(content_sha256='broken'),
    lambda s:s['rows'][0]['decision']['run'].update(config_sha256='0'*64),
    lambda s:s.update(as_of_ms=0),
    lambda s:s['rows'][-1]['horizons'][0].update(state='mature'),
    lambda s:s['rows'][0]['decision'].update(state='NO_SIGNAL',opportunity_id='0'*64),
])
def test_negative_source(tmp_path,mutation):
    p=mutable(tmp_path);anchor=change(p,'source.json',mutation,True)
    with pytest.raises(EvidenceStop):build(p,anchor)


def test_tamper_cannot_reanchor_itself(tmp_path):
    p=mutable(tmp_path);change(p,'results.json',lambda r:r[0].update(net_pnl='999'))
    with pytest.raises(EvidenceStop,match='MANIFEST_TRUST_ANCHOR'):build(p,ANCHOR)


@pytest.mark.parametrize('raw',['{','{"x":1,"x":2}','NaN'])
def test_corrupt_duplicate_key_nonfinite(tmp_path,raw):
    p=mutable(tmp_path);(p/'source.json').write_text(raw)
    with pytest.raises(EvidenceStop):build(p,ANCHOR)


def test_fresh_process_replay_and_no_side_effects(tmp_path):
    before={p.name:p.read_bytes() for p in FIXTURE.iterdir()}
    command=[sys.executable,'-B','-m','tools.research_evidence_gateway.gateway',
             '--inputs',str(FIXTURE),'--manifest-sha256',ANCHOR]
    a,b=tmp_path/'a.json',tmp_path/'b.json'
    for dest in (a,b):subprocess.run(command+['--output',str(dest)],check=True,capture_output=True)
    assert a.read_bytes()==b.read_bytes()
    assert subprocess.run(command+['--output',str(a)],capture_output=True).returncode==2
    assert subprocess.run(command+['--output',str(FIXTURE/'out.json')],capture_output=True).returncode==2
    assert before=={p.name:p.read_bytes() for p in FIXTURE.iterdir()}


def test_no_rights_known_at_or_real_oos_invented():
    e=build(FIXTURE,ANCHOR)['evidence_boundary']
    assert e['rights']==e['known_at']==e['real_oos']=='NOT_ATTESTABLE'
