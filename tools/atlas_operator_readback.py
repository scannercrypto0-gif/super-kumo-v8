"""Shared saved-only JSON verification and immutable publication."""

import json
import os
from pathlib import Path
import tempfile


from aql.observation.contracts import digest


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def without_seal(doc):
    return digest({key: value for key, value in doc.items() if key != "sha256"})


def publish(path, report):
    path = path.absolute()
    raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            require(path.read_bytes() == raw, "DISPOSITION_ALREADY_SEALED")
    finally:
        temporary.unlink()
