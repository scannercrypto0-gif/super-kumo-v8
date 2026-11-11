"""Read-only as-of context over caller-pinned Core artifacts.

The caller supplies pins from trusted custody. Content hashing verifies that
binding and does not independently authenticate source rights or clocks.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .contracts import digest, timestamp


SCHEMA = "aql.core.source-view.v1"
RECORD_FIELDS = {
    "key", "version", "prior", "source", "market", "use", "grade", "value",
    "final", "event_at", "published_at", "received_at", "committed_at",
    "known_at", "witness", "rights",
}
RIGHTS_FIELDS = {"source", "state", "uses", "valid_from", "expires_at"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def is_pin(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def eligibility(record, rights, cutoff, use):
    if rights["state"] != "VERIFIED" or use not in rights["uses"]:
        return "RIGHTS_UNAVAILABLE"
    if not rights["valid_from"] <= cutoff < rights["expires_at"]:
        return "RIGHTS_OUTSIDE_WINDOW"
    if not record["final"]:
        return "NOT_FINAL"
    received, committed = record["received_at"], record["committed_at"]
    if received is None or committed is None:
        return "RECEIPT_UNKNOWN"
    if committed > cutoff or (
        record["published_at"] is not None and record["published_at"] > cutoff
    ):
        return "NOT_AVAILABLE_BY_CUTOFF"
    if record["grade"] == "PIT_ATTESTED":
        if record["known_at"] is None or record["witness"] is None:
            return "PIT_UNATTESTED"
        if record["known_at"] > cutoff:
            return "NOT_AVAILABLE_BY_CUTOFF"
    return None


def validate_record(record, rights, *, market, use, source):
    require(set(record) == RECORD_FIELDS, "SOURCE_SCHEMA")
    require(record["market"] == market and record["source"] == source, "SOURCE_IDENTITY")
    require(record["use"] == use, "CONSUMER_MODE")
    require(type(record["key"]) is str and bool(record["key"]), "SOURCE_KEY")
    require(type(record["version"]) is int and record["version"] >= 1, "SOURCE_VERSION")
    require(type(record["final"]) is bool and record["value"] is not None, "SOURCE_VALUE")
    require(record["grade"] in {"TEST_ONLY", "RETROSPECTIVE_NON_PIT",
                                "PROSPECTIVE_UNATTESTED", "PIT_ATTESTED"}, "SOURCE_GRADE")
    require(set(rights) == RIGHTS_FIELDS and rights["source"] == source, "RIGHTS_IDENTITY")
    require(isinstance(rights["uses"], list) and all(type(item) is str for item in rights["uses"]),
            "RIGHTS_SCHEMA")
    require(rights["state"] in {"VERIFIED", "DENIED", "UNKNOWN"}, "RIGHTS_SCHEMA")
    require(timestamp(rights["valid_from"]) < timestamp(rights["expires_at"]), "RIGHTS_WINDOW")

    published, received, committed, known = (
        record[k] for k in ("published_at", "received_at", "committed_at", "known_at")
    )
    for value in (record["event_at"], published, received, committed, known):
        if value is not None:
            timestamp(value)
    if committed is not None:
        require(received is not None and received <= committed, "SOURCE_CLOCK_ORDER")
    if received is not None and published is not None:
        require(published <= received, "SOURCE_CLOCK_ORDER")
    if known is not None and published is not None:
        require(published <= known, "SOURCE_CLOCK_ORDER")
    if record["grade"] == "PIT_ATTESTED":
        require(known is not None and is_pin(record["witness"]), "PIT_UNATTESTED")
    else:
        require(known is None and record["witness"] is None, "PIT_OVERCLAIM")


def as_of_view(records, *, expected_keys, pins, rights_by_digest, source, market,
               cutoff, max_age_ms, use, require_pit=False):
    """Project explicit keys without I/O or promotion.

    `pins` maps (key, version) to a trusted digest from the caller's manifest.
    Revisions are append-only. A post-cutoff revision leaves the earlier
    available version eligible. A current denial does not fall back to old data.
    """
    timestamp(cutoff)
    timestamp(max_age_ms)
    require(use in {"MONITOR_ONLY", "DECISION"}, "CONSUMER_MODE")
    keys = tuple(expected_keys)
    require(bool(keys) and all(type(key) is str and key for key in keys)
            and len(set(keys)) == len(keys), "INVALID_POPULATION")
    grouped = {key: {} for key in keys}
    for record in records:
        require(set(record) == RECORD_FIELDS, "SOURCE_SCHEMA")
        key, version = record["key"], record["version"]
        require(type(key) is str and key in grouped and type(version) is int, "SOURCE_KEY")
        record_digest = digest(record)
        require(pins.get((key, version)) == record_digest, "SOURCE_DIGEST")
        require(version not in grouped[key], "DUPLICATE_REVISION")
        rights_pin = record["rights"]
        require(is_pin(rights_pin), "RIGHTS_IDENTITY")
        rights = rights_by_digest.get(rights_pin)
        require(rights is not None and digest(rights) == rights_pin, "RIGHTS_PIN_UNAVAILABLE")
        validate_record(record, rights, market=market, use=use, source=source)
        grouped[key][version] = (record, rights, record_digest)

    slots = []
    for key, revisions in grouped.items():
        require({version for item, version in pins if item == key} == set(revisions),
                "MISSING_PINNED_REVISION")
        parent = None
        prior_commit = None
        selected = None
        for expected_version, version in enumerate(sorted(revisions), start=1):
            record, rights, record_digest = revisions[version]
            require(version == expected_version and record["prior"] == parent, "REVISION_LINEAGE")
            parent = record_digest
            committed = record["committed_at"]
            if prior_commit is not None and committed is not None:
                require(prior_commit <= committed, "REVISION_CLOCK_ORDER")
            if committed is not None:
                prior_commit = committed
            if ((committed is None or committed <= cutoff)
                    and (record["published_at"] is None or record["published_at"] <= cutoff)
                    and (record["known_at"] is None or record["known_at"] <= cutoff)):
                selected = record, rights, record_digest
        slot = {"key": key, "record": None, "digest": None,
                "reason": "MISSING" if not revisions else "NOT_AVAILABLE_BY_CUTOFF"}
        if selected:
            record, rights, record_digest = selected
            reason = eligibility(record, rights, cutoff, use)
            if reason is None and (require_pit or use == "DECISION") and record["grade"] != "PIT_ATTESTED":
                reason = "PIT_UNATTESTED"
            if reason is None and cutoff - record["received_at"] > max_age_ms:
                reason = "STALE"
            slot.update(record=deepcopy(record) if reason is None else None,
                        digest=record_digest, reason=reason)
        slots.append(slot)

    available = sum(slot["reason"] is None for slot in slots)
    coverage = "COMPLETE" if available == len(slots) else "PARTIAL" if available else "UNKNOWN"
    result = {"schema": SCHEMA, "source": source, "market": deepcopy(market), "use": use,
              "cutoff": cutoff, "coverage": coverage, "slots": slots}
    return {**result, "digest": digest(result)}
