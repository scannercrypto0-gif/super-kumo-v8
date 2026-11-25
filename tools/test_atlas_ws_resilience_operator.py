"""No host, scheduler, subprocess collector or network execution in these tests."""
from contextlib import closing
from io import StringIO
import json
from pathlib import Path
import sqlite3
import time

import pytest

from tools import atlas_ws_resilience_operator as op

COMMIT='a'*40
SLOT=1795259700000


@pytest.fixture
def host(tmp_path,monkeypatch):
    repo=tmp_path/'candidate';root=tmp_path/'owner';tree=root/'runtime'
    (repo/'tools').mkdir(parents=True);(tree/'tools').mkdir(parents=True)
    files=[]
    for rel in op.CANDIDATES:
        (repo/rel).write_text('new '+rel)
        (tree/rel).write_text('old '+rel)
        files.append(dict(path=str(tree/rel),sha256=op.digest((tree/rel).read_bytes())))
    config=root/'config.json'
    config.write_bytes(op.canonical(dict(tree=str(tree),python='python',files=files,
        source_rights_ref='PRIVATE_SOURCE_RIGHT',region_ref='PRIVATE_REGION',authorization_ref='PRIVATE_NETWORK')))
    (root/'supervisor.ps1').write_text('old service entry')
    (root/'hold.json').write_bytes(op.canonical(dict(reason='PILOT_STOP_TimeoutError',slot_ms=SLOT)))
    (root/'reset-recovery.claimed').write_bytes(b'{"claim":"prior automatic successor"}')
    (root/'activation.json').write_bytes(op.canonical(dict(config_sha256=op.digest(config.read_bytes()))))
    q=root/'segments'/str(SLOT)/'quota.sqlite';q.parent.mkdir(parents=True)
    with closing(sqlite3.connect(q)) as db, db:
        db.execute('CREATE TABLE quota_config(id INTEGER PRIMARY KEY,limits TEXT)')
        db.execute('INSERT INTO quota_config VALUES(1,?)',(op.LIMITS,))
        db.execute('CREATE TABLE state(key TEXT PRIMARY KEY,value INTEGER)')
        db.execute('CREATE TABLE sockets(id TEXT)')
        db.execute('CREATE TABLE usage(kind TEXT,at INTEGER,amount INTEGER)')
    (root/'supervisor.lock').write_bytes(b'')
    now=time.time_ns()//1000000
    snapshot=dict(task_name=op.TASK,task_state='Ready',task_enabled=True,task_xml='<Task private="yes"/>',
        task_xml_sha256=op.digest(b'<Task private="yes"/>'),task_policy_sha256='c'*64,task_config_sha256=op.digest(config.read_bytes()),task_action=dict(Execute='pwsh',Arguments='PRIVATE_ARGUMENTS'),
        config_path=str(config),root=str(root),service_path=str(root/'supervisor.ps1'),
        collector_processes=0,supervisor_lock_available=True,operator_stop=False,
        clock=dict(checked_ms=now,uncertainty_ms=100))
    monkeypatch.setattr(op,'verify_repo',lambda *a:None)
    monkeypatch.setattr(op.time,'time_ns',lambda:now*1000000)
    return dict(repo=repo,root=root,tree=tree,config=config,snapshot=snapshot,now=now)


def diagnostic(host):
    return op.inspect(host['snapshot'],host['repo'],COMMIT,host['now'])


def authorization(host,**overrides):
    d=diagnostic(host);a=dict(schema=op.SCHEMA,action='DEPLOY_ONE_RECOVERY',identity_sha256=d['identity_sha256'],
        candidate_commit=COMMIT,task_name=op.TASK,issued_ms=host['now'],expires_ms=host['now']+1800000,
        max_segments=1,max_connections=2,orders=0,trading_authority='NONE',allow_task_action_pin_update=True,
        allow_clock_probe=True,existing_pilot_quota_only=True,owner_decision_ref='PRIVATE_EXPLICIT_OWNER_REF')
    a.update(overrides);path=host['root'].parent/'explicit-owner-authorization.json';path.write_bytes(op.canonical(a))
    return path


def bytes_inventory(path):
    return {str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file()}


def test_diagnose_reads_only_and_excludes_private_strings(host):
    before=bytes_inventory(host['root']);r=diagnostic(host)
    assert bytes_inventory(host['root'])==before and r['writes']==r['network_calls']==0
    assert r['blockers']==[] and r['quota']['ready'] and r['hold_reason']=='PILOT_STOP_TimeoutError'
    text=json.dumps(r)
    assert 'PRIVATE_SOURCE_RIGHT' not in text and 'PRIVATE_ARGUMENTS' not in text and 'PRIVATE_NETWORK' not in text
    assert r['root_cause']=='ROOT_CAUSE_NOT_PROVEN'


@pytest.mark.parametrize('field,value,code',[
    ('action','ARBITRARY_RESTART','OWNER_AUTHORIZATION_SCOPE'),
    ('identity_sha256','0'*64,'OWNER_AUTHORIZATION_IDENTITY'),
    ('candidate_commit','f'*40,'OWNER_AUTHORIZATION_IDENTITY'),
    ('expires_ms',0,'OWNER_AUTHORIZATION_EXPIRED'),
    ('max_connections',3,'OWNER_AUTHORIZATION_SCOPE'),
    ('max_segments',True,'OWNER_AUTHORIZATION_SCOPE'),
    ('orders',False,'OWNER_AUTHORIZATION_SCOPE'),
    ('allow_task_action_pin_update',False,'OWNER_AUTHORIZATION_SCOPE'),
    ('allow_clock_probe',False,'OWNER_AUTHORIZATION_SCOPE'),
])
def test_explicit_authorization_is_exact_and_scoped(host,field,value,code):
    p=authorization(host,**{field:value})
    with pytest.raises(ValueError,match=code):op.authorize(p,diagnostic(host),host['now'])


@pytest.mark.parametrize('field,value,blocker',[
    ('task_state','Running','TASK_NOT_QUIESCENT_READY'),
    ('collector_processes',1,'COMPETING_COLLECTOR'),
    ('supervisor_lock_available',False,'SUPERVISOR_LOCK_UNPROVEN'),
    ('operator_stop',True,'OPERATOR_STOP_PRESENT'),
])
def test_active_or_unknown_host_cannot_deploy(host,field,value,blocker):
    host['snapshot'][field]=value
    assert any(blocker in item for item in diagnostic(host)['blockers'])
    p=authorization(host)
    with pytest.raises(ValueError,match='OWNER_HOST_PREFLIGHT_BLOCKED'):op.authorize(p,diagnostic(host),host['now'])


def test_runtime_or_hold_tamper_is_rejected(host):
    (host['tree']/op.CANDIDATES[0]).write_text('tampered')
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_quota_ban_and_policy_drift_block(host):
    q=host['root']/'segments'/str(SLOT)/'quota.sqlite'
    with closing(sqlite3.connect(q)) as db, db:db.execute("INSERT INTO state VALUES('ban',1)")
    assert diagnostic(host)['quota']['ban'] and 'QUOTA_NOT_READY' in diagnostic(host)['blockers']
    with closing(sqlite3.connect(q)) as db, db:db.execute("UPDATE quota_config SET limits='relaxed'")
    assert diagnostic(host)['quota']['reason']=='QUOTA_POLICY_DRIFT'
    assert 'QUOTA_NOT_READY' in diagnostic(host)['blockers']


def test_apply_stages_pins_and_one_use_ticket_without_clearing_hold(host):
    p=authorization(host);held=(host['root']/'hold.json').read_bytes();claimed=(host['root']/'reset-recovery.claimed').read_bytes()
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),out)
    lines=[json.loads(x) for x in out.getvalue().splitlines()]
    assert lines[0]['status']=='STAGED_AWAITING_TASK_PIN'
    receipt=lines[1];assert receipt['task_started'] is False and receipt['max_segments']==1
    ticket=op.load(host['root']/'operator-resume.authorized.json')
    assert ticket['schema']=='atlas.ws.operator-resume.v1' and ticket['max_connections']==2
    assert ticket['hold_sha256']==op.digest(held) and ticket['claimed_sha256']==op.digest(claimed)
    assert ticket['config_sha256']==op.digest(host['config'].read_bytes())
    assert (host['root']/'hold.json').read_bytes()==held and (host['root']/'reset-recovery.claimed').read_bytes()==claimed
    assert not (host['root']/'operator-deployment.in-progress').exists()
    backup=host['root']/receipt['backup'];assert op.digest((backup/'manifest.json').read_bytes())==receipt['backup_manifest_sha256']
    assert (backup/'hold.json').read_bytes()==held and (backup/'task.xml').exists()
    assert len(list((host['root']/'operator-authorizations').glob('*.claimed')))==1


def test_wrapper_failure_rolls_back_runtime_config_and_preserves_evidence(host):
    p=authorization(host);before={str(path):path.read_bytes() for path in (host['config'],host['root']/'supervisor.ps1',*(host['tree']/r for r in op.CANDIDATES))}
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('ROLLBACK\n'),out)
    assert all(Path(path).read_bytes()==raw for path,raw in before.items())
    assert json.loads(out.getvalue().splitlines()[-1])['status']=='STAGING_ROLLED_BACK_HOLD_PRESERVED'
    assert not (host['root']/'operator-resume.authorized.json').exists()
    assert (host['root']/'hold.json').exists() and (host['root']/'reset-recovery.claimed').exists()


def test_process_crash_before_wrapper_ack_keeps_marker_hold_and_backup(host):
    p=authorization(host)
    with pytest.raises(ValueError,match='OPERATOR_GATE_INTERRUPTED'):
        op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO(''),StringIO())
    assert (host['root']/'operator-deployment.in-progress').exists()
    assert (host['root']/'hold.json').exists() and not (host['root']/'operator-resume.authorized.json').exists()
    assert list(host['root'].glob('ws-recovery-backup-*/manifest.json'))


def test_collector_lease_conflict_prevents_any_deployment_write(host):
    p=authorization(host);lock=host['root']/'segments/service-writer.sqlite'
    db=sqlite3.connect(lock);db.execute('BEGIN EXCLUSIVE');before=bytes_inventory(host['root'])
    try:
        with pytest.raises(sqlite3.OperationalError):
            op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())
        assert bytes_inventory(host['root'])==before
    finally:db.rollback();db.close()


def test_existing_operator_claim_rejects_second_apply(host):
    p=authorization(host);(host['root']/'operator-recovery.active.json').write_bytes(b'{}')
    with pytest.raises(ValueError,match='OPERATOR_STAGE_ALREADY_PRESENT|OWNER_AUTHORIZATION_IDENTITY'):
        op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())


def test_path_links_and_parent_traversal_are_not_accepted(tmp_path):
    target=tmp_path/'real';target.write_bytes(b'x');link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(ValueError,match='PATH_LINK_DENIED'):op.read(link)
    with pytest.raises(ValueError,match='PATH_TRAVERSAL_DENIED'):op.read(tmp_path/'sub'/'..'/'real')


def test_missing_and_wal_quota_evidence_never_creates_sidecars(host):
    q=host['root']/'segments'/str(SLOT)/'quota.sqlite'
    original=q.read_bytes();q.unlink()
    before=bytes_inventory(host['root'])
    assert diagnostic(host)['quota']['reason']=='QUOTA_EVIDENCE_MISSING'
    assert bytes_inventory(host['root'])==before
    q.write_bytes(original);wal=Path(str(q)+'-wal');wal.write_bytes(b'private wal bytes')
    before=bytes_inventory(host['root'])
    assert diagnostic(host)['quota']['reason']=='QUOTA_WAL_REQUIRES_REVIEW'
    assert bytes_inventory(host['root'])==before


def test_unresolved_normal_segment_claim_is_not_archived_or_bypassed(host):
    marker=host['root']/'segment-execution.active.json';marker.write_bytes(b'{"orphan":"preserve"}')
    before=marker.read_bytes();assert 'SEGMENT_EXECUTION_UNRESOLVED' in diagnostic(host)['blockers']
    p=authorization(host)
    with pytest.raises(ValueError,match='OWNER_HOST_PREFLIGHT_BLOCKED'):
        op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())
    assert marker.read_bytes()==before


def test_task_xml_snapshot_pin_mismatch_is_not_accepted(host):
    host['snapshot']['task_xml']='different task or schedule'
    with pytest.raises(ValueError,match='TASK_XML_SNAPSHOT_MISMATCH'):diagnostic(host)


def test_diagnostic_main_preserves_utf8_bom_task_xml_identity(host,monkeypatch,capsys):
    from io import BytesIO,TextIOWrapper
    import sys
    host['snapshot']['task_xml']='<Task>'+''.join(chr(x) for x in (0x0623,0x03a9,0x4e2d))+'</Task>'
    host['snapshot']['task_xml_sha256']=op.digest(host['snapshot']['task_xml'].encode('utf-8'))
    wire=b'\xef\xbb\xbf'+json.dumps(host['snapshot'],ensure_ascii=False).encode('utf-8')+b'\n'
    monkeypatch.setattr(sys,'stdin',TextIOWrapper(BytesIO(wire),encoding='utf-8'))
    monkeypatch.setattr(sys,'argv',['operator','diagnose','--repo',str(host['repo']),'--expected-commit',COMMIT])
    before=bytes_inventory(host['root']);op.main()
    result=json.loads(capsys.readouterr().out)
    assert result['identity']['task_xml_sha256']==host['snapshot']['task_xml_sha256']
    assert result['writes']==result['network_calls']==0 and bytes_inventory(host['root'])==before


def test_stream_preamble_does_not_relax_duplicate_key_rejection(monkeypatch):
    from io import BytesIO,TextIOWrapper
    import sys
    monkeypatch.setattr(sys,'stdin',TextIOWrapper(BytesIO(b'\xef\xbb\xbf{"task_name":"a","task_name":"b"}\n'),encoding='utf-8'))
    monkeypatch.setattr(sys,'argv',['operator','diagnose','--repo','.','--expected-commit',COMMIT])
    with pytest.raises(ValueError,match='DUPLICATE_JSON_KEY'):op.main()


def pinned_manifest(host, extra=(), *, relative_first=False, python=None):
    cfg=op.load(host['config'])
    cfg['files'].extend(dict(x) for x in extra)
    if relative_first:cfg['files'][0]['path']=str(Path(cfg['files'][0]['path']).relative_to(host['tree']))
    if python is not None:cfg['python']=str(python)
    host['config'].write_bytes(op.canonical(cfg))
    pin=op.digest(host['config'].read_bytes());host['snapshot']['task_config_sha256']=pin
    (host['root']/'activation.json').write_bytes(op.canonical(dict(config_sha256=pin)))
    return cfg


def test_pinned_task_supervisor_outside_tree_is_a_named_anchor_read_only(host):
    service=Path(host['snapshot']['service_path'])
    pinned_manifest(host,[dict(path=str(service),sha256=op.digest(service.read_bytes()))])
    before=bytes_inventory(host['root']);r=diagnostic(host)
    assert r['blockers']==[] and r['manifest_scope']['verification_complete']
    assert any(x['scope']=='TASK_SUPERVISOR' and x['path']=='@TASK_SUPERVISOR' for x in r['identity']['runtime'])
    assert bytes_inventory(host['root'])==before


def test_unknown_external_binding_is_not_read_or_granted_authority(host,monkeypatch):
    external=host['root']/'unrelated-private-file.dat';external.write_bytes(b'PRIVATE_UNKNOWN_CONTENT')
    pinned_manifest(host,[dict(path=str(external),sha256=op.digest(external.read_bytes()))])
    original=op.read
    def guarded(path,*a,**kw):
        assert Path(path)!=external,'UNAPPROVED_EXTERNAL_FILE_READ'
        return original(path,*a,**kw)
    monkeypatch.setattr(op,'read',guarded);before=bytes_inventory(host['root']);r=diagnostic(host)
    assert 'RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS' in r['blockers']
    assert not r['manifest_scope']['verification_complete']
    assert str(external) not in json.dumps(r) and 'PRIVATE_UNKNOWN_CONTENT' not in json.dumps(r)
    assert bytes_inventory(host['root'])==before
    with pytest.raises(ValueError,match='OWNER_HOST_PREFLIGHT_BLOCKED'):
        op.authorize(authorization(host),r,host['now'])


def test_identical_manifest_duplicates_are_idempotent_not_rewritten(host):
    first=op.load(host['config'])['files'][0]
    pinned_manifest(host,[first]);before=bytes_inventory(host['root']);r=diagnostic(host)
    assert r['manifest_scope']['identical_duplicate_bindings']==1 and not r['blockers']
    assert r['manifest_scope']['verified_unique_files']==len(op.CANDIDATES)
    assert bytes_inventory(host['root'])==before


def test_conflicting_duplicate_manifest_pin_is_terminal(host):
    first=op.load(host['config'])['files'][0]
    pinned_manifest(host,[{**first,'sha256':'0'*64}])
    with pytest.raises(ValueError,match='RUNTIME_DUPLICATE_PIN_CONFLICT'):diagnostic(host)


def test_only_exact_declared_interpreter_is_an_external_anchor(host):
    interpreter=host['root'].parent/'private-python.exe';interpreter.write_bytes(b'generated interpreter fixture')
    pinned_manifest(host,[dict(path=str(interpreter),sha256=op.digest(interpreter.read_bytes()))],python=interpreter)
    r=diagnostic(host)
    assert not r['blockers'] and any(x['scope']=='TASK_INTERPRETER' for x in r['identity']['runtime'])
    sibling=interpreter.with_name('other-executable.exe');sibling.write_bytes(b'unrelated')
    pinned_manifest(host,[dict(path=str(sibling),sha256=op.digest(sibling.read_bytes()))])
    assert 'RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS' in diagnostic(host)['blockers']


def test_apply_updates_supervisor_and_every_identical_binding_pin(host):
    first=op.load(host['config'])['files'][0];service=Path(host['snapshot']['service_path'])
    pinned_manifest(host,[first,dict(path=str(service),sha256=op.digest(service.read_bytes()))])
    p=authorization(host);out=StringIO()
    op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),out)
    cfg=op.load(host['config'])
    # Existing supervisor preflight hashes every binding, including duplicates.
    assert all(op.digest(Path(x['path']).read_bytes())==x['sha256'] for x in cfg['files'])
    assert (host['root']/'hold.json').exists()
    assert op.load(host['root']/'operator-resume.authorized.json')['max_segments']==1


def test_relative_binding_uses_exact_task_working_directory(host):
    host['snapshot']['task_action']['WorkingDirectory']=str(host['tree'])
    pinned_manifest(host,relative_first=True)
    assert not diagnostic(host)['blockers']
    p=authorization(host);op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())
    cfg=op.load(host['config'])
    for x in cfg['files']:
        path=Path(x['path']);path=path if path.is_absolute() else host['tree']/path
        assert op.digest(path.read_bytes())==x['sha256']


def test_relative_binding_without_declared_workdir_does_not_guess_cwd(host):
    pinned_manifest(host,relative_first=True)
    r=diagnostic(host)
    assert r['manifest_scope']['unverified_bindings'][0]['reason']=='RELATIVE_RUNTIME_PATH_UNRESOLVED'
    assert not r['manifest_scope']['verification_complete'] and r['blockers']


def test_supervisor_named_anchor_still_requires_original_hash(host):
    service=Path(host['snapshot']['service_path'])
    pinned_manifest(host,[dict(path=str(service),sha256='0'*64)])
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_task_shell_exact_anchor_requires_its_pin(host):
    shell=host['root'].parent/'pwsh.exe';shell.write_bytes(b'exact installed task shell')
    sibling=shell.with_name('other.exe');sibling.write_bytes(b'not an anchor')
    host['snapshot']['task_action']['Execute']=str(shell)
    cfg=op.load(host['config']);cfg['files'].extend([
        dict(path=str(shell),sha256=op.digest(shell.read_bytes())),
        dict(path=str(sibling),sha256=op.digest(sibling.read_bytes()))])
    host['config'].write_bytes(op.canonical(cfg))
    host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    result=diagnostic(host)
    assert any(r['scope']=='TASK_SHELL' for r in result['identity']['runtime'])
    assert len(result['manifest_scope']['unverified_bindings'])==1
    shell.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_relative_task_shell_does_not_guess_search_path(host):
    shell=host['root'].parent/'pwsh.exe';shell.write_bytes(b'shell')
    host['snapshot']['task_action']['Execute']='pwsh.exe'
    cfg=op.load(host['config']);cfg['files'].append(dict(path=str(shell),sha256=op.digest(shell.read_bytes())))
    host['config'].write_bytes(op.canonical(cfg));host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    assert diagnostic(host)['blockers']==['RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS']


def test_known_legacy_supervisor_is_verified_without_staging_authority(host,monkeypatch):
    raw=b'known retained supervisor fixture'
    monkeypatch.setattr(op,'LEGACY_SUPERVISOR_SHA256',op.digest(raw))
    legacy=host['root']/'supervisor.ps1';legacy.write_bytes(raw)
    # Actual task points at the runtime-tree supervisor; legacy stays retained.
    host['snapshot']['service_path']=str(host['tree']/'tools/atlas_live_research_service_windows.ps1')
    cfg=op.load(host['config']);cfg['files'].append(dict(path=str(legacy),sha256=op.digest(raw)))
    host['config'].write_bytes(op.canonical(cfg));host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    d=diagnostic(host)
    assert not d['blockers']
    assert any(r['scope']=='RETAINED_LEGACY_SUPERVISOR' for r in d['identity']['runtime'])
    legacy.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_unknown_legacy_supervisor_pin_is_not_an_anchor(host):
    legacy=host['root']/'supervisor.ps1'
    host['snapshot']['service_path']=str(host['tree']/'tools/atlas_live_research_service_windows.ps1')
    cfg=op.load(host['config']);cfg['files'].append(dict(path=str(legacy),sha256=op.digest(legacy.read_bytes())))
    host['config'].write_bytes(op.canonical(cfg));host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    assert diagnostic(host)['blockers']==['RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS']


def test_continuous_permit_requires_policy_and_explicit_gap_scope(host):
    p=authorization(host,continuous_research=True)
    with pytest.raises(ValueError,match='CONTINUITY_POLICY_AUTHORIZATION'):
        op.authorize(p,diagnostic(host),host['now'])
    p=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    assert op.authorize(p,diagnostic(host),host['now'])[0]['continuous_research'] is True


def test_continuous_stage_archives_consumed_claim_and_installs_policy(host):
    from io import StringIO
    claim=host['root']/'operator-recovery.active.json';claim.write_bytes(b'original consumed one-shot')
    before=claim.read_bytes()
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,permit,host['now'],StringIO('COMMIT\n'),out)
    rows=[json.loads(s) for s in out.getvalue().splitlines()]
    r=rows[-1]
    assert r['continuous_research'] is True
    assert not claim.exists()
    assert (host['root']/r['backup']/'prior-operator-recovery.archived.json').read_bytes()==before
    policy=op.load(host['root']/'continuous-research.authorized.json')
    assert policy['policy_sha256']==op.continuity_pin() and policy['config_sha256']==r['config_sha256']
    assert (host['root']/'hold.json').exists()


def test_continuous_rejected_precommit_rolls_back_without_new_authority(host):
    claim=host['root']/'operator-recovery.active.json';claim.write_bytes(b'original claim')
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    old=bytes_inventory(host['tree'])
    op.gate(host['snapshot'],host['repo'],COMMIT,permit,host['now'],StringIO('ROLLBACK\n'),StringIO())
    assert bytes_inventory(host['tree'])==old and claim.read_bytes()==b'original claim'
    assert not (host['root']/'continuous-research.authorized.json').exists()


def test_claim_preserves_exact_noncanonical_powershell_authorization_bytes(host):
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    a=op.load(permit)
    a['owner_decision_ref']='owner-approved-تصريح'
    raw=json.dumps(a,indent=2,ensure_ascii=False).encode('utf-8')
    assert raw!=op.canonical(a)
    permit.write_bytes(raw)
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,permit,host['now'],StringIO('COMMIT\n'),out)
    result=json.loads(out.getvalue().splitlines()[-1])
    claimed=host['root']/'operator-authorizations'/(result['authorization_sha256']+'.claimed')
    assert claimed.read_bytes()==raw
    assert op.digest(claimed.read_bytes())==result['authorization_sha256']
    from tools.atlas_ws_continuity import authority
    assert authority(host['root'],result['config_sha256'])


@pytest.mark.parametrize('reason',['LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN','PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED'])
def test_special_hold_requires_explicit_fresh_ping_correction_scope(host,reason):
    (host['root']/'hold.json').write_bytes(op.canonical(dict(reason=reason,slot_ms=SLOT)))
    p=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    with pytest.raises(ValueError,match='FRESH_PING_CORRECTION_AUTHORITY_REQUIRED'):op.authorize(p,diagnostic(host),host['now'])


@pytest.mark.parametrize('reason',['LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN','PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED'])
def test_fresh_ping_rollout_preserves_prior_grant_and_existing_policy(host,monkeypatch,reason):
    old=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    op.gate(host['snapshot'],host['repo'],COMMIT,old,host['now'],StringIO('COMMIT\n'),StringIO())
    grant=host['root']/'continuous-research.authorized.json';prior=grant.read_bytes()
    (host['root']/'operator-resume.authorized.json').unlink()
    """No host, scheduler, subprocess collector or network execution in these tests."""
from contextlib import closing
from io import StringIO
import json
from pathlib import Path
import sqlite3
import time

import pytest

from tools import atlas_ws_resilience_operator as op

COMMIT='a'*40
SLOT=1795259700000


@pytest.fixture
def host(tmp_path,monkeypatch):
    repo=tmp_path/'candidate';root=tmp_path/'owner';tree=root/'runtime'
    (repo/'tools').mkdir(parents=True);(tree/'tools').mkdir(parents=True)
    files=[]
    for rel in op.CANDIDATES:
        (repo/rel).write_text('new '+rel)
        (tree/rel).write_text('old '+rel)
        files.append(dict(path=str(tree/rel),sha256=op.digest((tree/rel).read_bytes())))
    config=root/'config.json'
    config.write_bytes(op.canonical(dict(tree=str(tree),python='python',files=files,
        source_rights_ref='PRIVATE_SOURCE_RIGHT',region_ref='PRIVATE_REGION',authorization_ref='PRIVATE_NETWORK')))
    (root/'supervisor.ps1').write_text('old service entry')
    (root/'hold.json').write_bytes(op.canonical(dict(reason='PILOT_STOP_TimeoutError',slot_ms=SLOT)))
    (root/'reset-recovery.claimed').write_bytes(b'{"claim":"prior automatic successor"}')
    (root/'activation.json').write_bytes(op.canonical(dict(config_sha256=op.digest(config.read_bytes()))))
    q=root/'segments'/str(SLOT)/'quota.sqlite';q.parent.mkdir(parents=True)
    with closing(sqlite3.connect(q)) as db, db:
        db.execute('CREATE TABLE quota_config(id INTEGER PRIMARY KEY,limits TEXT)')
        db.execute('INSERT INTO quota_config VALUES(1,?)',(op.LIMITS,))
        db.execute('CREATE TABLE state(key TEXT PRIMARY KEY,value INTEGER)')
        db.execute('CREATE TABLE sockets(id TEXT)')
        db.execute('CREATE TABLE usage(kind TEXT,at INTEGER,amount INTEGER)')
    (root/'supervisor.lock').write_bytes(b'')
    now=time.time_ns()//1000000
    snapshot=dict(task_name=op.TASK,task_state='Ready',task_enabled=True,task_xml='<Task private="yes"/>',
        task_xml_sha256=op.digest(b'<Task private="yes"/>'),task_policy_sha256='c'*64,task_config_sha256=op.digest(config.read_bytes()),task_action=dict(Execute='pwsh',Arguments='PRIVATE_ARGUMENTS'),
        config_path=str(config),root=str(root),service_path=str(root/'supervisor.ps1'),
        collector_processes=0,supervisor_lock_available=True,operator_stop=False,
        clock=dict(checked_ms=now,uncertainty_ms=100))
    monkeypatch.setattr(op,'verify_repo',lambda *a:None)
    monkeypatch.setattr(op.time,'time_ns',lambda:now*1000000)
    return dict(repo=repo,root=root,tree=tree,config=config,snapshot=snapshot,now=now)


def diagnostic(host):
    return op.inspect(host['snapshot'],host['repo'],COMMIT,host['now'])


def authorization(host,**overrides):
    d=diagnostic(host);a=dict(schema=op.SCHEMA,action='DEPLOY_ONE_RECOVERY',identity_sha256=d['identity_sha256'],
        candidate_commit=COMMIT,task_name=op.TASK,issued_ms=host['now'],expires_ms=host['now']+1800000,
        max_segments=1,max_connections=2,orders=0,trading_authority='NONE',allow_task_action_pin_update=True,
        allow_clock_probe=True,existing_pilot_quota_only=True,owner_decision_ref='PRIVATE_EXPLICIT_OWNER_REF')
    a.update(overrides);path=host['root'].parent/'explicit-owner-authorization.json';path.write_bytes(op.canonical(a))
    return path


def bytes_inventory(path):
    return {str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file()}


def test_diagnose_reads_only_and_excludes_private_strings(host):
    before=bytes_inventory(host['root']);r=diagnostic(host)
    assert bytes_inventory(host['root'])==before and r['writes']==r['network_calls']==0
    assert r['blockers']==[] and r['quota']['ready'] and r['hold_reason']=='PILOT_STOP_TimeoutError'
    text=json.dumps(r)
    assert 'PRIVATE_SOURCE_RIGHT' not in text and 'PRIVATE_ARGUMENTS' not in text and 'PRIVATE_NETWORK' not in text
    assert r['root_cause']=='ROOT_CAUSE_NOT_PROVEN'


@pytest.mark.parametrize('field,value,code',[
    ('action','ARBITRARY_RESTART','OWNER_AUTHORIZATION_SCOPE'),
    ('identity_sha256','0'*64,'OWNER_AUTHORIZATION_IDENTITY'),
    ('candidate_commit','f'*40,'OWNER_AUTHORIZATION_IDENTITY'),
    ('expires_ms',0,'OWNER_AUTHORIZATION_EXPIRED'),
    ('max_connections',3,'OWNER_AUTHORIZATION_SCOPE'),
    ('max_segments',True,'OWNER_AUTHORIZATION_SCOPE'),
    ('orders',False,'OWNER_AUTHORIZATION_SCOPE'),
    ('allow_task_action_pin_update',False,'OWNER_AUTHORIZATION_SCOPE'),
    ('allow_clock_probe',False,'OWNER_AUTHORIZATION_SCOPE'),
])
def test_explicit_authorization_is_exact_and_scoped(host,field,value,code):
    p=authorization(host,**{field:value})
    with pytest.raises(ValueError,match=code):op.authorize(p,diagnostic(host),host['now'])


@pytest.mark.parametrize('field,value,blocker',[
    ('task_state','Running','TASK_NOT_QUIESCENT_READY'),
    ('collector_processes',1,'COMPETING_COLLECTOR'),
    ('supervisor_lock_available',False,'SUPERVISOR_LOCK_UNPROVEN'),
    ('operator_stop',True,'OPERATOR_STOP_PRESENT'),
])
def test_active_or_unknown_host_cannot_deploy(host,field,value,blocker):
    host['snapshot'][field]=value
    assert any(blocker in item for item in diagnostic(host)['blockers'])
    p=authorization(host)
    with pytest.raises(ValueError,match='OWNER_HOST_PREFLIGHT_BLOCKED'):op.authorize(p,diagnostic(host),host['now'])


def test_runtime_or_hold_tamper_is_rejected(host):
    (host['tree']/op.CANDIDATES[0]).write_text('tampered')
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_quota_ban_and_policy_drift_block(host):
    q=host['root']/'segments'/str(SLOT)/'quota.sqlite'
    with closing(sqlite3.connect(q)) as db, db:db.execute("INSERT INTO state VALUES('ban',1)")
    assert diagnostic(host)['quota']['ban'] and 'QUOTA_NOT_READY' in diagnostic(host)['blockers']
    with closing(sqlite3.connect(q)) as db, db:db.execute("UPDATE quota_config SET limits='relaxed'")
    assert diagnostic(host)['quota']['reason']=='QUOTA_POLICY_DRIFT'
    assert 'QUOTA_NOT_READY' in diagnostic(host)['blockers']


def test_apply_stages_pins_and_one_use_ticket_without_clearing_hold(host):
    p=authorization(host);held=(host['root']/'hold.json').read_bytes();claimed=(host['root']/'reset-recovery.claimed').read_bytes()
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),out)
    lines=[json.loads(x) for x in out.getvalue().splitlines()]
    assert lines[0]['status']=='STAGED_AWAITING_TASK_PIN'
    receipt=lines[1];assert receipt['task_started'] is False and receipt['max_segments']==1
    ticket=op.load(host['root']/'operator-resume.authorized.json')
    assert ticket['schema']=='atlas.ws.operator-resume.v1' and ticket['max_connections']==2
    assert ticket['hold_sha256']==op.digest(held) and ticket['claimed_sha256']==op.digest(claimed)
    assert ticket['config_sha256']==op.digest(host['config'].read_bytes())
    assert (host['root']/'hold.json').read_bytes()==held and (host['root']/'reset-recovery.claimed').read_bytes()==claimed
    assert not (host['root']/'operator-deployment.in-progress').exists()
    backup=host['root']/receipt['backup'];assert op.digest((backup/'manifest.json').read_bytes())==receipt['backup_manifest_sha256']
    assert (backup/'hold.json').read_bytes()==held and (backup/'task.xml').exists()
    assert len(list((host['root']/'operator-authorizations').glob('*.claimed')))==1


def test_wrapper_failure_rolls_back_runtime_config_and_preserves_evidence(host):
    p=authorization(host);before={str(path):path.read_bytes() for path in (host['config'],host['root']/'supervisor.ps1',*(host['tree']/r for r in op.CANDIDATES))}
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('ROLLBACK\n'),out)
    assert all(Path(path).read_bytes()==raw for path,raw in before.items())
    assert json.loads(out.getvalue().splitlines()[-1])['status']=='STAGING_ROLLED_BACK_HOLD_PRESERVED'
    assert not (host['root']/'operator-resume.authorized.json').exists()
    assert (host['root']/'hold.json').exists() and (host['root']/'reset-recovery.claimed').exists()


def test_process_crash_before_wrapper_ack_keeps_marker_hold_and_backup(host):
    p=authorization(host)
    with pytest.raises(ValueError,match='OPERATOR_GATE_INTERRUPTED'):
        op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO(''),StringIO())
    assert (host['root']/'operator-deployment.in-progress').exists()
    assert (host['root']/'hold.json').exists() and not (host['root']/'operator-resume.authorized.json').exists()
    assert list(host['root'].glob('ws-recovery-backup-*/manifest.json'))


def test_collector_lease_conflict_prevents_any_deployment_write(host):
    p=authorization(host);lock=host['root']/'segments/service-writer.sqlite'
    db=sqlite3.connect(lock);db.execute('BEGIN EXCLUSIVE');before=bytes_inventory(host['root'])
    try:
        with pytest.raises(sqlite3.OperationalError):
            op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())
        assert bytes_inventory(host['root'])==before
    finally:db.rollback();db.close()


def test_existing_operator_claim_rejects_second_apply(host):
    p=authorization(host);(host['root']/'operator-recovery.active.json').write_bytes(b'{}')
    with pytest.raises(ValueError,match='OPERATOR_STAGE_ALREADY_PRESENT|OWNER_AUTHORIZATION_IDENTITY'):
        op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())


def test_path_links_and_parent_traversal_are_not_accepted(tmp_path):
    target=tmp_path/'real';target.write_bytes(b'x');link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(ValueError,match='PATH_LINK_DENIED'):op.read(link)
    with pytest.raises(ValueError,match='PATH_TRAVERSAL_DENIED'):op.read(tmp_path/'sub'/'..'/'real')


def test_missing_and_wal_quota_evidence_never_creates_sidecars(host):
    q=host['root']/'segments'/str(SLOT)/'quota.sqlite'
    original=q.read_bytes();q.unlink()
    before=bytes_inventory(host['root'])
    assert diagnostic(host)['quota']['reason']=='QUOTA_EVIDENCE_MISSING'
    assert bytes_inventory(host['root'])==before
    q.write_bytes(original);wal=Path(str(q)+'-wal');wal.write_bytes(b'private wal bytes')
    before=bytes_inventory(host['root'])
    assert diagnostic(host)['quota']['reason']=='QUOTA_WAL_REQUIRES_REVIEW'
    assert bytes_inventory(host['root'])==before


def test_unresolved_normal_segment_claim_is_not_archived_or_bypassed(host):
    marker=host['root']/'segment-execution.active.json';marker.write_bytes(b'{"orphan":"preserve"}')
    before=marker.read_bytes();assert 'SEGMENT_EXECUTION_UNRESOLVED' in diagnostic(host)['blockers']
    p=authorization(host)
    with pytest.raises(ValueError,match='OWNER_HOST_PREFLIGHT_BLOCKED'):
        op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())
    assert marker.read_bytes()==before


def test_task_xml_snapshot_pin_mismatch_is_not_accepted(host):
    host['snapshot']['task_xml']='different task or schedule'
    with pytest.raises(ValueError,match='TASK_XML_SNAPSHOT_MISMATCH'):diagnostic(host)


def test_diagnostic_main_preserves_utf8_bom_task_xml_identity(host,monkeypatch,capsys):
    from io import BytesIO,TextIOWrapper
    import sys
    host['snapshot']['task_xml']='<Task>'+''.join(chr(x) for x in (0x0623,0x03a9,0x4e2d))+'</Task>'
    host['snapshot']['task_xml_sha256']=op.digest(host['snapshot']['task_xml'].encode('utf-8'))
    wire=b'\xef\xbb\xbf'+json.dumps(host['snapshot'],ensure_ascii=False).encode('utf-8')+b'\n'
    monkeypatch.setattr(sys,'stdin',TextIOWrapper(BytesIO(wire),encoding='utf-8'))
    monkeypatch.setattr(sys,'argv',['operator','diagnose','--repo',str(host['repo']),'--expected-commit',COMMIT])
    before=bytes_inventory(host['root']);op.main()
    result=json.loads(capsys.readouterr().out)
    assert result['identity']['task_xml_sha256']==host['snapshot']['task_xml_sha256']
    assert result['writes']==result['network_calls']==0 and bytes_inventory(host['root'])==before


def test_stream_preamble_does_not_relax_duplicate_key_rejection(monkeypatch):
    from io import BytesIO,TextIOWrapper
    import sys
    monkeypatch.setattr(sys,'stdin',TextIOWrapper(BytesIO(b'\xef\xbb\xbf{"task_name":"a","task_name":"b"}\n'),encoding='utf-8'))
    monkeypatch.setattr(sys,'argv',['operator','diagnose','--repo','.','--expected-commit',COMMIT])
    with pytest.raises(ValueError,match='DUPLICATE_JSON_KEY'):op.main()


def pinned_manifest(host, extra=(), *, relative_first=False, python=None):
    cfg=op.load(host['config'])
    cfg['files'].extend(dict(x) for x in extra)
    if relative_first:cfg['files'][0]['path']=str(Path(cfg['files'][0]['path']).relative_to(host['tree']))
    if python is not None:cfg['python']=str(python)
    host['config'].write_bytes(op.canonical(cfg))
    pin=op.digest(host['config'].read_bytes());host['snapshot']['task_config_sha256']=pin
    (host['root']/'activation.json').write_bytes(op.canonical(dict(config_sha256=pin)))
    return cfg


def test_pinned_task_supervisor_outside_tree_is_a_named_anchor_read_only(host):
    service=Path(host['snapshot']['service_path'])
    pinned_manifest(host,[dict(path=str(service),sha256=op.digest(service.read_bytes()))])
    before=bytes_inventory(host['root']);r=diagnostic(host)
    assert r['blockers']==[] and r['manifest_scope']['verification_complete']
    assert any(x['scope']=='TASK_SUPERVISOR' and x['path']=='@TASK_SUPERVISOR' for x in r['identity']['runtime'])
    assert bytes_inventory(host['root'])==before


def test_unknown_external_binding_is_not_read_or_granted_authority(host,monkeypatch):
    external=host['root']/'unrelated-private-file.dat';external.write_bytes(b'PRIVATE_UNKNOWN_CONTENT')
    pinned_manifest(host,[dict(path=str(external),sha256=op.digest(external.read_bytes()))])
    original=op.read
    def guarded(path,*a,**kw):
        assert Path(path)!=external,'UNAPPROVED_EXTERNAL_FILE_READ'
        return original(path,*a,**kw)
    monkeypatch.setattr(op,'read',guarded);before=bytes_inventory(host['root']);r=diagnostic(host)
    assert 'RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS' in r['blockers']
    assert not r['manifest_scope']['verification_complete']
    assert str(external) not in json.dumps(r) and 'PRIVATE_UNKNOWN_CONTENT' not in json.dumps(r)
    assert bytes_inventory(host['root'])==before
    with pytest.raises(ValueError,match='OWNER_HOST_PREFLIGHT_BLOCKED'):
        op.authorize(authorization(host),r,host['now'])


def test_identical_manifest_duplicates_are_idempotent_not_rewritten(host):
    first=op.load(host['config'])['files'][0]
    pinned_manifest(host,[first]);before=bytes_inventory(host['root']);r=diagnostic(host)
    assert r['manifest_scope']['identical_duplicate_bindings']==1 and not r['blockers']
    assert r['manifest_scope']['verified_unique_files']==len(op.CANDIDATES)
    assert bytes_inventory(host['root'])==before


def test_conflicting_duplicate_manifest_pin_is_terminal(host):
    first=op.load(host['config'])['files'][0]
    pinned_manifest(host,[{**first,'sha256':'0'*64}])
    with pytest.raises(ValueError,match='RUNTIME_DUPLICATE_PIN_CONFLICT'):diagnostic(host)


def test_only_exact_declared_interpreter_is_an_external_anchor(host):
    interpreter=host['root'].parent/'private-python.exe';interpreter.write_bytes(b'generated interpreter fixture')
    pinned_manifest(host,[dict(path=str(interpreter),sha256=op.digest(interpreter.read_bytes()))],python=interpreter)
    r=diagnostic(host)
    assert not r['blockers'] and any(x['scope']=='TASK_INTERPRETER' for x in r['identity']['runtime'])
    sibling=interpreter.with_name('other-executable.exe');sibling.write_bytes(b'unrelated')
    pinned_manifest(host,[dict(path=str(sibling),sha256=op.digest(sibling.read_bytes()))])
    assert 'RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS' in diagnostic(host)['blockers']


def test_apply_updates_supervisor_and_every_identical_binding_pin(host):
    first=op.load(host['config'])['files'][0];service=Path(host['snapshot']['service_path'])
    pinned_manifest(host,[first,dict(path=str(service),sha256=op.digest(service.read_bytes()))])
    p=authorization(host);out=StringIO()
    op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),out)
    cfg=op.load(host['config'])
    # Existing supervisor preflight hashes every binding, including duplicates.
    assert all(op.digest(Path(x['path']).read_bytes())==x['sha256'] for x in cfg['files'])
    assert (host['root']/'hold.json').exists()
    assert op.load(host['root']/'operator-resume.authorized.json')['max_segments']==1


def test_relative_binding_uses_exact_task_working_directory(host):
    host['snapshot']['task_action']['WorkingDirectory']=str(host['tree'])
    pinned_manifest(host,relative_first=True)
    assert not diagnostic(host)['blockers']
    p=authorization(host);op.gate(host['snapshot'],host['repo'],COMMIT,p,host['now'],StringIO('COMMIT\n'),StringIO())
    cfg=op.load(host['config'])
    for x in cfg['files']:
        path=Path(x['path']);path=path if path.is_absolute() else host['tree']/path
        assert op.digest(path.read_bytes())==x['sha256']


def test_relative_binding_without_declared_workdir_does_not_guess_cwd(host):
    pinned_manifest(host,relative_first=True)
    r=diagnostic(host)
    assert r['manifest_scope']['unverified_bindings'][0]['reason']=='RELATIVE_RUNTIME_PATH_UNRESOLVED'
    assert not r['manifest_scope']['verification_complete'] and r['blockers']


def test_supervisor_named_anchor_still_requires_original_hash(host):
    service=Path(host['snapshot']['service_path'])
    pinned_manifest(host,[dict(path=str(service),sha256='0'*64)])
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_task_shell_exact_anchor_requires_its_pin(host):
    shell=host['root'].parent/'pwsh.exe';shell.write_bytes(b'exact installed task shell')
    sibling=shell.with_name('other.exe');sibling.write_bytes(b'not an anchor')
    host['snapshot']['task_action']['Execute']=str(shell)
    cfg=op.load(host['config']);cfg['files'].extend([
        dict(path=str(shell),sha256=op.digest(shell.read_bytes())),
        dict(path=str(sibling),sha256=op.digest(sibling.read_bytes()))])
    host['config'].write_bytes(op.canonical(cfg))
    host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    result=diagnostic(host)
    assert any(r['scope']=='TASK_SHELL' for r in result['identity']['runtime'])
    assert len(result['manifest_scope']['unverified_bindings'])==1
    shell.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_relative_task_shell_does_not_guess_search_path(host):
    shell=host['root'].parent/'pwsh.exe';shell.write_bytes(b'shell')
    host['snapshot']['task_action']['Execute']='pwsh.exe'
    cfg=op.load(host['config']);cfg['files'].append(dict(path=str(shell),sha256=op.digest(shell.read_bytes())))
    host['config'].write_bytes(op.canonical(cfg));host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    assert diagnostic(host)['blockers']==['RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS']


def test_known_legacy_supervisor_is_verified_without_staging_authority(host,monkeypatch):
    raw=b'known retained supervisor fixture'
    monkeypatch.setattr(op,'LEGACY_SUPERVISOR_SHA256',op.digest(raw))
    legacy=host['root']/'supervisor.ps1';legacy.write_bytes(raw)
    # Actual task points at the runtime-tree supervisor; legacy stays retained.
    host['snapshot']['service_path']=str(host['tree']/'tools/atlas_live_research_service_windows.ps1')
    cfg=op.load(host['config']);cfg['files'].append(dict(path=str(legacy),sha256=op.digest(raw)))
    host['config'].write_bytes(op.canonical(cfg));host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    d=diagnostic(host)
    assert not d['blockers']
    assert any(r['scope']=='RETAINED_LEGACY_SUPERVISOR' for r in d['identity']['runtime'])
    legacy.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='RUNTIME_PIN_MISMATCH'):diagnostic(host)


def test_unknown_legacy_supervisor_pin_is_not_an_anchor(host):
    legacy=host['root']/'supervisor.ps1'
    host['snapshot']['service_path']=str(host['tree']/'tools/atlas_live_research_service_windows.ps1')
    cfg=op.load(host['config']);cfg['files'].append(dict(path=str(legacy),sha256=op.digest(legacy.read_bytes())))
    host['config'].write_bytes(op.canonical(cfg));host['snapshot']['task_config_sha256']=op.digest(host['config'].read_bytes())
    assert diagnostic(host)['blockers']==['RUNTIME_PATH_OUTSIDE_VERIFIED_ANCHORS']


def test_continuous_permit_requires_policy_and_explicit_gap_scope(host):
    p=authorization(host,continuous_research=True)
    with pytest.raises(ValueError,match='CONTINUITY_POLICY_AUTHORIZATION'):
        op.authorize(p,diagnostic(host),host['now'])
    p=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    assert op.authorize(p,diagnostic(host),host['now'])[0]['continuous_research'] is True


def test_continuous_stage_archives_consumed_claim_and_installs_policy(host):
    from io import StringIO
    claim=host['root']/'operator-recovery.active.json';claim.write_bytes(b'original consumed one-shot')
    before=claim.read_bytes()
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,permit,host['now'],StringIO('COMMIT\n'),out)
    rows=[json.loads(s) for s in out.getvalue().splitlines()]
    r=rows[-1]
    assert r['continuous_research'] is True
    assert not claim.exists()
    assert (host['root']/r['backup']/'prior-operator-recovery.archived.json').read_bytes()==before
    policy=op.load(host['root']/'continuous-research.authorized.json')
    assert policy['policy_sha256']==op.continuity_pin() and policy['config_sha256']==r['config_sha256']
    assert (host['root']/'hold.json').exists()


def test_continuous_rejected_precommit_rolls_back_without_new_authority(host):
    claim=host['root']/'operator-recovery.active.json';claim.write_bytes(b'original claim')
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    old=bytes_inventory(host['tree'])
    op.gate(host['snapshot'],host['repo'],COMMIT,permit,host['now'],StringIO('ROLLBACK\n'),StringIO())
    assert bytes_inventory(host['tree'])==old and claim.read_bytes()==b'original claim'
    assert not (host['root']/'continuous-research.authorized.json').exists()


def test_claim_preserves_exact_noncanonical_powershell_authorization_bytes(host):
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    a=op.load(permit)
    a['owner_decision_ref']='owner-approved-تصريح'
    raw=json.dumps(a,indent=2,ensure_ascii=False).encode('utf-8')
    assert raw!=op.canonical(a)
    permit.write_bytes(raw)
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,permit,host['now'],StringIO('COMMIT\n'),out)
    result=json.loads(out.getvalue().splitlines()[-1])
    claimed=host['root']/'operator-authorizations'/(result['authorization_sha256']+'.claimed')
    assert claimed.read_bytes()==raw
    assert op.digest(claimed.read_bytes())==result['authorization_sha256']
    from tools.atlas_ws_continuity import authority
    assert authority(host['root'],result['config_sha256'])


@pytest.mark.parametrize('reason',['LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN','PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED'])
def test_special_hold_requires_explicit_fresh_ping_correction_scope(host,reason):
    (host['root']/'hold.json').write_bytes(op.canonical(dict(reason=reason,slot_ms=SLOT)))
    p=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    with pytest.raises(ValueError,match='FRESH_PING_CORRECTION_AUTHORITY_REQUIRED'):op.authorize(p,diagnostic(host),host['now'])


@pytest.mark.parametrize('reason',['LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN','PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED'])
def test_fresh_ping_rollout_preserves_prior_grant_and_existing_policy(host,monkeypatch,reason):
    old=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True)
    op.gate(host['snapshot'],host['repo'],COMMIT,old,host['now'],StringIO('COMMIT\n'),StringIO())
    grant=host['root']/'continuous-research.authorized.json';prior=grant.read_bytes()
    (host['root']/'operator-resume.authorized.json').unlink()
    
    oldpin=op.digest(host['config'].read_bytes());host['snapshot']['task_config_sha256']=oldpin
    fresh=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True,
        fresh_ping_correction=True,expected_previous_config_sha256=oldpin)
    module=op.continuity_module();ledger=host['root']/'continuous-admission.sqlite'
    for i in range(4):module.outcome(ledger,host['now']-100+i,SLOT+i*900000,failed=True)
    with pytest.raises(ValueError,match='EXISTING_CIRCUIT_WINDOW_NOT_EXPIRED'):
        op.gate(host['snapshot'],host['repo'],COMMIT,fresh,host['now'],StringIO('COMMIT\n'),StringIO())
    assert grant.read_bytes()==prior and not (host['root']/'operator-resume.authorized.json').exists()
    host['now']+=3601000;host['snapshot']['clock']['checked_ms']=host['now']
    monkeypatch.setattr(op.time,'time_ns',lambda:host['now']*1000000)
    fresh=authorization(host,continuous_research=True,continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True,
        fresh_ping_correction=True,expected_previous_config_sha256=oldpin)
    assert module.reserve(ledger,host['now']-1,SLOT)==0 and module.reserve(ledger,host['now'],SLOT)==0
    out=StringIO();op.gate(host['snapshot'],host['repo'],COMMIT,fresh,host['now'],StringIO('COMMIT\n'),out)
    result=json.loads(out.getvalue().splitlines()[-1]);ticket=op.load(host['root']/'operator-resume.authorized.json')
    assert result['fresh_ping_correction'] and ticket['fresh_ping_correction']
    assert (host['root']/result['backup']/'continuous-authority.prior.json').read_bytes()==prior
    marker=op.continuity_module().authority(host['root'],result['config_sha256'])
    assert 'circuit_epoch_ms' not in marker
    assert (host['root']/'hold.json').exists()

    assert module.reserve(ledger,host['now']+1,SLOT)>0
    with closing(sqlite3.connect(ledger)) as db:assert db.execute("SELECT count(*) FROM events WHERE kind='OUTCOME'").fetchone()[0]==4

@pytest.mark.parametrize('blockers,enabled,collectors,locked,retryable',[
    (['TASK_NOT_QUIESCENT_READY'],True,0,True,True),
    (['TASK_NOT_QUIESCENT_READY'],False,0,True,False),
    (['TASK_NOT_QUIESCENT_READY','QUOTA_NOT_READY'],True,0,True,False),
    (['TASK_NOT_QUIESCENT_READY'],True,1,True,False),
    (['UNKNOWN_BLOCKER'],True,0,True,False),
])
def test_preflight_failure_is_exact_sanitized_and_narrow(blockers,enabled,collectors,locked,retryable):
    d=dict(blockers=blockers,task_state='Running',task_enabled=enabled,
           collector_processes=collectors,supervisor_lock_available=locked,
           task_xml='PRIVATE_SECRET',root='PRIVATE_HOST_PATH')
    error=op.HostPreflightBlocked(d)
    assert str(error)=='OWNER_HOST_PREFLIGHT_BLOCKED'
    assert error.preflight['blockers']==blockers
    assert error.preflight['retryable_scheduler_only'] is retryable
    assert 'PRIVATE' not in json.dumps(error.preflight)

def test_disk_reserve_hold_requires_exact_scoped_disk_correction(host):
    (host['root']/'hold.json').write_bytes(op.canonical(dict(reason='PILOT_STOP_DISK_RESERVE_LOW',slot_ms=SLOT)))
    d=diagnostic(host)
    scope=dict(continuous_research=True,continuity_policy_sha256=op.continuity_pin(),
        allow_explicit_missing_intervals=True,expected_previous_config_sha256=d['identity']['config_sha256'])
    with pytest.raises(ValueError,match='DISK_RESERVE_CORRECTION_AUTHORITY_REQUIRED'):
        op.authorize(authorization(host,**scope),d,host['now'])
    permit=authorization(host,**scope,disk_reserve_correction=True)
    auth,_=op.authorize(permit,d,host['now'])
    assert auth['disk_reserve_correction'] is True
    assert auth['expected_previous_config_sha256']==d['identity']['config_sha256']
    bad_scope=dict(scope);bad_scope['expected_previous_config_sha256']='0'*64
    with pytest.raises(ValueError,match='DISK_RESERVE_CORRECTION_AUTHORITY_REQUIRED'):
        op.authorize(authorization(host,**bad_scope,disk_reserve_correction=True),d,host['now'])
    (host['root']/'hold.json').write_bytes(op.canonical(dict(reason='PILOT_STOP_TimeoutError',slot_ms=SLOT)))
    d=diagnostic(host)
    with pytest.raises(ValueError,match='DISK_RESERVE_CORRECTION_AUTHORITY_REQUIRED'):
        op.authorize(authorization(host,**scope,disk_reserve_correction=True),d,host['now'])

def test_disk_reserve_correction_stages_one_ticket_and_preserves_prior_authority(host):
    module=op.continuity_module()
    now=host['now'];config_pin=op.digest(host['config'].read_bytes())
    prior=dict(schema='atlas.ws.operator-authorization.v1',action='DEPLOY_ONE_RECOVERY',
        continuous_research=True,continuity_policy_sha256=module.PIN,allow_explicit_missing_intervals=True,
        max_connections=2,max_segments=1,orders=0,trading_authority='NONE',
        issued_ms=now-1000,expires_ms=now+600000)
    prior_raw=op.canonical(prior);prior_pin=op.digest(prior_raw)
    claims=host['root']/'operator-authorizations';claims.mkdir()
    (claims/(prior_pin+'.claimed')).write_bytes(prior_raw)
    grant=dict(schema='atlas.ws.continuous-authority.v1',policy_sha256=module.PIN,
        config_sha256=config_pin,config_filename=host['config'].name,authorization_sha256=prior_pin,
        activated_ms=now-500,orders=0,trading_authority='NONE')
    (host['root']/'continuous-research.authorized.json').write_bytes(op.canonical(grant))
    (host['root']/'hold.json').write_bytes(op.canonical(dict(reason='PILOT_STOP_DISK_RESERVE_LOW',slot_ms=SLOT)))
    host['snapshot']['task_config_sha256']=config_pin
    d=diagnostic(host)
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=module.PIN,
        allow_explicit_missing_intervals=True,disk_reserve_correction=True,
        expected_previous_config_sha256=d['identity']['config_sha256'])
    out=StringIO()
    op.gate(host['snapshot'],host['repo'],COMMIT,permit,now,StringIO('COMMIT\n'),out)
    lines=[json.loads(x) for x in out.getvalue().splitlines()]
    receipt=lines[-1];ticket=op.load(host['root']/'operator-resume.authorized.json')
    assert receipt['status']=='WS_ENGINEERING_INSTALLED_ONE_RECOVERY_WAITING_FOR_EXISTING_SCHEDULE'
    assert receipt['disk_reserve_correction'] is True and receipt['max_segments']==1
    assert ticket['disk_reserve_correction'] is True and ticket['fresh_ping_correction'] is False
    assert (host['root']/receipt['backup']/'continuous-authority.prior.json').read_bytes()==op.canonical(grant)
    assert op.load(host['root']/'hold.json')['reason']=='PILOT_STOP_DISK_RESERVE_LOW'



def test_disk_reserve_correction_rebinds_valid_prior_grant_after_config_relocation(host):
    module=op.continuity_module()
    now=host['now'];current_pin=op.digest(host['config'].read_bytes());old_pin='b'*64
    prior=dict(schema='atlas.ws.operator-authorization.v1',action='DEPLOY_ONE_RECOVERY',
        continuous_research=True,continuity_policy_sha256=module.PIN,allow_explicit_missing_intervals=True,
        max_connections=2,max_segments=1,orders=0,trading_authority='NONE',
        issued_ms=now-1000,expires_ms=now+600000)
    prior_raw=op.canonical(prior);prior_pin=op.digest(prior_raw)
    claims=host['root']/'operator-authorizations';claims.mkdir()
    (claims/(prior_pin+'.claimed')).write_bytes(prior_raw)
    grant=dict(schema='atlas.ws.continuous-authority.v1',policy_sha256=module.PIN,
        config_sha256=old_pin,config_filename=host['config'].name,authorization_sha256=prior_pin,
        activated_ms=now-500,orders=0,trading_authority='NONE')
    (host['root']/'continuous-research.authorized.json').write_bytes(op.canonical(grant))
    (host['root']/'activation.json').write_bytes(op.canonical(dict(config_sha256=old_pin)))
    (host['root']/'hold.json').write_bytes(op.canonical(dict(reason='PILOT_STOP_DISK_RESERVE_LOW',slot_ms=SLOT)))
    d=diagnostic(host)
    permit=authorization(host,continuous_research=True,continuity_policy_sha256=module.PIN,
        allow_explicit_missing_intervals=True,disk_reserve_correction=True,
        expected_previous_config_sha256=d['identity']['config_sha256'])
    out=StringIO()
    op.gate(host['snapshot'],host['repo'],COMMIT,permit,now,StringIO('COMMIT\n'),out)
    rows=[json.loads(s) for s in out.getvalue().splitlines()]
    receipt=rows[-1];ticket=op.load(host['root']/'operator-resume.authorized.json')
    assert receipt['disk_reserve_correction'] is True and receipt['task_started'] is False
    assert ticket['disk_reserve_correction'] is True and ticket['config_sha256']==op.digest(host['config'].read_bytes())
    rebound=module.authority(host['root'],ticket['config_sha256'])
    assert rebound['config_sha256']==ticket['config_sha256']
    assert (host['root']/receipt['backup']/'continuous-authority.prior.json').exists()
    assert op.load(host['root']/'hold.json')['reason']=='PILOT_STOP_DISK_RESERVE_LOW'
