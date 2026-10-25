"""New behavior only; disposable bundles and ephemeral test recovery keys."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from aql.archive import automation as a
from aql.archive import encrypted as e
from aql.archive.contracts import canonical, digest, parse
from aql.archive.local import writer_lock, LocalArchive
from aql.archive.backup import create_backup
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar

PASSWORD=b"ephemeral-test-only-not-a-production-secret"


@pytest.fixture(scope="session")
def key_bytes():
    key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    return (key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo),
            key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(PASSWORD)))


def setup(root,key_bytes):
    source=root/"source";source.mkdir();(source/"data.csv").write_bytes(b"synthetic fixture\n"*30)
    (source/"nested").mkdir();(source/"nested/empty").write_bytes(b"")
    kit=e.kit_module();evidence=kit.build_custody_manifest(source)
    anchor=root/"anchor.sha256";anchor.write_text(evidence["manifest_sha256"],encoding="ascii")
    public=root/"public.pem";private=root/"test-private.pem"
    public.write_bytes(key_bytes[0]);private.write_bytes(key_bytes[1]);private.chmod(0o600)
    media=root/"media";media.mkdir();(media/".atlas-backup71-volume").write_text("test-volume-marker-123456",encoding="ascii")
    value={"source":str(source),"source_kind":"custody_bundle","source_version":"SYNTHETIC_TEST-v1",
        "anchor":str(anchor),"public_key":str(public),"external_root":str(media),
        "public_key_sha256":e.public_key(public)[1],
        "volume_marker":"test-volume-marker-123456","destination":str(media/"runs"),
        "local_state":str(root/"state"),"reserve_bytes":0,"quiescent":True}
    config=root/"config.json";config.write_bytes(canonical(value))
    return config,value,private


def test_dry_run_encrypted_backup_restore_and_receipts(tmp_path,key_bytes):
    config,v,private=setup(tmp_path,key_bytes)
    assert a.run(config)["status"]=="PLAN_ONLY_NO_WRITES"
    assert not Path(v["local_state"]).exists() and not Path(v["destination"]).exists()
    result=a.run(config,execute=True);backup=Path(v["destination"])/result["backup_id"]
    assert result["status"]=="VERIFIED_ENCRYPTED_LOCAL"
    assert set(result["tiers"])=={"daily","weekly","monthly"}
    assert b"synthetic fixture" not in (backup/"backup.atlas71").read_bytes()
    target=tmp_path/"restored"
    assert a.restore(config,backup,target,private,expected_receipt_sha256=result["receipt_file_sha256"],password=PASSWORD)["status"]=="ENCRYPTED_RESTORE_VERIFIED"
    assert (target/"data.csv").read_bytes()==(Path(v["source"])/"data.csv").read_bytes()
    assert (target/"nested/empty").read_bytes()==b""
    receipt=parse((Path(v["local_state"])/"outbox"/(result["backup_id"]+".receipt.json")).read_bytes())
    assert receipt["independent_custody_verified"] is False and "source" not in receipt
    assert "private" not in json.dumps(receipt)
    assert a.health(config)["status"]=="LOCAL_BACKUP_OK_NOT_CUSTODY_ACCEPTANCE"


def test_same_day_idempotence_and_overlap_denial(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes);first=a.run(config,execute=True)
    again=a.run(config,execute=True)
    assert again["existing_backup_id"]==first["backup_id"] and len(a.completed(v["destination"],receipt_state=v["local_state"]))==1
    with writer_lock(Path(v["local_state"])):
        with pytest.raises(OSError):a.run(config,execute=True)


@pytest.mark.parametrize("failure",["missing_media","wrong_media","low_space","permission","source_tamper"])
def test_failure_no_verified_generation_and_typed_local_log(tmp_path,key_bytes,failure):
    config,v,_=setup(tmp_path,key_bytes)
    if failure=="missing_media":Path(v["external_root"]).rename(tmp_path/"disconnected")
    if failure=="wrong_media":(Path(v["external_root"])/".atlas-backup71-volume").write_text("wrong")
    if failure=="source_tamper":(Path(v["source"])/"data.csv").write_bytes(b"changed")
    ctx=(patch.object(a.shutil,"disk_usage",return_value=SimpleNamespace(free=0)) if failure=="low_space"
         else patch.object(a,"encrypt",side_effect=PermissionError("SENSITIVE_BACKEND_TEXT")) if failure=="permission"
         else patch.object(a,"now",wraps=a.now))
    with ctx:
        with pytest.raises((ValueError,OSError)):a.run(config,execute=True)
    assert not a.completed(v["destination"],receipt_state=v["local_state"])
    records=list(Path(v["local_state"]).glob("*.result.json"));assert len(records)==1
    raw=records[0].read_bytes();assert b"SENSITIVE_BACKEND_TEXT" not in raw
    assert parse(raw)["status"]=="FAILED_NO_ACCEPTANCE"


def test_changed_media_after_encryption_rejected(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes)
    def fault(stage):
        if stage=="after_encrypt":(Path(v["external_root"])/".atlas-backup71-volume").write_text("detached/replaced")
    with pytest.raises(ValueError):a.run(config,execute=True,fault=fault)
    assert not a.completed(v["destination"],receipt_state=v["local_state"])
    assert all(p.name.endswith(".partial") for p in Path(v["destination"]).iterdir())


@pytest.mark.parametrize("mode",["ciphertext","forged_receipt","wrong_key","existing_target"])
def test_restore_refuses_corruption_wrong_key_overwrite_and_logs(tmp_path,key_bytes,mode):
    config,v,private=setup(tmp_path,key_bytes);result=a.run(config,execute=True)
    backup=Path(v["destination"])/result["backup_id"];target=tmp_path/"restored"
    if mode in ("ciphertext","forged_receipt"):
        p=backup/"backup.atlas71";raw=bytearray(p.read_bytes());raw[-20]^=1;p.write_bytes(raw)
        if mode=="forged_receipt":
            # Even a local attacker rewriting untrusted receipt hashes must fail GCM.
            receipt=parse((backup/"receipt.json").read_bytes());receipt.pop("receipt_sha256")
            receipt["cipher_sha256"]=hashlib.sha256(raw).hexdigest();receipt["receipt_sha256"]=digest(receipt)
            (backup/"receipt.json").write_bytes(canonical(receipt))
    if mode=="wrong_key":
        other=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        private=tmp_path/"wrong.pem";private.write_bytes(other.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(PASSWORD)))
    if mode=="existing_target":target.mkdir();(target/"keep").write_bytes(b"original")
    with pytest.raises(Exception):a.restore(config,backup,target,private,expected_receipt_sha256=result["receipt_file_sha256"],password=PASSWORD)
    if mode=="existing_target":assert (target/"keep").read_bytes()==b"original"
    else:assert not target.exists()
    assert any(parse(p.read_bytes())["status"]=="RESTORE_FAILED_NO_ACCEPTANCE" for p in Path(v["local_state"]).glob("restore-*.result.json"))


@pytest.mark.parametrize("stage",["after_encrypt","before_publish","after_publish"])
def test_real_process_interruption_retry_preserves_partial_or_recovers_outbox(tmp_path,key_bytes,stage):
    config,v,_=setup(tmp_path,key_bytes)
    script='''import os,sys
from aql.archive.automation import run
def fault(stage):
    if stage==sys.argv[2]:os._exit(91)
run(sys.argv[1],execute=True,fault=fault)
'''
    result=subprocess.run([sys.executable,"-B","-c",script,str(config),stage],capture_output=True,timeout=30)
    assert result.returncode==91,result.stderr
    retried=a.run(config,execute=True)
    assert len(a.completed(v["destination"],receipt_state=v["local_state"]))==1
    receipt=a.completed(v["destination"],receipt_state=v["local_state"])[0][1]
    assert (Path(v["local_state"])/"outbox"/(receipt["backup_id"]+".receipt.json")).exists()
    if stage in ("after_encrypt","before_publish"):assert any(p.name.endswith(".partial") for p in Path(v["destination"]).iterdir())
    else:assert retried["status"]=="ALREADY_VERIFIED_TODAY"
    assert "INTERRUPTED_ATTEMPT_REQUIRES_REVIEW" in a.health(config)["issues"]


def test_daily_weekly_monthly_points_and_retention_never_deletes(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes)
    dates=[datetime(2024,1,1,tzinfo=timezone.utc),datetime(2024,1,2,tzinfo=timezone.utc),datetime(2024,2,1,tzinfo=timezone.utc)]
    results=[]
    for date in dates:
        with patch.object(a,"now",return_value=date):results.append(a.run(config,execute=True))
    assert results[0]["tiers"]==["daily","weekly","monthly"]
    assert results[1]["tiers"]==["daily"]
    assert results[2]["tiers"]==["daily","weekly","monthly"]
    before={p.relative_to(Path(v["destination"])).as_posix():p.read_bytes() for p in Path(v["destination"]).rglob("*") if p.is_file()}
    with patch.object(a,"now",return_value=datetime(2026,10,25,tzinfo=timezone.utc)):
        plan=a.retention(config)
    assert len(plan["candidates"])==3 and plan["delete_enabled"] is False
    assert before=={p.relative_to(Path(v["destination"])).as_posix():p.read_bytes() for p in Path(v["destination"]).rglob("*") if p.is_file()}


def test_health_detects_overdue_failed_corrupt_and_missing_restore(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes);result=a.run(config,execute=True)
    assert "MONTHLY_RESTORE_DRILL_NOT_VERIFIED_OR_OVERDUE" in a.health(config)["issues"]
    with patch.object(a,"now",return_value=datetime(2090,1,1,tzinfo=timezone.utc)):
        assert "BACKUP_OVERDUE_OR_CLOCK_UNCERTAIN" in a.health(config)["issues"]
    (Path(v["destination"])/result["backup_id"]/"backup.atlas71").write_bytes(b"broken")
    assert any("INTEGRITY" in reason for reason in a.health(config)["issues"])


@pytest.mark.parametrize("change",[{"quiescent":False},{"source_kind":"live_sqlite"},{"destination":"relative"},{"source_version":"personal/path"}])
def test_config_fails_closed(tmp_path,key_bytes,change):
    config,v,_=setup(tmp_path,key_bytes);config.write_bytes(canonical(v|change))
    with pytest.raises(ValueError):a.run(config)
    assert not Path(v["local_state"]).exists()


def test_wal_aware_archive_snapshot_adapter_encrypts_and_restores(tmp_path,key_bytes):
    config,v,private=setup(tmp_path,key_bytes)
    journal=DurableJournal(str(tmp_path/"journal.sqlite"))
    journal.commit(MarketBar("BTCUSDT","1m",0,59999,10.,11.,9.,10.,1.,True,"synthetic",60000).with_checksum())
    archive=LocalArchive(journal.db_path,tmp_path/"archive",market="spot",build="test",policy="test",reserve_bytes=0)
    assert archive.drain_once()==1
    source,evidence=create_backup(archive,tmp_path/"sealed-source")
    Path(v["anchor"]).write_text(evidence["inventory_hash"],encoding="ascii")
    v|={"source":str(source),"source_kind":"archive_backup"};config.write_bytes(canonical(v))
    result=a.run(config,execute=True)
    assert a.restore(config,Path(v["destination"])/result["backup_id"],tmp_path/"restored",private,expected_receipt_sha256=result["receipt_file_sha256"],password=PASSWORD)["status"]=="ENCRYPTED_RESTORE_VERIFIED"
    assert journal.count_by_state()=={"LOCAL_COMMITTED":1}


def test_weak_public_key_denied(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    Path(v["public_key"]).write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    with pytest.raises(ValueError):a.run(config)


def test_source_changed_during_encryption_never_published(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes)
    original=a.encrypt
    def changed(*args,**kwargs):
        evidence=original(*args,**kwargs)
        (Path(v["source"])/"data.csv").write_bytes(b"mutated")
        return evidence
    with patch.object(a,"encrypt",side_effect=changed):
        with pytest.raises(ValueError):a.run(config,execute=True)
    assert not a.completed(v["destination"],receipt_state=v["local_state"])


@pytest.mark.parametrize("date,expected",[(datetime(2025,1,1,tzinfo=timezone.utc),0),
                                         (datetime(2025,1,15,tzinfo=timezone.utc),1)])
def test_monthly_retention_preserves_full_calendar_year(tmp_path,key_bytes,date,expected):
    config,v,_=setup(tmp_path,key_bytes)
    with patch.object(a,"now",return_value=datetime(2024,1,15,tzinfo=timezone.utc)):
        a.run(config,execute=True)
    with patch.object(a,"now",return_value=date):assert len(a.retention(config)["candidates"])==expected


def test_recovery_public_key_pinning_denies_substitution(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes)
    config.write_bytes(canonical(v|{"public_key_sha256":"0"*64}))
    with pytest.raises(ValueError,match="PUBLIC_KEY_CHANGED"):a.run(config)


def test_zip_member_count_bounded_before_directory_materialization(tmp_path):
    raw=struct.pack("<4s4H2LH",b"PK\x05\x06",0,0,5000,5000,0,0,0)
    target=tmp_path/"new"
    with pytest.raises(ValueError,match="central-directory"):
        e.extract(io.BytesIO(raw),target,deadline=__import__("time").monotonic()+2)
    assert not target.exists()


def test_second_process_cannot_overlap_backup_lock(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes);state=Path(v["local_state"]);state.mkdir()
    code='''import sys
from aql.archive.automation import run
try:run(sys.argv[1],execute=True)
except OSError:sys.exit(23)
'''
    with writer_lock(state):
        result=subprocess.run([sys.executable,"-B","-c",code,str(config)],capture_output=True,timeout=15)
    assert result.returncode==23,result.stderr
    assert not Path(v["destination"]).exists()


def test_blocked_backup_does_not_hold_authoritative_journal_commit(tmp_path,key_bytes):
    config,v,_=setup(tmp_path,key_bytes)
    journal=DurableJournal(str(tmp_path/"independent-core.sqlite"))
    entered,release=threading.Event(),threading.Event();errors=[]
    def fault(stage):
        if stage=="before_encrypt":entered.set();assert release.wait(5)
    def worker():
        try:a.run(config,execute=True,fault=fault)
        except Exception as error:errors.append(type(error).__name__)
    task=threading.Thread(target=worker);task.start()
    try:
        assert entered.wait(3)
        start=time.monotonic()
        assert journal.commit(MarketBar("BTCUSDT","1m",0,59999,10.,11.,9.,10.,1.,True,"synthetic",60000).with_checksum())
        assert time.monotonic()-start<2  # Dependency check, not a production SLA.
    finally:release.set();task.join(10)
    assert not task.is_alive() and not errors
    assert journal.count_by_state()=={"LOCAL_COMMITTED":1}
