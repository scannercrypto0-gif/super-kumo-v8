"""Synthetic injected contract tests only; not a Core parser or engine rerun."""
from dataclasses import replace
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_wp_r0.historical_library import (
    BarQuality, DataAvailabilityKind, HistoricalBar, SourceType, validate_bars,
)
from research_wp_r0.post149_source_readiness import inspect_source, digest, ReadinessError

START = 1704067200000


def fixture():
    envelope = {
        "schema": "core-dev-source-1", "scope": "DEV_ONLY", "origin": "SYNTHETIC",
        "market": "SPOT", "symbol": "BTCUSDT", "interval": "1m", "start_ms": START,
        "end_ms_exclusive": START+180000, "bytes_ref": "synthetic:injected-contract",
        "archive_sha256": "a"*64, "archive_size": 100, "format": "canonical-csv-7-v1",
        "member": None, "checksum_provenance": "SYNTHETIC_FIXTURE",
        "normalization": "ohlcv-ms-float64-grid-1", "source_version": "UNKNOWN",
        "correction_status": "UNKNOWN", "issuer_first_available_at": "UNKNOWN",
        "bounded_UTC": "UNKNOWN", "independent_custody": "UNKNOWN",
    }
    source_id = "dev1:"+digest(envelope)
    rows = [[START+i*60000, START+(i+1)*60000-1, 10.0, 12.0, 9.0, 11.0, 2.0] for i in range(3)]
    bars = [HistoricalBar(
        symbol="BTCUSDT", interval="1m", bar_open=r[0], bar_close=r[1], open=r[2], high=r[3],
        low=r[4], close=r[5], volume=r[6], quality=BarQuality.FINAL, source=SourceType.FIXTURE,
        source_label=source_id, observation_cutoff_ms=r[1]+1, ingest_time_ms=None,
        availability_kind=DataAvailabilityKind.RETROSPECTIVE,
    ) for r in rows]
    _, manifest = validate_bars(bars, "BTCUSDT", "1m")
    manifest = replace(manifest, dataset_id=source_id, exchange="SYNTHETIC", market="SPOT",
                       source_hash="a"*64, created_at_ms=0)
    receipt = {
        "schema": "core-dev-import-1", "source_id": source_id, "scope": "DEV_ONLY",
        "availability": "BYTES_VERIFIED", "source_quality": "VALIDATED_GRID_OHLCV",
        "real_pit_accepted": False, "verified_source_timing": False, "empirical_eligible": False,
        "issuer_first_available_at": "UNKNOWN", "bounded_UTC": "UNKNOWN",
        "independent_custody": "UNKNOWN", "correction_status": "UNKNOWN",
        "normalized_ohlcv_sha256": digest(rows), "manifest": manifest.to_dict(),
    }
    expected = {"source_id": source_id, "archive_sha256": "a"*64, "archive_size": 100,
                "normalized7_sha256": digest(rows), "core_receipt_sha256": digest(receipt)}
    declarations = {"availability": "UNKNOWN", "correction_timing": "UNKNOWN", "bounded_UTC": "UNKNOWN",
                    "independent_custody": "UNKNOWN", "available_ms": None, "modeled_quote": None,
                    "verified_source_timing": False, "real_pit_accepted": False}
    return envelope, receipt, rows, expected, declarations


def inspect(f):
    e, r, rows, expected, declarations = f
    return inspect_source(e, r, rows, expected=expected, declarations=declarations)


def test_valid_fixture_deterministic_static_receipt_and_no_input_mutation():
    f = fixture()
    before = copy.deepcopy(f)
    a, b = inspect(f), inspect(copy.deepcopy(f))
    assert a.payload == b.payload and a.receipt_sha256 == b.receipt_sha256
    assert f == before
    r = a.spec
    assert r["source_quality"] == "PASS_SOURCE_QUALITY"
    assert r["pit_status"] == "BLOCKED_PIT"
    assert r["consumer_status"] == "NEED_CONSUMER_ACK"
    assert r["archive_readback"] == "NOT_PERFORMED"
    assert r["factory_execution_eligible"] is False
    assert r["real_pit_accepted"] is False and r["verified_source_timing"] is False
    assert "CORRECTION_CHRONOLOGY" in r["missing_evidence"]
    r["real_pit_accepted"] = True
    assert a.spec["real_pit_accepted"] is False


@pytest.mark.parametrize("key,value", [
    ("symbol", "ETHUSDT"), ("interval", "5m"), ("schema", "core-dev-source-2"),
    ("scope", "OOS"), ("archive_sha256", "b"*64), ("archive_size", 101),
    ("source_version", "ORIGINAL"), ("correction_status", "CORRECTED"),
    ("issuer_first_available_at", START), ("bounded_UTC", "VERIFIED"),
    ("independent_custody", "VERIFIED"), ("start_ms", START+1),
])
def test_wrong_identity_version_integrity_or_provenance_rejected(key, value):
    f = fixture()
    f[0][key] = value
    with pytest.raises(ValueError):
        inspect(f)


@pytest.mark.parametrize("key,value", [
    ("available_ms", START+180000), ("modeled_quote", True), ("modeled_quote", False),
    ("availability", "CONFIRMED"), ("correction_timing", "KNOWN"),
    ("verified_source_timing", True), ("real_pit_accepted", True),
])
def test_unexpected_time_quote_or_pit_claim_rejected(key, value):
    f = fixture()
    f[4][key] = value
    with pytest.raises(ReadinessError, match="PROVENANCE_OR_QUOTE_CONFLICT"):
        inspect(f)


def test_missing_correction_status_is_not_defaulted():
    f = fixture()
    del f[4]["correction_timing"]
    with pytest.raises(ReadinessError):
        inspect(f)


@pytest.mark.parametrize("mutate", [
    lambda rows: rows.__setitem__(1, rows[0][:]),
    lambda rows: rows.reverse(),
    lambda rows: rows.pop(1),
    lambda rows: rows[1].__setitem__(0, rows[1][0]+1),
    lambda rows: rows[1].__setitem__(1, rows[1][1]+1),
    lambda rows: rows[1].__setitem__(2, float("nan")),
    lambda rows: rows[1].__setitem__(3, float("inf")),
    lambda rows: rows[1].__setitem__(2, -1.0),
    lambda rows: rows[1].__setitem__(3, 8.0),
    lambda rows: rows[1].__setitem__(6, -1.0),
    lambda rows: rows[1].pop(),
    lambda rows: rows[1].__setitem__(2, True),
])
def test_malformed_duplicate_order_grid_or_finite_ohlcv_fail_closed(mutate):
    f = fixture()
    mutate(f[2])
    with pytest.raises(ValueError):
        inspect(f)


@pytest.mark.parametrize("key", ["normalized7_sha256", "core_receipt_sha256", "source_id"])
def test_separately_retained_hash_domain_mismatch(key):
    f = fixture()
    f[3][key] = "b"*64
    with pytest.raises(ReadinessError):
        inspect(f)


def test_core_receipt_cannot_claim_pit_even_when_rehashed():
    f = fixture()
    f[1]["real_pit_accepted"] = True
    f[3]["core_receipt_sha256"] = digest(f[1])
    with pytest.raises(ReadinessError, match="CORE_RECEIPT_CLAIM_CONFLICT"):
        inspect(f)


def test_manifest_binding_cannot_drift_even_when_rehashed():
    f = fixture()
    manifest = f[1]["manifest"]
    from research_wp_r0.historical_library import DatasetManifest
    m = DatasetManifest.from_dict(manifest)
    f[1]["manifest"] = replace(m, symbol="ETHUSDT").to_dict()
    f[3]["core_receipt_sha256"] = digest(f[1])
    with pytest.raises(ReadinessError, match="MANIFEST_BINDING_CONFLICT"):
        inspect(f)


def test_engine_dictionary_hash_is_not_normalized7_hash():
    f = fixture()
    f[3]["normalized7_sha256"] = digest([{"open_ms": row[0], "available_ms": None, "modeled_quote": None}
                                          for row in f[2]])
    with pytest.raises(ReadinessError, match="NORMALIZED_HASH_MISMATCH"):
        inspect(f)
