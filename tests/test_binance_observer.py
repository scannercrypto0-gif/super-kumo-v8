import copy
import importlib
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from aql.binance_observer import ObserverLedger, canonical, payload, ws_payload, verify_bundle
from aql.data_proof import ProofError
from aql.data_proof_envelope import verify_envelope

FACTORY_SHA = 'fbf70afbcf3ba051a9b1522328893bf9ab7f2a67'


def row(c='11'):
    return [0, '10', '12', '9', c, '100', 59999, '1000', 20, '50', '500', '0']


def observe(ledger, c='11', wall=60001, mono=None):
    raw = json.dumps([row(c)])
    return ledger.observe(payload(symbol='BTCUSDT', interval='1m', row=row(c)), raw=raw,
        endpoint='https://data-api.binance.vision/api/v3/klines', transport='REST', wall_ms=wall,
        monotonic_ns=mono if mono is not None else wall*1_000_000, clock_ref=None,
        metadata=dict(symbol='BTCUSDT', interval='1m'))


def test_restart_correction_and_no_future_leakage(tmp_path):
    path=tmp_path/'watch.db'; l=ObserverLedger(path)
    v1=observe(l); head=l.verify(); l.close()
    l=ObserverLedger(path)
    assert observe(l).version_id == v1.version_id
    v2=observe(l, '12', 90000)
    assert v2.supersedes_version_id == v1.version_id
    assert v2.first_local_seen_ms == 90000 and v2.provider_available_ms is None
    assert l.as_of(70000)['versions'] == (v1,)
    assert l.as_of(90001)['versions'] == (v2,)
    assert l.as_of(59999)['versions'] == ()
    assert not l.as_of(90001)['real_pit_accepted']
    v3=observe(l, '11', 91000)
    assert v3.version_number == 3  # A -> B -> A is a revision, not replay.
    with pytest.raises(ProofError): l.verify(head)
    b=l.bundle(); assert verify_bundle(b,b['ledger_head'])
    assert all(s=='UNKNOWN' for s in b['envelope']['gap_states'].values())
    l.close()


def test_tamper_and_truncation(tmp_path):
    l=ObserverLedger(tmp_path/'w.db'); observe(l); b=l.bundle(); pin=b['ledger_head']
    altered=copy.deepcopy(b); altered['evidence'][1]['body']['data']['raw']='[]'
    with pytest.raises(ProofError): verify_bundle(altered,pin)
    truncated=copy.deepcopy(b); truncated['evidence'].pop()
    with pytest.raises(ProofError): verify_bundle(truncated,pin)
    l.db.execute("UPDATE evidence SET body='{}' WHERE seq=2")
    with pytest.raises(ProofError): l.verify()
    l.close()
    with pytest.raises(ProofError): ObserverLedger(tmp_path/'w.db')


def test_clock_drift_backward_and_disconnect(tmp_path):
    l=ObserverLedger(tmp_path/'w.db'); observe(l)
    l.record('GAP',dict(reason='DISCONNECT',coverage='UNKNOWN'))
    observe(l,'12',90000,mono=60002*1_000_000)
    assert any(e['body']['data'].get('reason')=='CLOCK_DISCONTINUITY' for e in l.entries())
    with pytest.raises(ProofError): observe(l,'11',50000)
    assert l.as_of(100000)['status']=='UNKNOWN_CLOCK_OR_COVERAGE'
    l.close()


def test_ws_event_is_not_first_seen(tmp_path):
    k=dict(s='BTCUSDT',i='1m',t=0,T=59999,o='10',h='12',l='9',c='11',v='100',q='1000',n=20,V='50',Q='500',x=True,f=1,L=20)
    raw=json.dumps(dict(e='kline',E=60000,s='BTCUSDT',k=k)); p,msg=ws_payload(raw,'BTCUSDT','1m')
    l=ObserverLedger(tmp_path/'w.db')
    v=l.observe(p,raw=raw,endpoint='wss://data-stream.binance.vision/ws/btcusdt@kline_1m',transport='WS',wall_ms=70000,monotonic_ns=1,clock_ref=None,source_event_ms=msg['E'])
    assert v.first_local_seen_ms==70000 and v.provider_available_ms is None
    assert v.eligibility(65000)=='REJECT_LATE'
    assert v.eligibility(80000)=='UNKNOWN_PENDING_EVIDENCE'
    b=l.bundle(); assert verify_bundle(b,b['ledger_head'])==(v,)
    k['x']=False
    assert ws_payload(json.dumps(dict(e='kline',E=60000,s='BTCUSDT',k=k)),'BTCUSDT','1m')[0] is None
    with pytest.raises(ProofError): ws_payload(raw,'ETHUSDT','1m')
    l.close()


def test_forced_exit_retains_commit(tmp_path):
    path=tmp_path/'w.db'
    code = """from aql.binance_observer import ObserverLedger, payload
import json,os
l=ObserverLedger(%r)
l.record=lambda *args: os._exit(9)
r=[0,'10','12','9','11','100',59999,'1000',20,'50','500','0']
l.observe(payload(symbol='BTCUSDT',interval='1m',row=r),raw=json.dumps([r]),endpoint='https://data-api.binance.vision/api/v3/klines',transport='REST',wall_ms=60001,monotonic_ns=1,clock_ref=None,metadata={'symbol':'BTCUSDT','interval':'1m'})
""" % str(path)
    p=subprocess.run([sys.executable,'-c',code])
    assert p.returncode==9
    l=ObserverLedger(path)
    assert len(l.versions())==1
    assert not any(e['body']['kind']=='POSTCOMMIT' for e in l.entries())
    assert l.versions()[0].ingest_committed_ms is None
    l.verify(); l.close()



def factory_bridge(tmp_path):
    """Execute existing Factory code pinned to reviewed #141; no new admission gate."""
    package=tmp_path/'pinned_factory'; package.mkdir(); (package/'__init__.py').write_text('')
    for name in ('core_proof_bridge.py','data_admission_b.py'):
        source=subprocess.check_output(['git','show',f'{FACTORY_SHA}:research_wp_r0/{name}'])
        (package/name).write_bytes(source)
    sys.path.insert(0,str(tmp_path))
    try: return importlib.import_module('pinned_factory.core_proof_bridge').review_core_envelope
    finally: sys.path.pop(0)


def test_existing_factory_e2e(tmp_path):
    review=factory_bridge(tmp_path)
    l=ObserverLedger(tmp_path/'w.db'); observe(l); observe(l,'12',90000)
    b=l.bundle(); verify_bundle(b,b['ledger_head']); env=b['envelope']; pin=env['manifest_sha256']
    receipts=review(env,pinned_digest=pin,cutoff_ms=70000)
    assert receipts and all(not r.empirical_eligible and not r.real_pit_accepted for r in receipts)
    bad=copy.deepcopy(env); bad['epoch']=0
    assert review(bad,pinned_digest=pin,cutoff_ms=70000)[0].status=='REJECT_FOR_EMPIRICAL'
    with pytest.raises(ProofError): verify_envelope(env,consumer='factory',minimum_epoch=2,pinned_sha256=pin)
    l.close()


def test_real_capture_and_factory(tmp_path):
    root=Path('evidence/binance-observer-20261028')
    captures=json.loads((root/'capture_manifest.json').read_text())['captures']
    assert captures, 'Required authentic bounded Binance sample is missing'
    review=factory_bridge(tmp_path)
    for capture in captures:
        path=root/capture['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==capture['sha256']
        b=json.loads(path.read_text()); versions=verify_bundle(b,capture['ledger_head'])
        assert versions and all(v.provider_available_ms is None for v in versions)
        receipts=review(b['envelope'],pinned_digest=b['envelope']['manifest_sha256'],cutoff_ms=max(v.first_local_seen_ms for v in versions))
        assert all(not r.empirical_eligible and not r.real_pit_accepted for r in receipts)


def test_atomic_failure_does_not_publish_partial_version(tmp_path):
    l=ObserverLedger(tmp_path/'w.db'); initial=l.verify(); append=l._append
    def fail(kind,data):
        if kind=='VERSION': raise RuntimeError('injected storage outage')
        return append(kind,data)
    l._append=fail
    with pytest.raises(RuntimeError): observe(l)
    assert l.verify()==initial and l.versions()==()
    l._append=append; observe(l); assert len(l.versions())==1
    l.close()

def test_current_operational_capture_drive_backup_still_denied_by_factory(tmp_path):
    root=Path('evidence/observation-e2e-20261028')
    manifest=json.loads((root/'capture-manifest.json').read_text())
    raw=(root/manifest['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==manifest['sha256']
    bundle=json.loads(raw)
    versions=verify_bundle(bundle,manifest['ledger_head'])
    review=factory_bridge(tmp_path)
    receipts=review(bundle['envelope'],pinned_digest=bundle['envelope']['manifest_sha256'],
        cutoff_ms=max(v.first_local_seen_ms for v in versions))
    assert receipts and all(not r.empirical_eligible and not r.real_pit_accepted for r in receipts)
