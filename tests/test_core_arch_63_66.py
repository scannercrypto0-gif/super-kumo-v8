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
from aql.storage.operational_store import OperationalStore


def bar(i=0, **kwargs):
    return replace(MarketBar('BTCUSDT','1m',i*60000,(i+1)*60000-1,
        100.,101.,99.,100.,1.,True,'synthetic-core128',(i+1)*60000),**kwargs).with_checksum()


def setup(root,n=3,**kwargs):
    j=DurableJournal(str(root/'source.sqlite'))
    for i in range(n): j.commit(bar(i))
    limits=Limits(max_records=32,max_bytes=131072,timeout_seconds=2,max_events=256)
    # Activation now explicitly enrolls a fresh store. The historical R2 test
    # body is unchanged; separate tests preserve the genuinely-unbound premise.
    store=OperationalStore(str(root/'store.sqlite'))
    a=Authority(j,limits=limits,synthetic=True,stores=[store],**kwargs)
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
    ('WITHHELD',dict(consumer='sandbox',source_seq=1,epoch=1,key='BTCUSDT:1m:60000',evidence='fake')),
    ('PUBLISH',dict(consumer='sandbox',source_seq=2,epoch=1,stage='forged')),
    ('DELIVERED',dict(consumer='sandbox',source_seq=2,epoch=1,receipt='forged')),
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


@pytest.mark.parametrize('op,data',[
    ('DELIVERED',dict(consumer='sandbox',source_seq=1,epoch=1,receipt=None)),
    ('PUBLISH',dict(consumer='sandbox',source_seq=1,epoch=None,stage=None)),
    ('PUBLISH',dict(consumer='sandbox',source_seq=1,epoch=1,stage=None)),
])
def test_R4_null_publication_and_null_ack_never_settle(tmp_path,op,data):
    from aql.delivery.authority import _append
    j,a,e=setup(tmp_path)
    with j._connect() as conn: _append(conn,op,data)
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


def test_R5_copied_source_path_cannot_fork_publication_authority(tmp_path):
    j,a,e=setup(tmp_path);a.stage('sandbox',e,1);head=a.checkpoint()
    copied=sqlite3.connect(tmp_path/'copy.sqlite')
    with j._connect() as conn: conn.backup(copied)
    copied.close()
    with pytest.raises(PublicationDenied,match='Copied source path'):
        Authority(DurableJournal(str(tmp_path/'copy.sqlite')),limits=a.limits,synthetic=True,
                  anchor=a.anchor,checkpoint=head)


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
    a=Authority(j,limits=Limits(4,8192,2,4),synthetic=True,
                stores=[OperationalStore(str(tmp_path/'store.sqlite'))]);e=a.fence('sandbox')
    sid=a.stage('sandbox',e,1);receipt=a.publish('sandbox',e,1,sid)
    with pytest.raises(PublicationDenied,match='ledger full'): a.settle('sandbox',e,1,receipt=receipt)
    assert a.view('sandbox')==dict(D=[],W=[],V=[1],S=0)


def test_R6_reopen_cannot_raise_frozen_capacity(tmp_path):
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    a=Authority(j,limits=Limits(1,8192,2,32),synthetic=True,
                stores=[OperationalStore(str(tmp_path/'store.sqlite'))])
    e=a.fence('sandbox');a.stage('sandbox',e,1)
    with pytest.raises(PublicationDenied,match='Runtime limits'):
        Authority(DurableJournal(j.db_path),limits=Limits(32,8192,2,32),synthetic=True,
                  anchor=a.anchor,checkpoint=a.checkpoint())


def test_R2_no_binding_activation_is_refused_not_guessed(tmp_path):
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    unrelated=OperationalStore(str(tmp_path/'unrelated.sqlite'))
    unrelated.upsert(bar())
    with pytest.raises(PublicationDenied,match='Explicit OperationalStore'):
        Authority(j,limits=Limits(4,8192,2,32),synthetic=True)
    # No successful activation/ProtectedReader exists. The unrelated v1 DB is
    # not magically enrolled by matching market keys, and v1 remains intact.
    assert len(j.replay())==1 and unrelated.count()==1


def test_R2_unbound_configured_writer_rejected_before_effect(tmp_path):
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    unrelated=OperationalStore(str(tmp_path/'unrelated.sqlite'))
    with pytest.raises(PublicationDenied,match='Unbound configured'):
        a.store_writer(unrelated)
    assert unrelated.count()==0
    # A truly unrelated legacy store has no source authority to contaminate.
    unrelated.upsert(bar(1))
    with pytest.raises(ContentConflictError): unrelated.upsert(bar(1,close=100.5))
    assert a.read('sandbox',2)['bar_open']==60000


def test_R2_writer_created_before_registration_cannot_bypass(tmp_path):
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    path=str(tmp_path/'store.sqlite')
    preexisting=OperationalStore(path);registered=OperationalStore(path)
    a=Authority(j,limits=Limits(4,8192,2,64),synthetic=True,stores=[registered])
    with pytest.raises(PublicationDenied,match='Unbound configured'):
        preexisting.upsert(bar())
    assert preexisting.count()==0
    assert a.store_writer(registered).upsert(bar())


def test_R2_registered_reopen_propagates_conflict_and_preserves_other_key(tmp_path):
    j,a,e=setup(tmp_path)
    for seq in (1,2,3): a.deliver('sandbox',e,seq)
    store=a.store_writer(OperationalStore(str(tmp_path/'store.sqlite')))
    store.upsert(bar(1))
    with pytest.raises(ContentConflictError): store.upsert(bar(1,close=100.5))
    with pytest.raises(ContentConflictError): reopen(a).reader('sandbox').read(2)
    assert reopen(a).view('sandbox')==dict(D=[1,2,3],W=[],V=[1,3],S=3)
    assert a.read('sandbox',1)['bar_open']==0
    assert a.read('sandbox',3)['bar_open']==120000
    # Repeated quarantine remains blocked; it cannot reinstate eligibility.
    with pytest.raises(ContentConflictError): store.upsert(bar(1))
    with pytest.raises(ContentConflictError): a.read('sandbox',2)


@pytest.mark.parametrize('mode',['missing','new_db','old_snapshot','changed_path'])
def test_R2_store_identity_or_state_replacement_denies(tmp_path,mode):
    from pathlib import Path
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    path=tmp_path/'store.sqlite'
    store=OperationalStore(str(path))
    backup=sqlite3.connect(tmp_path/'old.sqlite')
    with store._connect() as conn: conn.backup(backup)
    conn.close()
    backup.close()
    store.upsert(bar(1))
    if mode=='missing':
        # All managed handles are closed; disposable fixture file only.
        path.rename(tmp_path/'removed.sqlite')
    elif mode=='new_db':
        with sqlite3.connect(tmp_path/'replacement.sqlite') as replacement:
            with sqlite3.connect(path) as target: replacement.backup(target)
    elif mode=='old_snapshot':
        with sqlite3.connect(tmp_path/'old.sqlite') as old:
            with sqlite3.connect(path) as target: old.backup(target)
    else:
        store.db_path=str(tmp_path/'different.sqlite')
        with pytest.raises(PublicationDenied,match='path changed'): store.upsert(bar(1))
        return
    with pytest.raises((PublicationDenied,sqlite3.DatabaseError)):
        a.reader('sandbox').read(2)


def test_R2_store_writer_epoch_fenced_across_reopen(tmp_path):
    from aql.delivery.store_binding import fence_store
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    old=OperationalStore(str(tmp_path/'store.sqlite'))
    assert fence_store(a,old)==2
    with pytest.raises(PublicationDenied,match='Stale store writer'): old.upsert(bar(1))
    fresh=OperationalStore(str(tmp_path/'store.sqlite'))
    assert reopen(a).store_writer(fresh).upsert(bar(1))
    with pytest.raises(ContentConflictError): fresh.upsert(bar(1,close=100.5))
    with pytest.raises(ContentConflictError): a.read('sandbox',2)


@pytest.mark.parametrize('failure',['source_audit','store_audit','completion','post_commit'])
def test_R2_audit_or_completion_failure_retains_durable_denial(tmp_path,failure):
    import aql.delivery.store_binding as module
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    store=OperationalStore(str(tmp_path/'store.sqlite'));store.upsert(bar(1))
    actual=module.record_event
    def fail(conn,*args,**kwargs):
        is_source=bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='journal_entries'").fetchone())
        if (failure=='source_audit' and is_source) or (failure=='store_audit' and not is_source):
            raise sqlite3.OperationalError('injected audit failure')
        return actual(conn,*args,**kwargs)
    original_append=module._append
    def append(conn,op,data):
        if failure=='completion' and op=='STORE_COMMIT':
            raise sqlite3.OperationalError('injected completion failure')
        return original_append(conn,op,data)
    if failure=='post_commit':
        store.binding_fault=lambda stage: (_ for _ in ()).throw(sqlite3.OperationalError('after store commit')) if stage=='after_store_commit' else None
    with patch.object(module,'record_event',side_effect=fail),patch.object(module,'_append',side_effect=append):
        with pytest.raises(sqlite3.OperationalError): store.upsert(bar(1,close=100.5))
    for attempt in range(2):
        with pytest.raises(PublicationDenied): a.reader('sandbox').read(2)
        with pytest.raises(PublicationDenied): reopen(a)
    with j._connect() as conn:
        assert sum(json.loads(r[0])['op']=='STORE_INTENT' for r in conn.execute('SELECT body FROM core128_events'))==2


@pytest.mark.parametrize('winner',['publish','intent'])
def test_R2_store_conflict_publish_serialization(tmp_path,winner):
    j,a,e=setup(tmp_path);sid=a.stage('sandbox',e,2)
    store=OperationalStore(str(tmp_path/'store.sqlite'));store.upsert(bar(1))
    entered,release=threading.Event(),threading.Event()
    def pause(stage):
        if stage==('before_publish' if winner=='publish' else 'after_intent'):
            entered.set();assert release.wait(10)
    def quarantine():
        with pytest.raises(ContentConflictError): store.upsert(bar(1,close=100.5))
    if winner=='publish':
        a.fault=pause
        with ThreadPoolExecutor(2) as pool:
            published=pool.submit(a.publish,'sandbox',e,2,sid)
            assert entered.wait(10)
            blocked=pool.submit(quarantine)
            release.set();assert published.result(10);blocked.result(10)
    else:
        store.binding_fault=pause
        with ThreadPoolExecutor(2) as pool:
            blocked=pool.submit(quarantine)
            assert entered.wait(10)
            try:
                with pytest.raises(PublicationDenied,match='denial intent'): a.publish('sandbox',e,2,sid)
                with pytest.raises(PublicationDenied): a.read('sandbox',2)
            finally: release.set()
            blocked.result(10)
    a.fault=lambda _:None
    with pytest.raises(ContentConflictError): a.reader('sandbox').read(2)
    with pytest.raises(ContentConflictError): a.settle('sandbox',e,2,receipt='forged')


@pytest.mark.parametrize('window',['after_intent','after_store_commit','before_source_commit'])
def test_R2_store_process_exit_retains_denial_on_restart(tmp_path,window):
    import os,subprocess,sys
    from pathlib import Path
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    store=OperationalStore(str(tmp_path/'store.sqlite'));store.upsert(bar(1))
    script='''
import os,sys
from dataclasses import replace
from aql.storage.operational_store import OperationalStore
from aql.models.bar import MarketBar
s=OperationalStore(sys.argv[1])
s.binding_fault=lambda stage:os._exit(29) if stage==sys.argv[2] else None
b=MarketBar('BTCUSDT','1m',60000,119999,100.,101.,99.,100.5,1.,True,'synthetic-core128',120000).with_checksum()
s.upsert(b)
'''
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP') if k in os.environ}
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    p=subprocess.run([sys.executable,'-B','-c',script,store.db_path,window],env=env,
                     capture_output=True,text=True,timeout=30)
    assert p.returncode==29,p.stderr
    # Even a current head read by this independent parent fixture cannot clear
    # the unresolved intent. No successful store completion/ACK is fabricated.
    with j._connect() as conn:
        head=tuple(conn.execute('SELECT seq,hash FROM core128_events ORDER BY seq DESC LIMIT 1').fetchone())
    with pytest.raises(PublicationDenied): a.read('sandbox',2)
    with pytest.raises(PublicationDenied):
        Authority(DurableJournal(j.db_path),limits=a.limits,synthetic=True,anchor=a.anchor,checkpoint=head)


def test_R2_bound_store_legacy_coverage_and_outside_inventory_denied(tmp_path):
    j,a,e=setup(tmp_path)
    store=OperationalStore(str(tmp_path/'store.sqlite'))
    with pytest.raises(PublicationDenied): store.get_stored_keys('BTCUSDT','1m')
    with pytest.raises(PublicationDenied): store.get_range('BTCUSDT','1m')
    with pytest.raises(PublicationDenied,match='outside frozen'): store.upsert(bar(9))
    assert store.count()==0


def test_R2_mirrored_quarantine_uses_bound_protocol(tmp_path):
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    store=OperationalStore(str(tmp_path/'store.sqlite'));store.upsert(bar(1))
    with pytest.raises(ContentConflictError) as error: j.commit(bar(1,close=100.5))
    store.quarantine(error.value)
    with pytest.raises(ContentConflictError): a.read('sandbox',2)
    assert store.quarantined_keys()=={bar(1).stable_key()}


@pytest.mark.parametrize('operation',['upsert','quarantine'])
def test_R2_legacy_dispatch_cannot_write_after_enrollment(tmp_path,operation):
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    path=str(tmp_path/'store.sqlite')
    old=OperationalStore(path);fresh=OperationalStore(path)
    entered,release=threading.Event(),threading.Event()
    def pause():
        entered.set();assert release.wait(10)
    if operation=='upsert':
        actual=old._upsert_local
        def delayed(*args,**kwargs):
            pause();return actual(*args,**kwargs)
        old._upsert_local=delayed
        work=lambda:old.upsert(bar())
        scope=patch('aql.delivery.authority.prepare_candidate',wraps=__import__('aql.delivery.authority',fromlist=['prepare_candidate']).prepare_candidate)
    else:
        from aql.g1_integrity import IntegrityAccess
        actual=__import__('aql.delivery.authority',fromlist=['prepare_candidate']).prepare_candidate
        def delayed(*args,**kwargs):
            pause();return actual(*args,**kwargs)
        scope=patch('aql.delivery.authority.prepare_candidate',side_effect=delayed)
        work=lambda:old._record_integrity_event(bar(),bar(close=100.5))
    with scope,ThreadPoolExecutor(1) as pool:
        pending=pool.submit(work)
        assert entered.wait(10)
        try:
            a=Authority(j,limits=Limits(4,8192,2,64),synthetic=True,stores=[fresh])
            e=a.fence('sandbox');a.deliver('sandbox',e,1)
        finally: release.set()
        with pytest.raises(PublicationDenied): pending.result(10)
    assert fresh.count()==0 and fresh.quarantined_keys()==set()
    assert a.read('sandbox',1)['close']==100.


@pytest.mark.parametrize('conflicting',[False,True])
def test_R2_rehashed_completion_cannot_erase_unperformed_intent(tmp_path,conflicting):
    import aql.delivery.store_binding as module
    from aql.delivery.authority import _append,_project
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    store=OperationalStore(str(tmp_path/'store.sqlite'))
    def interrupted(stage):
        if stage=='after_intent': raise RuntimeError('interrupted before store effect')
    store.binding_fault=interrupted
    with pytest.raises(RuntimeError): store.upsert(bar(1,close=100.5 if conflicting else 100.))
    with pytest.raises(PublicationDenied): a.read('sandbox',2)
    # Same adversarial SQL/rehash privilege as retained R4 tests. A matching
    # local hash is not semantic proof of quarantine or a completed write.
    with j._connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        intent=json.loads(conn.execute("SELECT body FROM core128_events ORDER BY seq DESC LIMIT 1").fetchone()[0])['data']
        with module.existing(store.db_path) as target: current=module.state_digest(target,a.limits)
        _append(conn,'STORE_COMMIT',dict(store=intent['store'],epoch=intent['epoch'],id=intent['id'],state_digest=current))
        _project(conn);conn.commit()
    with pytest.raises(PublicationDenied,match='completion lacks matching'): a.read('sandbox',2)


def test_R2_original_acceptance_function_is_text_unchanged():
    import ast,hashlib
    from pathlib import Path
    text=Path(__file__).read_text(encoding='utf-8')
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)
              and n.name=='test_R2_unbound_operational_store_conflict_must_deny_read')
    assert hashlib.sha256(ast.get_source_segment(text,node).encode()).hexdigest()=='ab467cdba1339ae499d5acad4a6097012ec9d1728b0650de2c5030a9e46c7a5d'


def test_R2_configured_legacy_collector_and_recovery_refused_before_effect(tmp_path):
    from aql.collector.binance_collector import BinanceCollector
    from aql.pipeline import _run_gap_recovery
    j,a,e=setup(tmp_path);a.deliver('sandbox',e,2)
    unrelated=OperationalStore(str(tmp_path/'unrelated.sqlite'))
    with pytest.raises(PublicationDenied): BinanceCollector('BTCUSDT','1m',j,unrelated)
    with patch('aql.pipeline.recover_gap') as rest:
        with pytest.raises(PublicationDenied): _run_gap_recovery(j,unrelated,'BTCUSDT','1m',0,180000)
        rest.assert_not_called()
    assert unrelated.count()==0
    with pytest.raises(PublicationDenied,match='legacy writer retries'): j.commit(bar(1))
    assert a.read('sandbox',2)['bar_open']==60000


def test_R2_collector_constructed_before_activation_prevents_activation(tmp_path):
    from aql.collector.binance_collector import BinanceCollector
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    unrelated=OperationalStore(str(tmp_path/'unrelated.sqlite'))
    collector=BinanceCollector('BTCUSDT','1m',j,unrelated)
    registered=OperationalStore(str(tmp_path/'registered.sqlite'))
    with pytest.raises(PublicationDenied,match='configured legacy writers'):
        Authority(j,limits=Limits(4,8192,2,64),synthetic=True,stores=[registered])
    # Refuse source conversion, rather than pretending to recall already
    # prefetched legacy records or auto-enroll the old collector's target.
    assert unrelated.count()==0
    assert len(j.replay())==1


@pytest.mark.parametrize('client',['consumer','sandbox','startup','recovery'])
def test_R2_supported_legacy_clients_prevent_later_activation(tmp_path,client):
    from aql.lanes import JournalConsumer
    from aql.pipeline import _run_gap_recovery
    from aql.storage.sandbox_store import SandboxReplicator
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    target=OperationalStore(str(tmp_path/'legacy.sqlite'))
    if client=='consumer': JournalConsumer(j,target,'BTCUSDT','1m')
    elif client=='sandbox': SandboxReplicator(j,Mock(),str(tmp_path/'cursor.sqlite'))
    elif client=='startup':
        with patch('aql.journal.durable_journal.time.time',return_value=60):
            j.startup_reconcile(target,'BTCUSDT','1m')
    else:
        with patch('aql.pipeline.recover_gap',return_value=([],None)):
            _run_gap_recovery(j,target,'BTCUSDT','1m',0,60000)
    fresh=OperationalStore(str(tmp_path/'new.sqlite'))
    with pytest.raises(PublicationDenied,match='configured legacy writers'):
        Authority(j,limits=Limits(4,8192,2,64),synthetic=True,stores=[fresh])


def test_R2_activation_reservation_refuses_concurrent_legacy_registration(tmp_path):
    import aql.delivery.store_binding as module
    from aql.delivery.authority import register_legacy_writer
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    store=OperationalStore(str(tmp_path/'store.sqlite'))
    entered,release=threading.Event(),threading.Event()
    original=module.freeze_stores
    def pause(*args):
        entered.set();assert release.wait(10)
        return original(*args)
    with patch.object(module,'freeze_stores',side_effect=pause),ThreadPoolExecutor(1) as pool:
        activation=pool.submit(Authority,j,limits=Limits(4,8192,2,64),synthetic=True,stores=[store])
        assert entered.wait(10)
        try:
            with pytest.raises(PublicationDenied): register_legacy_writer(j,'collector')
            with pytest.raises(PublicationDenied): j.commit(bar())
            with pytest.raises(PublicationDenied): j.replay()
        finally: release.set()
        a=activation.result(10)
    e=a.fence('sandbox');a.deliver('sandbox',e,1)
    assert a.read('sandbox',1)['bar_open']==0


def test_R2_failed_activation_reservation_survives_restart(tmp_path):
    from aql.delivery.authority import register_legacy_writer
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar())
    store=OperationalStore(str(tmp_path/'store.sqlite'))
    with patch('aql.delivery.store_binding.freeze_stores',side_effect=OSError('enrollment interrupted')):
        with pytest.raises(OSError): Authority(j,limits=Limits(4,8192,2,64),synthetic=True,stores=[store])
    reopened=DurableJournal(j.db_path)
    with pytest.raises(PublicationDenied): reopened.commit(bar())
    with pytest.raises(PublicationDenied): reopened.replay()
    with pytest.raises(PublicationDenied): register_legacy_writer(reopened,'collector')
    with pytest.raises(PublicationDenied):
        Authority(reopened,limits=Limits(4,8192,2,64),synthetic=True,stores=[store])
