"""Synthetic one-archive Daily -> Warehouse -> Registry -> Watchdog seam."""
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "peer-watchdog" / "tools"))

from aql.warehouse.daily import import_one_retained
from aql.warehouse.engine import HistoricalWarehouse
from aql.warehouse.storage import seal, canonical
import atlas_ops_watchdog as watchdog


def archive_fixture(path, source_day_ms, rows=1440):
    date = datetime.fromtimestamp(source_day_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    name = f"BTCUSDT-1m-{date}.zip"
    lines = []
    for minute in range(rows):
        opened = source_day_ms + minute * 60_000
        lines.append(f"{opened},1,2,1,1,3,{opened+59_999},4,1,2,3,0\n")
    out = BytesIO()
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as z:
        z.writestr(name[:-4] + ".csv", "".join(lines))
    raw = out.getvalue()
    checksum = (seal(raw) + "  " + name + "\n").encode()
    path.mkdir()
    (path / name).write_bytes(raw)
    (path / (name + ".CHECKSUM")).write_bytes(checksum)
    return path / name, source_day_ms, seal(raw), seal(checksum)


def health_report(day_ms, source, worker_receipt):
    return {
        "schema": "aql.recurring-runtime.health.v1",
        "source_cadence": "DAILY_UTC",
        "trading_authority": "NONE",
        "current_entry": "NO_CURRENT_ENTRY",
        "observed_at_ms": day_ms + 2 * 86_400_000,
        "cycle_evidence": "RECENT_RESEARCH_RECEIPT",
        "tick_freshness": "RECENT",
        "source_freshness": "LATEST_DUE_DAY_RECEIVED",
        "last_success": {
            "source_day_ms": day_ms,
            "source_zip_sha256": source["source_zip_sha256"],
            "checksum_sha256": source["checksum_sha256"],
            "daily_source_evidence_status": "VERIFIED",
            "daily_worker_receipt_sha256": worker_receipt,
            "receipts": [worker_receipt],
        },
        "next_check_ms": day_ms + 3 * 86_400_000,
        "last_failure": None,
    }


def test_one_pinned_daily_archive_reaches_watchdog_and_replay_is_idempotent(tmp_path):
    day_ms = 1_704_067_200_000  # 2024-01-01T00:00:00Z
    archive, day_ms, zip_pin, checksum_pin = archive_fixture(tmp_path / "retained", day_ms)
    worker = "2" * 64
    w = HistoricalWarehouse(tmp_path / "warehouse", reserve=0, test_root=True)
    first = import_one_retained(w, archive, source_day_ms=day_ms,
        expected_zip_sha256=zip_pin, expected_checksum_sha256=checksum_pin,
        observed_ms=day_ms + 2 * 86_400_000)
    source = json.loads(w.path(f"catalog/{zip_pin}.json").read_bytes())
    before = w.report()["registry"]
    retry = import_one_retained(w, archive, source_day_ms=day_ms,
        expected_zip_sha256=zip_pin, expected_checksum_sha256=checksum_pin,
        observed_ms=day_ms + 3 * 86_400_000)
    after = w.report()["registry"]
    assert retry["this_run"][0]["inserted_rows"] == 0
    assert after["event_watermark"] == before["event_watermark"]
    assert after["physical_rows"] == before["physical_rows"] == 1440
    assert first["warehouse_receipt_sha256"] and source["receipt_sha256"]

    linked = watchdog.daily_view(
        health_report(day_ms, source, worker), first,
        source, after, first["warehouse_receipt_sha256"])
    assert linked["source_receipt_link_verified"] is True
    assert linked["last_success"]["source_day_ms"] == day_ms
    assert linked["last_success"]["source_zip_sha256"] == zip_pin
    assert linked["last_success"]["daily_worker_receipt_sha256"] == worker


@pytest.mark.parametrize("mutation,reason", [
    ("day", "DAILY_ARCHIVE_DAY_MISMATCH"),
    ("zip", "DAILY_INPUT_PIN_MISMATCH"),
    ("checksum", "DAILY_INPUT_PIN_MISMATCH"),
])

def test_one_archive_retry_recovers_after_source_catalog_io_failure(tmp_path, monkeypatch):
    day_ms = 1_704_067_200_000
    archive, day_ms, zip_pin, checksum_pin = archive_fixture(
        tmp_path / "retained", day_ms, rows=2)
    w = HistoricalWarehouse(tmp_path / "warehouse", reserve=0, test_root=True)
    original_write_once = w.write_once
    injected = [False]

    def fail_source_receipt_once(relative, raw):
        if relative == f"catalog/{zip_pin}.json" and not injected[0]:
            injected[0] = True
            raise OSError("injected source receipt publication failure")
        return original_write_once(relative, raw)

    monkeypatch.setattr(w, "write_once", fail_source_receipt_once)
    args = dict(source_day_ms=day_ms, expected_zip_sha256=zip_pin,
                expected_checksum_sha256=checksum_pin,
                observed_ms=day_ms + 2 * 86_400_000)
    with pytest.raises(OSError, match="injected source receipt publication failure"):
        import_one_retained(w, archive, **args)

    # The failure is visible: validated raw inputs and the atomically published
    # day shard may exist, but no source receipt or successful CLI result exists.
    assert injected[0]
    assert w.path(f"raw/{zip_pin}.zip").read_bytes() == archive.read_bytes()
    assert w.path(f"raw/{checksum_pin}.CHECKSUM").read_bytes() == archive.with_name(
        archive.name + ".CHECKSUM").read_bytes()
    assert not w.path(f"catalog/{zip_pin}.json").exists()
    assert list(w.path("bars").glob("????-??-??.sqlite"))

    # The controlled retry reuses identical source bytes, verifies the partial
    # state through the native importer, publishes the missing receipt and seals
    # the Registry/report without re-inserting rows or changing source bytes.
    monkeypatch.setattr(w, "write_once", original_write_once)
    recovered = import_one_retained(w, archive, **args)
    assert recovered["this_run"][0]["status"] == "ARCHIVE_IMPORTED"
    assert recovered["this_run"][0]["inserted_rows"] == 0
    assert recovered["this_run"][0]["duplicate_rows"] == 2
    assert recovered["this_run"][0]["conflicts"] == 0
    source = json.loads(w.path(f"catalog/{zip_pin}.json").read_bytes())
    assert source["schema"] == "aql.research.warehouse-source.v1"
    assert source["source_zip_sha256"] == zip_pin
    assert source["receipt_sha256"]
    assert recovered["warehouse_receipt_sha256"]
    assert w.path(f"receipts/{recovered['warehouse_receipt_sha256']}.json").is_file()
    registry = recovered["registry"]
    assert any(item["source_zip_sha256"] == zip_pin
               for item in registry["sources"])
    assert registry["physical_rows"] == 2


def test_daily_identity_mismatch_fails_before_warehouse_admission(tmp_path, mutation, reason):
    day_ms = 1_704_067_200_000
    archive, day_ms, zip_pin, checksum_pin = archive_fixture(tmp_path / "retained", day_ms, rows=2)
    w = HistoricalWarehouse(tmp_path / "warehouse", reserve=0, test_root=True)
    args = dict(source_day_ms=day_ms, expected_zip_sha256=zip_pin,
                expected_checksum_sha256=checksum_pin,
                observed_ms=day_ms + 2 * 86_400_000)
    if mutation == "day":
        args["source_day_ms"] += 86_400_000
    elif mutation == "zip":
        args["expected_zip_sha256"] = "0" * 64
    else:
        args["expected_checksum_sha256"] = "0" * 64
    with pytest.raises(ValueError, match=reason):
        import_one_retained(w, archive, **args)
    assert not list((tmp_path / "warehouse" / "raw").glob("*.zip"))
    assert not list((tmp_path / "warehouse" / "bars").glob("*.sqlite"))
