"""Bounded process scheduler over native Discoverer checkpoint + Factory store.

Only orchestration control receipts are new. All reports and accounting remain
owned by Factory. Scientific-result identity excludes execution order/metrics;
physical claims/native raw checkpoint are separately retained, not hidden.
"""
from collections import Counter
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest,migrate_store_v2
from research_wp_r0.aql_factory_h_research_package_v1 import _store_package,TABLE
from tools.research_capacity_scale.contracts import validate,freeze,canonical,need,TERMINAL
from tools.research_capacity_scale.dependencies import activate,kernel_identity
from tools.research_capacity_scale.resources import counters,parent_pid,terminate_verified,lower_priority

def safe(path):
    path=Path(path).absolute()
    for p in (path,*path.parents):
        need(not p.is_symlink() and not(p.exists() and getattr(p.lstat(),'st_file_attributes',0)&0x400),'REPARSE_PATH')
    return path

def save(path,doc):
    raw=canonical(doc)
    with Path(path).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def disk_bytes(root):
    total=0
    for path in root.rglob('*'):
        try:
            if path.is_file():total+=path.stat().st_size
        except FileNotFoundError:pass  # Atomic ready publication can rename between stat calls.
    return total

def store(path,body):
    identity,status=_store_package(path,body)
    return {**body,'sha256':identity},status

def catalog(path):
    con=sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True)
    try:
        need(con.execute('PRAGMA quick_check').fetchone()[0]=='ok','CORRUPT_RESULT_STORE')
        rows=con.execute(f'SELECT experiment_id,canonical_sha256,document,immutable FROM {TABLE}').fetchall()
        need(len(rows)<=4096,'STORE_BOUND');result={}
        for identity,sha,raw,immutable in rows:
            d=json.loads(raw)
            need(immutable==1 and d['experiment_id']==identity and d['sha256']==sha==digest({k:v for k,v in d.items() if k!='sha256'}),'RESULT_STORE_TAMPER')
            result[identity]=d
        return result
    finally:con.close()

def closed_checkpoint(deps,path):
    activate(deps)
    from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint
    # Adapter owns connection lifetime; native transaction/schema/chain logic
    # is unchanged. sqlite context managers alone do not close their handles.
    class Close:
        def __init__(self,db):self.db=db
        def __getattr__(self,k):return getattr(self.db,k)
        def __enter__(self):return self.db.__enter__()
        def __exit__(self,*args):
            try:return self.db.__exit__(*args)
            finally:self.db.close()
    class LocalCheckpoint(DurableDiscovererCheckpoint):
        def _connect(self):return Close(super()._connect())
    return LocalCheckpoint(path)

def backup_checkpoint(root):
    src=sqlite3.connect(root/'checkpoint.sqlite');dest=sqlite3.connect(root/'checkpoint-backup.sqlite')
    try:src.backup(dest)
    finally:src.close();dest.close()
    raw=(root/'checkpoint-backup.sqlite').read_bytes()
    return hashlib.sha256(raw).hexdigest()

def restore_checkpoint(root,backup,expected_sha):
    root,backup=safe(root),safe(backup);need(backup.is_file() and hashlib.sha256(backup.read_bytes()).hexdigest()==expected_sha,'BACKUP_PIN')
    # Explicit restore only. Do not discard corrupt evidence or repair silently.
    target=root/'checkpoint.sqlite';gc.collect()
    need(not Path(str(target)+'-wal').exists() or not Path(str(target)+'-wal').stat().st_size,'NONEMPTY_CORRUPT_WAL')
    if target.exists():
        quarantine=root/('checkpoint-corrupt-'+hashlib.sha256(target.read_bytes()).hexdigest()+'.sqlite')
        need(not quarantine.exists(),'QUARANTINE_EXISTS');target.rename(quarantine)
    shutil.copyfile(backup,target)

def _run(root,plan,*,deps,workers=1,control=None,crash=None,_owned=None):
    validate(plan);root=safe(root);deps=safe(deps)
    need(type(workers) is int and 1<=workers<=plan['budgets']['max_workers'],'CONCURRENCY')
    repo=Path(__file__).resolve().parents[2]
    need(kernel_identity(repo)==plan['kernel_hashes'],'EVALUATOR_PIN')
    fresh=not root.exists()
    if fresh:root.mkdir(parents=True)
    else:need((root/'plan.json').is_file(),'UNOWNED_RUN_DIRECTORY')
    freeze(root/'plan.json',plan)
    result_path=root/'results.sqlite';checkpoint_path=root/'checkpoint.sqlite'
    if fresh:migrate_store_v2(result_path)
    else:
        need(result_path.is_file() and checkpoint_path.is_file(),'DURABLE_STATE_MISSING')
        con=sqlite3.connect(checkpoint_path.as_uri()+'?mode=ro',uri=True)
        try:
            need(con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
                 and con.execute('SELECT COUNT(*) FROM ledger_checkpoints').fetchone()[0]>0,'CORRUPT_CHECKPOINT')
        finally:con.close()
    store(result_path,dict(schema='aql.capacity.plan-receipt.v1',experiment_id='CAPACITY-PLAN-'+plan['sha256'],
                           plan_sha256=plan['sha256'],trading_authority='NONE'))
    documents=catalog(result_path)
    checkpoint=closed_checkpoint(deps,checkpoint_path)
    from tools.strategy_discoverer_offline.ledger import DiscovererLedger,AttemptState
    from tools.research_evidence_gateway.gateway import modeled_factory_comparison
    snapshots=checkpoint.ledger_snapshots();ledger=DiscovererLedger.from_dict_list(snapshots[-1]['entries']) if snapshots else DiscovererLedger()
    tasks={t['sha256']:t for t in plan['tasks']};task_ids=sorted(tasks)
    # A crashed runner's real workers self-terminate on parent death. Admission
    # waits for their bounded lifetime rather than exceeding concurrency on resume.
    stale_deadline=time.monotonic()+plan['budgets']['worker_wall_s']+1
    for path in (root/'workers').glob('*.ready.json') if (root/'workers').exists() else ():
        info=json.loads(path.read_text());need(info['task_sha256'] in tasks,'FOREIGN_WORKER_LEASE')
        while True:
            stat=counters(info['pid'])
            if stat is None or stat['created']!=info['created']:break
            need(time.monotonic()<stale_deadline,'STALE_WORKER_LIFETIME')
            time.sleep(.025)
    last={e.attempt_id:e for e in ledger.entries()}
    need(set(last)<=set(task_ids),'CHECKPOINT_FOREIGN_ATTEMPT')
    for tid in task_ids:
        t=tasks[tid]
        if tid not in last:
            ledger.register(tid,'candidate-'+tid[:20],t['family_id'],t['packet']['strategy_sha256'],
                            plan['sha256'],t['source_snapshot_sha256'],'CREATED')
    if not snapshots or len(ledger.entries())!=len(snapshots[-1]['entries']):checkpoint.append_ledger(ledger.to_dict_list())
    if fresh:
        backup=backup_checkpoint(root)
        save(root/'backup-pin.json',dict(sha256=backup,scope='CALLER_MUST_RETAIN_OUTSIDE_MUTABLE_AUTHORITY'))
    b=plan['budgets'];outcomes={};active={};samples=[];total_child_cpu=0.;peak_children=0
    parent0=counters(os.getpid());started=time.monotonic();critical_since=None;attempt_logs=[];stop_reason=None
    def latest():return {e.attempt_id:e for e in ledger.entries()}
    def hook(stage):
        if crash==stage:os._exit({'before_result_commit':72,'after_report_commit':73,'after_outcome_commit':74,'after_checkpoint_before_ack':75}[stage])
    def validate_report(t,r):
        need(r['input_sha256']==t['packet']['sha256'] and r['strategy_sha256']==t['packet']['strategy_sha256']
             and r['implementation_sources']==plan['kernel_hashes'],'RESULT_PARENT_MISMATCH')
        modeled_factory_comparison(r)
    def finish(tid,status,reason,report=None):
        t=tasks[tid];need(status in TERMINAL,'TERMINAL_STATUS')
        report_sha=package_sha=None
        if report is not None:
            validate_report(t,report);hook('before_result_commit')
            body=dict(schema='aql.factory.h.execution-comparison-package.v1',experiment_id=t['packet']['experiment_id'],
                      input_sha256=t['packet']['sha256'],comparison=report,holdout='SEALED_UNOPENED',trading_authority='NONE')
            package,_=store(result_path,body);documents[body['experiment_id']]=package
            package_sha=package['sha256'];report_sha=report['sha256'];hook('after_report_commit')
        body=dict(schema='aql.capacity.terminal-outcome.v1',experiment_id='CAPACITY-OUTCOME-'+tid,
                  task_sha256=tid,packet_sha256=t['packet']['sha256'],status=status,reason=reason,
                  report_sha256=report_sha,report_package_sha256=package_sha,
                  selected_cell=t['selected_cell'],trading_authority='NONE',actual_fills=None)
        outcome,_=store(result_path,body);documents[body['experiment_id']]=outcome;hook('after_outcome_commit')
        state=latest()[tid].state
        if state in ('REGISTERED','PENDING'):
            if status in ('SUCCEEDED','NO_FILL','FAILED','TIMEOUT') or status=='REJECTED' and state=='PENDING':
                if state=='REGISTERED':ledger.transition(tid,AttemptState.PENDING,'RECOVERED_RESULT_OR_RUNNING')
                native=AttemptState.COMPLETE if status in ('SUCCEEDED','NO_FILL') else AttemptState.FAILED
            elif status=='CANCELLED':native=AttemptState.ABANDONED
            else:native=AttemptState.INVALID
            ledger.transition(tid,native,json.dumps(dict(status=status,outcome_sha256=outcome['sha256']),sort_keys=True,separators=(',',':')))
            checkpoint.append_ledger(ledger.to_dict_list())
        else:
            note=json.loads(latest()[tid].reason)
            need(note['status']==status and note['outcome_sha256']==outcome['sha256'],'TERMINAL_CHECKPOINT_CONFLICT')
        outcomes[tid]=outcome;hook('after_checkpoint_before_ack')
    # Recover immutable result/outcome committed before the previous ACK.
    for tid in task_ids:
        t=tasks[tid];out=documents.get('CAPACITY-OUTCOME-'+tid);package=documents.get(t['packet']['experiment_id'])
        if out:
            need(out['packet_sha256']==t['packet']['sha256'],'RECOVERED_PACKET')
            r=package['comparison'] if package else None
            if r:validate_report(t,r)
            need(out['report_package_sha256']==(package['sha256'] if package else None),'RECOVERED_PACKAGE')
            finish(tid,out['status'],out['reason'],r)
        elif package:
            r=package['comparison'];validate_report(t,r)
            cell=r['comparisons'][t['selected_cell']]
            status='NO_FILL' if cell['nonfill_count']==cell['attempted_entry_count'] else 'SUCCEEDED'
            finish(tid,status,'EVALUATED_FROZEN_SYNTHETIC_CELL',r)
        else:need(latest()[tid].state in ('REGISTERED','PENDING'),'MISSING_COMMITTED_TERMINAL')
    while len(outcomes)<len(tasks):
        now=time.monotonic();parent=counters(os.getpid());memory=parent['rss'];running_cpu=0.
        local_bytes=disk_bytes(root)
        fatal=stop_reason
        if now-started>b['batch_wall_s']:fatal='BATCH_WALL_BUDGET'
        if local_bytes>b['batch_local_mb']*1024*1024:fatal='BATCH_LOCAL_BYTES'
        cfg={'critical':False,'cancel':[]}
        if control is not None:
            cp=safe(control)
            need(cp.is_file() and cp.stat().st_size<4096,'CONTROL_UNAVAILABLE')
            cfg=json.loads(cp.read_text());need(set(cfg)=={'critical','cancel'} and type(cfg['critical']) is bool
                and type(cfg['cancel']) is list and set(cfg['cancel'])<=set(tasks),'CONTROL_FIELDS')
        if cfg['critical']:
            critical_since=critical_since or now
            if now-critical_since>=b['critical_wait_s']:fatal='CRITICAL_BACKPRESSURE_DEADLINE'
        else:critical_since=None
        for tid,a in list(active.items()):
            ready_path=a['output'].with_suffix('.ready.json')
            if a['real'] is None and ready_path.exists():
                ready=json.loads(ready_path.read_text())
                stat=counters(ready['pid'])
                if stat is not None:
                    need(ready['task_sha256']==tid and parent_pid(ready['pid']) in (a['p'].pid,os.getpid()),'WORKER_PID_PARENT')
                    need(stat['created']==ready['created'],'WORKER_PID_GENERATION')
                    need(stat['priority']==0x4000 if os.name=='nt' else stat['priority']>=10,'WORKER_PRIORITY')
                    a['real']=ready
            stat=counters(a['real']['pid']) if a['real'] is not None else counters(a['p'].pid,getattr(a['p'],'_handle',None))
            if stat:
                a['cpu']=max(a['cpu'],stat['cpu_s']);a['rss']=max(a['rss'],stat['peak_rss']);a['io']=max(a['io'],stat['io_bytes'])
                running_cpu+=stat['cpu_s'];memory+=stat['rss']
            limit=('WORKER_CPU_BUDGET' if a['cpu']>b['worker_cpu_s'] else
                   'WORKER_MEMORY_BUDGET' if a['rss']>b['worker_memory_mb']*1024*1024 else
                   'WORKER_IO_BUDGET' if a['io']>b['worker_io_mb']*1024*1024 else
                   'WORKER_WALL_BUDGET' if now-a['start']>b['worker_wall_s'] else None)
            if fatal or tid in cfg['cancel'] or limit:
                if a['real'] is not None:
                    terminate_verified(a['real']['pid'],a['real']['created'],{a['p'].pid,os.getpid()})
                if a['p'].poll() is None:a['p'].kill()
                a['p'].wait();a['forced']=fatal or ('CANCEL_REQUESTED' if tid in cfg['cancel'] else limit)
            if a['p'].poll() is not None:
                total_child_cpu+=a['cpu'];peak_children=max(peak_children,a['rss']);attempt_logs.append({k:a[k] for k in ('claim','cpu','rss','io','forced')})
                if a['forced']:
                    status='CANCELLED' if fatal or tid in cfg['cancel'] else 'TIMEOUT' if 'CPU' in a['forced'] or 'WALL' in a['forced'] else 'REJECTED'
                    finish(tid,status,a['forced'])
                elif a['p'].returncode!=0 or not a['output'].exists():
                    status='TIMEOUT' if tasks[tid]['fault'] in ('cpu','sleep') else 'REJECTED' if tasks[tid]['fault'] in ('memory','io') else 'FAILED'
                    finish(tid,status,'BOUNDED_WORKER_EXIT')
                else:
                    need(a['output'].stat().st_size<=b['result_bytes'],'RESULT_BYTE_BOUND')
                    response=json.loads(a['output'].read_text())
                    need(response['task_sha256']==tid and response['guard'] and response['guard']['memory_kernel_cap']
                         and response['guard']['cpu_kernel_cap'],'WORKER_GUARD_OR_IDENTITY')
                    if response['metrics']:
                        total_child_cpu+=max(0,response['metrics']['cpu_s']-a['cpu']);peak_children=max(peak_children,response['metrics']['peak_rss'])
                        attempt_logs[-1]['io']=max(a['io'],response['metrics']['io_bytes'])
                    if response['error']:
                        status='FAILED' if response['error']=='INJECTED_FAILURE' else 'REJECTED'
                        finish(tid,status,response['error'])
                    else:
                        r=response['report'];cell=r['comparisons'][tasks[tid]['selected_cell']]
                        finish(tid,'NO_FILL' if cell['nonfill_count']==cell['attempted_entry_count'] else 'SUCCEEDED',
                               'EVALUATED_FROZEN_SYNTHETIC_CELL',r)
                del active[tid]
        running_cpu=sum(a['cpu'] for a in active.values())
        if parent['cpu_s']-parent0['cpu_s']+total_child_cpu+running_cpu>b['batch_cpu_s']:fatal='BATCH_CPU_BUDGET'
        if memory>b['batch_memory_mb']*1024*1024:fatal='BATCH_MEMORY_BUDGET'
        if sum(x['io'] for x in attempt_logs)+sum(a['io'] for a in active.values())>b['batch_io_mb']*1024*1024:fatal='BATCH_IO_BUDGET'
        if fatal:stop_reason=fatal
        samples.append(dict(active=len(active),rss=memory,local_bytes=local_bytes))
        for tid in task_ids:
            if tid in outcomes or tid in active:continue
            t=tasks[tid]
            if fatal or tid in cfg['cancel']:
                finish(tid,'CANCELLED',fatal or 'CANCEL_REQUESTED');continue
            if t['fault'] in ('skip','reject'):
                finish(tid,'SKIPPED' if t['fault']=='skip' else 'REJECTED','PREDECLARED_'+t['fault'].upper());continue
            if cfg['critical'] or len(active)>=workers:continue
            old=latest()[tid]
            if old.state=='REGISTERED':ledger.transition(tid,AttemptState.PENDING,'RUNNING');checkpoint.append_ledger(ledger.to_dict_list())
            claim=1+sum(d.get('schema')=='aql.capacity.execution-claim.v1' and d.get('task_sha256')==tid for d in documents.values())
            if claim>b['max_claims_per_task']:
                finish(tid,'FAILED','RETRY_BUDGET_EXHAUSTED');continue
            body=dict(schema='aql.capacity.execution-claim.v1',experiment_id=f'CAPACITY-CLAIM-{tid}-{claim}',
                      task_sha256=tid,packet_sha256=t['packet']['sha256'],ordinal=claim,state='STARTED',trading_authority='NONE')
            record,_=store(result_path,body);documents[body['experiment_id']]=record
            folder=root/'workers';folder.mkdir(exist_ok=True);nonce=uuid.uuid4().hex
            ip=folder/(nonce+'.input.json');op=folder/(nonce+'.output.json');save(ip,dict(task=t,budgets=b))
            env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join((str(repo/'src'),str(repo)));env['PYTHONDONTWRITEBYTECODE']='1'
            proc=subprocess.Popen([sys.executable,'-B','-m','tools.research_capacity_scale.worker','--input',str(ip),
                '--output',str(op),'--deps',str(deps),'--parent',str(os.getpid())],cwd=repo,env=env,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            _owned.append(proc)
            proc.capacity_output=op;proc.capacity_task=tid
            active[tid]=dict(p=proc,start=time.monotonic(),output=op,claim=claim,cpu=0.,rss=0,io=0,forced=None,real=None)
        time.sleep(0.025)
    final_docs=catalog(result_path);need(len(outcomes)==len(tasks),'LOST_LOGICAL_ATTEMPTS')
    scientific=dict(schema='aql.capacity.canonical-result.v1',plan_sha256=plan['sha256'],
        outcomes=[outcomes[k] for k in sorted(outcomes)],population=dict(planned=len(tasks),
        statuses=dict(sorted(Counter(x['status'] for x in outcomes.values()).items())),
        factory_comparison_packages=sum(d.get('schema')=='aql.factory.h.execution-comparison-package.v1' for d in final_docs.values())),
        multiplicity=plan['multiplicity'],holdout='SEALED_UNOPENED',historical_pit='NOT_ATTESTED',
        actual_fills=None,orders_created=0,winner=None,trading_authority='NONE',scientific_inference='NOT_ESTIMABLE')
    scientific={**scientific,'sha256':digest(scientific)}
    # Raw order/checkpoint/claims are deliberately separate from invariant
    # sorted logical results; all physical retry records remain inspectable.
    claims=[d for d in final_docs.values() if d.get('schema')=='aql.capacity.execution-claim.v1']
    metrics=dict(wall_s=time.monotonic()-started,parent_cpu_s=counters(os.getpid())['cpu_s']-parent0['cpu_s'],
        child_cpu_s=total_child_cpu,peak_worker_rss_bytes=peak_children,
        peak_total_rss_bytes=max((s['rss'] for s in samples),default=parent0['rss']),
        peak_concurrency=max((s['active'] for s in samples),default=0),
        local_bytes=disk_bytes(root),
        worker_io_bytes=sum(x['io'] for x in attempt_logs),
        physical_claims=len(claims),claims_by_task=dict(Counter(d['task_sha256'] for d in claims)),
        native_checkpoint_sha256=checkpoint.read_latest_ledger()['checkpoint_sha'],
        os_priority_scope='OWN_WORKERS_ONLY_LOWER_PRIORITY_NO_LIVE_G1_G2_QUEUE_ADAPTER',
        cumulative_io_scope='POLLED_WITH_SAMPLE_OVERSHOOT_NOT_KERNEL_BANDWIDTH')
    (root/'canonical-result.json').write_bytes(canonical(scientific));(root/'metrics.json').write_bytes(canonical(metrics))
    return scientific,metrics

def run(root,plan,*,deps,workers=1,control=None,crash=None):
    lower_priority()
    owned=[];root=safe(root);lock=root.with_name(root.name+'.capacity-run-lock')
    token=dict(pid=os.getpid(),created=counters(os.getpid())['created'],plan_sha256=plan['sha256'],nonce=uuid.uuid4().hex)
    if lock.exists():
        old=json.loads(lock.read_text());stat=counters(old['pid'])
        need(not stat or stat['created']!=old['created'],'CONCURRENT_RUNNER')
        need(old['plan_sha256']==plan['sha256'],'STALE_LOCK_PLAN')
        lock.rename(lock.with_name(lock.name+'-stale-'+old['nonce']))
    save(lock,token)
    try:return _run(root,plan,deps=deps,workers=workers,control=control,crash=crash,_owned=owned)
    finally:
        for process in owned:
            if process.poll() is None:
                output=getattr(process,'capacity_output',None)
                if output is not None:
                    output.with_suffix('.cancel').touch(exist_ok=True)
                    ready=output.with_suffix('.ready.json')
                    if ready.exists():
                        info=json.loads(ready.read_text())
                        if info['task_sha256']==process.capacity_task:
                            terminate_verified(info['pid'],info['created'],{process.pid,os.getpid()})
                if process.poll() is None:process.kill()
            process.wait()
        if lock.exists() and json.loads(lock.read_text())==token:lock.unlink()
