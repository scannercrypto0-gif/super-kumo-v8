"""Versioned frozen orchestration inputs; existing Factory still owns evaluation."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest
from tools.atlas_factory_pkg02_execution_smoke import fixture_packet,seal
from tools.research_capacity_scale.dependencies import PINS,FACTORY

TERMINAL={'SUCCEEDED','FAILED','SKIPPED','REJECTED','CANCELLED','TIMEOUT','NO_FILL'}
FAULTS={'none','raise','sleep','cpu','memory','io','no_fill','skip','reject'}
SCHEMA='aql.research-capacity.frozen-batch.v1'

def need(ok,code):
    if not ok:raise ValueError('CAPACITY_'+code)

def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sealed(obj):return {**obj,'sha256':digest(obj)}

def packet(seed,index):
    """New generated scaling workloads, not reruns of accepted market/G4 cycles."""
    p=deepcopy(fixture_packet());rng=random.Random(seed);null_rng=random.Random(seed^0x55AA)
    p['experiment_id']='RESEARCH-H-EXEC-CMP-CAPACITY-'+digest(['capacity295',seed,index])
    factor=Decimal(rng.randint(95,105))/100
    null_factor=Decimal(null_rng.randint(95,105))/100
    shift=index*86400000
    for key,multiplier in (('entries',factor),('null_entries',null_factor)):
        for row in p[key]:
            row['signal_ms']+=shift;row['entry_ms']+=shift
            row['entry_price']=str(Decimal(row['entry_price'])*multiplier)
            for b in row['bars']:
                b['open_ms']+=shift;b['close_ms']+=shift
                for field in ('open','high','low','close'):b[field]=str(Decimal(b[field])*multiplier)
    p['evaluation_start_ms']+=shift;p['train_end_ms']+=shift
    p['initial_risk_fraction']='0.01' if index%2==0 else '0.02'
    p['strategy_sha256']=digest(['GENERATED_FROZEN_ENTRY_RISK_PROFILE',index%2,p['initial_risk_fraction']])
    p['scanner_entry_batch_sha256']=digest(p['entries'])
    p['attempts'][0]['source_receipt_sha256']=digest(p['entries'])
    p['baseline_sha256']=digest(['INDEPENDENT_GENERATED_NULL',seed^0x55AA,p['null_entries'],p['costs']])
    return seal(p)

DEFAULT_BUDGET=dict(max_workers=2,worker_memory_mb=128,worker_cpu_s=2,
                    worker_wall_s=5,worker_io_mb=16,result_bytes=262144,
                    batch_wall_s=120,batch_cpu_s=80,batch_memory_mb=512,batch_local_mb=128,batch_io_mb=512,
                    critical_wait_s=1,max_claims_per_task=3)

def make_plan(count,kernel_hashes,*,faults=None,budgets=None):
    need(type(count) is int and 1<=count<=256,'TASK_BOUND')
    budgets={**DEFAULT_BUDGET,**(budgets or {})};tasks=[]
    for i in range(count):
        fault=(faults or {}).get(i,'none');p=packet(295000+i,i)
        if fault=='no_fill':
            for r in p['entries']:r.update(maker_state='NONFILL',maker_fill_fraction='0')
            p['scanner_entry_batch_sha256']=digest(p['entries']);p['attempts'][0]['source_receipt_sha256']=digest(p['entries']);seal(p)
        body=dict(family_id='GENERATED_FROZEN_ENTRY_RISK_'+str(i%2),regime='GENERATED_'+('RANGE','GAP','TREND')[i%3],
            period='GENERATED_PERIOD_'+str(i//10),fold=i%3,hypothesis_sha256=digest(['capacity-hypothesis',i%2]),
            seed=295000+i,config_sha256=digest([p['costs'],p['initial_risk_fraction']]),
            evaluator_sha256=digest(kernel_hashes),source_snapshot_sha256=digest([p['entries'],p['null_entries']]),
            selected_cell='CANDIDATE:PASSIVE_ENTRY_MARKET_EXIT:A',packet=p,fault=fault)
        tasks.append(sealed(body))
    last=max(b['close_ms'] for t in tasks for k in ('entries','null_entries') for e in t['packet'][k] for b in e['bars'])
    body=dict(schema=SCHEMA,source_class='INTERNAL_GENERATED_SYNTHETIC_ONLY',dependency_pins={**PINS,'factory':FACTORY},
        source_terms=dict(use='INTERNAL_GENERATED_FIXTURE_NO_MARKET_SOURCE',version='capacity295-v1'),
        tasks=tasks,budgets=budgets,kernel_hashes=kernel_hashes,
        holdout=dict(status='SEALED_UNOPENED',start_ms=last+259200001,peek_allowed=False),
        multiplicity=dict(familywise_alpha='0.05',planned_cells=count*18,
                          bonferroni_alpha=str(Decimal('0.05')/(count*18)),p_values='NOT_ESTIMABLE',promotion='NONE'),
        historical_pit='NOT_ATTESTED',real_OOS='BLOCKED_EXTERNAL_EVIDENCE',trading_authority='NONE')
    result=sealed(body);validate(result);return result

def validate(p):
    need(type(p) is dict and p.get('schema')==SCHEMA and p.get('sha256')==digest({k:v for k,v in p.items() if k!='sha256'}),'PLAN_SEAL')
    need(set(p)=={'schema','source_class','dependency_pins','source_terms','tasks','budgets','kernel_hashes','holdout','multiplicity',
                  'historical_pit','real_OOS','trading_authority','sha256'} and p['dependency_pins']=={**PINS,'factory':FACTORY},'PLAN_FIELDS_OR_DEPENDENCY')
    need(p['source_class']=='INTERNAL_GENERATED_SYNTHETIC_ONLY' and p['historical_pit']=='NOT_ATTESTED'
         and p['trading_authority']=='NONE' and p['real_OOS']=='BLOCKED_EXTERNAL_EVIDENCE','AUTHORITY')
    need(1<=len(p['tasks'])<=256 and len(canonical(p))<=4*1024*1024,'PLAN_BOUND')
    b=p['budgets'];need(set(b)==set(DEFAULT_BUDGET) and all(type(v) is int and v>0 for v in b.values()),'BUDGET_FIELDS')
    need(1<=b['max_workers']<=2 and 64<=b['worker_memory_mb']<=256 and b['worker_cpu_s']<=5
         and b['worker_wall_s']<=10 and b['worker_io_mb']<=32 and b['result_bytes']<=1048576
         and b['batch_wall_s']<=180 and b['batch_cpu_s']<=80 and b['batch_memory_mb']<=768
         and b['batch_local_mb']<=256 and b['batch_io_mb']<=768 and b['critical_wait_s']<=2 and b['max_claims_per_task']<=3,'BUDGET_BOUND')
    need(p['source_terms']==dict(use='INTERNAL_GENERATED_FIXTURE_NO_MARKET_SOURCE',version='capacity295-v1'),'SOURCE_TERMS')
    need(len(p['tasks'])*2*b['result_bytes']+len(p['tasks'])**2*8192+20*1024*1024
         <=b['batch_local_mb']*1024*1024,'LOCAL_WRITE_RESERVATION')
    need(p['holdout']['status']=='SEALED_UNOPENED' and p['holdout']['peek_allowed'] is False
         and set(p['holdout'])=={'status','start_ms','peek_allowed'}
         and p['multiplicity']['familywise_alpha']=='0.05'
         and p['multiplicity']['planned_cells']==len(p['tasks'])*18
         and p['multiplicity']['bonferroni_alpha']==str(Decimal('0.05')/(len(p['tasks'])*18))
         and p['multiplicity']['promotion']=='NONE' and p['multiplicity']['p_values']=='NOT_ESTIMABLE','HOLDOUT_MULTIPLICITY')
    ids=set();experiments=set();seeds=set()
    for t in p['tasks']:
        need(set(t)=={'family_id','regime','period','fold','hypothesis_sha256','seed','config_sha256',
             'evaluator_sha256','source_snapshot_sha256','selected_cell','packet','fault','sha256'},'TASK_FIELDS')
        need(t['sha256']==digest({k:v for k,v in t.items() if k!='sha256'}) and t['sha256'] not in ids,'TASK_ID_OR_DUPLICATE');ids.add(t['sha256'])
        need(t['fault'] in FAULTS and type(t['seed']) is int and t['evaluator_sha256']==digest(p['kernel_hashes']),'TASK_PIN')
        q=t['packet'];need(q['sha256']==digest({k:v for k,v in q.items() if k!='sha256'}),'PACKET_SEAL')
        need(q['experiment_id'] not in experiments and t['seed'] not in seeds,'DUPLICATE_EXPERIMENT_OR_SEED')
        experiments.add(q['experiment_id']);seeds.add(t['seed'])
        from research_wp_r0.aql_factory_h_execution_comparison_v1 import _validate
        _validate(q)  # Native admission applies even to skipped/rejected tasks.
        need(t['selected_cell']=='CANDIDATE:PASSIVE_ENTRY_MARKET_EXIT:A','SELECTED_CELL')
        need(t['source_snapshot_sha256']==digest([q['entries'],q['null_entries']])
             and t['config_sha256']==digest([q['costs'],q['initial_risk_fraction']]),'SOURCE_CONFIG_PIN')
        need(all(b['close_ms']<p['holdout']['start_ms']-259200000
                 for k in ('entries','null_entries') for e in q[k] for b in e['bars']),'HOLDOUT_PEEK')

def freeze(path,plan):
    validate(plan);path=Path(path);raw=canonical(plan)
    if path.exists():need(path.read_bytes()==raw,'FROZEN_INPUT_REPLACED')
    else:
        import os
        with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    return plan['sha256']
