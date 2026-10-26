"""Focused CORE-G1-INTEGRITY-58-59 acceptance; synthetic, no network/activation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
import threading
import time
from unittest.mock import Mock, patch

import pytest

from aql.g1_integrity import CommitEvidenceError, ContentConflictError, content
from aql.journal.durable_journal import DurableJournal, JOURNAL_SCHEMA
from aql.models.bar import MarketBar, BarState
from aql.storage.operational_store import OperationalStore
from aql.storage.sandbox_store import SandboxReplicator
from aql.lanes import JournalConsumer
from aql.collector.binance_collector import BinanceCollector
from aql.health import take_snapshot


def bar(i=0, **changes):
    value=MarketBar("BTCUSDT","1m",i*60000,(i+1)*60000-1,
                    100.,101.,99.,100.,1.,True,"synthetic",60000*(i+1))
    return replace(value,**changes).with_checksum()


def pair(tmp_path):
    return DurableJournal(str(tmp_path/"journal.sqlite")),OperationalStore(str(tmp_path/"store.sqlite"))


class CommitProbe:
    def __init__(self, conn, *, fail_on=None, after_data=None):
        self.conn,self.fail_on,self.after_data=conn,fail_on,after_data
        self.commits=0
    def __getattr__(self,name): return getattr(self.conn,name)
    def execute(self,sql,*args):
        if sql == "COMMIT":
            self.commits += 1
            if self.commits == self.fail_on:
                raise sqlite3.OperationalError("injected COMMIT failure")
            result=self.conn.execute(sql,*args)
            if self.commits==1 and self.after_data: self.after_data()
            return result
        return self.conn.execute(sql,*args)


def test_success_receipt_is_after_data_commit_not_legacy_marker(tmp_path):
    journal,_=pair(tmp_path);clock=[100.]
    conn=CommitProbe(journal._connect(),after_data=lambda:clock.__setitem__(0,120.))
    b=bar()
    with patch.object(journal,"_connect",return_value=conn),patch("time.time",side_effect=lambda:clock[0]):
        assert journal.commit(b)
    proof=journal.commit_receipt(b.stable_key())
    assert b.committed_at==100000
    assert proof["version"]==1 and proof["commit_return_observed_at_ms"]==120000
    assert proof["record_contract_version"]==1
    assert not proof["physical_fsync_or_powerloss_verified"]
    assert DurableJournal(journal.db_path).commit_receipt(b.stable_key())==proof
    assert journal.replay()[0].committed_at==100000  # legacy wire field unchanged


@pytest.mark.parametrize("fail_on,stored",[(1,False),(2,True)])
def test_failed_data_or_receipt_commit_never_has_completion_evidence(tmp_path,fail_on,stored):
    journal,_=pair(tmp_path);b=bar()
    conn=CommitProbe(journal._connect(),fail_on=fail_on)
    with patch.object(journal,"_connect",return_value=conn):
        with pytest.raises((sqlite3.OperationalError,CommitEvidenceError)):
            journal.commit(b)
    reopened=DurableJournal(journal.db_path)
    assert bool(reopened.replay())==stored
    assert reopened.commit_receipt(b.stable_key())["version"]==0
    assert reopened.commit_receipt(b.stable_key())["record_contract_version"]==(1 if stored else None)
    if stored:
        assert reopened.commit(bar()) is False
        assert reopened.commit_receipt(b.stable_key())["commit_return_observed_at_ms"] is None


def test_clock_rollback_after_commit_cannot_fabricate_timestamp(tmp_path):
    journal,_=pair(tmp_path);clock=[100.]
    conn=CommitProbe(journal._connect(),after_data=lambda:clock.__setitem__(0,99.))
    with patch.object(journal,"_connect",return_value=conn),patch("time.time",side_effect=lambda:clock[0]):
        with pytest.raises(CommitEvidenceError): journal.commit(bar())
    assert journal.replay()
    assert journal.commit_receipt(bar().stable_key())["version"]==0


@pytest.mark.parametrize("stage,version",[("after_data",0),("after_receipt",1)])
def test_real_child_exit_around_receipt_boundary(tmp_path,stage,version):
    import os
    from pathlib import Path
    import subprocess
    import sys
    path=str(tmp_path/"child.sqlite")
    script='''
import os,sys
import aql.journal.durable_journal as module
from aql.models.bar import MarketBar
j=module.DurableJournal(sys.argv[1])
if sys.argv[2]=='after_data':
    module.post_commit_receipt=lambda *args:os._exit(23)
b=MarketBar('BTCUSDT','1m',0,59999,100.,101.,99.,100.,1.,True,'synthetic',60000).with_checksum()
j.commit(b)
os._exit(24)
'''
    child_env={key:os.environ[key] for key in ("PATH","SYSTEMROOT","WINDIR","TEMP","TMP") if key in os.environ}
    child_env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1]/"src")
    result=subprocess.run([sys.executable,'-B','-c',script,path,stage],timeout=20,env=child_env)
    assert result.returncode==(23 if stage=="after_data" else 24)
    journal=DurableJournal(path)
    assert len(journal.replay())==1
    assert journal.commit_receipt(bar().stable_key())["version"]==version
    assert journal.commit_receipt(bar().stable_key())["record_contract_version"]==1


def test_true_legacy_schema_and_payload_remain_unchanged(tmp_path):
    path=str(tmp_path/"old.sqlite");b=bar();b.committed_at=60001;b.state=BarState.LOCAL_COMMITTED
    raw=json.dumps(b.to_dict(),sort_keys=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(JOURNAL_SCHEMA)
        conn.execute("INSERT INTO journal_entries "
            "(stable_key,bar_open,bar_close,symbol,interval,is_final,source,ingested_at,committed_at,payload_json,checksum,state) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(b.stable_key(),b.bar_open,b.bar_close,b.symbol,b.interval,1,
            b.source,b.ingested_at,b.committed_at,raw,b.checksum,b.state.value))
    journal=DurableJournal(path)
    assert journal.replay()[0].to_dict()==b.to_dict()
    assert journal.commit_receipt(b.stable_key())["version"]==0
    assert journal.commit_receipt(b.stable_key())["record_contract_version"]==0
    assert journal.commit(bar()) is False
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT payload_json FROM journal_entries").fetchone()[0]==raw


@pytest.mark.parametrize("kind",["journal","store"])
def test_identical_and_cross_transport_duplicate_preserves_original(tmp_path,kind):
    j,s=pair(tmp_path);target=j if kind=="journal" else s
    write=target.commit if kind=="journal" else target.upsert
    assert write(bar())
    conn=target._connect()
    try: original=target._original_bar(conn,bar().stable_key()).to_dict()
    finally: conn.close()
    assert write(bar()) is False
    assert write(bar(source="binance_rest_recovery",ingested_at=99999)) is False
    conn=target._connect()
    try: assert target._original_bar(conn,bar().stable_key()).to_dict()==original
    finally: conn.close()
    assert not target.quarantined_keys()


@pytest.mark.parametrize("kind",["journal","store"])
def test_conflict_preserves_original_quarantine_and_evidence_after_restart(tmp_path,kind):
    j,s=pair(tmp_path);target=j if kind=="journal" else s
    write=target.commit if kind=="journal" else target.upsert
    assert write(bar())
    original=bar().stable_key()
    with pytest.raises(ContentConflictError): write(bar(close=100.5))
    target=type(target)(target.db_path)
    conn=target._connect()
    try:
        assert target._original_bar(conn,original).close==100.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM g1_integrity_events")
        conn.rollback()
    finally: conn.close()
    with pytest.raises(ContentConflictError): target.require_eligible(original)
    evidence=target.conflict_evidence(original)
    assert len(evidence)==1 and not evidence[0]["decision_eligible"]
    assert evidence[0]["incoming_record"]["close"]==100.5
    assert evidence[0]["audit_availability_receipt"]["version"]==1
    write=target.commit if kind=="journal" else target.upsert
    assert write(bar(1))  # unrelated identity continues
    if kind=="journal":
        assert [b.bar_open for b in target.replay()]==[60000]
        assert len(target.replay(include_quarantined=True))==2
        with pytest.raises(ContentConflictError): target.mark_persisted(original)


@pytest.mark.parametrize("kind",["journal","store"])
def test_concurrent_conflicting_inserts_have_one_original(tmp_path,kind):
    j,s=pair(tmp_path);target=j if kind=="journal" else s
    barrier=threading.Barrier(2)
    def write(price):
        barrier.wait(5)
        try:
            return (target.commit if kind=="journal" else target.upsert)(bar(close=price))
        except ContentConflictError: return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=pool.submit(write,100.),pool.submit(write,100.5)
        assert sorted([str(a.result()),str(b.result())])==["True","conflict"]
    assert len(target.quarantined_keys())==1
    assert len(target.conflict_evidence(bar().stable_key()))==1


def test_restart_reconcile_validates_existing_store_content_before_ack(tmp_path):
    j,s=pair(tmp_path);j.commit(bar());s.upsert(bar(close=100.5))
    _,_,errors,_=j.startup_reconcile(s,"BTCUSDT","1m")
    assert errors==1
    assert j.count_by_state()["LOCAL_COMMITTED"]==1
    assert j.quarantined_keys()==s.quarantined_keys()=={bar().stable_key()}
    assert not j.replay()
    assert not take_snapshot(journal=j,store=s,symbol="BTCUSDT",interval="1m",now_ms_fn=lambda:120000).integrity_ok


def test_consumer_continues_unrelated_records_without_false_ack(tmp_path):
    j,s=pair(tmp_path);j.commit(bar());j.commit(bar(1));s.upsert(bar(close=100.5))
    consumer=JournalConsumer(j,s,"BTCUSDT","1m")
    consumer.drain_once()
    assert consumer.errors==1
    assert j.count_by_state()=={"LOCAL_COMMITTED":1,"PERSISTED":1}
    assert consumer.drain_once()==0
    s.upsert(bar(symbol="ETHUSDT"));j.commit(bar(symbol="ETHUSDT"))
    JournalConsumer(j,s,"ETHUSDT","1m").drain_once()
    healthy=take_snapshot(journal=j,store=s,symbol="ETHUSDT",interval="1m",now_ms_fn=lambda:60001)
    assert healthy.status=="HEALTHY"


def test_collector_conflict_mirrors_quarantine_and_new_metric_uses_receipt(tmp_path):
    j,s=pair(tmp_path);c=BinanceCollector("BTCUSDT","1m",j,s)
    k=dict(s="BTCUSDT",i="1m",t=0,T=59999,o="100",h="101",l="99",c="100",v="1",x=True)
    c._on_message(Mock(),json.dumps({"k":k}))
    assert c.metrics.journal_commit_count==1
    assert c.metrics.last_commit_return_observed_at==j.commit_receipt(bar().stable_key())["commit_return_observed_at_ms"]
    k["c"]="100.5";c._on_message(Mock(),json.dumps({"k":k}))
    assert c.metrics.error_count==1 and j.quarantined_keys()==s.quarantined_keys()
    assert c.metrics.store_insert_count==1  # conflict never counts as success


def test_remote_cursor_never_acknowledges_quarantined_input(tmp_path):
    j,s=pair(tmp_path);j.commit(bar())
    remote=Mock()
    def conflict(_):
        with pytest.raises(ContentConflictError): j.commit(bar(close=100.5))
        return True
    remote.upsert.side_effect=conflict
    replicator=SandboxReplicator(j,remote,str(tmp_path/"cursor.sqlite"))
    with pytest.raises(ContentConflictError): replicator.deliver_once()
    with sqlite3.connect(replicator.path) as conn:
        assert conn.execute("SELECT seq FROM delivery_cursor").fetchone()[0]==0


def test_correction_is_new_provenance_and_audit_availability_not_replacement(tmp_path):
    j,_=pair(tmp_path);j.commit(bar());original=j.replay()[0]
    changed=bar(close=100.5,source="corrected_source",ingested_at=70000)
    eid=j.record_correction(original,changed,reason="provider correction proposed")
    assert eid
    records=j.conflict_evidence(original.stable_key());assert len(records)==1
    assert records[0]["kind"]=="CORRECTION_PROPOSAL"
    proof=records[0]["audit_availability_receipt"]
    assert proof["version"]==1 and proof["commit_return_observed_at_ms"]>=70000
    assert j.replay(include_quarantined=True)[0].to_dict()==original.to_dict()
    with pytest.raises(ContentConflictError): j.require_eligible(original.stable_key())
    with pytest.raises(ValueError): j.record_correction(original,bar(close=100.5),reason="backdated")


def test_local_archive_refuses_quarantined_new_export_without_schema_change(tmp_path):
    from aql.archive.local import source_row
    j,_=pair(tmp_path);j.commit(bar())
    with pytest.raises(ContentConflictError): j.commit(bar(close=100.5))
    conn=j._connect()
    try:
        with pytest.raises(ContentConflictError): source_row(conn,1)
    finally: conn.close()


def test_gap_recovery_validates_already_stored_fetched_bar(tmp_path):
    from aql.pipeline import _run_gap_recovery
    from aql.recovery.gap_recovery import recover_gap
    j,s=pair(tmp_path);j.commit(bar());s.upsert(bar())
    rows=[[0,"100","101","99","100.5","1",59999]]
    with patch("aql.recovery.gap_recovery._fetch_klines",return_value=(rows,2)):
        fetched,report=recover_gap("BTCUSDT","1m",0,60000,{0},include_existing=True)
        assert len(fetched)==1 and report.already_stored==1
        result=_run_gap_recovery(j,s,"BTCUSDT","1m",0,60000)
    assert result["recovery_errors"]==1
    assert j.quarantined_keys()==s.quarantined_keys()=={bar().stable_key()}


def test_conflict_receipt_failure_still_reports_persisted_quarantine(tmp_path):
    j,s=pair(tmp_path);j.commit(bar())
    with patch("aql.journal.durable_journal.post_commit_receipt",side_effect=CommitEvidenceError("receipt failure")):
        with pytest.raises(ContentConflictError): j.commit(bar(close=100.5))
    assert j.quarantined_keys()=={bar().stable_key()}
    assert j.conflict_evidence(bar().stable_key())[0]["audit_availability_receipt"]["version"]==0
