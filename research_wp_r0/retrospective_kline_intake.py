"""P0 Research Milestone 01: immutable Binance SPOT kline source intake.

Retrospective archive data is NEVER promoted to confirmed point-in-time custody.
No network access, trading, signals, or OOS evaluation occurs here.
"""
import csv
import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile, BadZipFile


@dataclass(frozen=True)
class RetrospectiveKlineReceipt:
    archive_sha256: str
    symbol: str
    interval_ms: int
    first_open_ms: int
    last_open_ms: int
    count: int
    gap_count: int
    availability: str = "RETROSPECTIVE_NOT_CONFIRMED"


def inspect_binance_spot_zip(path, *, expected_sha256, symbol="BTCUSDT",
                             interval_ms=60000):
    """Verify independently recorded ZIP hash and return canonical OHLCV rows.

    Binance spot archive timestamps from 2025 onward are microseconds.
    Historical exchange publication/ingestion timestamps are NOT known.
    Reject missing/duplicate candles; caller may explicitly allow gaps for
    diagnostic inspection, but not for execution acceptance.
    """
    if (type(expected_sha256) is not str or len(expected_sha256) != 64 or
        any(ch not in "0123456789abcdef" for ch in expected_sha256)):
        raise ValueError("Independent SHA256 required")
    if symbol != "BTCUSDT" or interval_ms != 60000:
        raise ValueError("Only BTCUSDT 1m archive identity supported")
    if type(interval_ms) is not int or interval_ms <= 0:
        raise ValueError("Invalid interval")
    archive_path = Path(path)
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("Regular archive file required")
    if archive_path.stat().st_size > 110_000_000:
        raise ValueError("Archive exceeds bounded input size")
    raw = archive_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != expected_sha256:
        raise ValueError("Archive checksum mismatch")
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            members = [m for m in z.infolist() if not m.is_dir()]
            if len(members) != 1 or not members[0].filename.endswith(".csv"):
                raise ValueError("Exactly one CSV required")
            if not members[0].filename.startswith("BTCUSDT-1m-"):
                raise ValueError("Archive member market identity mismatch")
            if members[0].file_size > 100_000_000:
                raise ValueError("Archive exceeds bounded CSV size")
            if members[0].compress_size == 0 or members[0].file_size > 100 * members[0].compress_size:
                raise ValueError("Excessive archive expansion ratio")
            csv_bytes = z.read(members[0])
    except BadZipFile as exc:
        raise ValueError("Invalid ZIP") from exc
    rows = []
    previous = None
    gaps = 0
    for record in csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))):
        if not record:
            continue
        if len(record) != 12:
            raise ValueError("Binance SPOT klines require 12 columns")
        opening, closing = int(record[0]), int(record[6])
        # Distinguish millisecond and microsecond timestamps explicitly.
        divisor = 1000 if opening >= 10**14 else 1
        if (closing >= 10**14) != (opening >= 10**14):
            raise ValueError("Mixed timestamp precision")
        if divisor == 1000 and (opening % 1000 != 0 or closing % 1000 != 999):
            raise ValueError("Microsecond candle boundary misaligned")
        opening //= divisor
        closing //= divisor
        if closing != opening + interval_ms - 1 or opening % interval_ms:
            raise ValueError("Invalid candle grid")
        prices = tuple(float(record[i]) for i in (1, 2, 3, 4, 5))
        op, high, low, close, volume = prices
        if (not all(math.isfinite(v) for v in prices) or
            min(op, high, low, close) <= 0 or volume < 0 or
            high < max(op, low, close) or low > min(op, close)):
            raise ValueError("Invalid OHLCV")
        if previous is not None:
            if opening <= previous:
                raise ValueError("Duplicate or unordered candle")
            step = opening - previous
            if step % interval_ms:
                raise ValueError("Off-grid candle")
            gaps += step // interval_ms - 1
        rows.append((opening, closing, op, high, low, close, volume))
        previous = opening
    if not rows:
        raise ValueError("Empty archive")
    receipt = RetrospectiveKlineReceipt(sha, symbol, interval_ms,
                                       rows[0][0], rows[-1][0],
                                       len(rows), gaps)
    return receipt, tuple(rows)
