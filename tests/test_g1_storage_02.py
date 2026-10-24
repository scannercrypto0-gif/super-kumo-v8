"""Local-only archive acceptance. All records and failures use disposable paths."""
import errno
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

from aql.archive import local
from aql.archive.local import LocalArchive, ArchiveService, verify_segment, writer_lock
from aql.archive.backup import create_backup, restore_backup, verify_backup, sqlite_snapshot
from aql.archive.contracts import FEATURES, canonical, decision_context, digest, parse
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.storage.operational_store import OperationalStore


def bar(i=0):
    return MarketBar("BTCUSDT", "1m", i*60000, (i+1)*60000-1,
                     10., 11., 9., 10., 1., True, "synthetic", (i+1)*60000).with_checksum()


def setup(tmp_path, n=3, **kwargs):
    journal = DurableJournal(str(tmp_path/"journal.sqlite"))
    for i in range(n): journal.commit(bar(i))
    archive = LocalArchive(journal.db_path, tmp_path/"archive", market="spot", build="test-build",
                           policy="phase1-v1", reserve_bytes=0, **kwargs)
    return journal, archive


def watermark(archive):
    with archive.catalog() as conn:
        return int(conn.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()[0])


def first_segment(archive):
    with archive.catalog() as conn:
        relative, mh = conn.execute("SELECT path,manifest_hash FROM segments ORDER BY path LIMIT 1").fetchone()
    return archive.root/relative, mh


def test_real_archive_duplicate_restart_and_ack_independence(tmp_path):
    journal, archive = setup(tmp_path)
    assert archive.drain_once()==3
    assert archive.drain_once()==0 and watermark(archive)==3
    assert journal.count_by_state()=={"LOCAL_COMMITTED":3}
    assert not journal.commit(bar(0))
    again=LocalArchive(journal.db_path,archive.root,market="spot",build="test-build",policy="phase1-v1",reserve_bytes=0)
    assert again.drain_once()==0
    rows,m=verify_segment(first_segment(archive)[0],expected_hash=first_segment(archive)[1])
    assert len(rows)==m["count"]==3 and m["completion_watermark"]==3
    assert rows[0]["times"]["source_event_ms"] is None
    assert rows[0]["times"]["available_ms"] is None
    assert rows[0]["availability_kind"]=="DERIVED_LOWER_BOUND_NOT_CONFIRMED"
    assert rows[0]["times"]["fsync_completed_ms"] is None


@pytest.mark.parametrize("field,value", [("is_final",False),("close",float("nan")),
    ("volume",-1),("bar_close",100),("ingested_at",253402300700000)])
def test_invalid_or_future_candles_never_acked(tmp_path,field,value):
    journal,archive=setup(tmp_path,n=0)
    item=bar();setattr(item,field,value);item.with_checksum();journal.commit(item)
    with pytest.raises(ValueError):archive.drain_once()
    assert watermark(archive)==0 and archive.health()["status"]=="UNHEALTHY"


def test_temporal_payload_tamper_after_archive_detected(tmp_path):
    journal,archive=setup(tmp_path)
    archive.drain_once()
    with journal._connect() as conn:
        row=conn.execute("SELECT payload_json FROM journal_entries WHERE id=3").fetchone()
        value=json.loads(row[0]);value["ingested_at"]+=1
        conn.execute("UPDATE journal_entries SET payload_json=? WHERE id=3",(json.dumps(value),))
    with pytest.raises(ValueError,match="anchor"):archive.drain_once()


@pytest.mark.parametrize("stage",["before_write","after_data","after_manifest","after_rename","before_ack"])
def test_fault_boundaries_do_not_ack_and_restart_recovers(tmp_path,stage):
    def fault(point):
        if point==stage:raise RuntimeError("injected crash boundary")
    journal,archive=setup(tmp_path,fault=fault)
    with pytest.raises(RuntimeError):archive.drain_once()
    assert watermark(archive)==0
    restarted=LocalArchive(journal.db_path,archive.root,market="spot",build="test-build",policy="phase1-v1",reserve_bytes=0)
    assert restarted.drain_once()==3 and restarted.drain_once()==0
    with restarted.catalog() as conn:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]==3
        assert conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]==1
    assert journal.count_by_state()=={"LOCAL_COMMITTED":3}


@pytest.mark.parametrize("stage",["after_data","after_manifest","after_rename","before_ack"])
def test_real_process_termination_and_replay(tmp_path,stage):
    journal,archive=setup(tmp_path)
    code='''import os,sys
from aql.archive.local import LocalArchive
def fault(stage):
    if stage==sys.argv[3]:os._exit(93)
a=LocalArchive(sys.argv[1],sys.argv[2],market="spot",build="test-build",policy="phase1-v1",reserve_bytes=0,fault=fault)
a.drain_once()
'''
    result=subprocess.run([sys.executable,"-B","-c",code,journal.db_path,str(archive.root),stage],timeout=15,capture_output=True)
    assert result.returncode==93, result.stderr.decode(errors="replace")
    assert watermark(archive)==0
    assert archive.drain_once()==3 and archive.drain_once()==0


@pytest.mark.parametrize("error",[OSError(errno.ENOSPC,"injected full"),PermissionError(errno.EACCES,"injected readonly")])
def test_injected_disk_full_permission_failure_preserves_primary(tmp_path,error):
    journal,archive=setup(tmp_path)
    with patch.object(local,"write_new",side_effect=error):
        with pytest.raises(OSError):archive.drain_once()
    assert watermark(archive)==0
    assert len(journal.replay())==3
    assert archive.drain_once()==3


def test_fsync_failure_is_not_success(tmp_path):
    journal,archive=setup(tmp_path)
    # Intent is durable but segment file sync is injected to fail.
    original=local.write_new
    def fail(path,data):
        if path.name=="records.jsonl":raise OSError("fsync unavailable")
        return original(path,data)
    with patch.object(local,"write_new",side_effect=fail):
        with pytest.raises(OSError):archive.drain_once()
    assert watermark(archive)==0


def test_catalog_write_lock_bounded_and_journal_independent(tmp_path):
    journal,archive=setup(tmp_path)
    conn=sqlite3.connect(archive.root/"catalog.sqlite");conn.execute("BEGIN IMMEDIATE")
    start=time.monotonic()
    try:
        with pytest.raises(sqlite3.OperationalError):archive.drain_once()
        assert time.monotonic()-start<2
        assert journal.commit(bar(4))
    finally:conn.rollback();conn.close()
    assert watermark(archive)==0 and archive.drain_once()==4


def test_real_writer_lock_excludes_second_writer(tmp_path):
    _,archive=setup(tmp_path)
    with writer_lock(archive.root):
        with pytest.raises(OSError):archive.drain_once()
    assert watermark(archive)==0


def test_bounded_lane_and_core_latency_while_archive_blocked(tmp_path):
    entered,release=threading.Event(),threading.Event()
    def fault(stage):
        if stage=="before_write":entered.set();release.wait(5)
    journal,archive=setup(tmp_path,fault=fault)
    service=ArchiveService(archive)
    try:
        assert service.request() and entered.wait(2)
        assert service.request() and not service.request()
        start=time.monotonic();assert journal.commit(bar(5));elapsed=time.monotonic()-start
        assert elapsed<2  # Detect synchronous dependency, not a production latency SLA.
        assert watermark(archive)==0 and service.lane.rejected==1
    finally:release.set();service.finish(3)
    assert len(journal.replay())==4
    assert archive.drain_once() in (0,1)


def test_batch_and_cross_segment_gap_inventory(tmp_path):
    journal,archive=setup(tmp_path,n=1,batch_size=1)
    archive.drain_once();journal.commit(bar(3));archive.drain_once()
    with archive.catalog() as conn:
        path,mh=conn.execute("SELECT path,manifest_hash FROM segments ORDER BY path DESC LIMIT 1").fetchone()
    _,manifest=verify_segment(archive.root/path,expected_hash=mh)
    assert manifest["coverage"]["BTCUSDT"]["gaps"]==[[60000,180000]]
    assert manifest["coverage_scope"]=="OBSERVED_JOURNAL_PREFIX_NOT_FULL_MARKET"


def test_recovered_out_of_order_is_marked_not_rewritten(tmp_path):
    journal,archive=setup(tmp_path,n=0,batch_size=1)
    journal.commit(bar(3));archive.drain_once();journal.commit(bar(1));archive.drain_once()
    with archive.catalog() as conn:
        path,mh=conn.execute("SELECT path,manifest_hash FROM segments WHERE path LIKE '%/2-2-%'").fetchone()
    _,m=verify_segment(archive.root/path,expected_hash=mh)
    assert m["coverage"]["BTCUSDT"]["out_of_order"] is True


@pytest.mark.parametrize("target",["records.jsonl","manifest.json"])
def test_archive_or_manifest_tampering_fails_closed(tmp_path,target):
    _,archive=setup(tmp_path);archive.drain_once()
    path,mh=first_segment(archive)
    (path/target).write_bytes(b"corrupt")
    with pytest.raises((ValueError,KeyError)):verify_segment(path,expected_hash=mh)
    with pytest.raises((ValueError,KeyError)):create_backup(archive,tmp_path/"backups")


def test_backup_wal_restore_exact_and_out_of_place_replay(tmp_path):
    journal,archive=setup(tmp_path);archive.drain_once()
    store=OperationalStore(str(tmp_path/"hot.sqlite"))
    for item in journal.replay():store.upsert(item)
    # Keep WAL reader open while a fourth committed journal record is not archived.
    observer=sqlite3.connect(journal.db_path);observer.execute("SELECT COUNT(*) FROM journal_entries").fetchone()
    journal.commit(bar(5))
    try:
        backup,evidence=create_backup(archive,tmp_path/"backups",operational_path=store.db_path)
    finally:observer.close()
    assert evidence["records"]==3 and evidence["journal_records"]==4
    assert evidence["off_device_protection"]=="NOT_VERIFIED"
    target=tmp_path/"restored"
    assert restore_backup(backup,target,expected_digest=evidence["inventory_hash"])==evidence
    assert verify_backup(backup,expected_digest=evidence["inventory_hash"])==evidence
    # Original catalog stays forensic: explicit out-of-place rebuild, never path-rebind.
    rebuilt=LocalArchive(target/"journal.sqlite",tmp_path/"rebuilt",market="spot",build="test-build",policy="phase1-v1",reserve_bytes=0)
    assert rebuilt.drain_once()==4 and rebuilt.drain_once()==0
    assert len(journal.replay())==4


def test_backup_rejects_pending_intent_and_restore_overwrite(tmp_path):
    _,archive=setup(tmp_path)
    with patch.object(local,"write_new",side_effect=OSError("full")):
        with pytest.raises(OSError):archive.drain_once()
    with pytest.raises(ValueError,match="pending"):create_backup(archive,tmp_path/"backup")
    archive.drain_once();backup,evidence=create_backup(archive,tmp_path/"backup")
    with pytest.raises(ValueError):restore_backup(backup,archive.root,expected_digest=evidence["inventory_hash"])
    with pytest.raises(ValueError):restore_backup(backup,tmp_path/"new",expected_digest="0"*64)
    assert not (tmp_path/"new").exists()


@pytest.mark.parametrize("target",["inventory.json","journal.sqlite","archive/catalog.sqlite"])
def test_backup_tamper_detected(tmp_path,target):
    _,archive=setup(tmp_path);archive.drain_once()
    backup,evidence=create_backup(archive,tmp_path/"backups")
    (backup/target).write_bytes(b"corrupt")
    with pytest.raises((ValueError,KeyError)):verify_backup(backup,expected_digest=evidence["inventory_hash"])


def test_snapshot_timeout_and_inventory_bounds(tmp_path):
    journal,archive=setup(tmp_path);archive.drain_once()
    with pytest.raises(TimeoutError):sqlite_snapshot(journal.db_path,tmp_path/"deadline.sqlite",timeout=-1)
    with pytest.raises(ValueError):create_backup(archive,tmp_path/"small",max_bytes=10)
    with pytest.raises(ValueError):create_backup(archive,tmp_path/"few",max_files=2)


def test_backup_path_overlap_and_traversal_denied(tmp_path):
    _,archive=setup(tmp_path)
    with pytest.raises(ValueError):create_backup(archive,archive.root/"backup")
    for path in ("../escape","/absolute","C:/escape","x\\y"):
        with pytest.raises(ValueError):local.child(archive.root,path)


def test_journal_replacement_and_rollback_detected(tmp_path):
    journal,archive=setup(tmp_path);archive.drain_once()
    with journal._connect() as conn:conn.execute("DELETE FROM journal_entries WHERE id=3")
    with pytest.raises(ValueError,match="rollback"):archive.drain_once()
    with journal._connect() as conn:conn.execute("UPDATE journal_meta SET value='replacement' WHERE key='instance_id'")
    with pytest.raises(ValueError,match="replaced"):archive.drain_once()


def test_reparse_metadata_fail_closed_without_privilege(tmp_path):
    path=tmp_path/"link";path.mkdir()
    original=Path.lstat
    def replaced(self,*a,**k):
        if self==path:
            from types import SimpleNamespace
            return SimpleNamespace(st_file_attributes=0x400)
        return original(self,*a,**k)
    with patch.object(Path,"lstat",replaced):
        with pytest.raises(ValueError,match="reparse"):local.check_path(path)


def test_stale_unavailable_backup_disk_telemetry_not_healthy(tmp_path):
    _,archive=setup(tmp_path)
    assert archive.health()["status"]=="UNHEALTHY"
    archive.drain_once()
    assert archive.health()["status"]!="HEALTHY"  # No backup evidence.
    archive.last_check_ms=0
    assert archive.health()["status"]=="UNHEALTHY"
    with patch("shutil.disk_usage",side_effect=OSError("unknown")):
        assert archive.health()["status"]=="UNHEALTHY"


def test_disk_reserve_blocks_archive_only(tmp_path):
    journal,archive=setup(tmp_path)
    archive.reserve_bytes=10**30
    with pytest.raises(OSError,match="reserve"):archive.drain_once()
    assert journal.commit(bar(4)) and watermark(archive)==0


@pytest.mark.parametrize("outcome",["ACCEPTED","REJECTED","EXPIRED","NO_FILL"])
def test_pit_contract_unknown_fields_and_frozen_bytes(outcome):
    missing={"value":None,"source":None,"version":None,"event_ms":None,"receipt_ms":None,"available_ms":None,"freshness_ms":None,"status":"UNAVAILABLE"}
    features={name:dict(missing) for name in FEATURES}
    raw=decision_context(context_id="ctx1",decision_ms=100,outcome=outcome,strategy_version="v1",policy_version="p1",features=features)
    restored=parse(raw);stored=restored.pop("context_hash")
    assert stored==digest(restored)
    features["btc_regime"]["value"]=1
    assert parse(raw)["features"]["btc_regime"]["value"] is None
    with pytest.raises(ValueError):decision_context(context_id="ctx1",decision_ms=100,outcome=outcome,strategy_version="v1",policy_version="p1",features=features)


def test_pit_contract_future_and_inconsistent_freshness_rejected():
    value={"value":1,"source":"synthetic","version":"1","event_ms":1,"receipt_ms":2,"available_ms":3,"freshness_ms":97,"status":"AVAILABLE"}
    features={name:dict(value) for name in FEATURES}
    args=dict(context_id="ctx1",decision_ms=100,outcome="REJECTED",strategy_version="v1",policy_version="p1",features=features)
    assert decision_context(**args)
    features["liquidity"]["available_ms"]=101
    with pytest.raises(ValueError):decision_context(**args)


def test_canonical_encoding_duplicate_keys_nonfinite():
    assert canonical({"b":2,"a":1})==b'{"a":1,"b":2}'
    with pytest.raises(ValueError):parse('{"x":1,"x":2}')
    with pytest.raises(ValueError):canonical({"x":float("nan")})


def test_conflicting_index_identity_is_not_overwritten(tmp_path):
    _,archive=setup(tmp_path)
    with archive.catalog() as conn:
        conn.execute("INSERT INTO records VALUES (99,?,?,?)",(bar().stable_key(),"conflicting-digest","untrusted"))
    with pytest.raises(ValueError,match="Conflicting"):archive.drain_once()
    assert watermark(archive)==0
    with archive.catalog() as conn:
        assert conn.execute("SELECT hash FROM records WHERE seq=99").fetchone()[0]=="conflicting-digest"


def test_oversized_source_rejected_before_payload_materialization(tmp_path):
    journal,archive=setup(tmp_path,n=0)
    item=bar();item.source="x"*20000;item.with_checksum();journal.commit(item)
    with pytest.raises(ValueError,match="Oversized"):archive.drain_once()
    assert watermark(archive)==0


def test_stopped_wakeup_does_not_ack(tmp_path):
    _,archive=setup(tmp_path)
    stop=threading.Event();stop.set()
    assert archive.drain_once(stop)==0 and watermark(archive)==0


def test_root_directory_replacement_denied(tmp_path):
    _,archive=setup(tmp_path)
    archive.root.rename(tmp_path/"old-root")
    archive.root.mkdir()
    # health fails closed even when a replacement has no valid catalog.
    assert archive.health()["status"]=="UNHEALTHY"
    with pytest.raises((ValueError,sqlite3.Error)):archive.drain_once()


def test_valid_legacy_optional_payload_checksum_not_invented(tmp_path):
    journal,archive=setup(tmp_path,n=0)
    item=bar();item.checksum=None
    journal.commit(item)
    assert archive.drain_once()==1
    path,mh=first_segment(archive)
    rows,_=verify_segment(path,expected_hash=mh)
    assert rows[0]["bar"]["checksum"] is None
    assert rows[0]["journal_content_checksum"]==item.compute_checksum()
    assert "bar_payload_checksum" in rows[0]["missing"]


def test_corrupt_optional_hot_snapshot_cannot_be_sealed(tmp_path):
    from aql.archive import backup as module
    journal, archive = setup(tmp_path); archive.drain_once()
    hot = OperationalStore(str(tmp_path/"hot.sqlite"))
    for item in journal.replay(): hot.upsert(item)
    original = module.sqlite_snapshot
    def corrupt_before_inventory(source, target, **kwargs):
        original(source, target, **kwargs)
        if Path(target).name == "operational.sqlite":
            Path(target).write_bytes(b"storage fault before inventory sealing")
    with patch.object(module, "sqlite_snapshot", corrupt_before_inventory):
        with pytest.raises((ValueError, sqlite3.DatabaseError)):
            create_backup(archive, tmp_path/"backups", operational_path=hot.db_path)
    assert archive.last_backup_ms is None
    assert len(journal.replay()) == 3
    assert all(p.name.endswith(".partial") for p in (tmp_path/"backups").iterdir())


def test_unlisted_empty_directory_rejected_and_walk_deadline_enforced(tmp_path):
    from aql.archive import backup as module
    _, archive = setup(tmp_path); archive.drain_once()
    sealed, evidence = create_backup(archive, tmp_path/"backups")
    (sealed/"not-in-inventory").mkdir()
    with pytest.raises(ValueError, match="directory"):
        verify_backup(sealed, expected_digest=evidence["inventory_hash"])
    # A separate valid backup demonstrates the deadline check during traversal,
    # after all file hashing, rather than disguising it as a checksum failure.
    sealed, evidence = create_backup(archive, tmp_path/"more-backups")
    original = module.os.scandir
    clock = [0.]
    def expired_scan(path):
        clock[0] = 61.
        return original(path)
    with patch.object(module.time, "monotonic", side_effect=lambda: clock[0]), patch.object(module.os, "scandir", expired_scan):
        with pytest.raises(TimeoutError, match="deadline"):
            verify_backup(sealed, expected_digest=evidence["inventory_hash"])


@pytest.mark.parametrize("raw", ['{"value":1e400}', '{"value":-1e400}', '{"value":NaN}', '{"value":Infinity}'])
def test_nonfinite_exponent_json_is_rejected(raw):
    with pytest.raises(ValueError, match="Nonfinite"):
        parse(raw)


def test_missing_backup_segment_never_publishes_restore(tmp_path):
    _, archive = setup(tmp_path); archive.drain_once()
    sealed, evidence = create_backup(archive, tmp_path/"backups")
    inventory = parse((sealed/"inventory.json").read_bytes())
    relative = next(item["path"] for item in inventory["files"] if item["path"].endswith("records.jsonl"))
    (sealed/relative).unlink()  # Disposable fixture only; no primary deletion.
    with pytest.raises(FileNotFoundError):
        restore_backup(sealed, tmp_path/"restored", expected_digest=evidence["inventory_hash"])
    assert not (tmp_path/"restored").exists()


def test_core_commits_while_backup_capture_is_blocked(tmp_path):
    from aql.archive import backup as module
    journal, archive = setup(tmp_path); archive.drain_once()
    entered, release = threading.Event(), threading.Event()
    original = module.sqlite_snapshot
    results, errors = [], []
    def blocked(source, target, **kwargs):
        original(source, target, **kwargs)
        if Path(target).name == "journal.sqlite":
            entered.set(); assert release.wait(5)
    def backup():
        try: results.append(create_backup(archive, tmp_path/"backups"))
        except Exception as error: errors.append(error)
    with patch.object(module, "sqlite_snapshot", blocked):
        worker = threading.Thread(target=backup); worker.start()
        try:
            assert entered.wait(3)
            start = time.monotonic()
            assert journal.commit(bar(5))
            assert time.monotonic()-start < 2  # Dependency check, not an SLA.
        finally:
            release.set(); worker.join(10)
    assert not worker.is_alive() and not errors
    assert results[0][1]["journal_records"] == 3
    assert len(journal.replay()) == 4
    assert journal.count_by_state() == {"LOCAL_COMMITTED":4}


@pytest.mark.parametrize("phase", ["backup", "restore"])
def test_real_terminated_copy_can_retry_without_primary_loss(tmp_path, phase):
    journal, archive = setup(tmp_path); archive.drain_once()
    sealed, evidence = create_backup(archive, tmp_path/"seed-backup")
    script = '''import os, sys
from aql.archive.local import LocalArchive
from aql.archive import backup as b
original = b.copy_new
def interrupted(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(94)
b.copy_new = interrupted
if sys.argv[1] == "backup":
    a = LocalArchive(sys.argv[2], sys.argv[3], market="spot", build="test-build", policy="phase1-v1", reserve_bytes=0)
    b.create_backup(a, sys.argv[4])
else:
    b.restore_backup(sys.argv[5], sys.argv[4], expected_digest=sys.argv[6])
'''
    destination = tmp_path/("interrupted-backup" if phase=="backup" else "interrupted-restore")
    result = subprocess.run([sys.executable,"-B","-c",script,phase,journal.db_path,str(archive.root),
                             str(destination),str(sealed),evidence["inventory_hash"]],
                            capture_output=True, timeout=20)
    assert result.returncode == 94, result.stderr.decode(errors="replace")
    assert len(journal.replay()) == 3 and watermark(archive) == 3
    if phase == "backup":
        assert all(p.name.endswith(".partial") for p in destination.iterdir())
        retry, checked = create_backup(archive, destination)
        assert verify_backup(retry, expected_digest=checked["inventory_hash"])["records"] == 3
    else:
        assert not destination.exists()
        assert restore_backup(sealed, destination, expected_digest=evidence["inventory_hash"])["records"] == 3


@pytest.mark.parametrize("reader", ["small", "hash"])
def test_nonregular_backup_file_rejected_before_blocking_read(tmp_path, reader):
    from aql.archive.backup import file_hash
    from types import SimpleNamespace
    import stat
    path = tmp_path/"nonregular"
    read = local.read_small if reader == "small" else file_hash
    if hasattr(os, "mkfifo"):
        os.mkfifo(path)  # Real FIFO on POSIX; must reject before open/read.
        with pytest.raises(ValueError, match="Regular"):
            read(path)
    else:
        path.write_bytes(b"fixture")
        original = Path.stat
        def nonregular(self, *args, **kwargs):
            if self == path: return SimpleNamespace(st_mode=stat.S_IFIFO)
            return original(self, *args, **kwargs)
        with patch.object(Path, "stat", nonregular):
            with pytest.raises(ValueError, match="Regular"):
                read(path)
