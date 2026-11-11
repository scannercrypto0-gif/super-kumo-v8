"""Joined new-workload acceptance; never rerun the accepted research cycle."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import pytest

from tools.research_capacity_scale.contracts import make_plan,validate,freeze,canonical,sealed
from tools.research_capacity_scale.dependencies import install,kernel_identity,activate,git,PINS
from tools.research_capacity_scale.runtime import run,catalog,restore_checkpoint,save,closed_checkpoint
from research_wp_r0.aql_factory_e_research_results_store_v1 import digest

REPO=Path(__file__).resolve().parents[3]

@pytest.fixture(scope='session')
def deps(tmp_path_factory):
    path=Path(os.environ.get('CAPACITY_DEPS',tmp_path_factory.mktemp('deps')))
    if not (path/'pins.json').exists():install(REPO,path)
    activate(path);return path

@pytest.fixture(scope='session')
def hashes():return kernel_identity(REPO)

def cli(root,plan,deps,workers=1,crash=None):
    p=root.parent/(root.name+'.plan.json');freeze(p,plan)
    cmd=[sys.executable,'-B','-m','tools.research_capacity_scale','run','--plan',str(p),'--root',str(root),'--deps',str(deps),'--workers',str(workers)]
    if crash:cmd+=['--crash',crash]
    env={**os.environ,'PYTHONPATH':os.pathsep.join((str(REPO/'src'),str(REPO))),'PYTHONDONTWRITEBYTECODE':'1'}
    return subprocess.run(cmd,cwd=REPO,env=env,capture_output=True,text=True,timeout=60)

def reseal(plan):
    for t in plan['tasks']:
        q=t['packet'];q['sha256']=digest({k:v for k,v in q.items() if k!='sha256'})
        t['source_snapshot_sha256']=digest([q['entries'],q['null_entries']]);t['config_sha256']=digest([q['costs'],q['initial_risk_fraction']])
        t['sha256']=digest({k:v for k,v in t.items() if k!='sha256'})
    plan['sha256']=digest({k:v for k,v in plan.items() if k!='sha256'});return plan

def test_seal_identity_budget_and_freeze(tmp_path,hashes):
    p=make_plan(10,hashes);assert p==make_plan(10,hashes)
    freeze(tmp_path/'plan',p)
    changed=copy.deepcopy(p);changed['tasks'][0]['seed']+=1
    with pytest.raises(ValueError):freeze(tmp_path/'plan',changed)
    duplicate=copy.deepcopy(p);duplicate['tasks'][1]=duplicate['tasks'][0];reseal(duplicate)
    with pytest.raises(ValueError,match='DUPLICATE'):validate(duplicate)
    with pytest.raises(ValueError,match='BUDGET_BOUND'):make_plan(1,hashes,budgets={'max_workers':3})
    with pytest.raises(ValueError,match='TASK_BOUND'):make_plan(257,hashes)

@pytest.mark.parametrize('attack',['pit','live','peek','embargo','future','false_fill','pnl','nonfinite','null_alias','alpha','promotion'])
def test_scientific_adversaries(hashes,attack):
    p=make_plan(1,hashes);q=p['tasks'][0]['packet']
    if attack=='pit':q['historical_pit']='ATTESTED'
    elif attack=='live':q['trading_authority']='LIVE'
    elif attack=='peek':p['holdout']['peek_allowed']=True
    elif attack=='embargo':q['embargo_ms']=1
    elif attack=='future':q['entries'][0]['signal_ms']=q['entries'][0]['entry_ms']+1
    elif attack=='false_fill':q['entries'][0].update(maker_state='UNKNOWN',maker_fill_fraction='1')
    elif attack=='pnl':q['entries'][0]['pnl']='1000000'
    elif attack=='nonfinite':q['initial_risk_fraction']='NaN'
    elif attack=='null_alias':q['null_entries']=copy.deepcopy(q['entries'])
    elif attack=='alpha':p['multiplicity']['familywise_alpha']='1'
    else:p['multiplicity']['promotion']='BEST'
    reseal(p)
    with pytest.raises(ValueError):validate(p)

def test_dependency_manifest_and_bytes_fail_closed(tmp_path,deps):
    import shutil
    target=tmp_path/'deps';shutil.copytree(deps,target)
    manifest=json.loads((target/'pins.json').read_text());name=next(iter(manifest))
    (target/name).write_text('malicious=True')
    with pytest.raises(ValueError,match='DEPENDENCY_BYTES'):activate(target)
    manifest[name]['sha256']=hashlib.sha256((target/name).read_bytes()).hexdigest()
    (target/'pins.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='DEPENDENCY_MANIFEST'):activate(target)
    (target/'pins.json').write_text((deps/'pins.json').read_text());(target/name).write_bytes((deps/name).read_bytes())
    (target/'unexpected.py').write_text('shadow=True')
    with pytest.raises(ValueError,match='DEPENDENCY_EXTRA_SOURCE'):activate(target)

def test_serial_parallel_full_population_exact_once(tmp_path,deps,hashes):
    p=make_plan(3,hashes);a,am=run(tmp_path/'serial',p,deps=deps);b,bm=run(tmp_path/'parallel',p,deps=deps,workers=2)
    assert a==b and a['population']['statuses']=={'SUCCEEDED':3}
    assert 1<=bm['peak_concurrency']<=2 and bm['peak_worker_rss_bytes']>0
    assert bm['peak_total_rss_bytes']<p['budgets']['batch_memory_mb']*1024**2
    before=catalog(tmp_path/'parallel/results.sqlite');again,metrics=run(tmp_path/'parallel',p,deps=deps,workers=2)
    assert again==b and before==catalog(tmp_path/'parallel/results.sqlite') and metrics['physical_claims']==3
    packages=[d for d in before.values() if 'comparison' in d]
    for d in packages:
        r=d['comparison'];assert r['denominators']['total_variant_rows']==72 and len(r['comparisons'])==18
        assert r['actual_fills'] is None and r['orders_created']==0 and r['winner'] is None
        assert any(row['status'].startswith('UNKNOWN') for row in r['outcomes'])

@pytest.mark.parametrize('stage,code,claims',[
    ('before_result_commit',72,2),('after_report_commit',73,1),
    ('after_outcome_commit',74,1),('after_checkpoint_before_ack',75,1)])
def test_fresh_process_crash_windows(tmp_path,deps,hashes,stage,code,claims):
    p=make_plan(1,hashes);root=tmp_path/'crash'
    failed=cli(root,p,deps,crash=stage);assert failed.returncode==code,failed.stderr
    resumed=cli(root,p,deps);assert resumed.returncode==0,resumed.stderr
    result=json.loads((root/'canonical-result.json').read_text());m=json.loads((root/'metrics.json').read_text())
    assert result['population']=={'planned':1,'statuses':{'SUCCEEDED':1},'factory_comparison_packages':1}
    assert m['physical_claims']==claims
    fresh=cli(tmp_path/'fresh',p,deps);assert fresh.returncode==0,fresh.stderr
    assert result==json.loads((tmp_path/'fresh/canonical-result.json').read_text())

def test_all_terminal_statuses_and_resource_faults(tmp_path,deps,hashes):
    faults={0:'none',1:'raise',2:'skip',3:'reject',4:'sleep',5:'cpu',6:'memory',7:'io',8:'no_fill'}
    p=make_plan(9,hashes,faults=faults);result,m=run(tmp_path/'mixed',p,deps=deps,workers=2)
    assert result['population']['statuses']=={'SUCCEEDED':1,'FAILED':1,'SKIPPED':1,'REJECTED':3,'TIMEOUT':2,'NO_FILL':1}
    assert result['population']['factory_comparison_packages']==2 and m['physical_claims']==7
    cp=closed_checkpoint(deps,tmp_path/'mixed/checkpoint.sqlite')
    assert len(cp.read_latest_ledger()['entries'])==25  # 9 registrations + 7 pending + 9 terminal; no failures omitted
    again,am=run(tmp_path/'mixed',p,deps=deps);assert result==again and am['physical_claims']==7

def test_cancellation_and_backpressure(tmp_path,deps,hashes):
    p=make_plan(2,hashes);control=tmp_path/'control.json'
    control.write_text(json.dumps({'critical':False,'cancel':[p['tasks'][0]['sha256']]}))
    result,m=run(tmp_path/'cancel',p,deps=deps,control=control)
    assert result['population']['statuses']=={'CANCELLED':1,'SUCCEEDED':1} and m['physical_claims']==1
    control.write_text(json.dumps({'critical':True,'cancel':[]}));start=time.monotonic()
    result,m=run(tmp_path/'critical',p,deps=deps,control=control)
    assert result['population']['statuses']=={'CANCELLED':2} and m['physical_claims']==0 and time.monotonic()-start<5

def test_corruption_explicit_restore_keeps_failures(tmp_path,deps,hashes):
    p=make_plan(2,hashes,faults={0:'raise'});root=tmp_path/'recover';result,m=run(root,p,deps=deps)
    pin=json.loads((root/'backup-pin.json').read_text())['sha256'];original=(root/'checkpoint.sqlite').read_bytes()
    (root/'checkpoint.sqlite').write_bytes(b'CORRUPT'+original[7:])
    with pytest.raises((ValueError,sqlite3.DatabaseError)):run(root,p,deps=deps)
    with pytest.raises(ValueError,match='BACKUP_PIN'):restore_checkpoint(root,root/'checkpoint-backup.sqlite','0'*64)
    restore_checkpoint(root,root/'checkpoint-backup.sqlite',pin)
    resumed,rm=run(root,p,deps=deps);assert resumed==result and rm['physical_claims']==2
    assert list(root.glob('checkpoint-corrupt-*.sqlite'))

def test_store_tamper_and_retry_budget(tmp_path,deps,hashes):
    p=make_plan(1,hashes);root=tmp_path/'tamper';run(root,p,deps=deps)
    con=sqlite3.connect(root/'results.sqlite')
    con.execute('DROP TRIGGER IF EXISTS factory_h_no_update');con.close()
    # Native immutable triggers reject UPDATE; corruption of bytes must also fail closed.
    raw=(root/'results.sqlite').read_bytes();(root/'results.sqlite').write_bytes(b'CORRUPT'+raw[7:])
    with pytest.raises((ValueError,sqlite3.DatabaseError)):run(root,p,deps=deps)
    retry=tmp_path/'retry'
    for _ in range(3):assert cli(retry,p,deps,crash='before_result_commit').returncode==72
    result,m=run(retry,p,deps=deps)
    assert result['population']['statuses']=={'FAILED':1} and m['physical_claims']==3

def test_concurrent_runner_rejected(tmp_path,deps,hashes):
    from tools.research_capacity_scale.resources import counters
    p=make_plan(1,hashes);root=tmp_path/'concurrent'
    save(root.with_name(root.name+'.capacity-run-lock'),dict(pid=os.getpid(),created=counters(os.getpid())['created'],plan_sha256=p['sha256'],nonce='test'))
    with pytest.raises(ValueError,match='CONCURRENT_RUNNER'):run(root,p,deps=deps)

def test_pinned_consumer_sources_and_no_shared_changes(deps):
    # Contract receipt/source inventory only: do NOT rerun accepted integration.
    for role,commit in PINS.items():
        assert git(REPO,'cat-file','-t',commit).strip()==b'commit'
    from tools.research_evidence_gateway.gateway import modeled_factory_comparison
    assert callable(modeled_factory_comparison)
    core=json.loads(git(REPO,'show',PINS['core']+':docs/evidence/pkg01/synthetic-receipt.json'))
    integration=json.loads(git(REPO,'show',PINS['integration']+':docs/evidence/pkg03-offline-delivery.json'))
    assert core['accepted_receipt']['schema']=='aql.core.prospective-readiness.synthetic.v1'
    assert core['accepted_receipt']['independent_pit']=='NOT_ATTESTED' and core['trading_authority']=='NONE'
    assert integration['schema']=='aql.integration.pkg03.delivery.v1'
    assert integration['sha256']==digest({k:v for k,v in integration.items() if k!='sha256'})
    assert integration['result']['trading_authority']=='NONE' and integration['result']['historical_pit']=='NOT_ATTESTED'
    assert integration['result']['duplicate_fills']==0 and integration['result']['stage_signoff']=='NOT_GRANTED'
    changed = git(REPO, 'diff', '--name-only', 'ea4ffd5ce278d93588338122ab6ac1af8ec4da26', 'HEAD').decode().splitlines()
    unexpected = [
        path for path in changed
        if not path.startswith('tools/research_capacity_scale/')
        and path != '.github/workflows/research-capacity-scale.yml'
    ]
    assert changed and not unexpected, unexpected

def test_fabricated_report_unknown_profit_or_actual_fill(deps,hashes):
    from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_execution_exit_comparison
    from tools.research_evidence_gateway.gateway import modeled_factory_comparison
    r=evaluate_execution_exit_comparison(make_plan(1,hashes)['tasks'][0]['packet'])
    for attack in ('actual_fill','unknown_profit','nonfill_profit','tamper'):
        fake=copy.deepcopy(r)
        if attack=='actual_fill':fake['actual_fills']=1
        elif attack=='unknown_profit':
            row=next(x for x in fake['outcomes'] if x['status'].startswith('UNKNOWN'));row['net_return']='1'
        elif attack=='nonfill_profit':
            row=next(x for x in fake['outcomes'] if x['status']=='NONFILL');row['net_return']='1'
        else:fake['outcomes'][0]['net_return']='999999'
        if attack!='tamper':fake['sha256']=digest({k:v for k,v in fake.items() if k!='sha256'})
        with pytest.raises(ValueError):modeled_factory_comparison(fake)

def test_active_cancel_and_parent_death_bounded(tmp_path,deps,hashes):
    p=make_plan(1,hashes,faults={0:'sleep'});root=tmp_path/'active';pp=tmp_path/'active-plan';freeze(pp,p)
    control=tmp_path/'active-control';control.write_text(json.dumps({'critical':False,'cancel':[]}))
    env={**os.environ,'PYTHONPATH':os.pathsep.join((str(REPO/'src'),str(REPO)))}
    cmd=[sys.executable,'-B','-m','tools.research_capacity_scale','run','--plan',str(pp),'--root',str(root),'--deps',str(deps),'--control',str(control)]
    proc=subprocess.Popen(cmd,cwd=REPO,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    deadline=time.monotonic()+10
    while not list(root.glob('workers/*.ready.json')) and proc.poll() is None and time.monotonic()<deadline:time.sleep(.025)
    assert list(root.glob('workers/*.ready.json'))
    control.write_text(json.dumps({'critical':False,'cancel':[p['tasks'][0]['sha256']]}))
    stdout,stderr=proc.communicate(timeout=15);assert proc.returncode==0,stderr
    assert json.loads(stdout)['population']['statuses']=={'CANCELLED':1}
    # Killing the runner is different from orderly cancellation; orphan is bounded.
    root=tmp_path/'orphan';cmd[cmd.index('--root')+1]=str(root);cmd=cmd[:cmd.index('--control')]
    proc=subprocess.Popen(cmd,cwd=REPO,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    deadline=time.monotonic()+10
    while not list(root.glob('workers/*.ready.json')) and proc.poll() is None and time.monotonic()<deadline:time.sleep(.025)
    ready=json.loads(next(root.glob('workers/*.ready.json')).read_text())
    from tools.research_capacity_scale.resources import counters,terminate_verified
    owner=json.loads(root.with_name(root.name+'.capacity-run-lock').read_text())
    terminate_verified(owner['pid'],owner['created'],{proc.pid,os.getpid()});proc.communicate(timeout=10)
    deadline=time.monotonic()+p['budgets']['worker_wall_s']+2
    while time.monotonic()<deadline:
        stat=counters(ready['pid'])
        if stat is None or stat['created']!=ready['created'] or stat['rss']==0:break
        time.sleep(.025)
    else:pytest.fail('unbounded orphan worker')
    result,m=run(root,p,deps=deps);assert result['population']['statuses']=={'TIMEOUT':1} and m['physical_claims']==2

def test_total_cpu_and_unknown_control_fail_closed(tmp_path,deps,hashes):
    p=make_plan(5,hashes,faults={i:'cpu' for i in range(5)},budgets={'batch_cpu_s':1})
    result,m=run(tmp_path/'cpu',p,deps=deps,workers=2)
    assert result['population']['statuses'].get('CANCELLED',0)>0 and m['wall_s']<15
    control=tmp_path/'unknown';control.write_text('{}')
    with pytest.raises(ValueError,match='CONTROL_FIELDS'):run(tmp_path/'control',make_plan(1,hashes),deps=deps,control=control)

def test_sampled_worker_and_batch_io_limits(tmp_path,deps,hashes):
    p=make_plan(1,hashes,budgets={'worker_io_mb':1})
    result,m=run(tmp_path/'worker-io',p,deps=deps)
    assert result['population']['statuses']=={'REJECTED':1}
    p=make_plan(4,hashes,budgets={'batch_io_mb':1})
    result,m=run(tmp_path/'batch-io',p,deps=deps,workers=2)
    assert result['population']['statuses'].get('CANCELLED',0)>0

def test_atomic_publication_disk_scan_race():
    from tools.research_capacity_scale.runtime import disk_bytes
    class Renamed:
        def is_file(self):return True
        def stat(self):raise FileNotFoundError('published atomically')
    class Root:
        def rglob(self,pattern):return [Renamed()]
    assert disk_bytes(Root())==0
