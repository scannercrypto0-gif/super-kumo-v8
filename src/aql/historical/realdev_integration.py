"""Owner172 bounded input inspection only. No engine/order/feature execution.

Owner authorization is the separately reviewed human instruction, NOT a hash,
boolean or signature invented by this module. Capability pins constrain that
instruction; they do not authenticate arbitrary Python callers or grant study
permission. REAL_SOURCE in the existing binder is untouched and stays denied.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import getpass
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys

from .dev_source import DevSourceEnvelope, import_bytes
from .dev_factory_binder import SCHEMA, FACTORY_SHA, FACTORY_COMPATIBILITY, CORE_SHA

EXPERIMENT = "AQL-CORE-REALDEV-001"
OWNER_SCOPE = "https://github.com/scannercrypto0-gif/super-kumo-v8/issues/172"
BASE = "0ee2254568479ee5cbcfcca3846716a84404db3c"
RAW_SHA = "4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e"
RECEIPT_SHA = "ffce2bbe7890414d84360be80a0ac478795ae8d1a28085f8bb34075faca83386"
START, END = 1704067200000, 1704153600000


class IntegrationDenied(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise IntegrationDenied(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class RuntimePin:
    host: str
    account: str
    python: str
    python_version: str
    checkout: str
    head: str


def observe_runtime(checkout):
    """Read current local identity/HEAD, never rely on a cached owner ACK."""
    root = Path(checkout).resolve()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    require(git("rev-parse", "--show-toplevel").replace("\\", "/").casefold() ==
            root.as_posix().casefold(), "CHECKOUT_ROOT")
    require(not git("status", "--porcelain", "--untracked-files=normal"), "DIRTY_OR_STALE_CODE")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=root, check=True)
    require(Path(__file__).resolve() == root / "src/aql/historical/realdev_integration.py",
            "LOADED_CODE_ORIGIN")
    return RuntimePin(socket.gethostname(), getpass.getuser(), str(Path(sys.executable).resolve()),
                      platform.python_version(), str(root), git("rev-parse", "HEAD"))


@dataclass(frozen=True)
class IntegrationCapability:
    """Explicit owner-scoped request commitment, not a signed approval service.

    Must be supplied by the authorized recipient after independently selecting
    exact runtime/HEAD. No approved=True, policy numbers or execution authority.
    """
    experiment_id: str
    permission: str
    owner_scope: str
    runtime: RuntimePin
    raw_sha256: str
    receipt_sha256: str
    mapping_schema: str
    factory_sha: str
    compatibility_profile: str
    prefix_start_ms: int
    prefix_end_ms_exclusive: int
    decision_cutoff_ms: int
    warmup_bars: int


def validate_capability(capability, runtime, request):
    require(request == "DEV_INTEGRATION_ONLY", "DEFAULT_DENY_OR_EXECUTION_SCOPE")
    require(type(capability) is IntegrationCapability, "EXPLICIT_CAPABILITY_REQUIRED")
    c = capability
    require(c.experiment_id == EXPERIMENT and c.permission == request and c.owner_scope == OWNER_SCOPE,
            "OWNER_EXPERIMENT_SCOPE")
    require(type(c.runtime) is RuntimePin and c.runtime == runtime, "STALE_RUNTIME_OR_HEAD")
    require(c.raw_sha256 == RAW_SHA and c.receipt_sha256 == RECEIPT_SHA, "SOURCE_RECEIPT_PIN")
    require(c.mapping_schema == SCHEMA == "core-factory-dev-map-2" and
            c.factory_sha == FACTORY_SHA == "eacb5e50150c6e6c64c8a41b8eaa410aebd71532" and
            c.compatibility_profile == FACTORY_COMPATIBILITY == "factory148-u160-whole-policy-null-1",
            "UNSUPPORTED_INTERFACE")
    require(type(c.prefix_start_ms) is int and type(c.prefix_end_ms_exclusive) is int and
            c.prefix_start_ms == START and c.prefix_end_ms_exclusive == END,
            "MISSING_OR_INCOMPLETE_FEATURE_PREFIX")
    require(type(c.decision_cutoff_ms) is int and END <= c.decision_cutoff_ms <= 2**53-1,
            "FUTURE_PREFIX_OR_BAD_CUTOFF")
    require(type(c.warmup_bars) is int and 22 <= c.warmup_bars <= 1440,
            "MISSING_WARMUP_REQUIREMENT")


def validate_receipt(receipt, *, raw_sha, raw_size, pinned_original):
    """Pure receipt binding; reusable synthetic unit fixtures are NOT original ACKs."""
    try:
        r = receipt
        a = r["artifact"]
        require(r["schema"] == "aql-work152-artifact-handoff-receipt-1" and
                r["receipt_id"] == "AQL-CORE-WORK152-BTCUSDT-20240101-001" and
                r["scope"] == "REAL_SOURCE_DEV_ONLY", "RECEIPT_SCHEMA_SCOPE")
        require(r["source_id"] == "binance-vision:spot:BTCUSDT:1m:2024-01-01" and
                r["payload_version_id"] == "sha256:"+raw_sha and
                r["acquisition"]["archive"]["sha256"] == raw_sha and
                r["acquisition"]["archive"]["size_bytes"] == raw_size and
                a["file_size_bytes"] == raw_size, "RECEIPT_ARCHIVE_BINDING")
        require(a["file_id"] == "file_00000000084c8208b5d65c8fc803426c" and
                a["library_file_id"] == "libfile_ae3ca38f8b288191a4c2ee4ea3139292" and
                type(a["current_version_number"]) is int and a["current_version_number"] == 0,
                "RETAINED_VERSION_BINDING")
        require(r["correction_history"] == "UNKNOWN" and r["historical_first_known_at"] is None and
                r["issuer_first_available_at"] is None and r["utc_bound_ms"] is None and
                r["independent_custody"] == "UNVERIFIED" and
                all(r[k] is False for k in ("verified_source_timing", "real_pit_accepted", "empirical_eligible")),
                "UNSUPPORTED_PROVENANCE_PROMOTION")
        n = r["normalization"]["receipt"]
        require(n["archive_sha256"] == raw_sha and n["symbol"] == "BTCUSDT" and
                n["interval_ms"] == 60000 and n["first_open_ms"] == START and
                n["last_open_ms"] == END-60000 and n["count"] == 1440 and n["gap_count"] == 0,
                "RECEIPT_CHRONOLOGY_QUALITY")
        if pinned_original:
            require(raw_sha == RAW_SHA and raw_size == 68923, "ORIGINAL_SOURCE_ONLY")
    except (KeyError, TypeError) as exc:
        raise IntegrationDenied("MISSING_RECEIPT_EVIDENCE") from exc


@dataclass(frozen=True)
class IntegrationReport:
    payload: bytes

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return sha(self.payload)


def read_pinned_file(path, size, expected):
    """Bounded fresh read; public integration supplies fixed original pins."""
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), "MISSING_OR_UNSUPPORTED_LOCAL_FILE")
    before = p.stat()
    with p.open("rb") as stream:
        raw = stream.read(size+1)
    after = p.stat()
    require(len(raw) == size and sha(raw) == expected and
            (before.st_size,before.st_mtime_ns) == (after.st_size,after.st_mtime_ns),
            "FRESH_READBACK_INTEGRITY")
    return raw, {"path": str(p.resolve()), "size_bytes": len(raw), "sha256": sha(raw)}


def inspect_local_pair(raw_path, receipt_path, *, checkout, capability=None,
                       request="REAL_SOURCE"):
    """Fresh read-only original pair verification. Returns NO execution rows/port.

    REAL_SOURCE remains the default denial. Only the separately authorized input
    integration scope exists here; missing model decisions are never defaulted.
    """
    require(request == "DEV_INTEGRATION_ONLY", "DEFAULT_DENY_OR_EXECUTION_SCOPE")
    require(type(capability) is IntegrationCapability, "EXPLICIT_CAPABILITY_REQUIRED")
    runtime = observe_runtime(checkout)
    validate_capability(capability, runtime, request)
    measured = []
    raws = []
    for path, size, expected in ((raw_path, 68923, RAW_SHA), (receipt_path, 4203, RECEIPT_SHA)):
        raw, measurement = read_pinned_file(path, size, expected)
        measured.append(measurement)
        raws.append(raw)
    try:
        receipt = json.loads(raws[1])
    except (ValueError, UnicodeError) as exc:
        raise IntegrationDenied("ISSUED_RECEIPT_JSON") from exc
    validate_receipt(receipt, raw_sha=RAW_SHA, raw_size=len(raws[0]), pinned_original=True)
    envelope = DevSourceEnvelope({
        "schema": "core-dev-source-1", "scope": "DEV_ONLY", "origin": "BINANCE_VISION",
        "market": "SPOT", "symbol": "BTCUSDT", "interval": "1m", "start_ms": START,
        "end_ms_exclusive": END, "bytes_ref": "chatgpt-library:file_00000000084c8208b5d65c8fc803426c:version0",
        "archive_sha256": RAW_SHA, "archive_size": 68923, "format": "binance-spot-zip-12-ms-v1",
        "member": "BTCUSDT-1m-2024-01-01.csv", "checksum_provenance": "SAME_PUBLISHER_REPORTED",
        "normalization": "ohlcv-ms-float64-grid-1", "source_version": "UNKNOWN", "correction_status": "UNKNOWN",
        "issuer_first_available_at": "UNKNOWN", "bounded_UTC": "UNKNOWN", "independent_custody": "UNKNOWN",
    })
    # Actual existing importer enforces full day/order/finite OHLCV/close grid.
    history = import_bytes(envelope, raws[0])
    bars = history.range_query(START, END, capability.decision_cutoff_ms)
    require(len(bars) == 1440 and len(bars) >= capability.warmup_bars, "QUALITY_OR_WARMUP")
    require(history.receipt["normalized_ohlcv_sha256"] == receipt["normalization"]["normalized_sha256"],
            "NORMALIZATION_CONTRACT_MISMATCH")
    # Read HEAD/clean state again after file parsing; don't emit a stale-code ACK.
    require(observe_runtime(checkout) == runtime, "CODE_CHANGED_DURING_READBACK")
    body = {
        "schema": "core-realdev-input-integration-1", "experiment_id": EXPERIMENT,
        "status": "DEV_INTEGRATION_ONLY_ACCEPTED_PENDING_AUDIT", "runtime": asdict(runtime),
        "capability": asdict(capability), "readback": measured,
        "receipt_id": receipt["receipt_id"], "source_id": receipt["source_id"],
        "retained_archive_version": 0, "receipt_version_evidence": "WORK152_EXTERNAL_PIN_VERSION0",
        "core_importer_sha": CORE_SHA, "mapping_schema": SCHEMA,
        "compatibility_profile": FACTORY_COMPATIBILITY, "factory_sha": FACTORY_SHA,
        "validation": {"fresh_pair": True, "receipt_binding": True, "full_grid_ohlcv": True,
                       "utc_ms_geometry": True, "chronological_prefix": True, "warmup_input_count": True},
        "normalized_seven_field_sha256": history.receipt["normalized_ohlcv_sha256"],
        "core_manifest_integrity_hash": history.manifest.manifest_integrity_hash,
        "bar_count": len(bars), "DEV_ONLY": True, "NOT_PIT": True,
        "NOT_EMPIRICALLY_VALIDATED": True, "actual_fill": False,
        "verified_source_timing": False, "real_pit_accepted": False, "empirical_eligible": False,
        "strategy_execution": "BLOCKED_NOT_AUTHORIZED", "factory_execution_eligible": False,
        "execution_policy": {k: "NOT_CONFIGURED" for k in (
            "source_lag", "execution_delay", "quote_convention", "spread", "slippage", "fees", "sizing",
            "limit_expiry", "tp_sl", "intrabar_priority", "sensitivity")},
        "issuer_first_available_at": "UNKNOWN", "correction_history": "UNKNOWN",
        "bounded_UTC": "UNKNOWN", "independent_custody": "UNVERIFIED",
        "uncertainty_semantics": "UNCHANGED_UNKNOWN_ENTRY_QUOTE_AND_WHOLE_POLICY_NULL",
        "output_scope": "PROVENANCE_ONLY_NO_FEATURES_ROWS_SIGNALS_ORDERS_FILLS_CASH_OR_PNL",
    }
    return IntegrationReport(canonical(body))


def replay_local_report(report, *, expected_digest, **invocation):
    """Remeasure originals and recompute deterministic report, not trust a JSON ACK."""
    require(type(report) is IntegrationReport and report.digest == expected_digest,
            "REPORT_COMMITMENT")
    fresh = inspect_local_pair(**invocation)
    require(fresh.payload == report.payload, "REPORT_REPLAY_MISMATCH")
    return fresh
