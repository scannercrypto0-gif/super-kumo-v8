"""Additive OD-01B identity. No legacy record or hash is rewritten."""
from dataclasses import asdict
from enum import Enum
import hashlib
import json
import math

from .historical_library import DatasetManifest, HistoricalBar, HistoricalDataError


def _canonical(value):
    # Tagged scalars avoid JSON float-format/platform ambiguities and collisions.
    if isinstance(value, Enum):
        return _canonical(value.value)
    if value is None:
        return ["null"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Nonfinite semantic number")
        return ["float64", value.hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) in (list, tuple):
        return ["array", [_canonical(x) for x in value]]
    if type(value) is dict and all(type(k) is str for k in value):
        return ["object", [[k, _canonical(value[k])] for k in sorted(value)]]
    raise ValueError("Unsupported semantic value")


def semantic_bytes_v1(value):
    return json.dumps(_canonical(value), ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def content_hash_v1(manifest, bars, *, price_unit, volume_unit,
                    session, normalization, adjustment):
    """Commit a COMPLETE verified dataset plus explicit caller metadata.

    Unknown receipt remains null and availability classification remains intact.
    This is an identity, not a custody/receipt/PIT eligibility certificate.
    Partial prefixes must not be mislabeled as the complete dataset identity.
    """
    if not isinstance(manifest, DatasetManifest) or not manifest.provenance_verified:
        raise HistoricalDataError("Verified stored manifest required")
    bars = tuple(bars)
    if not manifest.verify_integrity() or not bars:
        raise HistoricalDataError("Invalid manifest or empty dataset")
    if any(not isinstance(b, HistoricalBar) or not b.verify_checksum() for b in bars):
        raise HistoricalDataError("Invalid bar checksum")
    if any(b.symbol != manifest.symbol or b.interval != manifest.interval for b in bars):
        raise HistoricalDataError("Manifest/bar identity mismatch")
    if any(a.bar_open >= b.bar_open for a, b in zip(bars, bars[1:])):
        raise HistoricalDataError("Strict ordered unique bars required")
    if (len(bars) != manifest.bar_count or bars[0].bar_open != manifest.min_bar_open
            or bars[-1].bar_open != manifest.max_bar_open or not manifest.verify_hash(bars)):
        raise HistoricalDataError("Complete manifest-bound content required")
    metadata = dict(price_unit=price_unit, volume_unit=volume_unit, session=session,
                    normalization=normalization, adjustment=adjustment)
    if any(type(v) is not str or not v.strip() for v in metadata.values()):
        raise ValueError("Explicit units/session/transformation policy required")
    # These fields are per-import identity/lineage, not semantic data identity.
    excluded = {"dataset_id", "version", "created_at_ms", "parent_version",
                "lineage_reason", "manifest_integrity_hash"}
    meta = {k: v for k, v in manifest.to_dict().items() if k not in excluded}
    # Include existing checksums: numeric int/float distinctions in legacy
    # provenance are intentionally retained rather than silently normalized away.
    records = [asdict(bar) for bar in bars]
    payload = dict(schema="aql-content-identity-v1", manifest=meta,
                   metadata=metadata, bars=records)
    return hashlib.sha256(b"AQL:CONTENT_HASH_V1\x00" + semantic_bytes_v1(payload)).hexdigest()
