"""016: existing-receipt diagnosis and opt-in bounded report-only monitoring.

No warehouse DB, source acquisition, scheduler, producer launch or trading API.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import tempfile
import time
import subprocess
import sys

import atlas_mcp_refresh as refresh
import atlas_early_observation as early
import atlas_ops_watchdog as wd
import atlas_mcp_pilot as pilot

KEEP=8
QUOTA=8*1024*1024
INTERVAL=300


def classify_history(receipt, exit_code):
    result=dict(schema='atlas.operational016.history-diagnosis.v1',exit_code=exit_code,
        reason='INSUFFICIENT_TERMINAL_EVIDENCE',recovery_accepted=False,
        source_mutations=0,trading_authority='NONE')
    if receipt.get('status')=='FULL_HISTORY_STOPPED_FAIL_CLOSED':
        detail=str(receipt.get('reason',''))
        return dict(result,reason='EXECUTION_FAIL_CLOSED',
                    reported_error_type=receipt.get('error_type') if receipt.get('error_type') in
                        {'OSError','ValueError','TimeoutError','HTTPError','URLError'} else 'UNKNOWN',
                    reported_reason_code=detail if re.fullmatch('[A-Z0-9_]{1,120}',detail) else 'PRIVATE_DETAIL_RETAINED_LOCALLY',
                    reason_sha256=wd.digest(detail.encode()))
    if (receipt.get('schema')!='aql.warehouse.full-history-continuation.v1'
        or type(receipt.get('failures')) is not list
        or type(receipt.get('unresolved_gap_ranges')) is not list
        or type(receipt.get('all_published_partitions_ingested')) is not bool
        or receipt.get('accepted_prefix_unchanged') is not True):
        return result
    if receipt['failures']:
        reason='SOURCE_OR_EXECUTION_FAILURE_REQUIRES_EXACT_FAILURE_RECEIPT'
    elif receipt['unresolved_gap_ranges']:
        reason='UNRESOLVED_COVERAGE_GAPS'
    elif not receipt['all_published_partitions_ingested']:
        reason=('SOURCE_OBSTACLES_REMAIN' if receipt.get('unresolved_source_obstacles')
                else 'BOUNDED_PROGRESS_OR_UNFINISHED_PLAN_NOT_A_CRASH_PROOF')
    else:
        reason='PUBLISHED_SCOPE_FINISHED_WITH_DECLARED_LIMITATIONS'
    return dict(result,reason=reason,status=receipt.get('status') if re.fullmatch('[A-Z0-9_]{1,120}',str(receipt.get('status',''))) else 'UNKNOWN',
        gap_ranges=len(receipt['unresolved_gap_ranges']),failures=len(receipt['failures']),
        completion_claim=receipt['all_published_partitions_ingested'],
        exit_consistent=(exit_code==(0 if reason=='PUBLISHED_SCOPE_FINISHED_WITH_DECLARED_LIMITATIONS' else 2)),
        full_history_verified=False)


def diagnose_file(path, exit_code):
    p=Path(path)
    early.checked_root(p.absolute().parent,'RECEIPT_PARENT_INVALID')
    raw,sha=wd.read_json(p)  # existing bounded/no-link JSON loader
    early.require(re.fullmatch('[a-f0-9]{64}',p.stem) is not None and p.stem==sha,
                  'TERMINAL_RECEIPT_FILENAME_SHA_MISMATCH')
    return dict(classify_history(raw,exit_code),receipt_sha256=sha,
                evidence_grade='LOCAL_RECEIPT_DIGEST_CHECKED_NOT_HOST_ATTESTATION')


def state_write(root,body):
    body={k:v for k,v in body.items() if k!='sha256'};body['sha256']=wd.digest(wd.canonical(body))
    raw=wd.canonical(body);early.require(len(raw)<=65536,'MONITOR_STATE_BOUND')
    fd,name=tempfile.mkstemp(prefix='.monitor-pending-',dir=root)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(name,root/'monitor-state.json')
    finally:Path(name).unlink(missing_ok=True)


@contextmanager
def exclusive(root):
    path=early.require_direct_child(root/'monitor.lock',root,'MONITOR_LOCK_SCOPE')
    if path.exists():early.require(path.stat().st_nlink==1 and not path.is_symlink(),'MONITOR_LOCK_LINK')
    with path.open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def inventory(root):
    found=[];total=0
    with os.scandir(root) as entries:
        for entry in entries:
            early.require(len(found)<64,'MONITOR_OUTPUT_ENTRY_BOUND')
            p=early.require_direct_child(root/entry.name,root,'MONITOR_OUTPUT_SCOPE')
            early.require(not p.is_symlink() and p.is_file() and p.stat().st_nlink==1,'MONITOR_OUTPUT_LINK')
            early.require(entry.name in {'monitor.lock','monitor-state.json'} or
                re.fullmatch(r'early-[0-9]{12}(?:\.manifest)?\.json',entry.name), 'MONITOR_UNOWNED_OUTPUT')
            total+=p.stat().st_size;found.append(p)
    early.require(total<=QUOTA,'MONITOR_DISK_QUOTA')
    return found


def stdio_readback(root,result):
    requests=[dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2024-11-05'}),
              dict(jsonrpc='2.0',id=2,method='tools/list'),dict(jsonrpc='2.0',id=3,method='resources/list'),
              dict(jsonrpc='2.0',id=4,method='tools/call',params={'name':'atlas.runtime.health','arguments':{}})]
    for lane in pilot.LANES:
        requests.append(dict(jsonrpc='2.0',id=len(requests)+1,method='tools/call',
            params={'name':'atlas.lane.latest','arguments':{'lane':lane}}))
    for resource in pilot.resource_specs():
        requests.append(dict(jsonrpc='2.0',id=len(requests)+1,method='resources/read',params={'uri':resource['uri']}))
    requests.extend([dict(jsonrpc='2.0',id=len(requests)+1,method='resources/read',params={'uri':'file:///forbidden'}),
                     dict(jsonrpc='2.0',id=len(requests)+2,method='resources/write',params={})])
    raw=''.join(json.dumps(r)+'\n' for r in requests)
    child=subprocess.run([sys.executable,'-B',str(Path(pilot.__file__).resolve()),
        '--manifest',str(root/result['manifest_name']),'--manifest-sha256',result['manifest_sha256'],
        '--profile','early','--approved-output-root',str(root)],input=raw,text=True,
        capture_output=True,timeout=5)
    early.require(child.returncode==0 and len(child.stdout.encode())<=262144,'MONITOR_STDIO_BOUND')
    responses=[json.loads(line) for line in child.stdout.splitlines()]
    early.require(len(responses)==len(requests) and [r.get('id') for r in responses]==[r['id'] for r in requests],
                  'MONITOR_STDIO_RESPONSES')
    early.require(all('result' in r for r in responses[:-2]) and all('error' in r for r in responses[-2:]),
                  'MONITOR_STDIO_REFUSAL')
    early.require(len(responses[1]['result']['tools'])==2 and len(responses[2]['result']['resources'])==4,
                  'MONITOR_MCP_CONTRACT')
    return dict(transport='ACTUAL_FINITE_STDIO_PER_REFRESH',tools=2,resources=4,
        status=responses[3]['result']['structuredContent']['status'],
        response_sha256=wd.digest(child.stdout.encode()),writes_refused=True,arbitrary_reads_refused=True)


def prune(root,state):
    for old in state.get('prune_pending',[]):
        for namekey,hashkey in [('manifest_name','manifest_sha256'),('snapshot_name','snapshot_sha256')]:
            if not old.get(namekey):continue
            p=early.require_direct_child(root/old[namekey],root,'MONITOR_RETENTION_SCOPE')
            if p.exists():
                _,pin=wd.read_json(p);early.require(pin==old[hashkey],'MONITOR_RETENTION_TAMPER')
                p.unlink()
    if state.get('prune_pending'):
        state['prune_pending']=[];state_write(root,state)


def recover_publication(root,state):
    pending=state.get('pending_publish')
    if not pending:return
    snap=root/pending['snapshot_name'];manifest=root/pending['manifest_name']
    if snap.exists():
        snapshot,ssha=wd.read_json(snap);wd.sealed_hash(snapshot,'sha256','MONITOR_RECOVERY_SEAL')
        early.require(snapshot.get('schema')=='atlas.operator.early-observation.v1','MONITOR_RECOVERY_SCHEMA')
        record=dict(snapshot_name=snap.name,snapshot_sha256=ssha,
                    observed_ms=snapshot['observed_at_ms'],manifest_name=None,manifest_sha256=None)
        if manifest.exists():
            doc,msha=wd.read_json(manifest);wd.sealed_hash(doc,'manifest_sha256','MONITOR_RECOVERY_MANIFEST')
            early.require(doc.get('snapshot_file_sha256')==ssha and doc.get('snapshot_path')==str(snap.absolute()),
                          'MONITOR_RECOVERY_PIN')
            record.update(manifest_name=manifest.name,manifest_sha256=msha)
            state['pairs'].append(record)
        else:state.setdefault('orphans',[]).append(record)
    elif manifest.exists():raise ValueError('MONITOR_MANIFEST_WITHOUT_SNAPSHOT')
    state['pending_publish']=None;state_write(root,state)


def monitor(config, *, cycles=2, now=lambda:time.time_ns()//1_000_000,
            monotonic=time.monotonic_ns,wait=time.sleep,notify=lambda r:None):
    early.require(cycles is None or type(cycles) is int and 1<=cycles<=288,'MONITOR_CYCLE_BOUND')
    early.require(config.get('schema')=='atlas.operational016.config.v1','MONITOR_CONFIG_SCHEMA')
    early.require(config.get('activation_ref') and config.get('retention_authorization_ref'),
                  'HOST_ACTIVATION_AND_RETENTION_PERMISSION_REQUIRED')
    inp=early.checked_root(config['input_root'],'MONITOR_INPUT_ROOT')
    out=early.checked_root(config['output_root'],'MONITOR_OUTPUT_ROOT')
    early.require(inp!=out and inp not in out.parents and out not in inp.parents,'MONITOR_ROOT_OVERLAP')
    early.require(type(config.get('protected_roots')) is list and config['protected_roots'],
                  'MONITOR_PROTECTED_ROOTS_REQUIRED')
    for value in config['protected_roots']:
        protected=Path(value).resolve()
        early.require(all(p!=protected and p not in protected.parents and protected not in p.parents
                          for p in (inp,out)), 'MONITOR_PROTECTED_ROOT_OVERLAP')
    with exclusive(out):
        files=inventory(out);statefile=out/'monitor-state.json'
        if statefile.exists():
            state,_=wd.read_json(statefile);wd.sealed_hash(state,'sha256','MONITOR_STATE_SEAL')
            early.require(state.get('config_sha256')==wd.digest(wd.canonical(config)),'MONITOR_CONFIG_DRIFT')
        else:
            early.require(len(files)==1,'MONITOR_DEDICATED_EMPTY_OUTPUT_REQUIRED')
            state=dict(schema='atlas.operational016.monitor-state.v1',pairs=[],prune_pending=[],orphans=[],pending_publish=None,last_sequence=-1,last_error=None,
                       config_sha256=wd.digest(wd.canonical(config)))
        results=[];index=0
        while cycles is None or index<cycles:
            files=inventory(out)
            numbers=[int(p.name[6:18]) for p in files if p.name.startswith('early-')]
            recover_publication(out,state)
            sequence=max([state.get('last_sequence',-1),*numbers])+1
            previous=state['pairs'][-1]['snapshot_name'] if state['pairs'] else None
            if state['pairs'] and now()-state['pairs'][-1]['observed_ms']>1800000:previous=None
            try:
                prune(out,state)
                for orphan in list(state.get('orphans',[])):
                    if now()-orphan['observed_ms']>=2100000:
                        state['prune_pending'].append(orphan);state['orphans'].remove(orphan)
                        state_write(out,state);prune(out,state)
                # Reserve peak space before publishing; never delete unowned data.
                early.require(sum(p.stat().st_size for p in files)+2*early.MAX_FILE_BYTES<=QUOTA,
                              'MONITOR_DISK_QUOTA')
                state['last_sequence']=sequence
                state['pending_publish']=dict(snapshot_name=f'early-{sequence:012d}.json',
                    manifest_name=f'early-{sequence:012d}.manifest.json')
                state_write(out,state)
                result=refresh.refresh_once(config.get('paths',{}),approved_input_root=inp,
                    approved_output_root=out,sequence=sequence,now_ms=now(),
                    monotonic_ns=monotonic(),boot_id=wd.host_boot_id(),
                    clock_uncertainty_ms=config.get('clock_uncertainty_ms'),previous_name=previous,
                    producer_pins=config.get('producer_pins'),producer_selectors=config.get('producer_selectors'))
                result['mcp_readback']=stdio_readback(out,result)
                state['pairs'].append(dict(snapshot_name=result['snapshot_name'],manifest_name=result['manifest_name'],
                    snapshot_sha256=result['snapshot_sha256'],manifest_sha256=result['manifest_sha256'],observed_ms=now()))
                state['last_error']=None;state['pending_publish']=None
                # Eight 5-minute pairs retain >=35min; previous-age max remains30min.
                while len(state['pairs'])>KEEP:
                    old=state['pairs'][0]
                    early.require(now()-old['observed_ms']>=2100000,'MONITOR_RETENTION_AGE')
                    state['prune_pending'].append(state['pairs'].pop(0))
                    state_write(out,state)  # durable intent before any deletion
                    prune(out,state)
            except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
                result=dict(status='MONITOR_BLOCKED',reason=str(exc) if re.fullmatch('[A-Z0-9_]+',str(exc)) else type(exc).__name__,sequence=sequence,
                    source_mutations=0,network_calls=0,trading_authority='NONE')
                state['last_error']=result
                # No replacement of old immutable manifests; their TTL is not reset.
            state_write(out,state);notify(result);results.append(result);index+=1
            if cycles is None:results.clear()  # constant memory in continuous mode
            if cycles is None or index<cycles:wait(INTERVAL)
        return results


def inspect_config(path):
    config,pin=wd.read_json(path)
    result=dict(schema='atlas.operational016.config-inventory.v1',config_sha256=pin,
        host_changes=0,source_calls=0,activation='NOT_PERFORMED',trading_authority='NONE')
    for key in ('input_root','output_root'):
        try:
            early.checked_root(config.get(key,''),'APPROVED_ROOT_REQUIRED')
            result[key]='EXISTING_ROOT_PATH_CHECKED_NOT_ACTIVATED'
        except (OSError,ValueError):result[key]='MISSING_OR_UNAPPROVED_ROOT'
    result['activation_ref_supplied']=bool(config.get('activation_ref'))
    result['retention_ref_supplied']=bool(config.get('retention_authorization_ref'))
    result['producer_pins_supplied']=sorted(config.get('producer_pins',{}))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path);p.add_argument('--exit-code',type=int,default=2)
    p.add_argument('--config',type=Path);p.add_argument('--continuous',action='store_true')
    p.add_argument('--inspect-config',action='store_true')
    a=p.parse_args()
    if a.receipt:print(json.dumps(diagnose_file(a.receipt,a.exit_code),sort_keys=True));return
    early.require(a.config is not None,'CONFIG_OR_RECEIPT_REQUIRED')
    if a.inspect_config:print(json.dumps(inspect_config(a.config),sort_keys=True));return
    config,_=wd.read_json(a.config)
    monitor(config,cycles=None if a.continuous else 2,notify=lambda r:print(json.dumps(r,sort_keys=True),flush=True))


if __name__=='__main__':main()
