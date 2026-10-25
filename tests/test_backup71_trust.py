"""Missing trust/rotation/coverage cases from independent #111 review."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import shutil
import sqlite3
import time
import zipfile
from unittest.mock import patch

import pytest

from tests.test_backup71_automation import setup, key_bytes, PASSWORD
from aql.archive import automation as a
from aql.archive import encrypted as e
from aql.archive.contracts import canonical, digest, parse


def backup(root, keys):
    cfg,value,private=setup(root,keys)
    result=a.run(cfg,execute=True)
    return cfg,value,private,result,Path(value["destination"])/result["backup_id"]


def recover(cfg,generation,target,private,pin):
    return a.restore(cfg,generation,target,private,expected_receipt_sha256=pin,password=PASSWORD)


def test_restore_old_generation_after_current_anchor_rotation(tmp_path,key_bytes):
    cfg,value,private,result,generation=backup(tmp_path,key_bytes)
    old=(Path(value["source"])/"data.csv").read_bytes()
    # Only disposable mutable fixture anchor is rotated; old backup is untouched.
    Path(value["anchor"]).write_text("0"*64,encoding="ascii")
    target=tmp_path/"old-restored"
    assert recover(cfg,generation,target,private,result["receipt_file_sha256"])["receipt_pin_verified"]
    assert (target/"data.csv").read_bytes()==old


def test_new_release_B_can_restore_release_A_with_independent_pin(tmp_path,key_bytes):
    cfg,value,private,result,generation=backup(tmp_path,key_bytes)
    source_b=tmp_path/"release-b";source_b.mkdir();(source_b/"b.csv").write_bytes(b"generation B")
    commitment=e.kit_module().build_custody_manifest(source_b)["manifest_sha256"]
    anchor_b=tmp_path/"anchor-b.sha256";anchor_b.write_text(commitment,encoding="ascii")
    value|={"source":str(source_b),"anchor":str(anchor_b),"source_version":"release-B"}
    cfg.write_bytes(canonical(value));a.run(cfg,execute=True)
    report=recover(cfg,generation,tmp_path/"recovered-A",private,result["receipt_file_sha256"])
    assert report["source_version"]=="SYNTHETIC_TEST-v1"
    assert (tmp_path/"recovered-A/data.csv").exists() and not (tmp_path/"recovered-A/b.csv").exists()
    assert "MONTHLY_RESTORE_DRILL_NOT_VERIFIED_OR_OVERDUE" in a.health(cfg)["issues"]


def test_recovery_on_alternate_paths_without_original_source_anchor_or_media(tmp_path,key_bytes):
    cfg,value,private,result,generation=backup(tmp_path,key_bytes)
    moved=tmp_path/"offline-copy";shutil.copytree(generation,moved)
    Path(value["source"]).rename(tmp_path/"old-source-forensic")
    Path(value["anchor"]).rename(tmp_path/"old-anchor-forensic")
    value|={"source":str(tmp_path/"unavailable-source"),"anchor":str(tmp_path/"unavailable-anchor"),
            "external_root":str(tmp_path/"unmounted-media"),"destination":str(tmp_path/"unmounted-media/runs"),
            "public_key":str(tmp_path/"unavailable-public-file"),"local_state":str(tmp_path/"new-recovery-state")}
    cfg.write_bytes(canonical(value))
    assert recover(cfg,moved,tmp_path/"restored",private,result["receipt_file_sha256"])["status"]=="ENCRYPTED_RESTORE_VERIFIED"


@pytest.mark.parametrize("pin",[None,"", "0"*64])
def test_missing_or_wrong_external_receipt_pin_rejected_before_restore(tmp_path,key_bytes,pin):
    cfg,_,private,_,generation=backup(tmp_path,key_bytes)
    with pytest.raises(ValueError,match="receipt pin"):
        recover(cfg,generation,tmp_path/"restored",private,pin)
    assert not (tmp_path/"restored").exists()


@pytest.mark.parametrize("field",["source_version","source_commitment","key_fingerprint"])
def test_self_rehashed_receipt_cannot_replace_external_pin(tmp_path,key_bytes,field):
    cfg,_,private,result,generation=backup(tmp_path,key_bytes)
    receipt=parse((generation/"receipt.json").read_bytes());receipt.pop("receipt_sha256")
    receipt[field]="FORGED" if field=="source_version" else "0"*64
    receipt["receipt_sha256"]=digest(receipt)
    (generation/"receipt.json").write_bytes(canonical(receipt)+b"\n")
    with pytest.raises(ValueError,match="receipt pin"):
        recover(cfg,generation,tmp_path/"restored",private,result["receipt_file_sha256"])
    assert not (tmp_path/"restored").exists()


def test_gcm_still_rejects_corruption_even_with_matching_outer_receipt_pin(tmp_path,key_bytes):
    cfg,_,private,_,generation=backup(tmp_path,key_bytes)
    cipher=generation/"backup.atlas71";raw=bytearray(cipher.read_bytes());raw[-20]^=1;cipher.write_bytes(raw)
    receipt=parse((generation/"receipt.json").read_bytes());receipt.pop("receipt_sha256")
    receipt["cipher_sha256"]=hashlib.sha256(raw).hexdigest();receipt["receipt_sha256"]=digest(receipt)
    receipt_raw=canonical(receipt)+b"\n";(generation/"receipt.json").write_bytes(receipt_raw)
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):recover(cfg,generation,tmp_path/"restored",private,hashlib.sha256(receipt_raw).hexdigest())
    assert not (tmp_path/"restored").exists()


def test_corrupt_earlier_tier_blocks_new_coverage_and_health(tmp_path,key_bytes):
    cfg,value,private=setup(tmp_path,key_bytes)
    with patch.object(a,"now",return_value=datetime(2026,10,19,tzinfo=timezone.utc)):
        first=a.run(cfg,execute=True)
    with patch.object(a,"now",return_value=datetime(2026,10,20,tzinfo=timezone.utc)):
        latest=a.run(cfg,execute=True)
    old=Path(value["destination"])/first["backup_id"]
    assert "weekly" in first["tiers"] and latest["tiers"]==["daily"]
    (old/"backup.atlas71").write_bytes(b"corrupt old point; new point remains intact")
    with patch.object(a,"now",return_value=datetime(2026,10,21,tzinfo=timezone.utc)):
        assert any("INTEGRITY" in issue for issue in a.health(cfg)["issues"])
        with pytest.raises(ValueError,match="CIPHERTEXT_HASH"):
            a.run(cfg,execute=True)
    # No new completed generation published, no deletion/replacement of old data.
    assert len([p for p in Path(value["destination"]).iterdir() if not p.name.endswith(".partial")])==2
    assert (old/"backup.atlas71").read_bytes().startswith(b"corrupt old")


def test_retained_audit_byte_and_time_budgets_fail_closed(tmp_path,key_bytes):
    _,value,_,_,_=backup(tmp_path,key_bytes)
    with pytest.raises(ValueError):a.completed(value["destination"],receipt_state=value["local_state"],max_cipher_bytes=1)
    with pytest.raises(TimeoutError):a.completed(value["destination"],receipt_state=value["local_state"],timeout=-1)


@pytest.mark.parametrize("kind",["sqlite","sidecar"])
def test_custody_manifest_cannot_launder_raw_sqlite_or_sidecars(tmp_path,key_bytes,kind):
    cfg,value,_=setup(tmp_path,key_bytes);source=Path(value["source"])
    if kind=="sqlite":
        with closing(sqlite3.connect(source/"raw.db")) as db:
            db.execute("CREATE TABLE records(id INTEGER)");db.commit()
    else:(source/"raw.db-wal").write_bytes(b"not a coherent DB snapshot")
    (source/"custody-manifest.json").unlink()  # Disposable fixture manifest only.
    commitment=e.kit_module().build_custody_manifest(source)["manifest_sha256"]
    Path(value["anchor"]).write_text(commitment,encoding="ascii")
    with pytest.raises(ValueError,match="WAL-aware"):a.run(cfg,execute=True)
    assert not Path(value["destination"]).exists()


def test_outbox_receipt_pin_is_exact_file_hash_and_recreated_exclusively(tmp_path,key_bytes):
    cfg,value,_,result,generation=backup(tmp_path,key_bytes)
    pin=hashlib.sha256((generation/"receipt.json").read_bytes()).hexdigest()
    outbox=Path(value["local_state"])/"outbox"
    assert result["receipt_file_sha256"]==pin
    path=outbox/(result["backup_id"]+".receipt.sha256")
    assert path.read_text(encoding="ascii").strip()==pin
    path.unlink()  # Disposable fixture only: emulate publish→outbox interruption.
    assert a.run(cfg,execute=True)["receipt_file_sha256"]==pin
    path.write_text("0"*64,encoding="ascii")
    with pytest.raises(ValueError,match="Outbox conflict"):a.run(cfg,execute=True)


def test_local_monitoring_rejects_self_rehashed_period_forgery(tmp_path,key_bytes):
    cfg,value,_,_,generation=backup(tmp_path,key_bytes)
    receipt=parse((generation/"receipt.json").read_bytes());receipt.pop("receipt_sha256")
    receipt["periods"]["weekly"]="2099-W01";receipt["receipt_sha256"]=digest(receipt)
    (generation/"receipt.json").write_bytes(canonical(receipt)+b"\n")
    with pytest.raises(ValueError,match="Retained receipt pin"):
        a.run(cfg,execute=True)
    assert a.health(cfg)["status"]=="DEGRADED"


def test_missing_local_monitor_cache_is_not_bootstrapped_from_backup(tmp_path,key_bytes):
    cfg,value,private,result,generation=backup(tmp_path,key_bytes)
    state=Path(value["local_state"])
    (state/(result["backup_id"]+".receipt-pin.sha256")).unlink()  # Disposable fixture only.
    (state/"outbox"/(result["backup_id"]+".receipt.json")).unlink()
    with pytest.raises(ValueError,match="retained receipt evidence missing"):
        a.run(cfg,execute=True)
    # Disaster recovery still works with a separately supplied pre-loss pin.
    assert recover(cfg,generation,tmp_path/"restored",private,result["receipt_file_sha256"])["receipt_pin_verified"]


def test_parent111_outbox_receipt_remains_a_compatible_local_monitor_cache(tmp_path,key_bytes):
    cfg,value,_,result,_=backup(tmp_path,key_bytes)
    state=Path(value["local_state"])
    (state/(result["backup_id"]+".receipt-pin.sha256")).unlink()  # Parent111 had no early intent pin.
    (state/"outbox"/(result["backup_id"]+".receipt.sha256")).unlink()
    assert a.run(cfg,execute=True)["status"]=="ALREADY_VERIFIED_TODAY"
    assert (state/"outbox"/(result["backup_id"]+".receipt.sha256")).exists()


def test_recovery_log_path_cannot_modify_backup_generation(tmp_path,key_bytes):
    cfg,value,private,result,generation=backup(tmp_path,key_bytes)
    before={p.name:p.read_bytes() for p in generation.iterdir()}
    value["local_state"]=str(generation/"new-audit");cfg.write_bytes(canonical(value))
    # This recovery config has a different destination, so source config path
    # separation alone cannot establish safety for the supplied backup argument.
    value["external_root"]=str(tmp_path/"other-media")
    value["destination"]=str(tmp_path/"other-media/runs");cfg.write_bytes(canonical(value))
    with pytest.raises(ValueError,match="audit state"):
        recover(cfg,generation,tmp_path/"restored",private,result["receipt_file_sha256"])
    assert before=={p.name:p.read_bytes() for p in generation.iterdir()}


@pytest.mark.parametrize("name",["../escape","CON"])
def test_malicious_archive_member_refused_without_path_escape(tmp_path,name):
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,"w",compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(name,b"malicious fixture")
    payload.seek(0);target=tmp_path/"partial"
    with pytest.raises(ValueError):e.extract(payload,target,deadline=time.monotonic()+2)
    assert not (tmp_path/"escape").exists() and not list(target.iterdir())
