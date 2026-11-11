"""Offline synthetic bytes only; no market download, strategy or PIT claims."""
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aql.historical.dev_source import DevSourceEnvelope, DevSourceError, import_bytes, import_local
from research_wp_r0.historical_library import CustodyAccessor, HistoricalLibrary, HistoricalDataError

START = 1704067200000


def csv_bytes(count=3):
    return "\n".join(f"{START+i*60000},{START+(i+1)*60000-1},10,12,9,11,2"
                     for i in range(count)).encode()


def spec(raw=None, **changes):
    raw = csv_bytes() if raw is None else raw
    value = {"schema": "core-dev-source-1", "scope": "DEV_ONLY", "origin": "SYNTHETIC",
             "market": "SPOT", "symbol": "BTCUSDT", "interval": "1m",
             "start_ms": START, "end_ms_exclusive": START+180000,
             "bytes_ref": "fixture:synthetic-only", "archive_sha256": hashlib.sha256(raw).hexdigest(),
             "archive_size": len(raw), "format": "canonical-csv-7-v1", "member": None,
             "checksum_provenance": "SYNTHETIC_FIXTURE", "normalization": "ohlcv-ms-float64-grid-1",
             "source_version": "UNKNOWN", "correction_status": "UNKNOWN",
             "issuer_first_available_at": "UNKNOWN", "bounded_UTC": "UNKNOWN",
             "independent_custody": "UNKNOWN"}
    value.update(changes)
    return value


def test_deterministic_acceptance_and_immutable_identity(tmp_path):
    raw = csv_bytes()
    p = tmp_path / "source.csv"
    p.write_bytes(raw)
    envelope = DevSourceEnvelope(spec())
    a, b = import_local(envelope, p), import_bytes(envelope, raw)
    assert a.receipt == b.receipt
    assert a.bars == b.bars
    assert a.manifest.verify_hash(a.bars) and a.manifest.verify_integrity()
    assert a.manifest.source_hash == hashlib.sha256(raw).hexdigest()
    assert p.read_bytes() == raw
    copy = envelope.spec
    copy["scope"] = "PIT"
    assert envelope.spec["scope"] == "DEV_ONLY"
    assert DevSourceEnvelope(json.loads(envelope.payload)).source_id == envelope.source_id
    assert DevSourceEnvelope(spec(bytes_ref="another:location")).source_id != envelope.source_id


def test_unknowns_do_not_become_confirmed_or_pit():
    data = import_bytes(DevSourceEnvelope(spec()), csv_bytes())
    for key in ("issuer_first_available_at", "bounded_UTC", "independent_custody", "correction_status"):
        assert data.receipt[key] == "UNKNOWN"
    assert data.receipt["real_pit_accepted"] is False
    assert all(b.ingest_time_ms is None and b.availability_kind.value == "RETROSPECTIVE" for b in data.bars)
    lib = HistoricalLibrary()
    lib.register(data.envelope.source_id, list(data.bars), data.manifest)
    with pytest.raises(HistoricalDataError):
        CustodyAccessor(lib).range_query(data.envelope.source_id, START, START+120000, START+180000)
    with pytest.raises(DevSourceError, match="PIT_QUALIFICATION"):
        data.range_query(START, START+180000, START+180000, require_pit=True)


def test_closed_bar_prefix_no_lookahead():
    data = import_bytes(DevSourceEnvelope(spec()), csv_bytes())
    assert len(data.range_query(START, START+60000, START+60000)) == 1
    with pytest.raises(DevSourceError, match="LOOKAHEAD"):
        data.range_query(START, START+180000, START+179999)
    with pytest.raises(DevSourceError, match="aligned"):
        data.range_query(START+1, START+60000, START+180000)


@pytest.mark.parametrize("missing", [None, "file"])
def test_missing_bytes(missing, tmp_path):
    env = DevSourceEnvelope(spec(bytes_ref=None))
    with pytest.raises(DevSourceError, match="DATA_AVAILABILITY"):
        import_bytes(env, None) if missing is None else import_local(env, tmp_path / "absent.zip")


@pytest.mark.parametrize("raw", [csv_bytes()+b"x", csv_bytes().replace(b",10,", b",20,", 1)])
def test_exact_hash_size_required(raw):
    with pytest.raises(DevSourceError, match="SOURCE_INTEGRITY"):
        import_bytes(DevSourceEnvelope(spec()), raw)


@pytest.mark.parametrize("change", [
    {"schema": "core-dev-source-2"}, {"scope": "OOS"}, {"scope": "PIT"},
    {"source_version": "ORIGINAL"}, {"correction_status": "CORRECTED"},
    {"issuer_first_available_at": START}, {"bounded_UTC": "VERIFIED"},
    {"independent_custody": True}, {"normalization": "guess"},
    {"interval": "2m"}, {"start_ms": START+1}, {"archive_size": True},
    {"format": "unknown"}, {"extra": "field"},
])
def test_unsupported_schema_provenance_and_correction_rejected(change):
    with pytest.raises(DevSourceError, match="SCHEMA"):
        DevSourceEnvelope(spec(**change))


@pytest.mark.parametrize("mutate", [
    lambda rows: [rows[0], rows[0], rows[2]],
    lambda rows: [rows[1], rows[0], rows[2]],
    lambda rows: [rows[0], rows[2]],
    lambda rows: rows[:2],
    lambda rows: [rows[0].replace(b",10,", b",nan,"), *rows[1:]],
    lambda rows: [rows[0].replace(b",10,", b",0,"), *rows[1:]],
    lambda rows: [rows[0].replace(b",12,", b",8,"), *rows[1:]],
    lambda rows: [rows[0].replace(b",2", b",-2"), *rows[1:]],
    lambda rows: [b"bad,row", *rows[1:]],
    lambda rows: [rows[0].replace(str(START+59999).encode(), str(START+299999).encode()), *rows[1:]],
])
def test_bad_source_quality_rejected(mutate):
    raw = b"\n".join(mutate(csv_bytes().splitlines()))
    with pytest.raises(DevSourceError, match="SOURCE_QUALITY"):
        import_bytes(DevSourceEnvelope(spec(raw)), raw)


def zip_fixture(extra=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BTCUSDT-1m-2024-01-01.csv", "\n".join(
            f"{START+i*60000},10,12,9,11,2,{START+(i+1)*60000-1},22,1,1,11,0" for i in range(3)))
        if extra:
            z.writestr("extra.csv", "bad")
    return buf.getvalue()


def test_synthetic_binance_zip_format_and_exact_archive_digest():
    raw = zip_fixture()
    env = DevSourceEnvelope(spec(raw, origin="BINANCE_VISION", format="binance-spot-zip-12-ms-v1",
                                 member="BTCUSDT-1m-2024-01-01.csv"))
    data = import_bytes(env, raw)
    assert len(data.bars) == 3
    assert data.manifest.source_hash == hashlib.sha256(raw).hexdigest()
    assert data.receipt["real_pit_accepted"] is False


def test_zip_extra_member_rejected():
    raw = zip_fixture(extra=True)
    env = DevSourceEnvelope(spec(raw, origin="BINANCE_VISION", format="binance-spot-zip-12-ms-v1",
                                 member="BTCUSDT-1m-2024-01-01.csv"))
    with pytest.raises(DevSourceError, match="SOURCE_QUALITY"):
        import_bytes(env, raw)


@pytest.mark.parametrize("change", [{"symbol": "ETHUSDT"}, {"interval": "5m"}])
def test_zip_instrument_interval_mismatch(change):
    raw = zip_fixture()
    value = spec(raw, origin="BINANCE_VISION", format="binance-spot-zip-12-ms-v1",
                 member="BTCUSDT-1m-2024-01-01.csv")
    value.update(change)
    with pytest.raises(DevSourceError, match="SCHEMA"):
        DevSourceEnvelope(value)
