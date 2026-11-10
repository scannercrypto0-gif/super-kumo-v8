"""New actual-market adapter contract tests on declared simulated archives.

Actual authorized May/June run receipts are separate; no private payload in CI.
"""
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest
from tools.first_research_cycle.market_cycle import canonical,sha,load_archives


def fixture(root):
    root.mkdir();plan=json.loads(Path(__file__).with_name('market-plan.json').read_text())
    start=plan['first_open_ms'];data=[]
    for i in range(640):
        price=100+(i%32 if i%64<32 else 64-i%64)
        data.append([start+i*900000,str(price),str(price+1),str(price-1),str(price),'4',start+i*900000+899999,'0','1','0','0','0'])
    stream=io.StringIO();csv.writer(stream,lineterminator='\n').writerows(data)
    name='SIMULATED-ADAPTER-TEST.zip';p=root/name
    with zipfile.ZipFile(p,'w') as z:
        info=zipfile.ZipInfo(name[:-4]+'.csv',date_time=(2024,5,1,0,0,0));info.create_system=3
        z.writestr(info,stream.getvalue())
    digest=hashlib.sha256(p.read_bytes()).hexdigest();(root/(name+'.CHECKSUM')).write_text(digest+'  '+name)
    plan.update(source_class='SIMULATED_ADAPTER_TEST',archives=[dict(name=name,sha256=digest,rows=640)],expected_bars=640,
        train_end_ms=start+96*900000,validation_end_ms=start+192*900000,
        holdout_start_ms=start+480*900000,end_exclusive_ms=start+640*900000)
    return plan


def test_native_zip_grid_and_checksum(tmp_path):
    plan=fixture(tmp_path/'source');bars,proof=load_archives(tmp_path/'source',plan)
    assert len(bars)==640 and proof[0]['rows']==640


def test_changed_original_bytes_rejected(tmp_path):
    source=tmp_path/'source';plan=fixture(source)
    (source/plan['archives'][0]['name']).write_bytes(b'wrong source')
    with pytest.raises(ValueError,match='SOURCE_SHA_SWAP'):load_archives(source,plan)


@pytest.mark.parametrize('key,value',[('expected_bars',639),('first_open_ms',0)])
def test_missing_or_swapped_population(tmp_path,key,value):
    source=tmp_path/'source';plan=fixture(source);plan[key]=value
    with pytest.raises(ValueError):load_archives(source,plan)


def invoke(source,plan,out,*,crash=False):
    path=out.parent/(out.name+'-plan.json');path.write_bytes(canonical(plan));path.with_suffix('.sha256').write_text(sha(plan))
    deps=os.environ.get('CYCLE_DEPS')
    assert deps,'CYCLE_DEPS must point to separately staged immutable source snapshots'
    cmd=[sys.executable,'-B',str(Path(__file__).with_name('market_cycle.py')),'--source',str(source),
         '--deps',deps,'--output',str(out),'--plan',str(path)]
    if crash:cmd.append('--crash-after-commit')
    return subprocess.run(cmd,capture_output=True,text=True)


def test_joined_native_replay_and_crash(tmp_path):
    source=tmp_path/'source';plan=fixture(source)
    before={p.name:p.read_bytes() for p in source.iterdir()}
    a,b,c=[tmp_path/n for n in ('a','b','crash')]
    for out in (a,b):
        r=invoke(source,plan,out);assert r.returncode==0,r.stdout+r.stderr
    assert (a/'result.json').read_bytes()==(b/'result.json').read_bytes()
    result=json.loads((a/'result.json').read_text())
    assert result['status']=='PASS_ADAPTER_SIMULATION_ONLY'
    assert result['populations']['scanner_slots']==640
    assert result['actual_fills'] is None and result['trading_authority']=='NONE'
    if os.environ.get('CYCLE_EXPORT_RECEIPT'):
        Path(os.environ['CYCLE_EXPORT_RECEIPT']).write_bytes((a/'result.json').read_bytes())
    r=invoke(source,plan,c,crash=True);assert r.returncode==73,r.stdout+r.stderr
    r=invoke(source,plan,c);assert r.returncode==0,r.stdout+r.stderr
    assert (c/'result.json').read_bytes()==(a/'result.json').read_bytes()
    r=invoke(source,plan,c);assert r.returncode==0,r.stdout+r.stderr
    assert before=={p.name:p.read_bytes() for p in source.iterdir()}
    # Native ledger corruption must stop recovery, never omit the failed attempt.
    (c/'discoverer-ledger.json').write_text('[]')
    r=invoke(source,plan,c);assert r.returncode==2 and 'CORRUPT_OR_MISSING_LEDGER' in r.stdout
    # A different valid-looking candidate source is rejected by immutable package/store identity.
    changed=deepcopy(plan);changed['strategy']['digest']='0'*64
    r=invoke(source,changed,c);assert r.returncode!=0


def test_source_output_collision_has_no_side_effects(tmp_path):
    source=tmp_path/'source';plan=fixture(source)
    before={p.name:p.read_bytes() for p in source.iterdir()}
    r=invoke(source,plan,source/'forbidden-output')
    assert r.returncode==2 and not (source/'forbidden-output').exists()
    assert before=={p.name:p.read_bytes() for p in source.iterdir()}


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(real_pit='ATTESTED'),lambda p:p.update(holdout='OPENED'),
    lambda p:p.update(trading_authority='LIVE'),lambda p:p.update(winner='C'),
    lambda p:p.update(holdout_start_ms=p['validation_end_ms']+1),
    lambda p:p.update(source_class='SYNTHETIC_FIXTURE_ONLY'),
    lambda p:p.update(actual_fills=1),lambda p:p.update(ack='FAKE'),lambda p:p.update(claimed_pnl='999'),
])
def test_joined_authority_and_temporal_negatives(tmp_path,mutation):
    source=tmp_path/'source';plan=fixture(source);mutation(plan)
    r=invoke(source,plan,tmp_path/'out');assert r.returncode==2
