"""D2-B synthetic OFFLINE effect evidence. No real services/market inputs.

The first revision f964e1e recorded five RED baseline gaps against local D1.
These same five requirements now target the separately versioned D2 adapter;
the original 64 D1 tests and their accepted local semantics are untouched.
"""
from contextlib import closing
from dataclasses import replace
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import os

import pytest

from aql.archive.contracts import canonical, digest
from aql.delivery.authority import Authority, Limits, PublicationDenied
from aql.delivery.effects import EffectDelivery, EffectLimits, InDoubt, SQLiteEffectTarget
from aql.g1_integrity import ContentConflictError
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.storage.operational_store import OperationalStore


def bar(i=0, **kwargs):
    return replace(MarketBar('BTCUSDT','1m',i*60000,(i+1)*60000-1,
        100.,101.,99.,100.,1.,True,'synthetic-d2',(i+1)*60000),**kwargs).with_checksum()


def baseline(root, *, records=3, capacity=32, events=256):
    j=DurableJournal(str(root/'source.sqlite'))
    for i in range(records): j.commit(bar(i))
    a=Authority(j,limits=Limits(capacity,131072,2,events),synthetic=True,
                stores=[OperationalStore(str(root/'operational.sqlite'))])
    return j,a,a.fence('sandbox')


def effect_limits(**kw):
    return EffectLimits(**dict(dict(max_effects=8,max_events=128,max_bytes=131072,
                                    max_attempts=4,timeout_seconds=2),**kw))


def add_consumer(a,root,name='sandbox',*,limits=None,max_consumers=2):
    t=SQLiteEffectTarget.create(str(root/(name+'-target.sqlite')),synthetic=True)
    d=EffectDelivery(a,name,target=t,limits=limits or effect_limits(),
                     max_consumers=max_consumers,synthetic=True)
    return t,d,d.fence()


def setup(root,**kw):
    j,a,_=baseline(root,**kw)
    t,d,e=add_consumer(a,root)
    return j,a,t,d,e


def count_events(j,consumer='sandbox',table='core128_d2_events'):
    with closing(j._connect()) as c:
        return c.execute('SELECT COUNT(*) FROM '+table+
                         (' WHERE consumer=?' if table=='core128_d2_events' else ''),
                         (consumer,) if table=='core128_d2_events' else ()).fetchone()[0]


def reopen(d):
    return EffectDelivery(d.authority,d.consumer,anchor=d.anchor,checkpoint=d.checkpoint(),synthetic=True)


def conflict(j,i=0):
    with pytest.raises(ContentConflictError): j.commit(bar(i,close=100.5))


def backup(source,dest):
    with closing(sqlite3.connect(source)) as a,closing(sqlite3.connect(dest)) as b:
        a.backup(b)


def test_P1_no_target_effect_means_no_confirmed_D_or_S(tmp_path):
    j,a,t,d,e=setup(tmp_path)
    local=a.deliver('sandbox',1,1)
    assert a.view('sandbox')['D']==[1]  # Existing local-only D1 is not reinterpreted.
    with pytest.raises(PublicationDenied): d.confirm(e,local)
    d.begin(e,1)
    assert t.count()==0
    assert d.view()['D']==[] and d.view()['S']==0 and d.view()['IN_DOUBT']==[1]


def test_P2_duplicate_ack_has_no_event_growth(tmp_path):
    j,a,t,d,e=setup(tmp_path)
    receipt=d.deliver(e,1);before=count_events(j)
    assert d.confirm(e,receipt) is False
    assert d.deliver(e,1)==receipt
    assert count_events(j)==before and t.count()==1
    assert reopen(d).view()['D']==[1]


def test_P5_new_epoch_cannot_blindly_confirm_old_receipt(tmp_path):
    j,a,t,d,e=setup(tmp_path)
    old=d.perform(e,1);new=d.fence()
    with pytest.raises(PublicationDenied): d.confirm(e,old)
    with pytest.raises(PublicationDenied): d.confirm(new,old)
    assert d.view()['D']==[] and d.view()['S']==0
    receipt=reopen(d).reconcile(new,1)
    assert receipt['attempt_epoch']==new and receipt['origin_epoch']==e
    assert receipt['request']['effect_id']==old['request']['effect_id']
    assert t.count()==1 and d.view()['D']==[1]


def test_P7_archive_quota_does_not_consume_critical_consumer_quota(tmp_path):
    j,a,_=baseline(tmp_path,capacity=2,records=2)
    archive,ad,ae=add_consumer(a,tmp_path,'archive',limits=effect_limits(max_effects=1))
    target,d,e=add_consumer(a,tmp_path,'sandbox',limits=effect_limits(max_effects=2))
    before=count_events(j,table='core128_events')
    ad.deliver(ae,1)
    with pytest.raises(PublicationDenied): ad.deliver(ae,2)
    assert d.deliver(e,1) and d.deliver(e,2)
    assert archive.count()==1 and target.count()==2
    assert count_events(j,table='core128_events')==before
    assert d.view()['S']==2 and ad.view()['S']==1


def test_P8_idempotent_retries_do_not_fill_ledger(tmp_path):
    j,a,_=baseline(tmp_path,records=1)
    t,d,e=add_consumer(a,tmp_path,limits=effect_limits(max_events=4))
    first=d.deliver(e,1);before=count_events(j)
    for _ in range(12):
        assert d.deliver(e,1)==first
        assert d.confirm(e,first) is False
    assert before==count_events(j)==4 and t.count()==1
    with pytest.raises(PublicationDenied): d.fence()
    assert d.view()['D']==[1]


@pytest.mark.parametrize('window',[
    'before_intent','after_intent','pre_effect','post_target',
    'pre_receipt','post_receipt','pre_ack','post_ack'])
def test_crash_windows_require_explicit_reconciliation(tmp_path,window):
    j,a,t,d,e=setup(tmp_path)
    script="""
import json,os,sys
from aql.journal.durable_journal import DurableJournal
from aql.delivery.authority import Authority,Limits
from aql.delivery.effects import EffectDelivery
path,anchor,head,limits,danchor,dhead,epoch,window=sys.argv[1:]
a=Authority(DurableJournal(path),limits=Limits(**json.loads(limits)),synthetic=True,
            anchor=json.loads(anchor),checkpoint=json.loads(head))
d=EffectDelivery(a,'sandbox',anchor=json.loads(danchor),checkpoint=json.loads(dhead),synthetic=True)
d.fault=lambda stage:os._exit(37) if stage==window else None
d.deliver(int(epoch),1)
sys.exit(99)
"""
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP') if k in os.environ}
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    child=subprocess.run([sys.executable,'-B','-c',script,j.db_path,json.dumps(a.anchor),
        json.dumps(a.checkpoint()),json.dumps(a.limits.__dict__),json.dumps(d.anchor),
        json.dumps(d.checkpoint()),str(e),window],env=env,capture_output=True,text=True,timeout=30)
    assert child.returncode==37,child.stderr
    # A separate parent fixture retains the current observed source checkpoint.
    r=reopen(d);v=r.view()
    if window=='post_ack':
        assert v['D']==[1] and v['S']==1
    else:
        assert v['D']==[] and v['S']==0
        if window!='before_intent':
            assert v['IN_DOUBT']==[1]
            with pytest.raises(InDoubt): r.deliver(e,1)
    if window=='before_intent': r.deliver(e,1)
    else: r.reconcile(e,1)
    assert t.count()==1 and r.view()['D']==[1] and r.view()['S']==1
    before=count_events(j)
    r.deliver(e,1)
    assert count_events(j)==before and t.count()==1


@pytest.mark.parametrize('field,value',[
    ('consumer','archive'),('target_id','f'*32),('source_generation','g'*32),
    ('inventory','0'*64),('source_seq',2),('key','BTCUSDT:1m:60000'),
    ('payload_digest','0'*64),('effect_id','0'*64),('registration','0'*64)])
def test_rehashed_rebound_receipts_rejected(tmp_path,field,value):
    j,a,t,d,e=setup(tmp_path);receipt=d.perform(e,1)
    forged=copy.deepcopy(receipt);forged['request'][field]=value
    forged['proof_digest']=digest({k:v for k,v in forged.items() if k!='proof_digest'})
    with pytest.raises(PublicationDenied): d.confirm(e,forged)
    assert d.view()['D']==[] and d.view()['S']==0
    assert d.confirm(e,receipt) and t.count()==1


def test_cross_consumer_target_receipt_cannot_settle_other_consumer(tmp_path):
    j,a,t,d,e=setup(tmp_path);t2,d2,e2=add_consumer(a,tmp_path,'archive')
    receipt=d.perform(e,1);d2.begin(e2,1)
    with pytest.raises(PublicationDenied): d2.confirm(e2,receipt)
    assert d2.view()['D']==[] and t2.count()==0
    d.confirm(e,receipt)
    assert d.view()['D']==[1] and d2.view()['S']==0
    d2.reconcile(e2,1)
    assert d2.view()['D']==[1] and t2.count()==1


def test_source_rehashed_confirmation_without_target_effect_is_rejected(tmp_path):
    j,a,t,d,e=setup(tmp_path)
    attempt,_=d.begin(e,1)
    body=dict(schema='aql.d2-target-receipt.v1',request=attempt['request'],
              attempt_id=attempt['id'],attempt_epoch=e,origin_epoch=e,
              disposition='APPLIED',evidence=None)
    forged=dict(body,proof_digest=digest(body))
    with closing(j._connect()) as c:
        c.execute('BEGIN IMMEDIATE')
        d._append(c,'D2_CONFIRMED',dict(source_seq=1,epoch=e,id=attempt['id'],receipt=forged))
        c.commit()
    with pytest.raises(PublicationDenied): d.view()
    assert t.count()==0


def test_target_receipt_alone_without_effect_is_not_proof(tmp_path):
    j,a,t,d,e=setup(tmp_path);attempt,_=d.begin(e,1)
    body=dict(schema='aql.d2-target-receipt.v1',request=attempt['request'],
              attempt_id=attempt['id'],attempt_epoch=e,origin_epoch=e,
              disposition='APPLIED',evidence=None)
    forged=dict(body,proof_digest=digest(body))
    with closing(sqlite3.connect(t.path)) as c:
        c.execute('INSERT INTO d2_receipts VALUES(?,?,?)',(attempt['id'],attempt['request']['effect_id'],canonical(forged).decode()))
        c.commit()
    with pytest.raises(PublicationDenied): d.confirm(e,forged)
    assert t.count()==0


@pytest.mark.parametrize('mode',['missing','new_database','old_snapshot'])
def test_target_replacement_and_rollback_deny_only_own_consumer(tmp_path,mode):
    j,a,t,d,e=setup(tmp_path);other,od,oe=add_consumer(a,tmp_path,'archive')
    snapshot=tmp_path/'old-target.sqlite';backup(t.path,str(snapshot))
    d.deliver(e,1)
    a.deliver('sandbox',1,1)
    if mode=='missing': Path(t.path).rename(tmp_path/'removed-target.sqlite')
    elif mode=='new_database':
        new=SQLiteEffectTarget.create(str(tmp_path/'new-target.sqlite'),synthetic=True)
        backup(new.path,t.path)
    else: backup(str(snapshot),t.path)
    with pytest.raises(PublicationDenied): d.view()
    assert od.deliver(oe,2) and od.view()['D']==[2] and other.count()==1
    assert a.reader('sandbox').read(1)['bar_open']==0


def test_pending_archive_consumer_does_not_block_other_consumer(tmp_path):
    j,a,t,d,e=setup(tmp_path);other,ad,ae=add_consumer(a,tmp_path,'archive')
    ad.begin(ae,1)
    assert ad.view()['IN_DOUBT']==[1]
    assert d.deliver(e,1) and d.view()['S']==1 and other.count()==0
    assert t.count()==1


def test_late_conflict_preserves_historical_D_withdraws_V_and_never_releases_W(tmp_path):
    j,a,t,d,e=setup(tmp_path);receipt=d.deliver(e,1)
    conflict(j)
    v=d.view();assert v['D']==[1] and v['V']==[] and v['S']==1
    assert d.withhold(e,1)==receipt
    assert d.view()['W']==[1] and t.count()==1
    newer=d.fence()
    with pytest.raises(ContentConflictError): d.deliver(newer,1)
    assert reopen(d).view()['V']==[] and d.view()['D']==[1]


def test_withheld_settlement_requires_persisted_target_no_effect_disposition(tmp_path):
    j,a,t,d,e=setup(tmp_path);conflict(j)
    receipt=d.withhold(e,1)
    assert receipt['disposition']=='WITHHELD' and t.count()==0
    assert d.view()['D']==[] and d.view()['W']==[1] and d.view()['S']==1
    with closing(sqlite3.connect(t.path)) as c:
        assert c.execute('SELECT disposition FROM d2_inbox').fetchone()[0]=='WITHHELD'
        c.execute('DROP TRIGGER d2_receipts_no_delete');c.execute('DELETE FROM d2_receipts');c.commit()
    with pytest.raises(PublicationDenied): d.view()


def test_unconfirmed_target_effect_then_source_conflict_stays_in_doubt(tmp_path):
    j,a,t,d,e=setup(tmp_path);d.perform(e,1);conflict(j)
    with pytest.raises(ContentConflictError): d.reconcile(e,1)
    assert d.view()['D']==[] and d.view()['S']==0 and d.view()['IN_DOUBT']==[1]
    newer=d.fence()
    with pytest.raises(InDoubt): d.withhold(newer,1)
    assert t.count()==1 and d.view()['D']==[]


def test_sparse_actual_inventory_is_not_expected_market_coverage(tmp_path):
    j=DurableJournal(str(tmp_path/'source.sqlite'));j.commit(bar(0));j.commit(bar(2))
    with closing(j._connect()) as c: c.execute('UPDATE journal_entries SET id=7 WHERE id=2')
    a=Authority(j,limits=Limits(8,131072,2,64),synthetic=True,
                stores=[OperationalStore(str(tmp_path/'operational.sqlite'))])
    t,d,e=add_consumer(a,tmp_path)
    d.deliver(e,7)
    assert d.view()['D']==[7] and d.view()['S']==0
    d.deliver(e,1)
    assert d.view()['S']==7 and d.view()['coverage']=='UNKNOWN'
    assert 'COMPLETE' not in canonical(d.view()).decode()


def test_source_checkpoint_rollback_detected_in_live_and_reopened_consumer(tmp_path):
    j,a,t,d,e=setup(tmp_path);old=d.checkpoint()
    saved=tmp_path/'old-source.sqlite';backup(j.db_path,str(saved))
    d.deliver(e,1);current=d.checkpoint();backup(str(saved),j.db_path)
    with pytest.raises(PublicationDenied,match='rollback'): d.view()
    with pytest.raises(PublicationDenied,match='checkpoint'):
        EffectDelivery(a,'sandbox',anchor=d.anchor,checkpoint=current,synthetic=True)
    assert t.count()==1 and old!=current


def test_replay_rejects_reordered_confirmation_missing_intent_and_wrong_genesis(tmp_path):
    j,a,t,d,e=setup(tmp_path)
    with closing(j._connect()) as c:
        c.execute('BEGIN IMMEDIATE')
        d._append(c,'D2_CONFIRMED',dict(source_seq=1,epoch=e,id='x',receipt={}))
        c.commit()
    with pytest.raises(PublicationDenied): d.rebuild()


def test_registry_and_effect_attempt_budgets_are_bounded(tmp_path):
    j,a,_=baseline(tmp_path)
    t,d,e=add_consumer(a,tmp_path,max_consumers=1,limits=effect_limits(max_attempts=2))
    extra=SQLiteEffectTarget.create(str(tmp_path/'extra.sqlite'),synthetic=True)
    with pytest.raises(PublicationDenied,match='registry full'):
        EffectDelivery(a,'extra',target=extra,limits=effect_limits(),max_consumers=1,synthetic=True)
    d.begin(e,1);e=d.fence();d.begin(e,1,recovering=True);e=d.fence()
    with pytest.raises(PublicationDenied,match='attempt quota'): d.begin(e,1,recovering=True)
    assert t.count()==0 and d.view()['S']==0


@pytest.mark.parametrize('phase',['target_receipt','source_ack'])
def test_actual_sql_insert_failure_keeps_in_doubt_until_reconciled(tmp_path,phase):
    j,a,t,d,e=setup(tmp_path)
    path=t.path if phase=='target_receipt' else j.db_path
    table='d2_receipts' if phase=='target_receipt' else 'core128_d2_events'
    condition='' if phase=='target_receipt' else " WHEN json_extract(NEW.body,'$.op')='D2_CONFIRMED'"
    with closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TRIGGER injected_failure BEFORE INSERT ON "+table+condition+
                  " BEGIN SELECT RAISE(ABORT,'injected receipt/ACK failure'); END")
        c.commit()
    with pytest.raises((InDoubt,sqlite3.DatabaseError)): d.deliver(e,1)
    assert t.count()==1 and d.view()['D']==[] and d.view()['S']==0
    with closing(sqlite3.connect(path)) as c: c.execute('DROP TRIGGER injected_failure');c.commit()
    d.reconcile(e,1)
    assert t.count()==1 and d.view()['D']==[1]


@pytest.mark.parametrize('mutator',[
    lambda a:dict(a,source_generation='wrong'),
    lambda a:dict(a,consumer='archive'),
    lambda a:dict(a,limits=dict(a['limits'],max_effects=128)),
])
def test_reopen_rejects_forged_retained_registration(tmp_path,mutator):
    j,a,t,d,e=setup(tmp_path)
    with pytest.raises(PublicationDenied):
        EffectDelivery(a,'sandbox',anchor=mutator(copy.deepcopy(d.anchor)),checkpoint=d.checkpoint(),synthetic=True)


def test_real_mode_and_existing_target_adoption_refused(tmp_path):
    j,a,_=baseline(tmp_path)
    with pytest.raises(PublicationDenied): SQLiteEffectTarget.create(str(tmp_path/'real.sqlite'))
    t=SQLiteEffectTarget.create(str(tmp_path/'target.sqlite'),synthetic=True)
    with pytest.raises(FileExistsError): SQLiteEffectTarget.create(t.path,synthetic=True)
    with pytest.raises(PublicationDenied):
        EffectDelivery(a,'sandbox',target=t,limits=effect_limits(),max_consumers=2)
