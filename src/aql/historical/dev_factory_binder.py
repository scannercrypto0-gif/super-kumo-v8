"""Core-owned, synthetic-only candidate mapping for the pinned Factory148 seam.

Real admission is deliberately closed until independent interface acceptance
and remaining gates exist. No parser, engine, network or PIT authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re

from .dev_source import DevSourceEnvelope, MAX_BYTES, import_bytes

SCHEMA = "core-factory-dev-map-2"
CORE_SHA = "752d7cd6d652860134918a35727853b5ba52f876"
FACTORY_SHA = "eacb5e50150c6e6c64c8a41b8eaa410aebd71532"
FACTORY_COMPATIBILITY = "factory148-u160-whole-policy-null-1"
INSPECTOR_SHA = "9251d5f31ed06ecf87abf53ea604cf1d975923eb"
MAX_MS = 2**53 - 1


class BinderError(ValueError):
    def __init__(self, category, message):
        self.category = category
        super().__init__(f"{category}: {message}")


def _fail(category, message):
    raise BinderError(category, message)


def _canonical(value):
    # Matches actual pinned Factory148 digest, including default ASCII escaping.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _ref(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 1024


@dataclass(frozen=True)
class ArtifactPin:
    reference: str
    version: str
    size_bytes: int
    sha256: str

    def __post_init__(self):
        if (not _ref(self.reference) or not _ref(self.version) or
                type(self.size_bytes) is not int or not 0 < self.size_bytes <= MAX_BYTES or
                type(self.sha256) is not str or not re.fullmatch("[0-9a-f]{64}", self.sha256)):
            _fail("ARTIFACT_PIN", "explicit reference/version/size/SHA required")


def _measure(raw, pin, domain):
    if type(pin) is not ArtifactPin:
        _fail("ARTIFACT_PIN", domain)
    if raw is None:
        _fail("MISSING_BYTES", domain)
    if type(raw) is not bytes or len(raw) != pin.size_bytes or _sha(raw) != pin.sha256:
        _fail("BYTE_INTEGRITY", domain)


@dataclass(frozen=True)
class RecipientAck:
    consumer_task: str
    environment: str
    raw: ArtifactPin
    receipt: ArtifactPin


def measure_readback(raw, receipt, *, raw_pin, receipt_pin, consumer_task, environment):
    """Measure supplied local bytes; labels are caller assertions, not authentication.

    An owner Work ACK is never silently converted into this consumer's ACK.
    No Library or publisher retrieval is performed.
    """
    _measure(raw, raw_pin, "RAW_ARCHIVE")
    _measure(receipt, receipt_pin, "ISSUED_RECEIPT")
    if not _ref(consumer_task) or not _ref(environment):
        _fail("RECIPIENT_ACK", "consumer task and environment required")
    return RecipientAck(consumer_task, environment, raw_pin, receipt_pin)


@dataclass(frozen=True)
class LagPolicy:
    schema: str
    version: str
    lag_ms: int
    owner_decision_ref: str
    council_review_ref: str
    approved: bool

    def __post_init__(self):
        if (self.schema != "retrospective-close-plus-lag-1" or
                type(self.lag_ms) is not int or not 0 <= self.lag_ms <= MAX_MS or
                self.approved is not True or
                not all(_ref(v) for v in (self.version, self.owner_decision_ref, self.council_review_ref))):
            _fail("LAG_POLICY", "explicit approved versioned retrospective lag required")


@dataclass(frozen=True)
class QuotePolicy:
    schema: str
    version: str
    modeled_quote: bool
    owner_decision_ref: str
    council_review_ref: str
    approved: bool

    def __post_init__(self):
        if (self.schema != "hypothetical-ohlcv-quote-1" or
                type(self.modeled_quote) is not bool or self.approved is not True or
                not all(_ref(v) for v in (self.version, self.owner_decision_ref, self.council_review_ref))):
            _fail("QUOTE_POLICY", "separate explicit approved hypothetical quote policy required")


@dataclass(frozen=True)
class SyntheticCandidate:
    """Immutable canonical snapshot. Every accessor returns a detached copy."""
    payload: bytes

    @property
    def package(self):
        return json.loads(self.payload)

    @property
    def rows(self):
        return self.package["rows"]

    @property
    def source(self):
        return self.package["factory_source"]


def _inspector_commitment(decision, history, normalized):
    """Bind the actual157 static receipt, never interpret it as admission."""
    if decision is None:
        return None  # synthetic mapping-only fixtures; real mode always refuses
    if (type(decision) is not dict or set(decision) != {"code_sha", "payload"} or
            decision["code_sha"] != INSPECTOR_SHA or type(decision["payload"]) is not bytes):
        _fail("FACTORY_INSPECTOR_PENDING", "exact157 code/immutable static receipt required")
    raw = decision["payload"]
    try:
        p = json.loads(raw)
        s = history.envelope.spec
        commitments = {"source_id": history.envelope.source_id,
                       "archive_sha256": s["archive_sha256"], "archive_size": s["archive_size"],
                       "normalized7_sha256": _sha(normalized),
                       "core_receipt_sha256": _sha(_canonical(history.receipt))}
        fixed = {"schema": "sf-post149-source-review-1", "status": "READY_FOR_CONTRACT_REVIEW",
                 "scope": "DEV_ONLY_STATIC_REVIEW", "source_quality": "PASS_SOURCE_QUALITY",
                 "quality_scope": "INJECTED_NORMALIZED_RECORDS_AND_METADATA_ONLY",
                 "pit_status": "BLOCKED_PIT", "consumer_status": "NEED_CONSUMER_ACK",
                 "archive_readback": "NOT_PERFORMED", "source_id": history.envelope.source_id,
                 "expected_commitments": commitments, "envelope_sha256": _sha(history.envelope.payload),
                 "record_count": len(history.bars), "start_ms": s["start_ms"],
                 "end_ms_exclusive": s["end_ms_exclusive"],
                 "declarations": {"availability": "UNKNOWN", "correction_timing": "UNKNOWN",
                                  "bounded_UTC": "UNKNOWN", "independent_custody": "UNKNOWN",
                                  "available_ms": None, "modeled_quote": None,
                                  "verified_source_timing": False, "real_pit_accepted": False},
                 "factory_execution_eligible": False, "verified_source_timing": False,
                 "real_pit_accepted": False,
                 "missing_evidence": ["THIS_CODEX_CONSUMER_ZIP_AND_RECEIPT_ACK", "ISSUER_VERSION_FIRST_KNOWN",
                     "CORRECTION_CHRONOLOGY", "BOUNDED_UTC_AUTHORITY", "INDEPENDENT_CUSTODY",
                     "COUNCIL_148_149_AND_157_ACCEPTANCE", "OWNER_DEV_TIME_QUOTE_MODEL_PERMISSION",
                     "SIGNED_INTERFACE_AGREEMENT", "OWNER_INTEGRATION_AUTHORIZATION"]}
        # Byte equality also rejects bool/int equivalence, extra fields and
        # noncanonical/duplicate-key claims. A hash remains unsigned evidence.
        if raw != _canonical(fixed) or raw != _canonical(p):
            raise ValueError("receipt binding/claims mismatch")
    except (ValueError, TypeError) as exc:
        raise BinderError("FACTORY_INSPECTOR_PENDING", "157 receipt conflict") from exc
    return {"code_sha": INSPECTOR_SHA, "receipt_sha256": _sha(raw),
            "size_bytes": len(raw), "receipt": p}


def bind_dev(*, envelope, raw, raw_pin, issued_receipt, receipt_pin,
             recipient_ack, consumer_task, environment, lag_policy, quote_policy,
             decision_cutoff_ms, mode, core_sha=CORE_SHA, factory_sha=FACTORY_SHA,
             inspector_decision=None, require_pit=False):
    """Map validated seven-field bars into a SYNTHETIC candidate only.

    All arguments expressing policy/access are mandatory. Receipt bytes are
    committed as opaque issued bytes, not parsed as a guessed Work152 schema.
    REAL_SOURCE always stops; arbitrary caller inspector dictionaries cannot
    fabricate an interface or independent acceptance. No engine is invoked.
    """
    if require_pit is not False:
        _fail("PIT_QUALIFICATION", "historical timing/corrections/custody UNKNOWN")
    if mode not in ("SYNTHETIC_CONTRACT_TEST", "REAL_SOURCE"):
        _fail("MODE", "explicit supported scope required")
    if core_sha != CORE_SHA or factory_sha != FACTORY_SHA:
        _fail("CODE_VERSION", "mapping is pinned to reviewed dependency sources")
    if type(envelope) is not DevSourceEnvelope:
        _fail("SCHEMA", "Core149 envelope required")
    _measure(raw, raw_pin, "RAW_ARCHIVE")
    _measure(issued_receipt, receipt_pin, "ISSUED_RECEIPT")
    s = envelope.spec
    if (s["bytes_ref"] != raw_pin.reference or s["archive_size"] != raw_pin.size_bytes or
            s["archive_sha256"] != raw_pin.sha256):
        _fail("SOURCE_IDENTITY", "envelope and raw pin mismatch")
    expected_ack = measure_readback(raw, issued_receipt, raw_pin=raw_pin,
                                   receipt_pin=receipt_pin, consumer_task=consumer_task,
                                   environment=environment)
    if type(recipient_ack) is not RecipientAck or recipient_ack != expected_ack:
        _fail("RECIPIENT_ACK", "this recipient's two-file measured ACK required")
    if type(lag_policy) is not LagPolicy or type(quote_policy) is not QuotePolicy:
        _fail("MODEL_APPROVAL", "separate approved lag and quote policies required")
    if type(decision_cutoff_ms) is not int or not 0 <= decision_cutoff_ms <= MAX_MS:
        _fail("LOOKAHEAD", "bounded integer DEV cutoff required")
    if mode == "REAL_SOURCE":
        _fail("FACTORY_INSPECTOR_PENDING",
              "157 delivered but interface/independent S/R and real integration gates unaccepted; BLOCKED")
    if s["origin"] != "SYNTHETIC" or s["checksum_provenance"] != "SYNTHETIC_FIXTURE":
        _fail("SYNTHETIC_SCOPE", "only explicitly synthetic fixtures allowed")
    # Reuse actual importer, not a caller-constructed DevHistory or second parser.
    history = import_bytes(envelope, raw)
    rows = []
    for b in history.range_query(s["start_ms"], s["end_ms_exclusive"], decision_cutoff_ms):
        available = b.bar_close + 1 + lag_policy.lag_ms
        if available > MAX_MS or available > decision_cutoff_ms:
            _fail("LOOKAHEAD", "modeled bar unavailable at cutoff or timestamp overflow")
        rows.append({"open_ms": b.bar_open, "close_ms": b.bar_close,
                     "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                     "volume": b.volume, "available_ms": available,
                     "modeled_quote": quote_policy.modeled_quote})
    # Factory's current validator has a positive 1e-12 price floor, stricter than
    # Core's >0 quality validator. Refuse rather than emit incompatible rows.
    if any(row[k] < 1e-12 for row in rows for k in ("open", "high", "low", "close")):
        _fail("FACTORY_PRICE_DOMAIN", "price below pinned Factory minimum")
    normalized = _canonical([[b.bar_open, b.bar_close, b.open, b.high, b.low, b.close, b.volume]
                             for b in history.bars])
    inspector = _inspector_commitment(inspector_decision, history, normalized)
    full_rows = _canonical(rows)
    body = {
        "schema": SCHEMA, "scope": "SYNTHETIC_CONTRACT_TEST_ONLY",
        "status": "CANDIDATE_NOT_ADMITTED", "core_sha": core_sha, "factory_sha": factory_sha,
        "factory_compatibility": FACTORY_COMPATIBILITY,
        "core_source_id": envelope.source_id, "envelope": s,
        "raw_archive": asdict(raw_pin), "issued_receipt": asdict(receipt_pin),
        "normalized_seven_field": {"schema": s["normalization"], "size_bytes": len(normalized),
                                   "sha256": _sha(normalized)},
        "factory_dictionary_rows": {"schema": "factory148-dictionary-json-ascii-1",
                                    "size_bytes": len(full_rows), "sha256": _sha(full_rows)},
        "recipient_ack": asdict(recipient_ack), "lag_policy": asdict(lag_policy),
        "quote_policy": asdict(quote_policy), "decision_cutoff_ms": decision_cutoff_ms,
        "rows": rows, "inspector_decision": inspector,
        "source_version": "UNKNOWN", "correction_status": "UNKNOWN",
        "issuer_first_available_at": "UNKNOWN", "availability_evidence": "UNKNOWN",
        "bounded_UTC": "UNKNOWN", "independent_custody": "UNKNOWN",
        "claims": {"factory_execution_eligible": False, "real_source_admitted": False,
                   "real_pit_accepted": False, "as_known_at_cutoff": False,
                   "actual_quotes": False, "actual_fills": False, "empirical_eligible": False},
    }
    mapping_sha = _sha(_canonical(body))
    source = {"version": SCHEMA + ":" + mapping_sha,
              "reference": raw_pin.reference, "archive_sha256": raw_pin.sha256,
              "rows_sha256": _sha(full_rows), "availability_evidence": "UNKNOWN",
              "correction_evidence": "PINNED_VERSION_ONLY"}
    return SyntheticCandidate(_canonical({**body, "mapping_sha256": mapping_sha,
                                          "factory_source": source}))


def verify_candidate(candidate):
    """Verify content commitment; not provenance, policy approval or admission."""
    if type(candidate) is not SyntheticCandidate:
        _fail("CANDIDATE_INTEGRITY", "canonical candidate required")
    try:
        p = candidate.package
        if (p.get("schema") != SCHEMA or p.get("core_sha") != CORE_SHA
                or p.get("factory_sha") != FACTORY_SHA
                or p.get("factory_compatibility") != FACTORY_COMPATIBILITY):
            raise ValueError("unsupported dependency/compatibility contract")
        supplied_sha, source = p.pop("mapping_sha256"), p.pop("factory_source")
        if _sha(_canonical(p)) != supplied_sha:
            raise ValueError("mapping commitment")
        expected_source = {"version": SCHEMA + ":" + supplied_sha,
                           "reference": p["raw_archive"]["reference"],
                           "archive_sha256": p["raw_archive"]["sha256"],
                           "rows_sha256": _sha(_canonical(p["rows"])),
                           "availability_evidence": "UNKNOWN", "correction_evidence": "PINNED_VERSION_ONLY"}
        if source != expected_source or candidate.payload != _canonical(candidate.package):
            raise ValueError("source commitment")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise BinderError("CANDIDATE_INTEGRITY", "invalid candidate commitment") from exc
    return True
