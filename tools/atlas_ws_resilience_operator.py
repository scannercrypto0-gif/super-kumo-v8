"""Private Windows one-shot preparation: standard library, zero market calls.

Diagnose reads only. The gate is invoked by the companion PowerShell wrapper
while it holds supervisor.lock; it holds the existing collector SQLite lease
until the wrapper confirms task-pin readback. Authorization is separate from
this engineering package. HOLD and automatic claims are never deleted here.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import uuid

SCHEMA = 'atlas.ws.operator-authorization.v1'
MAX_JSON = 8 * 1024 * 1024
CANDIDATES = ('tools/atlas_live_research_cycle.py', 'tools/atlas_ws_receive_diagnostics.py',
              'tools/atlas_live_research_service_windows.ps1')
TASK = 'ATLAS-Research-Sustained-Spot-WS'
LIMITS = 'Limits(rest_weight=2, raw_requests=61000, connections=4, ws_messages=5, subscriptions=1024)'
HEX = re.compile(r'[0-9a-f]{64}')


def need(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(path, *, exists=True):
    p = Path(path).absolute()
    need('..' not in p.parts, 'PATH_TRAVERSAL_DENIED')
    for node in (p, *p.parents):
        if node.exists() or node.is_symlink():
            s = node.lstat()
            need(not stat.S_ISLNK(s.st_mode) and not getattr(s, 'st_file_attributes', 0) &
                 getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024), 'PATH_LINK_DENIED')
    if exists:
        need(p.is_file() and p.stat().st_nlink == 1, 'PRIVATE_FILE_REQUIRED')
    return p


def read(path, maximum=MAX_JSON):
    p = safe(path)
    need(p.stat().st_size <= maximum, 'PRIVATE_FILE_BOUND')
    return p.read_bytes()


def pairs(values):
    out = {}
    for k, v in values:
        need(k not in out, 'DUPLICATE_JSON_KEY')
        out[k] = v
    return out


def load(path):
    return json.loads(read(path).decode('utf-8-sig'), object_pairs_hook=pairs)


def optional_pin(path):
    p = safe(path, exists=False)
    return digest(read(p)) if p.exists() else None


def quota_view(path, now):
    p = safe(path, exists=False)
    unavailable = dict(policy_verified=False, ready=False, scoped_connections=2,
                       shared_ip_headroom='UNVERIFIED_EXISTING_PILOT_ONLY')
    if not p.exists():
        return dict(unavailable, reason='QUOTA_EVIDENCE_MISSING')
    if Path(str(p)+'-wal').exists() or Path(str(p)+'-shm').exists():
        return dict(unavailable, reason='QUOTA_WAL_REQUIRES_REVIEW')
    p = safe(p)
    need(p.stat().st_size <= 32 * 1024 * 1024, 'QUOTA_FILE_BOUND')
    db = sqlite3.connect(p.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=0)
    try:
        db.execute('PRAGMA query_only=ON')
        need(db.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'delete', 'QUOTA_JOURNAL_MODE')
        need(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'QUOTA_INTEGRITY')
        limits = db.execute('SELECT limits FROM quota_config WHERE id=1').fetchone()
        need(limits is not None and limits[0] == LIMITS, 'QUOTA_POLICY_DRIFT')
        state = dict(db.execute('SELECT key,value FROM state'))
        sockets = db.execute('SELECT count(*) FROM sockets').fetchone()[0]
        recent = db.execute("SELECT COALESCE(sum(amount),0) FROM usage WHERE kind='connect' AND at>?", (now-300000,)).fetchone()[0]
        ready = (not state.get('ban', 0) and not state.get('pending', 0) and
                 state.get('ws_retry_at', 0) <= now and state.get('clock', 0) <= now and
                 sockets == 0 and recent < 2)
        return dict(policy_verified=True, socket_count=sockets, ban=bool(state.get('ban', 0)),
                    pending_request=bool(state.get('pending', 0)), ready=ready,
                    scoped_connections=2, shared_ip_headroom='UNVERIFIED_EXISTING_PILOT_ONLY')
    finally:
        db.close()


def verify_repo(repo, expected_commit):
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    need(head == expected_commit, 'CANDIDATE_COMMIT_MISMATCH')
    protected = (*CANDIDATES, 'tools/atlas_ws_resilience_operator.py', 'tools/atlas_ws_resilience_windows.ps1')
    for rel in protected:
        subprocess.run(['git', '-C', str(repo), 'ls-files', '--error-unmatch', rel],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    subprocess.run(['git', '-C', str(repo), 'diff', '--quiet', 'HEAD', '--', *protected], check=True)


def inspect(snapshot, repo, expected_commit, now):
    need(type(snapshot) is dict and snapshot.get('task_name') == TASK, 'TASK_IDENTITY')
    need(re.fullmatch('[0-9a-f]{40}', expected_commit), 'EXACT_COMMIT_REQUIRED')
    repo = Path(repo).absolute()
    verify_repo(repo, expected_commit)
    root = Path(snapshot['root']).absolute()
    safe(root, exists=False)
    cfgpath = safe(snapshot['config_path'])
    need(cfgpath.parent == root, 'CONFIG_ROOT_IDENTITY')
    config_raw = read(cfgpath)
    need(digest(config_raw) == snapshot['task_config_sha256'], 'CONFIG_PIN_MISMATCH')
    cfg = load(cfgpath)
    tree = Path(cfg['tree']).absolute()
    safe(tree, exists=False)
    service = safe(snapshot['service_path'])
    need(service.is_relative_to(root) or service.is_relative_to(tree), 'SUPERVISOR_PATH_SCOPE')
    python_path = Path(cfg['python'])
    python_path = python_path.absolute() if python_path.is_absolute() else None
    working = snapshot.get('task_action', {}).get('WorkingDirectory')
    working = Path(working) if type(working) is str and working else None
    working = working.absolute() if working is not None and working.is_absolute() else None
    runtime, rejected = [], []
    need(type(cfg.get('files')) is list and 1 <= len(cfg['files']) <= 4096, 'RUNTIME_MANIFEST_BOUND')
    seen = {}; runtime_bytes = 0; duplicate_bindings = 0
    for item in cfg['files']:
        need(type(item) is dict and type(item.get('path')) is str and
             type(item.get('sha256')) is str and HEX.fullmatch(item['sha256']), 'RUNTIME_MANIFEST_BINDING')
        raw_path = Path(item['path'])
        need('..' not in raw_path.parts, 'PATH_TRAVERSAL_DENIED')
        if not raw_path.is_absolute() and working is None:
            rejected.append(dict(path_sha256=digest(item['path'].encode('utf-8')),
                expected_sha256=item['sha256'], reason='RELATIVE_RUNTIME_PATH_UNRESOLVED'))
            continue
        p = raw_path.absolute() if raw_path.is_absolute() else (working/raw_path).absolute()
        key = os.path.normcase(str(p))
        if key in seen:
            need(seen[key] == item['sha256'], 'RUNTIME_DUPLICATE_PIN_CONFLICT')
            duplicate_bindings += 1
            continue
        seen[key] = item['sha256']
        if p.is_relative_to(tree):
            role, label = 'CODE_TREE', str(p.relative_to(tree)).replace('\\', '/')
        elif p == service:
            role, label = 'TASK_SUPERVISOR', '@TASK_SUPERVISOR'
        elif python_path is not None and p == python_path:
            role, label = 'TASK_INTERPRETER', '@TASK_INTERPRETER'
        else:
            # Do not read unrelated private files or turn their config entries
            # into authority. The authenticated manifest is retained unchanged.
            rejected.append(dict(path_sha256=digest(str(p).encode('utf-8')),
                expected_sha256=item['sha256'], reason='RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS'))
            continue
        p = safe(p)
        runtime_bytes += p.stat().st_size
        need(runtime_bytes <= 128*1024*1024, 'RUNTIME_TOTAL_BOUND')
        pin = digest(read(p))
        need(pin == item['sha256'], 'RUNTIME_PIN_MISMATCH')
        runtime.append(dict(path=label, scope=role, sha256=pin))
    manifest_scope = dict(bindings=len(cfg['files']), verified_unique_files=len(runtime),
        identical_duplicate_bindings=duplicate_bindings, unverified_bindings=rejected,
        verification_complete=not rejected)
    need(type(snapshot.get('task_xml_sha256')) is str and HEX.fullmatch(snapshot['task_xml_sha256']), 'TASK_XML_PIN')
    need(type(snapshot.get('task_xml')) is str and digest(snapshot['task_xml'].encode('utf-8')) == snapshot['task_xml_sha256'], 'TASK_XML_SNAPSHOT_MISMATCH')
    need(type(snapshot.get('task_policy_sha256')) is str and HEX.fullmatch(snapshot['task_policy_sha256']), 'TASK_POLICY_PIN')
    hold = load(root/'hold.json')
    need(hold.get('reason') in ('PILOT_STOP_TimeoutError', 'PILOT_STOP_ConnectionResetError'), 'HOLD_NOT_RESUMABLE')
    need(type(hold.get('slot_ms')) is int and hold['slot_ms'] % 900000 == 0, 'HOLD_SLOT_IDENTITY')
    rights = {k:cfg.get(k) for k in ('source_rights_ref','region_ref','authorization_ref')}
    need(all(type(v) is str and v.strip() for v in rights.values()), 'SOURCE_RIGHTS_REQUIRED')
    candidates = []
    for rel in CANDIDATES:
        p = repo/rel
        if p.exists():
            candidates.append(dict(path=rel, sha256=digest(read(p))))
    cycle = tree/'tools/atlas_live_research_cycle.py'
    identity = dict(schema='atlas.ws.operator-identity.v1', task_name=TASK,
                    task_xml_sha256=snapshot['task_xml_sha256'], task_policy_sha256=snapshot['task_policy_sha256'], config_sha256=digest(config_raw),
                    runtime=sorted(runtime, key=lambda r:r['path']), manifest_scope=manifest_scope,
                    cycle_sha256=digest(read(cycle)), supervisor_sha256=digest(read(service)),
                    hold_sha256=optional_pin(root/'hold.json'),
                    claimed_sha256=optional_pin(root/'reset-recovery.claimed'),
                    pending_sha256=optional_pin(root/'reset-recovery.pending'),
                    activation_sha256=optional_pin(root/'activation.json'),
                    source_rights_sha256=digest(canonical(rights)), candidate_commit=expected_commit,
                    candidates=candidates)
    try:
        quota = quota_view(root/'segments'/str(hold['slot_ms'])/'quota.sqlite', now)
    except (sqlite3.Error, ValueError) as exc:
        code = str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{1,119}',str(exc)) else 'QUOTA_EVIDENCE_INVALID'
        quota = dict(policy_verified=False, ready=False, reason=code, scoped_connections=2,
                     shared_ip_headroom='UNVERIFIED_EXISTING_PILOT_ONLY')
    blockers = sorted({r['reason'] for r in rejected})
    if snapshot.get('task_state') != 'Ready' or snapshot.get('task_enabled') is not True:
        blockers.append('TASK_NOT_QUIESCENT_READY')
    if snapshot.get('collector_processes') != 0:
        blockers.append('COMPETING_COLLECTOR_OR_PROCESS_INSPECTION_UNKNOWN')
    if snapshot.get('supervisor_lock_available') is not True:
        blockers.append('SUPERVISOR_LOCK_UNPROVEN')
    if (root/'segment-execution.active.json').exists():
        blockers.append('SEGMENT_EXECUTION_UNRESOLVED')
    if snapshot.get('operator_stop') is not False:
        blockers.append('OPERATOR_STOP_PRESENT_OR_UNKNOWN')
    if not quota['ready']:
        blockers.append('QUOTA_NOT_READY')
    if shutil.disk_usage(root).free < 128 * 1024 * 1024:
        blockers.append('DISK_RESERVE_LOW')
    return dict(schema='atlas.ws.operator-diagnostic.v1', status='HELD_REQUIRES_SEPARATE_OWNER_AUTHORIZATION',
                identity=identity, identity_sha256=digest(canonical(identity)), quota=quota,
                task_state=snapshot.get('task_state'), hold_reason=hold['reason'],
                hold_slot_ms=hold['slot_ms'], blockers=blockers, manifest_scope=manifest_scope, clock_probe='NOT_PERFORMED',
                source_class='LIVE_CAPTURE', retention='SANITIZED_RECEIPTS_ONLY',
                root_cause='ROOT_CAUSE_NOT_PROVEN', network_calls=0, writes=0,
                orders=0, trading_authority='NONE', real_pit_oos='BLOCKED')


def authorize(path, diagnostic, now, *, action='DEPLOY_ONE_RECOVERY'):
    raw = read(path, 65536); auth = load(path)
    need(auth.get('schema') == SCHEMA and auth.get('action') == action, 'OWNER_AUTHORIZATION_SCOPE')
    need(auth.get('identity_sha256') == diagnostic['identity_sha256'] and
         auth.get('candidate_commit') == diagnostic['identity']['candidate_commit'] and
         auth.get('task_name') == TASK, 'OWNER_AUTHORIZATION_IDENTITY')
    need(type(auth.get('issued_ms')) is int and type(auth.get('expires_ms')) is int and
         0 <= now-auth['issued_ms'] <= 1800000 and now < auth['expires_ms'] <= auth['issued_ms']+1800000,
         'OWNER_AUTHORIZATION_EXPIRED')
    need(auth.get('max_segments') == 1 and auth.get('max_connections') == 2 and
         type(auth.get('max_segments')) is int and type(auth.get('max_connections')) is int and
         auth.get('orders') == 0 and type(auth.get('orders')) is int and auth.get('trading_authority') == 'NONE' and
         auth.get('allow_task_action_pin_update') is True and auth.get('allow_clock_probe') is True and
         auth.get('existing_pilot_quota_only') is True and type(auth.get('owner_decision_ref')) is str and
         auth['owner_decision_ref'].strip(), 'OWNER_AUTHORIZATION_SCOPE')
    need(not diagnostic['blockers'], 'OWNER_HOST_PREFLIGHT_BLOCKED')
    return auth, digest(raw)


def durable(path, raw, *, create=False):
    p = safe(path, exists=False)
    if create:
        with p.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        return
    temp = p.with_name(p.name+'.stage-'+uuid.uuid4().hex)
    try:
        with temp.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, p)
    finally:
        if temp.exists(): temp.unlink()


@contextmanager
def collector_lease(root):
    path = safe(root/'segments/service-writer.sqlite', exists=False)
    db = sqlite3.connect(path, timeout=0)
    try:
        db.execute('BEGIN EXCLUSIVE')
        yield
    finally:
        db.rollback(); db.close()


def gate(snapshot, repo, commit, authorization_path, now, inp, out):
    """PS holds supervisor.lock. A dead gate leaves marker/HOLD and backup intact."""
    diagnostic = inspect(snapshot, repo, commit, now)
    auth, authpin = authorize(authorization_path, diagnostic, now)
    root = Path(snapshot['root']).absolute(); cfgpath = Path(snapshot['config_path']).absolute()
    cfg = load(cfgpath); tree = Path(cfg['tree']).absolute()
    clock = snapshot.get('clock', {})
    need(type(clock.get('checked_ms')) is int and 0 <= now-clock['checked_ms'] <= 60000 and
         type(clock.get('uncertainty_ms')) is int and 0 <= clock['uncertainty_ms'] <= 250, 'HOST_CLOCK_QUALIFICATION')
    marker = root/'operator-deployment.in-progress'
    need(not marker.exists() and not (root/'operator-resume.authorized.json').exists()
         and not (root/'operator-recovery.active.json').exists(), 'OPERATOR_STAGE_ALREADY_PRESENT')
    with collector_lease(root):
        safe(root/'operator-authorizations', exists=False).mkdir(exist_ok=True)
        durable(root/'operator-authorizations'/f'{authpin}.claimed', canonical(auth), create=True)
        backup = root/('ws-recovery-backup-'+uuid.uuid4().hex)
        backup.mkdir()
        durable(marker, canonical(dict(authorization_sha256=authpin, backup=str(backup))), create=True)
        files = []
        for rel in CANDIDATES:
            source = Path(repo)/rel
            if not source.exists(): continue
            targets = [tree/rel]
            if rel.endswith('atlas_live_research_service_windows.ps1'):
                targets.append(Path(snapshot['service_path']))
            for target in dict.fromkeys(p.absolute() for p in targets):
                safe(target, exists=False)
                need(target.is_relative_to(tree) or target == Path(snapshot['service_path']).absolute(), 'STAGING_PATH_SCOPE')
                existing = target.exists(); name=f'file-{len(files):04d}'
                if existing: durable(backup/name, read(target), create=True)
                files.append(dict(path=str(target), backup=name if existing else None,
                                  old_sha256=digest(read(target)) if existing else None,
                                  new_sha256=digest(read(source)), source=str(source)))
        original_config = read(cfgpath)
        durable(backup/'config.json', original_config, create=True)
        durable(backup/'task.xml', snapshot['task_xml'].encode('utf-8'), create=True)
        durable(backup/'task-action.json', canonical(snapshot['task_action']), create=True)
        for name in ('hold.json','reset-recovery.claimed','reset-recovery.pending','activation.json'):
            p=root/name
            if p.exists():durable(backup/name,read(p),create=True)
        manifest = dict(schema='atlas.ws.operator-backup.v1', files=files,
                        config_sha256=digest(original_config), identity_sha256=diagnostic['identity_sha256'],
                        authorization_sha256=authpin, config_path=str(cfgpath), task_name=TASK)
        durable(backup/'manifest.json',canonical(manifest),create=True)
        try:
            for item in files:
                p=Path(item['path']);p.parent.mkdir(parents=True,exist_ok=True)
                durable(p,read(item['source']))
            by_path = {}
            working = snapshot.get('task_action', {}).get('WorkingDirectory')
            for binding in cfg['files']:
                target = Path(binding['path'])
                if not target.is_absolute():
                    need(type(working) is str and Path(working).is_absolute(), 'RELATIVE_RUNTIME_PATH_UNRESOLVED')
                    target = Path(working)/target
                by_path.setdefault(os.path.normcase(str(target.absolute())), []).append(binding)
            for item in files:
                key = os.path.normcase(item['path'])
                if key in by_path:
                    for binding in by_path[key]:binding['sha256'] = item['new_sha256']
                else:
                    cfg['files'].append(dict(path=item['path'],sha256=item['new_sha256']))
            durable(cfgpath,canonical(cfg));newpin=digest(read(cfgpath))
            active=root/'activation.json'
            if active.exists():
                a=load(active);need(a.get('config_sha256')==diagnostic['identity']['config_sha256'],'ACTIVATION_PIN_MISMATCH')
                a['config_sha256']=newpin;durable(active,canonical(a))
            print(json.dumps(dict(status='STAGED_AWAITING_TASK_PIN',config_sha256=newpin)),file=out,flush=True)
            answer=inp.readline().strip()
            if answer != 'COMMIT':
                need(answer=='ROLLBACK','OPERATOR_GATE_INTERRUPTED_REVIEW_BACKUP')
                rollback_stage(root,backup,manifest)
                print(json.dumps(dict(status='STAGING_ROLLED_BACK_HOLD_PRESERVED',backup=backup.name)),file=out,flush=True)
                return
            # The wrapper has verified exact action-only task pin readback.
            now2=time.time_ns()//1000000
            need(now2<auth['expires_ms'],'OWNER_AUTHORIZATION_EXPIRED_DURING_STAGE')
            ticket=dict(schema='atlas.ws.operator-resume.v1',authorization_sha256=authpin,
                config_sha256=newpin,hold_sha256=diagnostic['identity']['hold_sha256'],
                claimed_sha256=diagnostic['identity']['claimed_sha256'],pending_sha256=diagnostic['identity']['pending_sha256'],
                issued_ms=now2,expires_ms=min(auth['expires_ms'],now2+1800000),max_segments=1,
                max_connections=2,orders=0,trading_authority='NONE')
            durable(root/'operator-resume.authorized.json',canonical(ticket),create=True)
            marker.rename(backup/'deployment-marker.completed.json')
            receipt=dict(schema='atlas.ws.operator-deployment-receipt.v1',
                status='WS_ENGINEERING_INSTALLED_ONE_RECOVERY_WAITING_FOR_EXISTING_SCHEDULE',
                candidate_commit=commit,authorization_sha256=authpin,config_sha256=newpin,
                prior_identity_sha256=diagnostic['identity_sha256'],backup_manifest_sha256=digest(read(backup/'manifest.json')),
                backup=backup.name,hold_preserved=True,claims_preserved=True,task_started=False,
                task_schedule_changes=0,task_principal_changes=0,source_acquisition_calls=0,
                task_action_pin_readback=True,clock_checked_ms=clock['checked_ms'],
                clock_uncertainty_ms=clock['uncertainty_ms'],
                max_segments=1,max_connections=2,orders=0,trading_authority='NONE',
                host_reconnection='NOT_ATTESTED',root_cause='ROOT_CAUSE_NOT_PROVEN')
            durable(backup/'deployment-receipt.json',canonical(receipt),create=True)
            print(json.dumps(receipt),file=out,flush=True)
        except BaseException:
            # An uncertain task-pin state cannot be rolled back automatically.
            # The marker and exact backup preserve a fail-closed recovery path.
            raise


def rollback_stage(root,backup,manifest):
    """Only called while both locks are held and PS restored its old action."""
    for item in reversed(manifest['files']):
        p=Path(item['path']);need(digest(read(p))==item['new_sha256'],'ROLLBACK_RUNTIME_DRIFT')
        if item['backup'] is not None:
            raw=read(backup/item['backup']);need(digest(raw)==item['old_sha256'],'ROLLBACK_BACKUP_PIN')
            durable(p,raw)
        else:
            # Preserve newly introduced files rather than deleting evidence.
            p.rename(backup/(p.name+'.unused-candidate'))
    raw=read(backup/'config.json');need(digest(raw)==manifest['config_sha256'],'ROLLBACK_CONFIG_PIN')
    durable(manifest['config_path'],raw)
    if (backup/'activation.json').exists():durable(root/'activation.json',read(backup/'activation.json'))
    (root/'operator-deployment.in-progress').rename(backup/'deployment-marker.rolled-back.json')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('diagnose','authorize','gate'))
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--expected-commit',required=True)
    p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    # .NET Framework may emit one UTF-8 stream preamble when its native
    # StandardInput writer is first opened. Preserve JSON values exactly.
    raw=sys.stdin.buffer.readline(MAX_JSON+1);need(len(raw)<=MAX_JSON,'SNAPSHOT_BOUND')
    snapshot=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs);now=time.time_ns()//1000000
    if a.mode=='gate':
        need(a.authorization is not None,'SEPARATE_OWNER_AUTHORIZATION_REQUIRED')
        gate(snapshot,a.repo,a.expected_commit,a.authorization,now,sys.stdin,sys.stdout)
    else:
        result=inspect(snapshot,a.repo,a.expected_commit,now)
        if a.mode=='authorize':
            need(a.authorization is not None,'SEPARATE_OWNER_AUTHORIZATION_REQUIRED')
            _,pin=authorize(a.authorization,result,now)
            result=dict(status='EXPLICIT_OWNER_AUTHORIZATION_VERIFIED',authorization_sha256=pin)
        print(json.dumps(result,sort_keys=True),flush=True)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,sqlite3.Error,subprocess.SubprocessError,KeyError,TypeError,json.JSONDecodeError) as exc:
        # Never publish host paths, task args, raw market bytes or exception text.
        print(json.dumps(dict(status='WS_OPERATOR_BLOCKED',reason=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{1,119}',str(exc)) else 'PRIVATE_IO_SCHEMA_OR_LEASE_FAILURE',
                              hold_preserved=True,orders=0,trading_authority='NONE')),flush=True)
        raise SystemExit(2)
