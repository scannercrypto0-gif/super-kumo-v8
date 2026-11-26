"""Bounded RSA-OAEP/AES-256-GCM envelope; no key generation or secret logging."""
import base64
from contextlib import contextmanager
import hashlib
import io
import os
from pathlib import Path
import struct
import tempfile
import time
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .contracts import canonical, parse
from .local import check_path, child, read_small, sync_dir

MAGIC = b"ATLAS71\x01"
MAX_TOTAL = 128 << 20
MAX_FILE = 64 << 20
MAX_FILES = 4096


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=b"ATLAS71-v1")


def public_key(path):
    key = serialization.load_pem_public_key(read_small(path, 16384))
    if not isinstance(key, rsa.RSAPublicKey) or not 3072 <= key.key_size <= 8192:
        raise ValueError("RSA public recovery key must be3072..8192 bits")
    raw = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, hashlib.sha256(raw).hexdigest()


def signature(path):
    s = check_path(path).stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def kit_module():
    import importlib.util
    kit_path = Path(__file__).resolve().parents[3]/"tools/offline_custody_kit.py"
    spec = importlib.util.spec_from_file_location("atlas_backup71_path_kit", kit_path)
    kit = importlib.util.module_from_spec(spec); spec.loader.exec_module(kit)
    return kit


def limited_scan(root):
    """Reuse merged custody-kit cross-platform path/reparse/bounds contract."""
    kit = kit_module()
    return kit, kit.inventory(kit.checked(root))


def encrypt(source, output, public_path, *, deadline):
    source, output = check_path(source), check_path(output)
    kit, (files, total) = limited_scan(source)
    key, fingerprint = public_key(public_path)
    secret, nonce = os.urandom(32), os.urandom(12)
    header = canonical({"schema":"atlas-encrypted-backup-1", "key_fingerprint":fingerprint,
                        "nonce":base64.b64encode(nonce).decode(),
                        "wrapped_key":base64.b64encode(key.encrypt(secret, oaep())).decode()})
    prefix = MAGIC+struct.pack(">I", len(header))+header
    enc = Cipher(algorithms.AES(secret), modes.GCM(nonce)).encryptor()
    enc.authenticate_additional_data(prefix)
    plain_hash = hashlib.sha256()
    with open(output, "xb") as out:
        out.write(prefix)
        class Sink:
            position = 0
            def write(self, raw):
                if time.monotonic() > deadline: raise TimeoutError("Encryption deadline")
                self.position += len(raw)
                if self.position > MAX_TOTAL+(8 << 20): raise ValueError("Encrypted payload bound")
                plain_hash.update(raw); out.write(enc.update(raw)); return len(raw)
            def tell(self): return self.position
            def seek(self, *args): raise io.UnsupportedOperation("Streaming only")
            def flush(self): out.flush()
        with zipfile.ZipFile(Sink(), "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            for name, before in sorted(files.items()):
                path = child(source, name)
                with open(path, "rb") as inp, archive.open(name, "w") as member:
                    count = 0
                    while raw := inp.read(1 << 20):
                        count += len(raw)
                        if count > MAX_FILE: raise ValueError("Source file grew")
                        member.write(raw)
                if signature(path) != before or count != before[2]:
                    raise ValueError("Source changed during encryption")
        out.write(enc.finalize()); out.write(enc.tag); out.flush(); os.fsync(out.fileno())
    if kit.inventory(source)[0] != files: raise ValueError("Source inventory changed")
    # Verify the actual stored authenticated ciphertext while the ephemeral DEK
    # is still in RAM. No private recovery key is needed by the daily writer.
    with decrypted(output, secret=secret, expected_fingerprint=fingerprint, deadline=deadline) as plain:
        actual = hashlib.sha256()
        while raw := plain.read(1 << 20): actual.update(raw)
        if actual.hexdigest() != plain_hash.hexdigest(): raise ValueError("Encrypted readback mismatch")
    return {"file_count":len(files), "source_bytes":total, "key_fingerprint":fingerprint,
            "payload_sha256":plain_hash.hexdigest(), "cipher_bytes":output.stat().st_size}


@contextmanager
def decrypted(path, *, private=None, password=None, secret=None, expected_fingerprint, deadline):
    path = check_path(path)
    if path.stat().st_size > MAX_TOTAL+(8 << 20): raise ValueError("Ciphertext size bound")
    with open(path, "rb") as inp, tempfile.TemporaryFile() as plain:
        prefix = inp.read(len(MAGIC)+4)
        if prefix[:len(MAGIC)] != MAGIC or len(prefix) != len(MAGIC)+4: raise ValueError("Bad envelope")
        size = struct.unpack(">I", prefix[-4:])[0]
        if not 1 <= size <= 4096: raise ValueError("Header bound")
        raw = inp.read(size); header = parse(raw); aad = prefix+raw
        if (header["schema"] != "atlas-encrypted-backup-1" or
                header["key_fingerprint"] != expected_fingerprint): raise ValueError("Wrong recovery key identity")
        if secret is None:
            key = serialization.load_pem_private_key(read_small(private,16384), password=password)
            if not isinstance(key, rsa.RSAPrivateKey): raise ValueError("RSA recovery key required")
            pub = key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
            if hashlib.sha256(pub).hexdigest() != expected_fingerprint: raise ValueError("Wrong recovery key")
            secret = key.decrypt(base64.b64decode(header["wrapped_key"],validate=True), oaep())
        nonce = base64.b64decode(header["nonce"],validate=True)
        if len(secret) != 32 or len(nonce) != 12: raise ValueError("Invalid envelope key/nonce")
        remaining = path.stat().st_size-len(aad)-16
        if remaining < 0: raise ValueError("Truncated envelope")
        dec = Cipher(algorithms.AES(secret),modes.GCM(nonce)).decryptor()
        dec.authenticate_additional_data(aad)
        while remaining:
            if time.monotonic() > deadline: raise TimeoutError("Decryption deadline")
            raw = inp.read(min(1 << 20,remaining))
            if not raw: raise ValueError("Truncated ciphertext")
            remaining -= len(raw); plain.write(dec.update(raw))
        tag = inp.read(16)
        if len(tag) != 16 or inp.read(1): raise ValueError("Invalid tag/trailing data")
        plain.write(dec.finalize_with_tag(tag))
        # Never expose/use unauthenticated plaintext before GCM finalization.
        plain.seek(0); yield plain


def extract(plain, target, *, deadline):
    target = check_path(target)
    if target.exists(): raise FileExistsError("New restore target required")
    # Bound ZIP central-directory materialization before ZipFile constructs its
    # member list. The writer emits no comments, multi-disk or ZIP64 archives.
    plain.seek(0,os.SEEK_END);length=plain.tell()
    if length<22:raise ValueError("Truncated ZIP")
    plain.seek(-22,os.SEEK_END)
    mark,disk,central_disk,count_disk,count,size,offset,comment=struct.unpack("<4s4H2LH",plain.read(22))
    if (mark!=b"PK\x05\x06" or disk or central_disk or comment or count!=count_disk or
            not 1<=count<=MAX_FILES or size>(8 << 20) or offset+size!=length-22):
        raise ValueError("ZIP central-directory bound")
    plain.seek(0)
    target.mkdir()  # Preserved on failure; never remove/replace existing data.
    total = 0; seen = set(); kit = kit_module()
    with zipfile.ZipFile(plain) as archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= MAX_FILES: raise ValueError("ZIP inventory bound")
        for info in infos:
            if time.monotonic() > deadline: raise TimeoutError("Extraction deadline")
            name = info.filename
            from pathlib import PurePosixPath
            parts = PurePosixPath(name).parts
            if (info.is_dir() or info.compress_type != zipfile.ZIP_STORED or
                    not parts or len(parts)>17 or name.casefold() in seen or
                    info.file_size > MAX_FILE or "\\" in name or ":" in name):
                raise ValueError("Unsafe ZIP member")
            # Existing kit rejects Windows ambiguous names, traversal/reparse.
            kit.safe_name(name)
            destination = child(target,name)
            seen.add(name.casefold()); total += info.file_size
            if total > MAX_TOTAL: raise ValueError("ZIP total bound")
            destination.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(info) as inp, open(destination,"xb") as out:
                count=0
                while raw:=inp.read(1 << 20):
                    count+=len(raw)
                    if count>info.file_size: raise ValueError("ZIP size mismatch")
                    out.write(raw)
                if count!=info.file_size: raise ValueError("ZIP truncated")
                out.flush();os.fsync(out.fileno())
    sync_dir(target)
