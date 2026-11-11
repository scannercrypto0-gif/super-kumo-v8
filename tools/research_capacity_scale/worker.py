"""Fixed, capped process worker calling the existing Factory; no user callbacks."""
import argparse
import json
import os
from pathlib import Path
import time

from tools.research_capacity_scale.resources import enforce,counters,parent_pid

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--deps',type=Path,required=True)
    parser.add_argument('--parent',type=int,required=True);args=parser.parse_args()
    request=json.loads(args.input.read_text());budget=request['budgets'];task=request['task']
    guard=None;body=None
    try:
        guard=enforce(budget,args.parent,args.output.with_suffix('.cancel'))
        ready=dict(task_sha256=task['sha256'],pid=os.getpid(),created=counters(os.getpid())['created'],
                   parent_root_pid=args.parent,process_parent_pid=parent_pid(os.getpid()),guard=guard)
        staging=args.output.with_suffix('.ready.staging')
        with staging.open('x',encoding='utf-8') as f:
            json.dump(ready,f);f.flush();os.fsync(f.fileno())
        os.replace(staging,args.output.with_suffix('.ready.json'))
        from tools.research_capacity_scale.dependencies import activate
        activate(args.deps)
        from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_execution_exit_comparison
        fault=task['fault']
        if fault=='raise':raise RuntimeError('INJECTED_FAILURE')
        if fault=='sleep':time.sleep(budget['worker_wall_s']+2)
        if fault=='cpu':
            while True:sum(i*i for i in range(10000))
        if fault=='memory':bytearray(budget['worker_memory_mb']*3*1024*1024)
        if fault=='io':
            with args.output.with_suffix('.fault-io').open('xb') as f:
                count=0
                while True:
                    if count+65536>budget['result_bytes']:raise ValueError('RESOURCE_OUTPUT_LIMIT')
                    f.write(b'x'*65536);f.flush();count+=65536
        report=evaluate_execution_exit_comparison(task['packet'])
        body=dict(task_sha256=task['sha256'],report=report,error=None,guard=guard)
    except MemoryError:body=dict(task_sha256=task['sha256'],report=None,error='RESOURCE_MEMORY',guard=guard)
    except (ValueError,RuntimeError,OSError) as exc:
        code=str(exc)
        if not code or len(code)>128 or not all(c.isalnum() or c=='_' for c in code):code=type(exc).__name__
        body=dict(task_sha256=task['sha256'],report=None,error=code,guard=guard)
    body['metrics']=counters(os.getpid())
    raw=json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>budget['result_bytes']:raise ValueError('CAPACITY_RESULT_BYTES')
    with args.output.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

if __name__=='__main__':main()
