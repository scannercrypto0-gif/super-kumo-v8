"""Local DEV-only result custody; no data admission, study invocation or signing authority.

One exclusive run directory is the append-only identity. JSON/manifest are written
with exclusive creation and fsync; readback checks content digests. This does not
prove issuer PIT, WORM storage, OS durability or owner authentication.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import os
import re

from .historical_dev_exits_v1 import verify_receipt, digest

SCHEMA = "sf-dev-run-bundle-local-v1"
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_PATHS = frozenset(("FACTUAL", "TARGET_FIRST", "STOP_FIRST"))


def _bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8")


def _sha(raw):
    return sha256(raw).hexdigest()


def _write_exclusive(path, raw):
    with path.open("xb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def _validate(receipt, evidence):
    if not isinstance(receipt, dict) or not verify_receipt(receipt):
        raise ValueError("INVALID_REPLAY_RECEIPT")
    if set(receipt.get("paths", {})) != _PATHS:
        raise ValueError("MISSING_INDEPENDENT_PATH")
    for name in _PATHS:
        path = receipt["paths"][name]
        if (type(path.get("scheduled_denominator")) is not int
                or path["scheduled_denominator"] != len(path.get("opportunities", []))
                or path.get("status") not in
                ("UNKNOWN_UNRESOLVED", "OPEN_UNRESOLVED", "SETTLED_MODELED")):
            raise ValueError("INVALID_OPPORTUNITY_DENOMINATOR_OR_STATUS")
        if path["status"] == "UNKNOWN_UNRESOLVED" and (
                path.get("realized_pnl") is not None
                or path.get("modeled_equity_return") is not None):
            raise ValueError("UNKNOWN_POLICY_MUST_BE_NULL")
    required = ("policy_id", "policy_sha256", "source_zip_sha256",
                "issued_receipt_sha256", "code_sha", "input_prefix_sha256",
                "scenario_id", "warmup_bars", "experiment_id")
    if not isinstance(evidence, dict) or set(evidence) != set(required):
        raise ValueError("MISSING_OR_EXTRA_RUN_COMMITMENT")
    for k in ("policy_sha256", "source_zip_sha256", "issued_receipt_sha256",
              "input_prefix_sha256"):
        v = evidence[k]
        if not isinstance(v, str) or not re.fullmatch("[0-9a-f]{64}", v):
            raise ValueError("BAD_SHA_" + k)
    for k in ("policy_id", "code_sha", "scenario_id", "experiment_id"):
        if not isinstance(evidence[k], str) or not _SAFE.fullmatch(evidence[k]):
            raise ValueError("BAD_RUN_IDENTITY_" + k)
    if type(evidence["warmup_bars"]) is not int or evidence["warmup_bars"] < 22:
        raise ValueError("BAD_WARMUP")
    # Cross-bind independently supplied evidence to the exact replayed payload.
    # The original issued-receipt SHA and loaded code SHA are external claims:
    # this writer has no independent authority to authenticate either.
    source = receipt.get("source", {})
    if evidence["source_zip_sha256"] != source.get("archive_sha256"):
        raise ValueError("SOURCE_ARCHIVE_SHA_MISMATCH")
    if evidence["input_prefix_sha256"] != digest(receipt.get("input_rows")):
        raise ValueError("INPUT_PREFIX_SHA_MISMATCH")
    actual_warmup = receipt.get("config", {}).get("warmup_bars")
    if actual_warmup is None:
        actual_warmup = 22  # legacy default; not evidence of 252 study warmup
    if evidence["warmup_bars"] != actual_warmup:
        raise ValueError("WARMUP_CONFIG_MISMATCH")
    # Defined local binding: policy SHA commits to this engine config and ID.
    # It does NOT authenticate the wider policy registry or operator approval.
    config_pin = digest({"policy_id": evidence["policy_id"],
                         "engine_config": receipt.get("config")})
    if evidence["policy_sha256"] != config_pin:
        raise ValueError("POLICY_CONFIG_SHA_MISMATCH")
    # A receipt is local replay evidence, not proof of the claims in evidence.
    if receipt.get("claims", {}).get("actual_fills") is not False:
        raise ValueError("NOT_DEV_MODELED_ONLY")


def _validate_preflight_binding(preflight, receipt, evidence):
    required = {
        "schema": "sf-dev-input-preflight-v1",
        "status": "INPUT_BYTES_AND_NORMALIZED_ROWS_VALID_NOT_STUDY_AUTHORITY",
        "symbol": "BTCUSDT", "interval_ms": 60000,
        "start_ms": 1704067200000, "end_exclusive_ms": 1704153600000,
        "bar_count": 1440, "warmup_bars": 252,
        "receipt_authenticity": "NOT_AUTHENTICATED_BY_THIS_GATE",
        "point_in_time_provenance": "NOT_ESTABLISHED_BY_THIS_GATE",
    }
    if not isinstance(preflight, dict) or any(preflight.get(k) != v for k, v in required.items()):
        raise ValueError("INVALID_OR_NON_B0_INPUT_PREFLIGHT")
    if (preflight.get("archive_sha256") != receipt.get("source", {}).get("archive_sha256")
            or preflight.get("normalized_rows_sha256") != digest(receipt.get("input_rows"))
            or preflight.get("issued_receipt_sha256") != evidence.get("issued_receipt_sha256")
            or preflight.get("warmup_bars") != evidence.get("warmup_bars")
            or preflight.get("policy_id") != evidence.get("policy_id")
            or preflight.get("scenario_id") != evidence.get("scenario_id")
            or preflight.get("code_sha") != evidence.get("code_sha")):
        raise ValueError("INPUT_PREFLIGHT_RECEIPT_BINDING_MISMATCH")


def persist_bundle(store_dir, *, run_id, receipt, evidence, input_preflight=None):
    """Persist a verified *already generated* receipt; never run a study.

    Each run_id is allocated once; failure leaves the directory as an
    INCOMPLETE record and a retry must use a fresh run_id after investigation.
    External raw/source files are never read or copied by this module.
    """
    if not isinstance(run_id, str) or not _SAFE.fullmatch(run_id):
        raise ValueError("INVALID_RUN_ID")
    _validate(receipt, evidence)
    if input_preflight is not None:
        _validate_preflight_binding(input_preflight, receipt, evidence)
    root = Path(store_dir)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("MISSING_OR_UNTRUSTED_STORE_DIRECTORY")
    run = root / run_id
    payload = _bytes(receipt)
    meta = _bytes({"schema": SCHEMA, "run_id": run_id,
                   "evidence": evidence, "status": "DEV_ONLY_NOT_PIT"})
    files = {"receipt.json": payload, "evidence.json": meta}
    if input_preflight is not None:
        files["input_preflight.json"] = _bytes(input_preflight)
    run.mkdir(mode=0o700)  # FileExistsError => fail-closed, never overwrite
    manifest = {"schema": SCHEMA, "run_id": run_id,
                "files": {k: {"sha256": _sha(v), "bytes": len(v)}
                          for k, v in files.items()},
                "state": "COMPLETE_LOCAL_COPY_NOT_IMMUTABLE_CUSTODY"}
    for name, raw in files.items():
        _write_exclusive(run / name, raw)
    _write_exclusive(run / "manifest.json", _bytes(manifest))
    if hasattr(os, "O_DIRECTORY"):
        fd = os.open(str(run), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    if not verify_bundle(store_dir, run_id):
        raise ValueError("FAILED_LOCAL_READBACK")
    return manifest


def verify_bundle(store_dir, run_id):
    if not isinstance(run_id, str) or not _SAFE.fullmatch(run_id):
        return False
    run = Path(store_dir) / run_id
    if not run.is_dir() or run.is_symlink():
        return False
    try:
        raw = (run / "manifest.json").read_bytes()
        manifest = json.loads(raw)
        if manifest.get("schema") != SCHEMA or manifest.get("run_id") != run_id:
            return False
        names = set(manifest.get("files", {}))
        if names not in ({"receipt.json", "evidence.json"},
                         {"receipt.json", "evidence.json", "input_preflight.json"}):
            return False
        for name, commitment in manifest["files"].items():
            path = run / name
            if path.is_symlink():
                return False
            data = path.read_bytes()
            if (len(data) != commitment["bytes"]
                    or _sha(data) != commitment["sha256"]):
                return False
        receipt = json.loads((run / "receipt.json").read_bytes())
        evidence_doc = json.loads((run / "evidence.json").read_bytes())
        if (evidence_doc.get("run_id") != run_id
                or evidence_doc.get("schema") != SCHEMA):
            return False
        evidence = evidence_doc.get("evidence")
        _validate(receipt, evidence)
        if "input_preflight.json" in names:
            preflight = json.loads((run / "input_preflight.json").read_bytes())
            _validate_preflight_binding(preflight, receipt, evidence)
        return True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
