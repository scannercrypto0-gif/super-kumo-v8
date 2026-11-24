"""Real persistent admission tests, no network or scheduler."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from tools import atlas_ws_continuity as c

NOW=1795331700130
SLOT=1795329900000


def test_shared_budget_survives_process_style_reopen_and_other_segments(tmp_path):
    p=tmp_path/'state.sqlite'
    assert c.reserve(p,NOW,SLOT)==0
    assert c.reserve(p,NOW+100,SLOT+900000)==0
    assert c.reserve(p,NOW+200,SLOT+1800000)>299000
    assert c.reserve(p,NOW+300001,SLOT+1800000)==0


def test_crash_after_admission_never_refunds_and_clock_regression_rejected(tmp_path):
    p=tmp_path/'state.sqlite'
    assert c.reserve(p,NOW,SLOT)==0
    with pytest.raises(ValueError,match='CLOCK_REGRESSION'):c.reserve(p,NOW-1,SLOT)
    assert c.reserve(p,NOW+1,SLOT)==0
    assert c.reserve(p,NOW+2,SLOT)>0


def test_concurrent_admission_never_overdraws(tmp_path):
    p=tmp_path/'state.sqlite'
    with closing(c.database(p)):pass
    def worker(_):
        try:return c.reserve(p,NOW,SLOT)
        except sqlite3.OperationalError:return 'LOCKED'
    with ThreadPoolExecutor(max_workers=6) as workers:r=list(workers.map(worker,range(12)))
    assert r.count(0)<=2
    with closing(sqlite3.connect(p)) as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='CONNECT'").fetchone()[0]<=2


def test_failure_circuit_persists_across_success_and_outcomes_idempotent(tmp_path):
    p=tmp_path/'state.sqlite'
    for i in range(3):
        r=c.outcome(p,NOW+i*100,SLOT+i*900000,failed=True)
        assert not r['circuit_open']
        assert c.outcome(p,NOW+i*100,SLOT+i*900000,failed=True)==r
    c.outcome(p,NOW+301,SLOT+3*900000,failed=False)
    assert c.outcome(p,NOW+400,SLOT+4*900000,failed=True)['circuit_open']
    with pytest.raises(ValueError,match='OUTCOME_CONFLICT'):c.outcome(p,NOW+500,SLOT,failed=False)
    assert not c.outcome(p,NOW+3600001,SLOT+5*900000,failed=False)['circuit_open']


def test_policy_corruption_and_symlink_fail_closed(tmp_path):
    p=tmp_path/'state.sqlite'
    with closing(c.database(p)) as db,db:db.execute("UPDATE policy SET pin='wrong'")
    with pytest.raises(ValueError,match='POLICY_PIN'):c.reserve(p,NOW,SLOT)
    link=tmp_path/'linked.sqlite'
    try:link.symlink_to(p)
    except OSError:pytest.skip('symlink privilege unavailable')
    with pytest.raises(ValueError,match='STATE_LINK'):c.reserve(link,NOW,SLOT)


def install(root,activated=NOW):
    cfg=root/'config.json';cfg.write_bytes(b'owner pinned configuration')
    pin=hashlib.sha256(cfg.read_bytes()).hexdigest()
    permit=dict(schema='atlas.ws.operator-authorization.v1',action='DEPLOY_ONE_RECOVERY',
        continuous_research=True,continuity_policy_sha256=c.PIN,allow_explicit_missing_intervals=True,
        max_connections=2,max_segments=1,orders=0,trading_authority='NONE',issued_ms=activated-1000,expires_ms=activated+600000)
    raw=json.dumps(permit,sort_keys=True).encode();authpin=hashlib.sha256(raw).hexdigest()
    claims=root/'operator-authorizations';claims.mkdir()
    (claims/(authpin+'.claimed')).write_bytes(raw)
    body=dict(schema='atlas.ws.continuous-authority.v1',policy_sha256=c.PIN,
        config_sha256=pin,config_filename=cfg.name,authorization_sha256=authpin,activated_ms=activated,orders=0,trading_authority='NONE')
    (root/'continuous-research.authorized.json').write_text(json.dumps(body))
    return cfg,pin


def test_authority_is_opt_in_config_bound_and_never_grants_trading(tmp_path):
    assert c.authority(tmp_path) is None
    cfg,pin=install(tmp_path)
    assert c.authority(tmp_path,pin)
    cfg.write_text('changed')
    with pytest.raises(ValueError,match='CONFIG_PIN'):c.authority(tmp_path,pin)


def test_authority_rejects_traversal_duplicate_key_and_scope(tmp_path):
    _,pin=install(tmp_path);p=tmp_path/'continuous-research.authorized.json'
    original=p.read_text();a=json.loads(original);a['config_filename']='../config.json';p.write_text(json.dumps(a))
    with pytest.raises(ValueError,match='CONFIG_PATH'):c.authority(tmp_path)
    p.write_text(original[:-1]+',"orders":0}')
    with pytest.raises(ValueError,match='DUPLICATE_KEY'):c.authority(tmp_path)
    a=json.loads(original);a['trading_authority']='LIVE';p.write_text(json.dumps(a))
    with pytest.raises(ValueError,match='AUTHORITY_SCOPE'):c.authority(tmp_path)


def test_scheduler_backoff_and_hold_gate_are_durable(tmp_path):
    _,pin=install(tmp_path)
    assert c.next_action(tmp_path,pin,NOW)['wait_until_ms']==0
    r=c.next_action(tmp_path,pin,NOW,slot=SLOT,failed=True)
    assert r['wait_until_ms']>NOW and r['gap_status']=='OUTAGE_REQUIRES_COVERAGE_RECONCILIATION'
    assert c.next_action(tmp_path,pin,NOW+1)['wait_until_ms']==r['wait_until_ms']


def test_marker_cannot_enable_continuity_without_claimed_owner_permit(tmp_path):
    install(tmp_path)
    claim=next((tmp_path/'operator-authorizations').glob('*.claimed'))
    claim.write_bytes(b'changed')
    with pytest.raises(ValueError,match='OWNER_PERMIT_PIN'):c.authority(tmp_path)

def test_fresh_ping_resume_ticket_is_reported_as_pending_only_when_exact_and_live(tmp_path):
    ticket=dict(schema='atlas.ws.operator-resume.v1',config_sha256='a'*64,
        authorization_sha256='b'*64,issued_ms=NOW,expires_ms=NOW+60000,
        fresh_ping_correction=True)
    args=('PILOT_STOP_PONG_FRESH_PING_PROOF_REJECTED',False,ticket,'a'*64,'b'*64,NOW+1,False)
    assert c.resume_ticket_pending(*args)
    assert not c.resume_ticket_pending(*args[:2]+({**ticket,'fresh_ping_correction':False},)+args[3:])
    assert not c.resume_ticket_pending(*args[:2]+({**ticket,'config_sha256':'c'*64},)+args[3:])
    assert not c.resume_ticket_pending(*args[:2]+({**ticket,'expires_ms':NOW},)+args[3:])
    assert not c.resume_ticket_pending(*args[:2]+(ticket,)+args[3:-1]+(True,))
    assert not c.resume_ticket_pending(*args[:1]+(True,)+args[2:])
