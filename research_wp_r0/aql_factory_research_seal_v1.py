"""Canonical seals shared by Factory research contracts."""
from hashlib import sha256
import json

HEX = frozenset("0123456789abcdef")


class ResearchAdmissionError(ValueError):
    pass


def _require(ok, reason):
    if not ok:
        raise ResearchAdmissionError("FACTORY_AUTHENTIC_" + reason)


def _hash(value):
    return type(value) is str and len(value) == 64 and set(value) <= HEX


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=True).encode()).hexdigest()


def _check_seal(value, field):
    _require(type(value) is dict and _hash(value.get(field)), "SEAL_MISSING")
    payload = {k: v for k, v in value.items() if k != field}
    _require(_digest(payload) == value[field], "SEAL_TAMPER")


def seal(payload):
    _require(type(payload) is dict and "artifact_sha256" not in payload,
             "SEAL_INPUT")
    value = json.loads(json.dumps(payload, allow_nan=False))
    value["artifact_sha256"] = _digest(value)
    return value
