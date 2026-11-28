"""Generated fixtures only for the portable parser and daily readback."""
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from research_wp_r0.aql_native_binance_zip_v1 import NativeZipError, parse_binance_zip
from tools.atlas_saved_daily_health import DAY_MS, POLL_UTC_MS, read_daily_health


@pytest.mark.parametrize("start,stem,unit", [
    (1720051200000, "BTCUSDT-15m-2024-07-04", 1),
    (1735689600000, "BTCUSDT-15m-2025-01-01", 1000),
])
@pytest.mark.parametrize("close_offset", [0, 1])
def test_native_daily_zip_final_boundary(start, stem, unit, close_offset):
    width = 900_000
    records = []
    for i in range(96):
        opened = (start + i * width) * unit
        closed = opened + width * unit - 1 + (close_offset if i == 10 else 0)
        records.append(f"{opened},101,102,100,101,4,{closed},404,3,2,202,0\n")
    csv = "".join(records).encode()
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(stem + ".csv", csv)
    raw = buffer.getvalue()
    raw_sha = sha256(raw).hexdigest()
    checksum = f"{raw_sha}  {stem}.zip\n"
    meta = dict(kind="NATIVE_BINANCE_KLINES_ZIP", archive_name=stem + ".zip", archive_sha256=raw_sha,
                member_name=stem + ".csv", member_sha256=sha256(csv).hexdigest(),
                checksum_file_sha256=sha256(checksum.encode()).hexdigest(), checksum_text=checksum)
    spec = dict(symbol="BTCUSDT", exchange="BINANCE", market="SPOT", interval="15m",
                start_ms=start, end_exclusive_ms=start + DAY_MS)

    def materialize(spec, opened, closed, values, receipt_ms):
        return opened, closed, receipt_ms

    if close_offset:
        with pytest.raises(NativeZipError, match="NATIVE_ZIP_TIMESTAMP_OR_MARKET_FIELDS"):
            parse_binance_zip(raw, spec, meta, make_bar=materialize)
    else:
        bars, origin = parse_binance_zip(raw, spec, meta, make_bar=materialize)
        assert len(bars) == 96
        assert bars[0] == (start, start + width - 1, None)
        assert bars[-1][1] == start + DAY_MS - 1
        assert origin[-1]["historical_known_at_ms"] is None


@pytest.mark.parametrize("completed", [False, True])
def test_daily_health_is_pinned_and_source_age_is_separate(tmp_path, completed):
    now = 20_000 * DAY_MS + POLL_UTC_MS
    snapshot = dict(schema="aql.recurring-runtime.health.v1",
                    source_mode="AUTHORIZED_RETAINED_ARCHIVE", source_cadence="DAILY_UTC",
                    freshness_limit_ms=DAY_MS + 30_000, market_feed_health="NOT_MEASURED",
                    trading_authority="NONE", current_entry="NO_CURRENT_ENTRY",
                    observed_at_ms=now, tick_age_ms=0 if completed else None,
                    next_check_ms=now + 60_000,
                    cycle_evidence="RECENT_RESEARCH_RECEIPT" if completed else "WAIT_FOR_SOURCE",
                    last_success=dict(source_day_ms=(19_998 * DAY_MS)) if completed else None)
    path = tmp_path / "health.json"
    raw = json.dumps(snapshot).encode()
    path.write_bytes(raw)
    pin = sha256(raw).hexdigest()
    report = read_daily_health(path, pin, now)
    assert report == read_daily_health(path, pin, now)
    if completed:
        assert report["tick_freshness"] == "RECENT" and report["source_freshness"] == "STALE"
    else:
        assert report["cycle_evidence"] == "WAIT_FOR_SOURCE"
        assert read_daily_health(path, pin, now + 90_001)["cycle_evidence"] == "LAST_TICK_STALE"
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="DAILY_HEALTH_PIN"):
        read_daily_health(path, pin, now)
