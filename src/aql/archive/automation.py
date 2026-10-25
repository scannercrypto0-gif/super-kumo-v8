"""Finite opt-in encrypted backup jobs; no deletion, network, keys or autostart.

Only finalized bundles / sealed WAL-aware archive backups, <=128MiB. A live
database must first use the merged create_backup API; file-copy is not WAL backup.
"""
import argparse
import calendar
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import time
import uuid

from .backup import file_hash, verify_backup
from .contracts import canonical, digest, parse
from .encrypted import encrypt, decrypted, extract, limited_scan, public_key
from .local import check_path, read_small, sync_dir, write_new, writer_lock

CONFIG_KEYS = {"source","source_kind","source_version","anchor","public_key",
               "public_key_sha256",
               "external_root","volume_marker","destination","local_state",
               "reserve_bytes","quiescent"}


def config(path):
    value = parse(read_small(path,16384))
    if set(value) != CONFIG_KEYS or value["quiescent"] is not True:
        raise ValueError("Exact config schema and explicit quiescence required")
    if value["source_kind"] not in ("custody_bundle","archive_backup"):
        raise ValueError("Only finalized custody/SQLite-backup generations supported")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}",value["source_version"]):
        raise ValueError("Bounded nonpersonal source version required")
    if type(value["reserve_bytes"]) is not int or value["reserve_bytes"] < 0:
        raise ValueError("Nonnegative disk reserve required")
    for key in ("source","anchor","public_key","external_root","destination","local_state"):
        original = value[key]
        if not isinstance(original,str) or not Path(original).is_absolute() or original.startswith(("\\\\","//")):
            raise ValueError("Explicit local absolute paths required")
        value[key] = str(check_path(original))
    source, dest, state, root = (Path(value[k]) for k in ("source","destination","local_state","external_root"))
    if root not in dest.parents or state == root or root in state.parents:
        raise ValueError("Destination must be below external root; state on separate path")
    for a,b in ((source,dest),(source,state),(state,dest)):
        if a==b or a in b.parents or b in a.parents: raise ValueError("Overlapping source/state/destination")
    for key in ("public_key","anchor"):
        p = Path(value[key])
        if p==source or source in p.parents or p==dest or dest in p.parents:
            raise ValueError("Recovery public key/anchor must be outside bundle/destination")
    if not re.fullmatch(r"[A-Za-z0-9-]{16,80}",value["volume_marker"]):
        raise ValueError("Explicit previously provisioned volume marker required")
    if not re.fullmatch(r"[0-9a-f]{64}",value["public_key_sha256"]):
        raise ValueError("Independently confirmed public key fingerprint required")
    return value


def check_public(value):
    key,fingerprint=public_key(value["public_key"])
    if fingerprint!=value["public_key_sha256"]:raise ValueError("RECOVERY_PUBLIC_KEY_CHANGED")
    return key,fingerprint


def media(value):
    root = check_path(value["external_root"])
    # Never create a missing drive/root or silently redirect to the system disk.
    if not root.is_dir(): raise FileNotFoundError("EXTERNAL_MEDIA_UNAVAILABLE")
    marker = root/".atlas-backup71-volume"
    if read_small(marker,128).decode("ascii").strip() != value["volume_marker"]:
        raise ValueError("EXTERNAL_MEDIA_IDENTITY_MISMATCH")
    return root.stat().st_dev, root.stat().st_ino, marker.read_bytes()


def verify_generation(source, kind, commitment, anchor):
    source = Path(source)
    kit, (files, _) = limited_scan(source)
    if kind == "custody_bundle":
        # A manifest of copied live DB bytes does not establish WAL consistency.
        # SQLite belongs only in the existing verified archive-backup adapter.
        for name in files:
            if name.lower().endswith(("-wal", "-shm", "-journal")):
                raise ValueError("SQLite sidecar requires WAL-aware archive backup")
            with open(source/name,"rb") as stream:
                if stream.read(16)==b"SQLite format 3\x00":
                    raise ValueError("Raw SQLite requires WAL-aware archive backup")
        kit.verify_custody_bundle(source,anchor)
    elif kind == "archive_backup":
        verify_backup(source,expected_digest=commitment,max_bytes=128 << 20)
    else:raise ValueError("Unsupported generation kind")
    return commitment


def verify_source(value, source=None):
    source = Path(source or value["source"])
    kit, _ = limited_scan(source)
    anchor = kit.check_anchor(source,Path(value["anchor"]))
    commitment = read_small(anchor,128).decode("ascii").strip()
    if not re.fullmatch("[0-9a-f]{64}",commitment): raise ValueError("Invalid retained anchor")
    return verify_generation(source,value["source_kind"],commitment,anchor)


def now(): return datetime.now(timezone.utc)


def save(path, value):
    write_new(path,canonical(value)+b"\n"); sync_dir(path.parent)


def expected_published(destination, state, deadline):
    """Previously successful LOCAL results detect entire missing generations.

    An intent alone can precede a crash-before-publish, so it must not be treated
    as proof of publication. Interrupted intents remain degraded in health().
    """
    expected=set()
    if state is None or not Path(state).exists():return expected
    with os.scandir(check_path(state)) as entries:
        for count,entry in enumerate(entries,1):
            if time.monotonic()>deadline:raise TimeoutError("Published-point audit deadline")
            if count>8192:
                raise ValueError("Published-point audit bound exhausted")
            if not entry.name.endswith(".result.json"):continue
            row=parse(read_small(check_path(entry.path),32768))
            if row.get("destination")!=str(check_path(destination)):continue
            if row.get("status")=="VERIFIED_ENCRYPTED_LOCAL":bid=row["backup_id"]
            elif row.get("status")=="ALREADY_VERIFIED_TODAY":bid=row["existing_backup_id"]
            else:continue
            if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{32}",bid):raise ValueError("Invalid published identity")
            expected.add(bid)
            if len(expected)>4096:raise ValueError("Published-point count bound")
    return expected


def completed(destination, *, receipt_state=None, max_cipher_bytes=2_000_000_000, timeout=60):
    result=[]; count=0; remaining=max_cipher_bytes; deadline=time.monotonic()+timeout
    expected_ids=expected_published(destination,receipt_state,deadline)
    if not Path(destination).exists():
        if expected_ids:raise FileNotFoundError("Previously published recovery points missing")
        return []
    with os.scandir(check_path(destination)) as entries:
        for entry in entries:
            if time.monotonic()>deadline:raise TimeoutError("Retained-generation audit deadline")
            count+=1
            if count>4096: raise ValueError("Backup generation bound reached; no pruning authorized")
            path=check_path(entry.path)
            if path.name.endswith(".partial"): continue
            if not path.is_dir(): raise ValueError("Unexpected backup generation entry")
            raw=read_small(path/"receipt.json",32768)
            receipt=parse(raw)
            # Monitoring uses previously retained LOCAL state, not self-hashed
            # metadata supplied by the external disk. This is not independent
            # custody: an attacker controlling both stores is outside this gate.
            if receipt_state is None:raise ValueError("Retained receipt state required")
            state=check_path(receipt_state)
            bid=receipt["backup_id"]
            if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{32}",bid) or bid!=path.name:
                raise ValueError("Backup identity mismatch")
            pin_path=check_path(state/(bid+".receipt-pin.sha256"))
            if pin_path.exists():
                expected=read_small(pin_path,128).decode("ascii").strip()
                if expected!=hashlib.sha256(raw).hexdigest():raise ValueError("Retained receipt pin mismatch")
            else:
                # Compatibility with parent111: only an already retained outbox
                # receipt can establish this cache. Never bootstrap it from F:.
                retained=check_path(state/"outbox"/(bid+".receipt.json"))
                if not retained.exists() or read_small(retained,32768)!=raw:
                    raise ValueError("Previously retained receipt evidence missing")
            stored=receipt.pop("receipt_sha256")
            if digest(receipt)!=stored or receipt["status"]!="VERIFIED_ENCRYPTED_LOCAL":
                raise ValueError("Invalid completed receipt")
            if receipt["backup_id"]!=path.name: raise ValueError("Backup identity mismatch")
            if raw!=canonical(receipt|{"receipt_sha256":stored})+b"\n":
                raise ValueError("Noncanonical completed receipt")
            # All retained points must be intact before any can reserve tiers.
            # A corrupt point or exhausted audit budget fails closed, never
            # silently drops that point or claims retained coverage is healthy.
            remaining-=verify_cipher(path,receipt,max_bytes=remaining,deadline=deadline)
            result.append((path,receipt|{"receipt_sha256":stored}))
    if expected_ids-{receipt["backup_id"] for _,receipt in result}:
        raise FileNotFoundError("Previously published recovery point missing")
    return result


def verify_cipher(path, receipt, *, max_bytes=(136 << 20), deadline=None):
    size, hashed=file_hash(path/"backup.atlas71",max_bytes=min(max_bytes,136 << 20),
                          deadline=deadline if deadline is not None else time.monotonic()+60)
    if hashed!=receipt["cipher_sha256"] or size!=receipt["cipher_bytes"]:
        raise ValueError("CIPHERTEXT_HASH_MISMATCH")
    return size


def periods(date):
    return {"daily":date.date().isoformat(),"weekly":date.strftime("%G-W%V"),"monthly":date.strftime("%Y-%m")}


def outbox_write(state, receipt):
    outbox=state/"outbox";outbox.mkdir(exist_ok=True)
    receipt_bytes=canonical(receipt)+b"\n"
    pin=hashlib.sha256(receipt_bytes).hexdigest()
    for name,raw in ((receipt["backup_id"]+".receipt.json",receipt_bytes),
                     (receipt["backup_id"]+".receipt.sha256",(pin+"\n").encode("ascii")),
                     (receipt["backup_id"]+".anchor.sha256",(receipt["cipher_sha256"]+"\n").encode("ascii"))):
        path=check_path(outbox/name)
        if path.exists():
            if read_small(path,32768)!=raw:raise ValueError("Outbox conflict; never overwrite")
        else:write_new(path,raw)
    sync_dir(outbox)
    return pin


def run(config_path, *, execute=False, fault=None):
    value=config(config_path); date=now(); started=time.monotonic()
    identity=digest(value); fault=fault or (lambda stage:None)
    plan={"action":"backup", "mode":"EXECUTE" if execute else "DRY_RUN", "config_hash":identity,
          "source_version":value["source_version"], "deletion_enabled":False,
          "independent_custody_verified":False}
    if not execute:
        media(value); verify_source(value); check_public(value)
        return plan|{"status":"PLAN_ONLY_NO_WRITES"}
    state=check_path(value["local_state"]); state.mkdir(parents=True,exist_ok=True)
    # A fixed lock file survives restarts; OS lock release handles process death.
    with writer_lock(state):
        bid=date.strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex
        common=plan|{"backup_id":bid,"started_at":date.isoformat(),"source":value["source"],
                     "destination":value["destination"],"source_version":value["source_version"]}
        save(state/(bid+".started.json"),common|{"status":"STARTED"})
        try:
            observed=media(value); commitment=verify_source(value)
            check_public(value)
            _,(_,total)=limited_scan(value["source"])
            # source, encrypted copy and bounded ZIP restore temp can coexist.
            if shutil.disk_usage(value["external_root"]).free < value["reserve_bytes"]+total+ (8 << 20):
                raise OSError("INSUFFICIENT_EXTERNAL_SPACE")
            previous=completed(value["destination"],receipt_state=state); slots=periods(date)
            for path,receipt in previous:
                if (receipt["config_hash"]==identity and receipt["periods"]["daily"]==slots["daily"]
                        and receipt["source_commitment"]==commitment):
                    if media(value)!=observed: raise ValueError("MEDIA_CHANGED")
                    receipt_pin=outbox_write(state,receipt)
                    result=common|{"status":"ALREADY_VERIFIED_TODAY","existing_backup_id":receipt["backup_id"],
                                   "receipt_file_sha256":receipt_pin,
                                   "finished_at":now().isoformat(),"duration_s":time.monotonic()-started}
                    save(state/(bid+".result.json"),result);return result
            dest=check_path(value["destination"]);dest.mkdir(parents=True,exist_ok=True)
            partial=dest/(bid+".partial");partial.mkdir()
            fault("before_encrypt")
            evidence=encrypt(value["source"],partial/"backup.atlas71",value["public_key"],deadline=time.monotonic()+120)
            if evidence["key_fingerprint"]!=value["public_key_sha256"]:raise ValueError("RECOVERY_PUBLIC_KEY_CHANGED")
            fault("after_encrypt")
            if verify_source(value)!=commitment or media(value)!=observed: raise ValueError("SOURCE_OR_MEDIA_CHANGED")
            size,hashed=file_hash(partial/"backup.atlas71",max_bytes=(136 << 20),deadline=time.monotonic()+60)
            tiers=["daily"]+[tier for tier in ("weekly","monthly") if not any(r["config_hash"]==identity and r["periods"][tier]==slots[tier] and tier in r["tiers"] for _,r in previous)]
            receipt={"schema":"atlas-backup71-receipt-1","backup_id":bid,"receipt_id":uuid.uuid4().hex,
                     "created_at":date.isoformat(),"source_version":value["source_version"],
                     "source_kind":value["source_kind"],"source_commitment":commitment,
                     "config_hash":identity,"periods":slots,"tiers":tiers,**evidence,
                     "cipher_sha256":hashed,"cipher_bytes":size,"status":"VERIFIED_ENCRYPTED_LOCAL",
                     "restore_verification":"AUTHENTICATED_READBACK_NOT_PRIVATE_KEY_RECOVERY_DRILL",
                     "independent_custody_verified":False,"cloud_upload":"NOT_VERIFIED"}
            receipt["receipt_sha256"]=digest(receipt)
            save(partial/"receipt.json",receipt);verify_cipher(partial,receipt)
            # Durable independent-of-F local intent precedes publication, so a
            # crash after rename can recover without trusting new local metadata.
            pin=hashlib.sha256(canonical(receipt)+b"\n").hexdigest()
            write_new(state/(bid+".receipt-pin.sha256"),(pin+"\n").encode("ascii"));sync_dir(state)
            sync_dir(partial);fault("before_publish")
            if media(value)!=observed: raise ValueError("MEDIA_CHANGED")
            final=dest/bid
            if final.exists(): raise FileExistsError("Completed backup must never be replaced")
            os.rename(partial,final);sync_dir(dest);fault("after_publish")
            # Outbox is deliberately paths-free; uploads are explicit, never automatic.
            receipt_pin=outbox_write(state,receipt)
            result=common|receipt|{"receipt_file_sha256":receipt_pin,
                                   "finished_at":now().isoformat(),"duration_s":time.monotonic()-started}
            save(state/(bid+".result.json"),result);return result
        except Exception as error:
            # Exception text may contain keys/paths/backend details: only class/reason code.
            result=common|{"status":"FAILED_NO_ACCEPTANCE","failure_reason":type(error).__name__,
                           "finished_at":now().isoformat(),"duration_s":time.monotonic()-started}
            save(state/(bid+".result.json"),result)
            raise


def restore(config_path, backup, target, private_key, *, expected_receipt_sha256, password=None):
    value=config(config_path);backup=check_path(backup);target=check_path(target)
    state=check_path(value["local_state"])
    if state==backup or backup in state.parents or state in backup.parents:
        raise ValueError("Restore audit state must not overlap backup")
    state.mkdir(parents=True,exist_ok=True)
    rid="restore-"+uuid.uuid4().hex;started=now()
    try:
        if target.exists() or target==backup or target in backup.parents or backup in target.parents:
            raise ValueError("New separate disposable restore destination required")
        private_path=check_path(private_key)
        if private_path==backup or backup in private_path.parents:
            raise ValueError("Private recovery key must be separate from backup")
        raw=read_small(backup/"receipt.json",32768)
        if (type(expected_receipt_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}",expected_receipt_sha256)
                or hashlib.sha256(raw).hexdigest()!=expected_receipt_sha256):
            raise ValueError("Independently retained receipt pin mismatch")
        receipt=parse(raw);stored=receipt.pop("receipt_sha256")
        if (digest(receipt)!=stored or receipt["schema"]!="atlas-backup71-receipt-1"
                or receipt["status"]!="VERIFIED_ENCRYPTED_LOCAL"
                or receipt["source_kind"] not in ("custody_bundle","archive_backup")
                or not re.fullmatch(r"[0-9a-f]{64}",receipt["source_commitment"])):
            raise ValueError("Invalid pinned receipt")
        if receipt["key_fingerprint"]!=value["public_key_sha256"]:raise ValueError("Wrong recovery key commitment")
        verify_cipher(backup,receipt)
        deadline=time.monotonic()+120
        with decrypted(backup/"backup.atlas71",private=private_key,password=password,
                       expected_fingerprint=receipt["key_fingerprint"],deadline=deadline) as plain:
            hashed=hashlib.sha256()
            while raw:=plain.read(1 << 20):hashed.update(raw)
            if hashed.hexdigest()!=receipt["payload_sha256"]: raise ValueError("Payload commitment mismatch")
            plain.seek(0)
            target.parent.mkdir(parents=True,exist_ok=True)
            partial=target.parent/(rid+".restore-partial")
            extract(plain,partial,deadline=deadline)
        # The external receipt pin binds this OLD generation's source identity.
        # Never compare it with a rotated current anchor or old absolute paths.
        anchor=state/(rid+".source-anchor.sha256")
        write_new(anchor,(receipt["source_commitment"]+"\n").encode("ascii"));sync_dir(state)
        verify_generation(partial,receipt["source_kind"],receipt["source_commitment"],anchor)
        verify_cipher(backup,receipt)
        if target.exists(): raise FileExistsError("Restore target appeared")
        os.rename(partial,target);sync_dir(target.parent)
        result={"status":"ENCRYPTED_RESTORE_VERIFIED","backup_id":receipt["backup_id"],"restore_id":rid,
                "config_hash":digest(value),
                "source_version":receipt["source_version"],"source_kind":receipt["source_kind"],
                "receipt_file_sha256":expected_receipt_sha256,"receipt_pin_verified":True,
                "started_at":started.isoformat(),"finished_at":now().isoformat(),
                "independent_custody_verified":False}
        save(state/(rid+".result.json"),result);return result
    except Exception as error:
        save(state/(rid+".result.json"),{"status":"RESTORE_FAILED_NO_ACCEPTANCE","restore_id":rid,
            "started_at":started.isoformat(),"finished_at":now().isoformat(),"failure_reason":type(error).__name__})
        raise


def health(config_path):
    value=config(config_path);date=now();issues=[];success=None
    try:
        media(value)
        if shutil.disk_usage(value["external_root"]).free<value["reserve_bytes"]+(8 << 20): issues.append("LOW_SPACE")
        previous=[(p,r) for p,r in completed(value["destination"],receipt_state=value["local_state"]) if r["config_hash"]==digest(value)]
        if previous:
            path,success=max(previous,key=lambda pair:pair[1]["created_at"])
            age=(date-datetime.fromisoformat(success["created_at"])).total_seconds()
            if not 0<=age<=26*3600:issues.append("BACKUP_OVERDUE_OR_CLOCK_UNCERTAIN")
        else:issues.append("NO_VERIFIED_BACKUP")
    except Exception as error:issues.append("MEDIA_OR_INTEGRITY_"+type(error).__name__)
    state=Path(value["local_state"])
    if state.exists():
        try:
            last=None;last_restore=None;count=0
            with os.scandir(check_path(state)) as entries:
                for entry in entries:
                    count+=1
                    if count>8192:raise ValueError("LOCAL_LOG_BOUND")
                    p=check_path(entry.path)
                    if p.name.endswith(".result.json"):
                        row=parse(read_small(p,32768))
                        if last is None or row["finished_at"]>last["finished_at"]:last=row
                        if (row["status"]=="ENCRYPTED_RESTORE_VERIFIED" and row.get("config_hash")==digest(value)
                                and row.get("source_version")==value["source_version"] and row.get("receipt_pin_verified") is True):
                            if last_restore is None or row["finished_at"]>last_restore:last_restore=row["finished_at"]
                    elif p.name.endswith(".started.json") and not p.with_name(p.name.replace(".started.json",".result.json")).exists():
                        issues.append("INTERRUPTED_ATTEMPT_REQUIRES_REVIEW")
            if last and "FAILED" in last["status"]:issues.append("LAST_OPERATION_FAILED")
            if last_restore is None or not 0<=(date-datetime.fromisoformat(last_restore)).total_seconds()<=31*86400:
                issues.append("MONTHLY_RESTORE_DRILL_NOT_VERIFIED_OR_OVERDUE")
        except Exception as error:issues.append("LOCAL_LOG_"+type(error).__name__)
    else:issues.append("MONTHLY_RESTORE_DRILL_NOT_VERIFIED_OR_OVERDUE")
    return {"status":"LOCAL_BACKUP_OK_NOT_CUSTODY_ACCEPTANCE" if not issues else "DEGRADED",
            "issues":issues,"last_success_id":success["backup_id"] if success else None,
            "telegram":"NOT_VERIFIED","independent_custody_verified":False}


def retention(config_path):
    value=config(config_path);media(value);date=now();candidates=[]
    for path,receipt in completed(value["destination"],receipt_state=value["local_state"]):
        created=datetime.fromisoformat(receipt["created_at"])
        anniversary=created.replace(year=created.year+1,
            day=min(created.day,calendar.monthrange(created.year+1,created.month)[1]))
        if (date-created>timedelta(days=30) and
                ("weekly" not in receipt["tiers"] or date-created>timedelta(weeks=12)) and
                ("monthly" not in receipt["tiers"] or date>=anniversary)):
            candidates.append(receipt["backup_id"])
    return {"mode":"DRY_RUN_ONLY","delete_enabled":False,"candidates":candidates,
            "warning":"CANDIDATE_ONLY_REQUIRES_SEPARATE_CUSTODY_RETENTION_APPROVAL"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("backup","health","retention","restore"))
    parser.add_argument("--config",required=True);parser.add_argument("--execute",action="store_true")
    parser.add_argument("--backup");parser.add_argument("--target");parser.add_argument("--private-key")
    parser.add_argument("--receipt-sha256",help="Raw receipt-file SHA256 from independently retained evidence")
    args=parser.parse_args()
    try:
        if args.action=="backup":result=run(args.config,execute=args.execute)
        elif args.action=="health":result=health(args.config)
        elif args.action=="retention":result=retention(args.config)
        else:
            if not args.execute or not all((args.backup,args.target,args.private_key,args.receipt_sha256)):
                parser.error("restore requires execute, backup, new target, private-key and independent receipt-sha256")
            # Optional secure process environment, never CLI argument or log.
            password=os.environ.get("ATLAS_BACKUP_RECOVERY_PASSPHRASE")
            result=restore(args.config,args.backup,args.target,args.private_key,
                           expected_receipt_sha256=args.receipt_sha256,
                           password=password.encode() if password else None)
        print(canonical(result).decode())
        return 1 if result.get("status")=="DEGRADED" else 0
    except Exception as error:
        print(canonical({"status":"FAILED_NO_ACCEPTANCE","reason":type(error).__name__}).decode());return 1


if __name__=="__main__":raise SystemExit(main())
