"""Affected #293 native operational path -> current PKG04, read-only G4 reuse.

Git objects are source only. No G4 producer/accepted scientific test, original
March/April, external market source or owner-host observer is invoked.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tools.research_evidence_gateway.gateway import build, sha, EvidenceStop
from tools.research_evidence_gateway.research import FILES, COMMIT

INTEGRATION = 'c01f526e762a014e5ed84ca3cf695b9d77502ab3'
FACTORY02 = 'ea4ffd5ce278d93588338122ab6ac1af8ec4da26'


def save(path, value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def git(repo,*args):
    return subprocess.check_output(['git','-c','core.autocrlf=false','-c','core.eol=lf','-C',str(repo),*args])


def execute(repo, output, *, fetch=False):
    repo,root=Path(repo).resolve(),Path(output).resolve()
    if root.exists():raise ValueError('ACCEPTANCE_OUTPUT_MUST_BE_NEW')
    root.mkdir(parents=True);driver=root/'pinned-integration-driver';driver.mkdir()
    if fetch:
        for commit in (INTEGRATION,FACTORY02,COMMIT):
            subprocess.run(['git','-C',str(repo),'fetch','--no-tags','origin',commit],check=True)
    driver_hashes={}
    for name in ('atlas_pkg03_stage.py','atlas_pkg03_smoke.py'):
        raw=git(repo,'show',INTEGRATION+':tools/'+name)
        (driver/name).write_bytes(raw);driver_hashes[name]=hashlib.sha256(raw).hexdigest()
    env=os.environ.copy();env.pop('PYTHONPATH',None);env['PYTHONDONTWRITEBYTECODE']='1'
    def run(name,args,cwd):
        process=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,capture_output=True,text=True)
        (root/(name+'.log')).write_text(process.stdout+process.stderr,encoding='utf-8')
        if process.returncode:raise RuntimeError('AFFECTED_NATIVE_COMMAND_FAILED:'+name)
        return process
    if fetch:
        run('fetch-native-source',[str(driver/'atlas_pkg03_stage.py'),str(root/'fetched-source'),
                                  '--repo',str(repo),'--fetch'],repo)
    run('native-producer',[str(driver/'atlas_pkg03_smoke.py'),'--repo',str(repo),
                           '--output',str(root/'native')],repo)
    delivery=json.loads((root/'native/delivery.json').read_text())
    assert delivery['result']['g1_source_unchanged'] is True
    assert delivery['result']['duplicate_fills']==delivery['result']['skipped_commands']==0
    assert [x['returncode'] for x in delivery['processes']]==[0,73,0]
    overlay=root/'native/overlay'
    export_env=env.copy();export_env['PYTHONPATH']=os.pathsep.join((str(overlay/'src'),str(overlay)))
    journal=root/'native/run/simulation.jsonl';before=journal.read_bytes()
    code=('import json,pathlib,sys;from aql.paper_sim.engine import PaperSimulator;'
          'p=pathlib.Path(sys.argv[1]);s=PaperSimulator(p);'
          'pathlib.Path(sys.argv[2]).write_text(json.dumps(list(s.states.values()),sort_keys=True))')
    exported=root/'native-results.json'
    proc=subprocess.run([sys.executable,'-B','-c',code,str(journal),str(exported)],
                         env=export_env,cwd=overlay,capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    assert journal.read_bytes()==before
    inputs=root/'inputs';inputs.mkdir()
    shutil.copyfile(root/'native/run/g2-read.json',inputs/'source.json')
    shutil.copyfile(exported,inputs/'results.json')
    # Persisted PKG02 rows are compared as a separate modeled cohort only.
    raw=git(repo,'show',FACTORY02+':docs/evidence/codex-pkg02/report.json')
    (inputs/'factory.json').write_bytes(raw)
    files={n:sha(json.loads((inputs/n).read_text())) for n in ('source.json','results.json','factory.json')}
    research=dict(schema='aql.gateway.persisted-g4-bundle.v1',source_commit=COMMIT,files={})
    provenance={}
    for name in FILES:
        source_path='.github/atlas_evidence/g4_current_head/'+name
        raw=git(repo,'show',COMMIT+':'+source_path)
        dest=inputs/'g4_current_head'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        research['files'][name]=sha(json.loads(raw))
        provenance[name]=dict(commit=COMMIT,path=source_path,git_blob=git(repo,'rev-parse',COMMIT+':'+source_path).decode().strip(),
                              git_bytes_sha256=hashlib.sha256(raw).hexdigest())
    source=json.loads((inputs/'source.json').read_text());results=json.loads((inputs/'results.json').read_text())
    fixture=Path(__file__).parent/'fixtures/native-current'
    parity={name:sha(json.loads((fixture/name).read_text()))==sha(json.loads((inputs/name).read_text()))
            for name in ('source.json','results.json')}
    for name in FILES:
        parity['g4_current_head/'+name]=sha(json.loads((fixture/'g4_current_head'/name).read_text()))==research['files'][name]
    assert all(parity.values()), 'PERSISTED_FIXTURE_IS_NOT_EXACT_NATIVE_SOURCE'
    save(root/'fixture-provenance-parity.json',parity)
    manifest=dict(schema='aql.research-evidence-gateway.inputs.v1',files=files,run=source['run'],
        as_of_ms=source['as_of_ms'],expected_decisions=len(source['rows']),
        expected_signal_ids=sorted(r['decision']['opportunity_id'] for r in source['rows'] if r['decision']['state']=='ENTRY_SIGNAL'),
        expected_result_signal_ids=sorted(r['signal']['signal_id'] for r in results),
        engine_sha256=results[0]['engine_sha256'],research=research,
        pinned_heads=dict(integration=INTEGRATION,pkg02=FACTORY02,g4_existing=COMMIT,**delivery['pins']))
    save(inputs/'manifest.json',manifest);anchor=sha(manifest)
    (root/'manifest.sha256').write_text(anchor+'\n',encoding='utf-8')
    before_inputs={p.relative_to(inputs).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.rglob('*') if p.is_file()}
    args=['-m','tools.research_evidence_gateway.gateway','--inputs',str(inputs),'--manifest-sha256',anchor]
    for number in (1,2):run('consumer-'+str(number),args+['--output',str(root/('read-model-'+str(number)+'.json'))],repo)
    assert (root/'read-model-1.json').read_bytes()==(root/'read-model-2.json').read_bytes()
    result=json.loads((root/'read-model-1.json').read_text())
    assert result['mature_g2_consumer_seam']=='MATURE_G2_CONSUMER_SEAM_PASS'
    assert result['research']['status']=='RESEARCH_JOIN_PASS'
    assert result['status']=='PASS_READ_ONLY_EVIDENCE_INTEGRATION'
    assert result['pkg02_model_comparison']['rows']==72
    assert result['pkg02_model_comparison']['linked_to_discoverer_trial'] is False
    assert result['evidence_boundary']['actual_fills'] is None
    assert before_inputs=={p.relative_to(inputs).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.rglob('*') if p.is_file()}

    negatives=[]
    def rejection(name,mutation):
        probe=root/('negative-'+name);shutil.copytree(inputs,probe)
        d=json.loads((probe/'source.json').read_text());r=json.loads((probe/'results.json').read_text())
        mutation(d,r)
        for row in d['rows']:row['decision_sha256']=sha(row['decision'])
        d['visible_sha256']=sha(d['rows']);d['sha256']=sha({k:v for k,v in d.items() if k!='sha256'})
        save(probe/'source.json',d);save(probe/'results.json',r)
        m=deepcopy(manifest);m['files'].update({'source.json':sha(d),'results.json':sha(r)});save(probe/'manifest.json',m)
        try:build(probe,sha(m))
        except EvidenceStop as exc:negatives.append(dict(case=name,code=str(exc),status='REJECTED'))
        else:raise AssertionError('AFFECTED_NEGATIVE_ACCEPTED:'+name)
    def horizon(d):return next(h for r in d['rows'] for h in r['horizons'] if h['state']=='mature')
    for name,mutation in (
        ('wrong_receipt',lambda d,r:horizon(d)['evidence']['parent'].update(g1_receipt_sha256='0'*64)),
        ('future_horizon',lambda d,r:horizon(d)['evidence'].update(recorded_ms=d['as_of_ms']+1)),
        ('fake_maturity',lambda d,r:horizon(d).update(state='missing')),
        ('fake_PNL',lambda d,r:r[0].update(net_pnl='999')),
        ('fake_fill',lambda d,r:r[0]['fills'][0].update(liquidity='REAL_FILL')),
        ('fake_ACK',lambda d,r:r[0].update(source_ack_sha256='0'*64)),
        ('fake_PIT',lambda d,r:d.update(historical_pit='ATTESTED')),
        ('trading',lambda d,r:r[0].update(trading_authority='LIVE')),
    ):rejection(name,mutation)
    save(root/'negative-receipts.json',negatives)
    body=dict(schema='aql.pkg04.final-consumer-fix-receipt.v1',
        mature_g2_consumer_seam='MATURE_G2_CONSUMER_SEAM_PASS',research_join='RESEARCH_JOIN_PASS',
        research_scope='PERSISTED_ACCEPTED_SYNTHETIC_RECEIPTS_AND_PARENT_DIGESTS_ONLY',
        read_model_sha256=result['sha256'],input_manifest_sha256=anchor,
        actual_native_delivery_sha256=delivery['sha256'],native_overlay_sha256=delivery['combined_overlay_sha256'],
        integration_pin=INTEGRATION,native_driver_sha256=driver_hashes,
        accepted_g4_source_files=provenance,accepted_g4_executed=False,
        persisted_fixture_matches_actual_native_and_git_bytes=parity,
        decisions=result['decision_counts'],horizons=result['horizon_counts'],denominators=result['denominators'],
        pkg02_model_comparison=result['pkg02_model_comparison'],
        fresh_process_replay='BYTE_IDENTICAL',input_bytes_unchanged=True,durable_producer_bytes_unchanged=True,
        assumed_fill_count=sum(o.get('modeled_fill_count',0) for o in result['objects']),actual_fills=None,
        negative_rejections=negatives,observer_accessed=False,original_data_run=False,
        merge=False,trading_authority='NONE',G0='NOT_APPROVED',
        final_integrated_release='PENDING_INTEGRATION_271_NOT_SELF_AWARDED')
    receipt={**body,'sha256':sha(body)};save(root/'acceptance-receipt.json',receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fetch',action='store_true')
    a=parser.parse_args();r=execute(a.repo,a.output,fetch=a.fetch)
    print(json.dumps({k:r[k] for k in ('mature_g2_consumer_seam','research_join','read_model_sha256','sha256')},sort_keys=True))
