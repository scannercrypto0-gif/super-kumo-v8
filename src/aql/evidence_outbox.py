"""Optional, non-blocking external evidence delivery.

The primary watcher never waits for Guardian or cloud services. An append-only
local outbox stores immutable bundles and independently checks their digest
before retrying. Remote acceptance is separate from local observation.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

class OutboxError(Exception):
    pass

def encode(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(blob):
    return hashlib.sha256(blob).hexdigest()

class EvidenceOutbox:
    def __init__(self, root):
        self.root=Path(root)
        self.pending=self.root/"pending"
        self.acked=self.root/"acknowledged"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.acked.mkdir(parents=True, exist_ok=True)

    def enqueue(self, bundle):
        blob=encode(bundle)
        key=digest(blob)
        target=self.pending/(key+".json")
        if (self.acked/(key+".json")).exists():
            return key
        if target.exists():
            if digest(target.read_bytes()) != key:
                raise OutboxError("local pending evidence tampered")
            return key
        fd,name=tempfile.mkstemp(prefix=".new-", dir=self.pending)
        try:
            with os.fdopen(fd,"wb") as f:
                f.write(blob)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name,target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return key

    def deliver(self, sender, *, max_items=20):
        """Sender returns a remote receipt or None. Failure never raises into Core."""
        if not callable(sender) or type(max_items) is not int or max_items < 1:
            raise ValueError("invalid sender or limit")
        outcomes=[]
        for path in sorted(self.pending.glob("*.json"))[:max_items]:
            key=path.stem
            try:
                blob=path.read_bytes()
                if digest(blob)!=key:
                    outcomes.append((key,"TAMPERED_LOCAL"))
                    continue
                receipt=sender(json.loads(blob),key)
                if not isinstance(receipt,dict) or receipt.get("sha256")!=key or not receipt.get("remote_id"):
                    outcomes.append((key,"PENDING_EXTERNAL_ANCHOR"))
                    continue
                ack=self.acked/path.name
                data=encode({"sha256":key,"remote_id":receipt["remote_id"],"receipt":receipt})
                fd,name=tempfile.mkstemp(prefix=".ack-",dir=self.acked)
                try:
                    with os.fdopen(fd,"wb") as f:
                        f.write(data); f.flush(); os.fsync(f.fileno())
                    os.replace(name,ack)
                finally:
                    if os.path.exists(name):
                        os.unlink(name)
                path.unlink()
                outcomes.append((key,"REMOTE_RECEIPT_RECORDED_NOT_INDEPENDENTLY_VERIFIED"))
            except Exception:
                outcomes.append((key,"PENDING_EXTERNAL_ANCHOR"))
        return outcomes

    def pending_count(self):
        return len(list(self.pending.glob("*.json")))
