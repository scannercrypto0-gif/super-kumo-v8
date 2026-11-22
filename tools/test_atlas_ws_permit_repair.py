"""Known-byte artifact repair with real filesystem and SQLite leases only."""
from io import StringIO
import json
from pathlib import Path
from contextlib import closing
import sqlite3

import pytest
from tools import atlas_ws_resilience_operator as op
from tools import atlas_ws_permit_repair as repair
from tools.atlas_ws_continuity import authority

NOW=1795335000000


@pytest.fixture
def broken(tmp_path):
    root=tmp_path/'owner';root.mkdir();(root/'segments').mkdir()
    permit_dir=tmp_path/'temp';permit_dir.mkdir()
    runtime=root/'runtime.py';runtime.write_text('original pinned runtime')
    cfg=root/'config.json';cfg.write_bytes(op.canonical(dict(files=[dict(path=str(runtime),sha256=op.digest(runtime.read_bytes()))])))
    configpin=op.digest(cfg.read_bytes())
    a=dict(schema=op.SCHEMA,action='DEPLOY_ONE_RECOVERY',candidate_commit='d'*40,continuous_research=True,
        continuity_policy_sha256=op.continuity_pin(),allow_explicit_missing_intervals=True,
        issued_ms=NOW-120000,expires_ms=NOW+600000,max_connections=2,max_segments=1,orders=0,trading_authority='NONE')
    raw=json.dumps(a,indent=2).encode();pin=op.digest(raw)
    (permit_dir/'atlas-continuous-permit-original.json').write_bytes(raw)
    claims=root/'operator-authorizations';claims.mkdir();claimed=claims/(pin+'.claimed');claimed.write_bytes(op.canonical(a))
    (root/'continuous-research.authorized.json').write_bytes(op.canonical(dict(schema='atlas.ws.continuous-authority.v1',
        config_filename=cfg.name,config_sha256=configpin,authorization_sha256=pin,policy_sha256=op.continuity_pin(),
        activated_ms=NOW-110000,orders=0,trading_authority='NONE')))
    held=op.canonical(dict(reason='PILOT_STOP_ConnectionResetError',slot_ms=1795329900000))
    (root/'hold.json').write_bytes(held)
    backup=root/'ws-recovery-backup-fixture';backup.mkdir();(backup/'hold.json').write_bytes(held)
    (backup/'manifest.json').write_bytes(b'{"original":"backup manifest"}')
    (backup/'deployment-receipt.json').write_bytes(op.canonical(dict(candidate_commit='d'*40,
        config_sha256=configpin,authorization_sha256=pin,continuous_research=True)))
    ticket=dict(schema='atlas.ws.operator-resume.v1',authorization_sha256=pin,config_sha256=configpin,
        hold_sha256=op.digest(held),claimed_sha256=None,pending_sha256=None,
        issued_ms=NOW-100000,expires_ms=NOW+500000,max_segments=1,max_connections=2,orders=0,trading_authority='NONE')
    rejected=root/'operator-resume.rejected-fixture.json';rejected.write_bytes(op.canonical(ticket))
    expected=dict(config_sha256=configpin,authorization_sha256=pin,candidate_commit='d'*40,
        backup=backup.name,backup_manifest_sha256=op.digest((backup/'manifest.json').read_bytes()))
    return dict(root=root,cfg=cfg,permit_dir=permit_dir,expected=expected,raw=raw,claimed=claimed,rejected=rejected)


def run(b):return repair.repair(b['cfg'],b['permit_dir'],'OWNER_EXPLICIT_MANUAL_REPAIR',NOW,b['expected'])


def inventory(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_restore_real_original_bytes_preserve_evidence_and_manual_initial_ticket(broken):
    b=broken;before=b['claimed'].read_bytes();held=(b['root']/'hold.json').read_bytes()
    r=run(b)
    assert r['restored_claimed_sha256']==b['expected']['authorization_sha256']
    assert b['claimed'].read_bytes()==b['raw']
    assert (b['root']/r['evidence']/'claimed-before.bin').read_bytes()==before
    assert (b['root']/'hold.json').read_bytes()==held and b['rejected'].exists()
    t=op.load(b['root']/'operator-resume.authorized.json')
    assert t['issued_ms']==NOW and t['max_connections']==2 and t['max_segments']==1
    assert authority(b['root'],b['expected']['config_sha256'])
    assert r['task_changes']==r['source_calls']==0 and not r['deployment_repeated']


def test_valid_pending_ticket_is_archived_before_explicit_requeue(broken):
    b=broken;b['rejected'].rename(b['root']/'operator-resume.authorized.json')
    r=run(b)
    assert (b['root']/r['evidence']/'pending-ticket.archived.json').exists()
    assert (b['root']/'operator-resume.authorized.json').exists()


@pytest.mark.parametrize('mode',['missing-original','altered-claim','changed-config','changed-hold','changed-runtime','consumed','execution','marker','changed-backup','no-ticket'])
def test_unknown_or_consumed_state_refuses_before_claim_rewrite(broken,mode):
    b=broken
    if mode=='missing-original':next(b['permit_dir'].glob('*.json')).unlink()
    elif mode=='altered-claim':b['claimed'].write_bytes(b'not canonical original')
    elif mode=='changed-config':b['cfg'].write_bytes(b'changed')
    elif mode=='changed-hold':(b['root']/'hold.json').write_bytes(b'changed')
    elif mode=='changed-runtime':(b['root']/'runtime.py').write_bytes(b'changed')
    elif mode=='consumed':(b['root']/'operator-recovery.active.json').write_bytes(b'{}')
    elif mode=='execution':(b['root']/'segment-execution.active.json').write_bytes(b'{}')
    elif mode=='marker':(b['root']/'operator-deployment.in-progress').write_bytes(b'{}')
    elif mode=='changed-backup':(b['root']/b['expected']['backup']/'manifest.json').write_bytes(b'changed')
    elif mode=='no-ticket':b['rejected'].unlink()
    before=b['claimed'].read_bytes()
    with pytest.raises((ValueError,OSError)):run(b)
    assert b['claimed'].read_bytes()==before
    assert not list(b['root'].glob('permit-byte-repair-*'))
