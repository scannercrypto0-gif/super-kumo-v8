"""Predeclared 1/10/50, serial/2-worker, two fresh-process capacity matrix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from tools.research_capacity_scale.contracts import make_plan,freeze,canonical,need
from tools.research_capacity_scale.dependencies import kernel_identity,git
from tools.research_capacity_scale.resources import counters

REPO=Path(__file__).resolve().parents[2]

def baseline(plan):
    from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_execution_exit_comparison
    before=counters(os.getpid());start=time.monotonic()
    reports={t['sha256']:evaluate_execution_exit_comparison(t['packet'])['sha256'] for t in plan['tasks']}
    after=counters(os.getpid())
    return dict(wall_s=time.monotonic()-start,cpu_s=after['cpu_s']-before['cpu_s'],
        peak_rss_bytes=after['peak_rss'],io_bytes=after['io_bytes']-before['io_bytes'],
        reports_sha256=hashlib.sha256(canonical(reports)).hexdigest(),
        scope='NATIVE_IN_PROCESS_EVALUATOR_NO_DURABLE_ORCHESTRATION')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--deps',type=Path)
    p.add_argument('--baseline-plan',type=Path);a=p.parse_args()
    if a.baseline_plan:
        print(canonical(baseline(json.loads(a.baseline_plan.read_text()))).decode());return
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False);rows=[];hashes=kernel_identity(REPO)
    env={**os.environ,'PYTHONPATH':os.pathsep.join((str(REPO/'src'),str(REPO))),'PYTHONDONTWRITEBYTECODE':'1'}
    for n in (1,10,50):
        plan=make_plan(n,hashes);pp=root/f'plan-{n}.json';freeze(pp,plan);canonical_hashes=[];baseline_hashes=[]
        for repeat in (1,2):
            cmd=[sys.executable,'-B','-m','tools.research_capacity_scale.benchmark','--baseline-plan',str(pp)]
            proc=subprocess.run(cmd,cwd=REPO,env=env,capture_output=True,text=True,timeout=180)
            need(proc.returncode==0,'BASELINE_PROCESS:'+proc.stderr[-500:]);row=json.loads(proc.stdout)
            baseline_hashes.append(row['reports_sha256']);rows.append(dict(size=n,workers=0,repeat=repeat,**row))
            for workers in (1,2):
                folder=root/f'n{n}-w{workers}-r{repeat}'
                cmd=[sys.executable,'-B','-m','tools.research_capacity_scale','run','--plan',str(pp),'--root',str(folder),
                     '--deps',str(a.deps.resolve()),'--workers',str(workers)]
                proc=subprocess.run(cmd,cwd=REPO,env=env,capture_output=True,text=True,timeout=180)
                (root/f'n{n}-w{workers}-r{repeat}.log').write_text(proc.stdout+proc.stderr,encoding='utf-8')
                need(proc.returncode==0,'BENCHMARK_PROCESS:'+proc.stderr[-1000:])
                doc=json.loads(proc.stdout);m=doc['metrics'];canonical_hashes.append(doc['sha256'])
                result=json.loads((folder/'canonical-result.json').read_text())
                reports={o['task_sha256']:o['report_sha256'] for o in result['outcomes']}
                need(hashlib.sha256(canonical(reports)).hexdigest()==baseline_hashes[-1],'NATIVE_BASELINE_REPORT_EQUALITY')
                need(doc['population']==dict(planned=n,statuses={'SUCCEEDED':n},factory_comparison_packages=n),'POPULATION')
                need(m['physical_claims']==n and m['peak_concurrency']<=workers,'CLAIMS_OR_CONCURRENCY')
                need(m['wall_s']<plan['budgets']['batch_wall_s'] and m['parent_cpu_s']+m['child_cpu_s']<plan['budgets']['batch_cpu_s'],'CPU_WALL')
                need(m['peak_total_rss_bytes']<plan['budgets']['batch_memory_mb']*1024**2 and m['local_bytes']<plan['budgets']['batch_local_mb']*1024**2,'MEMORY_DISK')
                rows.append(dict(size=n,workers=workers,repeat=repeat,result_sha256=doc['sha256'],
                    throughput_tasks_s=n/m['wall_s'],**m))
        need(len(set(canonical_hashes))==1 and len(set(baseline_hashes))==1,'FRESH_REPLAY_IDENTITY')
    result=dict(schema='aql.capacity.benchmark.v1',sizes=[1,10,50],repeats=2,max_workers=2,
        source_head=git(REPO,'rev-parse','HEAD').decode().strip(),platform=platform.platform(),python=platform.python_version(),
        kernel_hashes=hashes,rows=rows,authority='NONE',disposition='PASS_BOUNDED_RESEARCH_CAPACITY')
    (root/'benchmark.json').write_bytes(canonical(result))
    manifest={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(root.rglob('*')) if p.is_file()}
    (root/'manifest.json').write_bytes(canonical(manifest));print(canonical(result).decode())

if __name__=='__main__':main()
