"""Disposable SYNTHETIC Windows acceptance; never a production key/source setup."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from aql.archive import automation as a
from aql.archive import encrypted as e
from aql.archive.contracts import canonical
from aql.archive.local import check_path

# This password protects ONLY generated synthetic fixture keys. It is public
# test input, never a human/production recovery password or key-generation tool.
TEST_PASSWORD=b"ATLAS_SYNTHETIC_ACCEPTANCE_ONLY"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","verify"))
    parser.add_argument("--root",required=True);parser.add_argument("--media-root")
    args=parser.parse_args();root=check_path(args.root)
    if args.action=="prepare":
        if not args.media_root:parser.error("new media-root required")
        media=check_path(args.media_root)
        if root.exists() or media.exists():raise ValueError("New disposable paths required")
        root.mkdir(parents=True);media.mkdir(parents=True)
        source=root/"source";source.mkdir();(source/"synthetic.txt").write_bytes(b"SYNTHETIC_TEST_NO_REAL_DATA\n"*4096)
        evidence=e.kit_module().build_custody_manifest(source)
        (root/"anchor.sha256").write_text(evidence["manifest_sha256"],encoding="ascii")
        key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        (root/"public.pem").write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        private=root/"synthetic-private.pem"
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(TEST_PASSWORD)))
        private.chmod(0o600)
        marker="synthetic-acceptance-volume-71"
        (media/".atlas-backup71-volume").write_text(marker,encoding="ascii")
        value={"source":str(source),"source_kind":"custody_bundle","source_version":"SYNTHETIC_ACCEPTANCE-v1",
               "anchor":str(root/"anchor.sha256"),"public_key":str(root/"public.pem"),
               "public_key_sha256":e.public_key(root/"public.pem")[1],
               "external_root":str(media),"volume_marker":marker,"destination":str(media/"runs"),
               "local_state":str(root/"state"),"reserve_bytes":0,"quiescent":True}
        (root/"config.json").write_bytes(canonical(value))
        print(json.dumps({"status":"SYNTHETIC_PREPARED_NOT_A_BACKUP","config":str(root/"config.json")}))
    else:
        cfg=root/"config.json";value=a.config(cfg);backups=a.completed(value["destination"])
        if len(backups)!=1:raise ValueError("Expected one actual scheduled/manual fixture backup")
        backup,receipt=backups[0]
        restored=a.restore(cfg,backup,root/"restored",root/"synthetic-private.pem",password=TEST_PASSWORD)
        left=(root/"source/synthetic.txt").read_bytes();right=(root/"restored/synthetic.txt").read_bytes()
        if left!=right:raise ValueError("Synthetic restore bytes differ")
        before=hashlib.sha256((backup/"backup.atlas71").read_bytes()).hexdigest()
        repeated=a.run(cfg,execute=True)
        if before!=hashlib.sha256((backup/"backup.atlas71").read_bytes()).hexdigest():raise ValueError("Completed backup changed")
        report={"status":"SYNTHETIC_ENCRYPTED_WINDOWS_ACCEPTANCE_PASS","backup_id":receipt["backup_id"],
                "cipher_sha256":before,"source_commitment":receipt["source_commitment"],
                "file_count":receipt["file_count"],"source_bytes":receipt["source_bytes"],
                "restore":restored["status"],"repeat":repeated["status"],"health":a.health(cfg),
                "production_schedule":"NOT_ACTIVE","independent_custody_verified":False}
        a.save(root/"acceptance-result.json",report);print(json.dumps(report))


if __name__=="__main__":main()
