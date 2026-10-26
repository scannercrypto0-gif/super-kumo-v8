"""SF-DEC-23/24/25: isolated DEV-only in-memory research admission.

The caller MUST supply a separately frozen DEV-only manifest/records through
an already approved data boundary. This module never opens a file or OOS.
Caller-provided partition metadata is checked, NOT independently authenticated.
"""
from dataclasses import dataclass
import re

from .content_identity import content_hash_v1
from .historical_library import (
    BarQuality, DataAvailabilityKind, DatasetManifest, HistoricalBar,
)
from .strategy_definition import canonical, digest

_HEX = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class DevBoundary:
    """Caller-retained commitment for an independently provisioned DEV resource.

    NOTE: Possessing this object is not independent custody or filesystem ACL
    evidence. Its purpose is to enforce scope before iterating supplied bars.
    """
    dataset_id: str
    version: int
    dev_start_ms: int
    dev_end_ms: int
    manifest_integrity_hash: str
    source_reference: str
    reserve_oos: bool = True


def _blocked(reason, boundary=None):
    return _seal({
        "schema": "sf-historical-admission-v1",
        "state": "INPUTS_ONLY_NOT_EVALUATED",
        "tier": "BLOCKED", "dev_eligible": False,
        "confirmed_pit_eligible": False,
        "oos_access": "LOCKED",
        "independent_custody": "NOT_VERIFIED",
        "partition_authority": "CALLER_CLAIM_NOT_EXTERNALLY_VERIFIED",
        "dataset_id": boundary.dataset_id if isinstance(boundary, DevBoundary) else None,
        "dataset_version": boundary.version if isinstance(boundary, DevBoundary) else None,
        "dev_bounds_ms": ([boundary.dev_start_ms, boundary.dev_end_ms]
                          if isinstance(boundary, DevBoundary) else None),
        "source_reference": (boundary.source_reference
                             if isinstance(boundary, DevBoundary) else None),
        "content_hash_v1": None,
        "manifest_integrity_hash": None,
        "availability": "UNKNOWN",
        "blocked_reasons": [reason],
    })


def _seal(body):
    result = dict(body)
    result["report_digest"] = digest(body)
    return result


def preflight_dev(manifest, bars, *, boundary, expected_content_hash,
                  price_unit, volume_unit, session, normalization,
                  adjustment, decision_cutoff_ms=None):
    """Read-only structural DEV admission; NEVER claim external verification.

    Before iterating 'bars', checks DEV boundaries and frozen manifest metadata.
    Rejected resources cannot be opened or scanned by this module. The caller
    must not load combined DEV+OOS content to construct this invocation.
    """
    if not isinstance(boundary, DevBoundary) or boundary.reserve_oos is not True:
        return _blocked("DEV_PARTITION_NOT_VERIFIED")
    if (not isinstance(manifest, DatasetManifest)
            or not manifest.provenance_verified
            or not manifest.verify_integrity()
            or not boundary.dataset_id
            or not boundary.source_reference
            or type(boundary.version) is not int or boundary.version < 1
            or type(boundary.dev_start_ms) is not int
            or type(boundary.dev_end_ms) is not int
            or boundary.dev_start_ms > boundary.dev_end_ms
            or boundary.dataset_id != manifest.dataset_id
            or boundary.version != manifest.version
            or boundary.manifest_integrity_hash != manifest.manifest_integrity_hash
            or manifest.min_bar_open != boundary.dev_start_ms
            or manifest.max_bar_open != boundary.dev_end_ms):
        return _blocked("DEV_PARTITION_NOT_VERIFIED", boundary)
    if (type(expected_content_hash) is not str
            or _HEX.fullmatch(expected_content_hash) is None):
        return _blocked("CONTENT_IDENTITY_NOT_ESTABLISHED", boundary)
    if (decision_cutoff_ms is not None
            and (type(decision_cutoff_ms) is not int
                 or decision_cutoff_ms <= boundary.dev_end_ms)):
        return _blocked("PIT_METADATA_INVALID", boundary)

    # This function never calls a file opener or evaluates the source archive.
    # Require exact full-DEV bounds BEFORE identity or any PIT checks.
    records = tuple(bars)
    if (not records or len(records) != manifest.bar_count
            or not all(isinstance(b, HistoricalBar) for b in records)
            or records[0].bar_open != boundary.dev_start_ms
            or records[-1].bar_open != boundary.dev_end_ms
            or any(b.bar_open < boundary.dev_start_ms
                   or b.bar_open > boundary.dev_end_ms for b in records)):
        return _blocked("DEV_PARTITION_NOT_VERIFIED", boundary)
    try:
        actual_content_hash = content_hash_v1(
            manifest, records, price_unit=price_unit, volume_unit=volume_unit,
            session=session, normalization=normalization,
            adjustment=adjustment)
    except (ValueError, TypeError):
        return _blocked("QUALITY_BLOCKED", boundary)
    if actual_content_hash != expected_content_hash:
        return _blocked("CONTENT_IDENTITY_MISMATCH", boundary)
    if (manifest.gap_count != 0 or manifest.duplicate_count != 0
            or manifest.non_final_count != 0
            or manifest.coverage_pct != 100.0
            or any(b.quality != BarQuality.FINAL for b in records)):
        return _blocked("QUALITY_BLOCKED", boundary)

    # Never silently relabel internally CONFIRMED or mixed-source bars as
    # retrospective simply because the decision cutoff or receipts are bad.
    kinds = {b.availability_kind for b in records}
    if kinds == {DataAvailabilityKind.RETROSPECTIVE}:
        tier = "RETROSPECTIVE_DEV"
    elif kinds == {DataAvailabilityKind.CONFIRMED}:
        if (decision_cutoff_ms is None
                or any(type(b.ingest_time_ms) is not int
                       or b.ingest_time_ms <= b.bar_close
                       or b.ingest_time_ms > b.observation_cutoff_ms
                       or b.observation_cutoff_ms > decision_cutoff_ms
                       for b in records)):
            return _blocked("PIT_METADATA_INVALID", boundary)
        tier = "PIT_METADATA_VALID"
    else:
        return _blocked("AVAILABILITY_CLASS_MIXED", boundary)
    confirmed = tier == "PIT_METADATA_VALID"
    return _seal({
        "schema": "sf-historical-admission-v1",
        "state": "INPUTS_ONLY_NOT_EVALUATED",
        "tier": tier,
        "dev_eligible": False,
        "confirmed_pit_eligible": False,
        "oos_access": "LOCKED",
        "independent_custody": "NOT_VERIFIED",
        "partition_authority": "CALLER_CLAIM_NOT_EXTERNALLY_VERIFIED",
        "dataset_id": boundary.dataset_id,
        "dataset_version": boundary.version,
        "dev_bounds_ms": [boundary.dev_start_ms, boundary.dev_end_ms],
        "source_reference": boundary.source_reference,
        "content_hash_v1": actual_content_hash,
        "manifest_integrity_hash": manifest.manifest_integrity_hash,
        "availability": ("RECORDED_NOT_INDEPENDENTLY_AUTHENTICATED"
                         if confirmed else "HISTORICAL_ARRIVAL_UNKNOWN"),
        "blocked_reasons": (["DEV_PARTITION_AUTHORITY_NOT_VERIFIED",
                             "CUSTODY_NOT_VERIFIED"]
                            if confirmed else ["DEV_PARTITION_AUTHORITY_NOT_VERIFIED",
                                               "SOURCE_AVAILABILITY_UNKNOWN",
                                               "CUSTODY_NOT_VERIFIED"]),
    })


def verify_admission_report(report, *, expected_report_digest):
    """Verify canonical report policy and separately retained digest.

    Does not certify the report's source inputs; replay source verification
    remains necessary. Reject even locally *rehashed* fake stronger claims.
    """
    if (type(expected_report_digest) is not str
            or _HEX.fullmatch(expected_report_digest) is None
            or type(report) is not dict):
        raise ValueError("Expected retained report commitment required")
    keys = {"schema", "state", "tier", "dev_eligible", "confirmed_pit_eligible",
            "oos_access", "independent_custody", "partition_authority",
            "dataset_id", "dataset_version", "dev_bounds_ms",
            "source_reference", "content_hash_v1", "manifest_integrity_hash",
            "availability", "blocked_reasons", "report_digest"}
    if set(report) != keys:
        raise ValueError("Unexpected report fields")
    if (report["schema"] != "sf-historical-admission-v1"
            or report["state"] != "INPUTS_ONLY_NOT_EVALUATED"
            or report["tier"] not in ("BLOCKED", "RETROSPECTIVE_DEV",
                                     "PIT_METADATA_VALID")
            or type(report["dev_eligible"]) is not bool
            or report["dev_eligible"] is not False
            or report["confirmed_pit_eligible"] is not False
            or report["oos_access"] != "LOCKED"
            or report["independent_custody"] != "NOT_VERIFIED"
            or report["partition_authority"] != "CALLER_CLAIM_NOT_EXTERNALLY_VERIFIED"
            or type(report["blocked_reasons"]) is not list
            or not report["blocked_reasons"]):
        raise ValueError("Unverified research promotion prohibited")
    if report["tier"] == "BLOCKED":
        if report["content_hash_v1"] is not None or report["availability"] != "UNKNOWN":
            raise ValueError("Blocked reports cannot claim verified content")
    else:
        if (type(report["content_hash_v1"]) is not str
                or _HEX.fullmatch(report["content_hash_v1"]) is None
                or type(report["manifest_integrity_hash"]) is not str
                or _HEX.fullmatch(report["manifest_integrity_hash"]) is None):
            raise ValueError("Admitted report requires content commitments")
        if (report["tier"] == "PIT_METADATA_VALID"
                and report["availability"] !=
                "RECORDED_NOT_INDEPENDENTLY_AUTHENTICATED"):
            raise ValueError("PIT metadata claim mismatch")
        if (report["tier"] == "RETROSPECTIVE_DEV"
                and report["availability"] != "HISTORICAL_ARRIVAL_UNKNOWN"):
            raise ValueError("Retrospective provenance claim mismatch")
    body = {k: v for k, v in report.items() if k != "report_digest"}
    if (digest(body) != report["report_digest"]
            or report["report_digest"] != expected_report_digest):
        raise ValueError("Retained report digest mismatch")
    return canonical(report)


def human_summary(report):
    verify_admission_report(report, expected_report_digest=report["report_digest"])
    return ("SF historical DEV-only preflight: " + report["tier"] +
            " | " + ", ".join(report["blocked_reasons"]) +
            " | OOS LOCKED; external custody NOT VERIFIED; no evaluation")
