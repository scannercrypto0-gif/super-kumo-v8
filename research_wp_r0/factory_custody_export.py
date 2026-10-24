"""Factory custody export: explicit destination, no claim of independent storage.

Write a verified envelope atomically to an existing, operator-selected
directory. The caller MUST choose a destination outside writer control.
"""
import os
from pathlib import Path
import tempfile

from .factory_custody_envelope import custody_envelope, verify_custody_envelope


def export_custody_envelope(destination, *, plan_digest, ledger_checkpoint):
    target = Path(destination)
    if not target.parent.is_dir() or target.is_symlink() or target.exists():
        raise ValueError("Existing destination or unsafe parent; refusing overwrite")
    payload = custody_envelope(plan_digest=plan_digest, ledger_checkpoint=ledger_checkpoint)
    temp_path = None
    try:
        fd, name = tempfile.mkstemp(prefix=".atlas-custody-", dir=str(target.parent))
        temp_path = Path(name)
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        # Link creation is exclusive: never overwrite a pre-existing anchor.
        os.link(temp_path, target)
        try:
            directory_fd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass  # Some platforms do not support directory fsync.
        verify_custody_envelope(target.read_bytes(),
                                plan_digest=plan_digest, ledger_checkpoint=ledger_checkpoint)
        return target
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def verify_exported_custody(destination, *, plan_digest, ledger_checkpoint):
    path = Path(destination)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or symlink custody file")
    return verify_custody_envelope(path.read_bytes(),
                                   plan_digest=plan_digest, ledger_checkpoint=ledger_checkpoint)
