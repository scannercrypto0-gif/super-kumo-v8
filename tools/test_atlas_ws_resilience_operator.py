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
    with pytest.raises(ValueError,match='OPERATOR_STAGE_ALREADY_PRESENT'):
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
