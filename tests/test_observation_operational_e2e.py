"""Synthetic/fault-injected tests; these are not owner Windows deployment."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from aql.binance_observer import ObserverLedger, payload, verify_bundle
from aql.data_proof import ProofError
from aql.evidence_outbox import EvidenceOutbox, encode, digest
from aql.evidence_guardian import RcloneDriveSender, VAULT_ID
from aql.utc_evidence import ClockSample, assess

spec=importlib.util.spec_from_file_location('watcher', 'scripts/binance_independent_observer.py')
watcher=importlib.util.module_from_spec(spec); spec.loader.exec_module(watcher)
ROW=[0,'10','12','9','11','100',59999,'1000',20,'50','500','0']

class FakeRclone:
    def __init__(self): self.remote={}; self.online=False; self.corrupt=False; self.uploads=0
    def __call__(self, cmd, **kw):
        assert cmd[-2:] == ['--drive-root-folder-id', VAULT_ID]
        if not self.online: raise subprocess.CalledProcessError(1,cmd)
        target=cmd[3] if cmd[1]=='copyto' else cmd[2]
        if cmd[1]=='cat':
            if target not in self.remote: raise subprocess.CalledProcessError(3,cmd)
            return SimpleNamespace(stdout=b'corrupt' if self.corrupt else self.remote[target])
        assert cmd[1]=='copyto' and '--immutable' in cmd
        if target in self.remote: raise subprocess.CalledProcessError(1,cmd)
        self.remote[target]=Path(cmd[2]).read_bytes(); self.uploads+=1
        return SimpleNamespace(stdout=b'')

def test_real_cli_callpath_local_export_guardian_off_restart_and_readback(tmp_path, monkeypatch):
    # Actual run() with synthetic REST/WS and UTC; no cloud/owner-host claim.
    class Socket:
        def recv(self): return json.dumps(dict(e='kline',E=60000,s='BTCUSDT',k=dict(
            s='BTCUSDT',i='1m',t=0,T=59999,o='10',h='12',l='9',c='11',v='100',q='1000',n=20,V='50',Q='500',x=True,f=1,L=20)))
        def close(self): pass
    tick=iter([0,0,0,0,0,0,2])
    monkeypatch.setattr(watcher.time, 'monotonic', lambda: next(tick,2))
    # Child exporter uses a separate process in production. A deterministic
    # stand-in snapshots the same DB after SESSION_STOP for this injected feed.
    from aql.observer_runtime import snapshot_loop
    class Worker:
        pid = 1
        def __init__(self, target, args, **kw): self.target, self.args = target, args
        def start(self): pass
        def join(self, *a): self.target(*self.args)
        def is_alive(self): return False
    class Context:
        def Event(self):
            import threading
            return threading.Event()
        Process = Worker
    monkeypatch.setattr(watcher.multiprocessing, 'get_context', lambda *_: Context())
    monkeypatch.setattr(watcher.websocket, 'create_connection', lambda *a,**k: Socket())
    monkeypatch.setattr(watcher,'get',lambda path: (
        json.dumps(dict(serverTime=100000)) if 'time' in path else json.dumps([ROW]),
        dict(wall_ms=100000,monotonic_ns=100000000000)))
    watcher.run(tmp_path,1)
    q=EvidenceOutbox(tmp_path/'outbox'); assert q.pending_count()>=1
    backend=FakeRclone(); sender=RcloneDriveSender('atlas:',runner=backend)
    assert all(s=='PENDING_EXTERNAL_ANCHOR' for _,s in q.deliver(sender))
    # Durable Core evidence exists and verifies while Guardian is disconnected.
    pending=list(q.pending.glob('*.json'))
    assert any(verify_bundle(json.loads(p.read_bytes()),json.loads(p.read_bytes())['ledger_head']) for p in pending)
    backend.online=True
    reopened=EvidenceOutbox(tmp_path/'outbox'); reopened.deliver(sender)
    assert reopened.pending_count()==0
    assert backend.uploads==len(pending)
    assert reopened.deliver(sender)==[]
    for ack in reopened.acked.glob('*.json'):
        receipt=json.loads(ack.read_bytes())['receipt']
        assert receipt['download_sha256']==ack.stem and receipt['independent_custody'] is False

def test_readback_tamper_and_upload_before_ack_replay(tmp_path):
    ledger=ObserverLedger(tmp_path/'ledger.db'); q=EvidenceOutbox(tmp_path/'outbox')
    key=ledger.queue_external_evidence(q); ledger.close()
    backend=FakeRclone(); backend.online=True
    sender=RcloneDriveSender('atlas:',runner=backend)
    blob=(q.pending/(key+'.json')).read_bytes()
    # Model crash after successful upload, before local ACK.
    backend.remote['atlas:'+key+'.json']=blob
    backend.corrupt=True
    assert q.deliver(sender)[0][1]=='PENDING_EXTERNAL_ANCHOR'
    assert q.pending_count()==1 and not list(q.acked.glob('*.json'))
    backend.corrupt=False
    q.deliver(sender); assert q.pending_count()==0 and backend.uploads==0

def test_expired_session_wall_step_and_event_binding(tmp_path):
    sample=ClockSample(1000000000,1000,'test.invalid',2,3,4,60000,True)
    assert assess(sample,2000000000,100,now_wall_ms=3000)['status']=='UNKNOWN'
    assert assess(sample,62000000000,100,now_wall_ms=62000)['status']=='UNKNOWN'
    ledger=ObserverLedger(tmp_path/'ledger.db')
    from dataclasses import asdict
    ref=ledger.record('UTC_DIAGNOSTIC',dict(sample=asdict(sample),session=ledger.session,authenticated=False,issuer_attestation=False))
    wall,mono=2000,2000000000
    ledger.observe(payload(symbol='BTCUSDT',interval='1m',row=ROW),raw=json.dumps([ROW]),
        endpoint='test',transport='REST',wall_ms=wall,monotonic_ns=mono,clock_ref=None,
        metadata=dict(symbol='BTCUSDT',interval='1m',utc_sample_ref=ref,
            utc_policy_max_uncertainty_ms=100,utc_diagnostic=assess(sample,mono,100,now_wall_ms=wall)))
    b=ledger.bundle(); assert verify_bundle(b,b['ledger_head'])
    ledger.close()
    reopened=ObserverLedger(tmp_path/'ledger.db')
    # A sample from prior process/session cannot certify the next event.
    reopened.observe(payload(symbol='BTCUSDT',interval='1m',row=ROW),raw=json.dumps([ROW]),
        endpoint='test',transport='REST',wall_ms=wall,monotonic_ns=mono,clock_ref=None,
        metadata=dict(symbol='BTCUSDT',interval='1m',utc_sample_ref=ref,
            utc_policy_max_uncertainty_ms=100,utc_diagnostic=assess(sample,mono,100,now_wall_ms=wall)))
    b=reopened.bundle()
    with pytest.raises(ProofError,match='session'): verify_bundle(b,b['ledger_head'])
    reopened.close()

def test_failed_checkpoint_preserves_ledger_and_retry(tmp_path,monkeypatch,capsys):
    l=ObserverLedger(tmp_path/'ledger.db'); q=EvidenceOutbox(tmp_path/'outbox')
    original=q.enqueue
    monkeypatch.setattr(q,'enqueue',lambda *_:(_ for _ in ()).throw(OSError('disk full')))
    head=l.verify(); assert watcher.checkpoint(l,q) is None and l.verify()==head
    assert 'LOCAL_EXPORT_PENDING' in capsys.readouterr().out
    monkeypatch.setattr(q,'enqueue',original)
    assert watcher.checkpoint(l,q); assert q.pending_count()==1
    l.close()

@pytest.mark.parametrize('invalid', ['origin','unsynchronized','short','processing'])
def test_sntp_rejects_invalid_packet(monkeypatch,invalid):
    import socket,struct,time
    from aql.utc_evidence import measure_sntp
    class Sock:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def settimeout(self,*_): pass
        def connect(self,*_): pass
        def send(self,request): self.request=request
        def recv(self,*_):
            r=bytearray(48);r[0]=0x24;r[1]=2
            r[24:32]=self.request[40:48]
            r[32:40]=self.request[40:48];r[40:48]=self.request[40:48]
            if invalid=='origin': r[24:32]=bytes(8)
            if invalid=='unsynchronized': r[0]=0xe4
            if invalid=='short': return bytes(8)
            if invalid=='processing': r[40:48]=struct.pack('!II',4000000000,0)
            return bytes(r)
    monkeypatch.setattr(socket,'socket',lambda *_:Sock())
    with pytest.raises(ValueError):measure_sntp()

def test_sntp_retains_packet_and_roundtrip(monkeypatch):
    import socket,struct
    from aql.utc_evidence import measure_sntp
    class Sock:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def settimeout(self,*_): pass
        def connect(self,*_): pass
        def send(self,request): self.request=request
        def recv(self,*_):
            r=bytearray(48);r[0]=0x24;r[1]=2
            r[4:8]=struct.pack('!i',655);r[8:12]=struct.pack('!I',655)
            r[24:32]=self.request[40:48]
            r[32:40]=self.request[40:48];r[40:48]=self.request[40:48]
            return bytes(r)
    monkeypatch.setattr(socket,'socket',lambda *_:Sock())
    sample=measure_sntp()
    assert sample.roundtrip_ms>=0 and len(sample.response_ntp_hex)==96
    assert sample.root_delay_ms>0 and sample.root_dispersion_ms>0
    assert assess(sample,sample.monotonic_ns,100,now_wall_ms=sample.wall_utc_ms)['status']=='UTC_DIAGNOSTIC_BOUNDED_NOT_ATTESTED'
