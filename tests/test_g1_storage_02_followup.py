"""Delta-only storage acceptance; disposable data, no network/research runtime."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from aql.archive.backup import create_backup, restore_backup, verify_backup, sqlite_snapshot
from aql.archive.contracts import canonical, digest, parse
from aql.archive.offline import snapshot
from aql.archive import offline
from aql.archive.local import LocalArchive
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def prepare(root, n=3):
    journal = DurableJournal(str(root/"journal.sqlite"))
    for i in range(n):
        journal.commit(MarketBar("BTCUSDT", "1m", i*60000, (i+1)*60000-1,
                       10., 11., 9., 10., 1., True, "synthetic-followup", (i+1)*60000).with_checksum())
    archive = LocalArchive(journal.db_path, root/"archive", market="spot", build="test",
                           policy="phase1-v1", reserve_bytes=0, batch_size=1)
    return journal, archive


def sealed(root):
    journal, archive = prepare(root)
    while archive.drain_once(): pass
    backup, evidence = create_backup(archive, root/"backups")
    return journal, archive, backup, evidence


def query(backup, evidence, **kwargs):
    args = dict(expected_digest=evidence["inventory_hash"], symbol="BTCUSDT", interval="1m",
                start_ms=0, end_ms=180000)
    return snapshot(backup, **(args | kwargs))


def test_future_unarchived_source_cannot_become_verified_backup(tmp_path):
    journal, archive = prepare(tmp_path, n=0)
    future = (int(time.time()*1000)//60000+10)*60000
    journal.commit(MarketBar("BTCUSDT", "1m", future, future+59999,
                   10.,11.,9.,10.,1.,True,"synthetic-future",int(time.time()*1000)).with_checksum())
    with pytest.raises(ValueError): create_backup(archive, tmp_path/"backup")
    assert list((tmp_path/"backup").iterdir())
    assert all(p.name.endswith(".partial") for p in (tmp_path/"backup").iterdir())
    with closing(sqlite3.connect(journal.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 1


def test_snapshot_observation_retained_and_future_observation_denied(tmp_path):
    _, _, backup, evidence = sealed(tmp_path)
    inventory = parse((backup/"inventory.json").read_bytes())
    assert 0 < inventory["journal_snapshot_completed_ms"] <= int(time.time()*1000)
    inventory.pop("inventory_hash")
    inventory["journal_snapshot_completed_ms"] = int(time.time()*1000)+60000
    commitment = digest(inventory)
    (backup/"inventory.json").write_bytes(canonical(inventory | {"inventory_hash": commitment}))
    with pytest.raises(ValueError, match="Future snapshot"):
        verify_backup(backup, expected_digest=commitment)


def test_legacy_inventory_compatible_without_capture_attestation(tmp_path):
    _, _, backup, _ = sealed(tmp_path)
    value = parse((backup/"inventory.json").read_bytes())
    value.pop("inventory_hash"); value.pop("journal_snapshot_completed_ms")
    commitment = digest(value)
    (backup/"inventory.json").write_bytes(canonical(value | {"inventory_hash": commitment}))
    assert verify_backup(backup, expected_digest=commitment)["records"] == 3


def test_query_restore_determinism_half_open_range_and_no_file_mutation(tmp_path):
    _, _, backup, evidence = sealed(tmp_path)
    before = {p.relative_to(backup).as_posix(): p.read_bytes() for p in backup.rglob("*") if p.is_file()}
    original = query(backup, evidence, start_ms=60000)
    data = parse(original)
    assert [r["bar"]["bar_open"] for r in data["records"]] == [60000,120000]
    assert data["retrospective_only"] and data["pit_eligibility"] == "NOT_ATTESTED"
    assert data["independent_custody_verified"] is False
    assert all(r["times"]["available_ms"] is None for r in data["records"])
    restored = tmp_path/"restored"
    restore_backup(backup, restored, expected_digest=evidence["inventory_hash"])
    assert query(restored, evidence, start_ms=60000) == original
    assert before == {p.relative_to(backup).as_posix(): p.read_bytes() for p in backup.rglob("*") if p.is_file()}


@pytest.mark.parametrize("changes", [{"max_rows":2},{"max_rows":True},{"max_rows":4097},
    {"start_ms":180000},{"end_ms":-1},{"symbol":""},{"expected_digest":"0"*64}])
def test_query_rejects_invalid_or_truncating_requests(tmp_path, changes):
    _, _, backup, evidence = sealed(tmp_path)
    with pytest.raises(ValueError): query(backup, evidence, **changes)


def test_query_unselected_corruption_not_hidden(tmp_path):
    _, _, backup, evidence = sealed(tmp_path)
    next((backup/"archive/segments").rglob("records.jsonl")).write_bytes(b"corrupt")
    with pytest.raises(ValueError): query(backup, evidence, symbol="MISSING")


def test_query_changed_source_after_initial_verification_rejected(tmp_path):
    _, _, backup, evidence = sealed(tmp_path)
    original = offline.verify_backup
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        (backup/"journal.sqlite").write_bytes(b"changed")
        return result
    with patch.object(offline, "verify_backup", side_effect=mutate):
        with pytest.raises(ValueError): query(backup, evidence)


def test_query_marks_unarchived_backlog_not_full_coverage(tmp_path):
    _, archive = prepare(tmp_path)
    assert archive.drain_once() == 1
    backup, evidence = create_backup(archive, tmp_path/"backup")
    data = parse(query(backup, evidence))
    assert data["count"] == 1 and data["unarchived_records"] == 2
    assert data["coverage"] == "ARCHIVED_RECORDS_ONLY_NOT_FULL_MARKET"


def test_query_cross_process_canonical_identity(tmp_path):
    _, _, backup, evidence = sealed(tmp_path)
    code = '''import sys
from aql.archive.offline import snapshot
sys.stdout.buffer.write(snapshot(sys.argv[1],expected_digest=sys.argv[2],symbol="BTCUSDT",interval="1m",start_ms=0,end_ms=180000))
'''
    result = subprocess.run([sys.executable,"-B","-c",code,str(backup),evidence["inventory_hash"]],
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout == query(backup, evidence)


def test_finite_cli_archives_authoritative_journal_backup_and_restore(tmp_path):
    journal, _ = prepare(tmp_path)
    result = subprocess.run([sys.executable,"-B","-m","aql.archive", "--journal",journal.db_path,
        "--root",str(tmp_path/"cli-archive"),"--market","spot","--build","test","--policy","phase1-v1",
        "--reserve-bytes","0","--batch-size","1","--batches","2",
        "--backup-to",str(tmp_path/"cli-backup"),"--restore-to",str(tmp_path/"cli-restored")],
        capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["archived_this_run"] == 2 and report["health"]["backlog"] == 1
    assert report["restore"]["records"] == 2 and report["restore"]["journal_records"] == 3
    assert report["restore_anchor_scope"] == "SAME_RUN_LOCAL_COMMITMENT_NOT_INDEPENDENT_CUSTODY"
    assert journal.count_by_state() == {"LOCAL_COMMITTED":3}


def test_cli_invalid_restore_request_does_not_create_archive(tmp_path):
    root = tmp_path/"new"
    result = subprocess.run([sys.executable,"-B","-m","aql.archive","--journal",str(tmp_path/"missing"),
        "--root",str(root),"--market","spot","--build","test","--policy","phase1-v1",
        "--restore-to",str(tmp_path/"target")],capture_output=True,timeout=10)
    assert result.returncode == 2 and not root.exists()


def test_live_wal_snapshot_excludes_uncommitted_transaction_and_reconciles_rows(tmp_path):
    source, target = tmp_path/"live.sqlite", tmp_path/"snapshot.sqlite"
    with closing(sqlite3.connect(source)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT)")
        writer.executemany("INSERT INTO records VALUES (?,?)", [(1,"a"),(2,"b")])
        writer.commit()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO records VALUES (3,'not committed')")
        assert Path(str(source)+"-wal").exists()
        sqlite_snapshot(source, target)
        with closing(sqlite3.connect(target.as_uri()+"?mode=ro&immutable=1",uri=True)) as restored:
            assert restored.execute("SELECT id,value FROM records ORDER BY id").fetchall() == [(1,"a"),(2,"b")]
            assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        writer.rollback()
