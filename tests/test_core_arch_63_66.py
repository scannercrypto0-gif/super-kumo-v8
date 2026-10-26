"""Synthetic local acceptance; T numbers refer to DESIGN-2, not deployed safety."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
from unittest.mock import Mock, patch

import pytest

from aql.delivery.authority import Authority, Limits, PublicationDenied
from aql.g1_integrity import ContentConflictError
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def bar(i=0, **kwargs):
    return replace(MarketBar('BTCUSDT','1m',i*60000,(i+1)*60000-1,
        100.,101.,99.,100.,1.,True,'synthetic-core128',(i+1)*60000),**kwargs).with_checksum()


def setup(root,n=3,**kwargs):
    j=DurableJournal(str(root/'source.sqlite'))
    for i in range(n): j.commit(bar(i))
    limits=Limits(max_records=32,max_bytes=131072,timeout_seconds=2,max_events=256)
    a=Authority(j,limits=limits,synthetic=True,**kwargs)
    return j,a,a.fence('sandbox')


def conflict(j,i=1):
    with pytest.raises(ContentConflictError): j.commit(bar(i,close=100.5))


def reopen(a):
    return Authority(DurableJournal(a.journal.db_path),limits=a.limits,synthetic=True,
                     anchor=a.anchor,checkpoint=a.checkpoint())


def test_T01_deliver_a_c_withhold_b(tmp_path):
    j,a,e=setup(tmp_path);conflict(j)
    for seq in (1,2,3): a.deliver('sandbox',e,seq)
    assert a.view('sandbox')==dict(D=[1,3],W=[2],V=[1,3],S=3)
    assert a.read('sandbox',1)['bar_open']==0 and a.read('sandbox',3)['bar_open']==120000
    with pytest.raises(ContentConflictError): a.read('sandbox',2)
    assert j.count_by_state()=={'LOCAL_COMMITTED':3}


def test_T07_failed_evidence_faults_authority_across_restart(tmp_path):
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    import aql.delivery.authority as module
    original=module._append
    def fail(conn,op,data):
        if op=='BLOCK': raise sqlite3.OperationalError('injected audit failure')
        return original(conn,op,data)
    with patch.object(module,'_append',side_effect=fail):
        with pytest.raises(sqlite3.OperationalError): j.commit(bar(1,close=100.5))
    with pytest.raises(PublicationDenied,match='BOOTSTRAP_BLOCKED'): a.read('sandbox',2)
    with pytest.raises(PublicationDenied,match='BOOTSTRAP_BLOCKED'): reopen(a)
    assert j.quarantined_keys()==set()  # failed proof is not fabricated


def test_T10_conflict_after_batch_and_stage_before_publish(tmp_path):
    j,a,e=setup(tmp_path)
    sid=a.stage('sandbox',e,2)
    with pytest.raises(PublicationDenied): a.read('sandbox',2)
    conflict(j)
    with pytest.raises(ContentConflictError): a.publish('sandbox',e,2,sid)
    a.settle('sandbox',e,2,withheld=True)
    a.deliver('sandbox',e,3)
    assert a.view('sandbox')['V']==[3]


@pytest.mark.parametrize('winner',['publish','quarantine'])
def test_T11_publication_conflict_serialization(tmp_path,winner):
    j,a,e=setup(tmp_path);sid=a.stage('sandbox',e,2)
    entered,release=threading.Event(),threading.Event()
    if winner=='publish':
        def hook(stage):
            if stage=='before_publish':
                entered.set();assert release.wait(5)
        a.fault=hook
        with ThreadPoolExecutor(2) as pool:
            publication=pool.submit(a.publish,'sandbox',e,2,sid)
            assert entered.wait(5)
            quarantine=pool.submit(conflict,j)
            release.set();receipt=publication.result(5);quarantine.result(5)
        assert receipt
    else:
        conflict(j)
        with pytest.raises(ContentConflictError): a.publish('sandbox',e,2,sid)
    a.fault=lambda _:None
    with pytest.raises(ContentConflictError): a.read('sandbox',2)
    with pytest.raises(ContentConflictError): a.settle('sandbox',e,2,receipt='forged')
    assert a.view('sandbox')['V']==[] and a.view('sandbox')['D']==[]


def test_T11e_legacy_paths_and_unpublished_read_fail_closed(tmp_path):
    from aql.archive.local import source_row
    from aql.storage.sandbox_store import SandboxReplicator
    j,a,e=setup(tmp_path);a.stage('sandbox',e,1)
    with pytest.raises(PublicationDenied): a.read('sandbox',1)
    with pytest.raises(PublicationDenied): j.replay()
    with pytest.raises(PublicationDenied): j.mark_persisted(bar().stable_key())
    with j._connect() as conn:
        with pytest.raises(PublicationDenied): source_row(conn,1)
    remote=Mock()
    with pytest.raises(PublicationDenied): SandboxReplicator(j,remote,str(tmp_path/'cursor')).deliver_once()
    remote.upsert.assert_not_called()
    with pytest.raises(PublicationDenied): j.commit(bar(4))


def test_T12_late_conflict_below_settlement(tmp_path):
    j,a,e=setup(tmp_path)
    for seq in (1,2,3): a.deliver('sandbox',e,seq)
    conflict(j)
    assert a.view('sandbox')==dict(D=[1,2,3],W=[],V=[1,3],S=3)
    with pytest.raises(ContentConflictError): reopen(a).read('sandbox',2)
    assert a.read('sandbox',3)['bar_open']==120000


def test_T14_stale_publisher_fence_and_consumer_independence(tmp_path):
    j,a,e=setup(tmp_path);sid=a.stage('sandbox',e,1)
    newer=reopen(a);f=newer.fence('sandbox')
    with pytest.raises(PublicationDenied,match='fence'): a.publish('sandbox',e,1,sid)
    newer.deliver('sandbox',f,1)
    assert newer.view('archive')==dict(D=[],W=[],V=[],S=0)
    with pytest.raises(PublicationDenied): newer.read('archive',1)


@pytest.mark.parametrize('failure',['before_hook','hook_and_fault_file'])
def test_R1_durable_denial_precedes_audit_failure(tmp_path,failure):
    import aql.delivery.authority as module
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    checkpoint=a.checkpoint()
    if failure=='before_hook':
        with patch('aql.journal.durable_journal.record_event',side_effect=sqlite3.OperationalError('audit failure')):
            with pytest.raises(sqlite3.OperationalError): j.commit(bar(1,close=100.5))
    else:
        original=module._append
        def fail(conn,op,data):
            if op=='BLOCK': raise sqlite3.OperationalError('audit failure')
            return original(conn,op,data)
        with patch.object(module,'_append',side_effect=fail),patch.object(module,'_trip',side_effect=OSError('unwritable fault file')):
            with pytest.raises(OSError): j.commit(bar(1,close=100.5))
    assert not j.quarantined_keys()
    with pytest.raises(PublicationDenied): a.reader('sandbox').read(2)
    with pytest.raises(PublicationDenied):
        Authority(DurableJournal(j.db_path),limits=a.limits,synthetic=True,anchor=a.anchor,checkpoint=checkpoint)


def test_R2_unbound_operational_store_conflict_must_deny_read(tmp_path):
    """OPEN INDEPENDENT FINDING: this acceptance test must remain RED until fixed."""
    from aql.storage.operational_store import OperationalStore
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    store=OperationalStore(str(tmp_path/'store.sqlite'));store.upsert(bar(1))
    with pytest.raises(ContentConflictError): store.upsert(bar(1,close=100.5))
    assert store.quarantined_keys()=={bar(1).stable_key()}
    with pytest.raises((ContentConflictError,PublicationDenied)):
        a.reader('sandbox').read(2)


def test_R3_operational_reader_has_no_public_sql_or_stage_capability(tmp_path):
    j,a,e=setup(tmp_path);a.stage('sandbox',e,1)
    reader=a.reader('sandbox')
    for name in ('connection','transaction','journal','stage','publish','_connection'):
        assert not hasattr(reader,name)
    assert not hasattr(a,'connection') and not hasattr(a,'transaction')
    with pytest.raises(PublicationDenied): reader.read(1)


@pytest.mark.parametrize('op,data',[
    ('WITHHELD',dict(consumer='sandbox',source_seq=1,key='BTCUSDT:1m:60000',evidence='fake')),
    ('PUBLISH',dict(consumer='sandbox',source_seq=2,epoch=1,stage='forged')),
    ('DELIVERED',dict(consumer='sandbox',source_seq=2,receipt='forged')),
])
def test_R4_T13_rehashed_semantic_ledger_forgery_rejected(tmp_path,op,data):
    from aql.delivery.authority import _append
    j,a,e=setup(tmp_path);conflict(j)
    with j._connect() as conn: _append(conn,op,data)
    with pytest.raises(PublicationDenied): a.rebuild()


def test_R4_empty_or_wrong_genesis_rejected(tmp_path):
    j,a,e=setup(tmp_path)
    with j._connect() as conn:
        conn.execute('DROP TRIGGER core128_events_no_delete')
        conn.execute('DELETE FROM core128_events')
    with pytest.raises(PublicationDenied): a.rebuild()


def test_R5_T15_old_snapshot_requires_current_progress_checkpoint(tmp_path):
    j,a,e=setup(tmp_path);sid=a.stage('sandbox',e,1)
    old=sqlite3.connect(tmp_path/'older.sqlite')
    with j._connect() as conn: conn.backup(old)
    old.close()
    a.fence('sandbox');current=a.checkpoint()
    saved=sqlite3.connect(tmp_path/'older.sqlite')
    with j._connect() as conn: saved.backup(conn)
    saved.close()
    with pytest.raises(PublicationDenied,match='progress checkpoint'):
        Authority(DurableJournal(j.db_path),limits=a.limits,synthetic=True,anchor=a.anchor,checkpoint=current)


def test_T08_T16_unproven_settlement_and_pending_stage(tmp_path):
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,1);a.stage('sandbox',e,2);a.deliver('sandbox',e,3)
    assert a.view('sandbox')==dict(D=[1,3],W=[],V=[1,3],S=1)
    with pytest.raises(PublicationDenied): a.settle('sandbox',e,2,receipt='false')
    with pytest.raises(PublicationDenied): a.settle('sandbox',e,2,withheld=True)
    assert reopen(a).view('sandbox')['S']==1


def test_T05_T06_projection_rebuild_and_failed_commit(tmp_path):
    j,a,e=setup(tmp_path)
    a.fault=lambda s:(_ for _ in ()).throw(sqlite3.OperationalError('commit failure')) if s=='before_commit' else None
    with pytest.raises(sqlite3.OperationalError): a.stage('sandbox',e,1)
    a.fault=lambda _:None
    assert a.view('sandbox')['S']==0
    a.deliver('sandbox',e,1)
    with j._connect() as conn: conn.execute('DELETE FROM core128_projection')
    with pytest.raises(PublicationDenied): a.view('sandbox')
    a.rebuild();assert a.view('sandbox')['D']==[1]


def test_E04_full_source_capsule_preserves_legacy_checksum_semantics(tmp_path):
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,1)
    with j._connect() as conn:
        data=json.loads(conn.execute('SELECT payload_json FROM journal_entries WHERE id=1').fetchone()[0])
        before=MarketBar.from_dict(data).compute_checksum()
        data['ingested_at']+=1
        assert MarketBar.from_dict(data).compute_checksum()==before
        conn.execute('UPDATE journal_entries SET payload_json=? WHERE id=1',(json.dumps(data),))
    with pytest.raises(PublicationDenied,match='Full source'): a.read('sandbox',1)


@pytest.mark.parametrize('window',['before_stage_commit','after_stage','after_publish'])
def test_T02_T03_T04_real_process_exit_and_reconcile(tmp_path,window):
    import os
    from pathlib import Path
    import subprocess
    import sys
    j,a,e=setup(tmp_path);initial=a.checkpoint()
    script='''
import json,os,sys
from aql.journal.durable_journal import DurableJournal
from aql.delivery.authority import Authority,Limits
path,anchor,checkpoint,limits,epoch,window=sys.argv[1:]
a=Authority(DurableJournal(path),limits=Limits(**json.loads(limits)),synthetic=True,
            anchor=json.loads(anchor),checkpoint=json.loads(checkpoint))
if window=='before_stage_commit':
    a.fault=lambda s:os._exit(23) if s=='before_commit' else None
sid=a.stage('sandbox',int(epoch),1)
if window=='after_publish': a.publish('sandbox',int(epoch),1,sid)
print(json.dumps(a.checkpoint()),flush=True)
os._exit(23)
'''
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP') if k in os.environ}
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    p=subprocess.run([sys.executable,'-B','-c',script,j.db_path,json.dumps(a.anchor),json.dumps(initial),
                      json.dumps(a.limits.__dict__),str(e),window],env=env,capture_output=True,text=True,timeout=20)
    assert p.returncode==23,p.stderr
    # Child's observed post-COMMIT head retained by independent parent fixture.
    head=json.loads(p.stdout) if p.stdout else initial
    recovered=Authority(DurableJournal(j.db_path),limits=a.limits,synthetic=True,anchor=a.anchor,checkpoint=head)
    assert recovered.view('sandbox')['S']==0
    if window!='after_publish':
        with pytest.raises(PublicationDenied): recovered.read('sandbox',1)
    recovered.deliver('sandbox',e,1);recovered.deliver('sandbox',e,1)
    with j._connect() as conn:
        ops=[json.loads(row[0])['op'] for row in conn.execute('SELECT body FROM core128_events')]
    assert ops.count('STAGE')==ops.count('PUBLISH')==1
    assert recovered.view('sandbox')==dict(D=[1],W=[],V=[1],S=1)


def test_E06_cross_process_stale_fence(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    j,a,e=setup(tmp_path);sid=a.stage('sandbox',e,1);head=a.checkpoint()
    script='''
import json,sys
from aql.journal.durable_journal import DurableJournal
from aql.delivery.authority import Authority,Limits,PublicationDenied
path,anchor,head,limits,epoch,sid=sys.argv[1:]
a=Authority(DurableJournal(path),limits=Limits(**json.loads(limits)),synthetic=True,
            anchor=json.loads(anchor),checkpoint=json.loads(head))
print('READY',flush=True);sys.stdin.readline()
try: a.publish('sandbox',int(epoch),1,sid)
except PublicationDenied: print('DENIED',flush=True)
else: sys.exit(9)
'''
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP') if k in os.environ}
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    p=subprocess.Popen([sys.executable,'-B','-c',script,j.db_path,json.dumps(a.anchor),json.dumps(head),
                        json.dumps(a.limits.__dict__),str(e),sid],env=env,stdin=subprocess.PIPE,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert p.stdout.readline().strip()=='READY'
        a.fence('sandbox')
        out,err=p.communicate('go\n',timeout=20)
        assert p.returncode==0 and 'DENIED' in out,err
    finally:
        if p.poll() is None: p.kill();p.wait()


def test_E07_concurrent_publication_has_one_receipt(tmp_path):
    j,a,e=setup(tmp_path);sid=a.stage('sandbox',e,1)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:a.publish('sandbox',e,1,sid),range(2)))
    assert results[0]==results[1]
    with j._connect() as conn:
        assert sum(json.loads(r[0])['op']=='PUBLISH' for r in conn.execute('SELECT body FROM core128_events'))==1


def test_T31_event_capacity_is_fail_closed_without_eviction(tmp_path):
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    a=Authority(j,limits=Limits(4,8192,2,4),synthetic=True);e=a.fence('sandbox')
    sid=a.stage('sandbox',e,1);receipt=a.publish('sandbox',e,1,sid)
    with pytest.raises(PublicationDenied,match='ledger full'): a.settle('sandbox',e,1,receipt=receipt)
    assert a.view('sandbox')==dict(D=[],W=[],V=[1],S=0)
