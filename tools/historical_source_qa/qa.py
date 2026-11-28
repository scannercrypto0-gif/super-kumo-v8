"""Offline validation and on-demand aggregation of bounded native Spot archives."""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import io
from itertools import islice
import json
from pathlib import Path
import re
from zipfile import ZipFile

MINUTE = 60_000
DAY = 1440 * MINUTE
FIXED = {"1m": MINUTE, "5m": 5 * MINUTE, "15m": 15 * MINUTE,
         "1h": 60 * MINUTE, "4h": 240 * MINUTE, "1d": DAY}
MARKET = ("BINANCE", "SPOT", "BTCUSDT", "BTC", "USDT", "UTC")
NUMBERS = ("open", "high", "low", "close", "base_volume", "quote_volume",
           "taker_base_volume", "taker_quote_volume")
MAX_ROWS = 31 * 1440
MAX_ZIP = 8 * 1024**2
MAX_CSV = 16 * 1024**2


def require(value, code):
    if not value:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def bounds(open_ms, interval):
    if interval in FIXED:
        start = open_ms // FIXED[interval] * FIXED[interval]
        return start, start + FIXED[interval]
    date = datetime.fromtimestamp(open_ms // 1000, timezone.utc)
    if interval == "1w":
        start = date.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=date.weekday())
        end = start + timedelta(days=7)
    elif interval == "1M":
        start = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1)
    else:
        raise ValueError("UNKNOWN_INTERVAL")
    return int(start.timestamp()) * 1000, int(end.timestamp()) * 1000


def decimal_field(text):
    require(len(text) <= 32 and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text), "DECIMAL_FIELD")
    return Decimal(text)


def read_small(path, limit):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink() and not getattr(part.lstat(), "st_file_attributes", 0) & 0x400,
                "LINKED_INPUT")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, "BYTE_BUDGET")
    return raw


def admit(zip_path, checksum_path, manifest, manifest_sha256):
    """Pin retained ZIP and checksum separately. The pin is caller-supplied evidence."""
    require(digest(manifest) == manifest_sha256, "MANIFEST_PIN")
    require(manifest["schema"] == "aql.historical-source-manifest.v1"
            and tuple(manifest["market"]) == MARKET, "MARKET_IDENTITY")
    require(manifest["evidence_class"] in ("TEST_ONLY", "RETROSPECTIVE_NON_PIT")
            and manifest["publisher_first_available_at_ms"] is None
            and manifest["pit"] == "NOT_ATTESTED", "FALSE_PIT")
    require(manifest["source_version"] and manifest["rights_ref"], "MISSING_RIGHTS_OR_VERSION")
    real = manifest["evidence_class"] == "RETROSPECTIVE_NON_PIT"
    require(not real or (manifest["rights_status"] == "VERIFIED_FOR_EXACT_USE"
                         and manifest["owner_authorization_ref"]), "RIGHTS_OR_OWNER_GATE")
    require(real or manifest["rights_status"] == "TEST_ONLY", "FIXTURE_RIGHTS")
    interval = manifest["native_interval"]
    require(interval in ("1m", "15m"), "NATIVE_INTERVAL")
    width = FIXED[interval]
    begin, end = manifest["start_ms"], manifest["end_exclusive_ms"]
    require(type(begin) is int and type(end) is int and begin % width == end % width == 0
            and 0 < end - begin <= MAX_ROWS * MINUTE, "WINDOW")
    cutoff = 1735689600000
    expected_unit = "ms" if end <= cutoff else "us" if begin >= cutoff else None
    require(expected_unit and manifest["timestamp_unit"] == expected_unit, "TIMESTAMP_UNIT")
    unit = 1 if expected_unit == "ms" else 1000
    zip_path = Path(zip_path)
    name = zip_path.name
    require(name.startswith(f"BTCUSDT-{interval}-") and name.endswith(".zip"), "ARCHIVE_NAME")
    raw = read_small(zip_path, MAX_ZIP)
    checksum = read_small(checksum_path, 1024)
    require(sha_bytes(raw) == manifest["archive_sha256"]
            and sha_bytes(checksum) == manifest["checksum_sha256"], "BYTE_PIN")
    require(checksum.decode("ascii").split() == [manifest["archive_sha256"], name], "CHECKSUM")
    member = name[:-4] + ".csv"
    with ZipFile(io.BytesIO(raw)) as archive:
        require(archive.namelist() == [member] and archive.getinfo(member).file_size <= MAX_CSV, "ZIP_MEMBER")
        with archive.open(member) as stream:
            rows = list(islice(csv.reader(io.TextIOWrapper(stream, encoding="ascii", newline="")),
                               MAX_ROWS + 1))
    require(len(rows) <= MAX_ROWS, "ROW_BUDGET")
    previous = None
    records = []
    for row in rows:
        require(len(row) == 12 and re.fullmatch(r"[0-9]{1,16}", row[0])
                and re.fullmatch(r"[0-9]{1,16}", row[6]), "NATIVE_ROW")
        start, close = int(row[0]), int(row[6])
        require(start % (width * unit) == 0 and close == start + width * unit - 1,
                "UTC_GRID_OR_UNIT")
        start //= unit
        require(begin <= start < end, "OUTSIDE_WINDOW")
        require(previous is None or start > previous, "DUPLICATE_OR_REORDERED")
        previous = start
        values = dict(zip(NUMBERS, (row[index] for index in (1, 2, 3, 4, 5, 7, 9, 10))))
        numbers = {key: decimal_field(text) for key, text in values.items()}
        require(0 < numbers["low"] <= min(numbers["open"], numbers["close"])
                <= max(numbers["open"], numbers["close"]) <= numbers["high"], "OHLC_RANGE")
        require(numbers["taker_base_volume"] <= numbers["base_volume"]
                and numbers["taker_quote_volume"] <= numbers["quote_volume"], "VOLUME_RANGE")
        require(re.fullmatch(r"[0-9]{1,16}", row[8]), "TRADE_COUNT")
        trades = int(row[8])
        require(trades or all(numbers[key] == 0 for key in NUMBERS[4:]), "NO_TRADE_VOLUME")
        record = dict(market=list(MARKET), product="BINANCE_VISION", interval=interval,
                      open_ms=start, end_exclusive_ms=start + width, is_final=True,
                      exchange_event_at_ms=None, received_at_ms=None, committed_at_ms=None,
                      publisher_first_available_at_ms=None, availability="UNKNOWN",
                      pit="NOT_ATTESTED",
                      evidence_class=manifest["evidence_class"], source_version=manifest["source_version"],
                      source_manifest_sha256=manifest_sha256, raw_row_sha256=digest(row),
                      missingness="OBSERVED_ZERO_TRADES" if trades == 0 else "OBSERVED",
                      actual_fill=None, trades=trades, **values)
        records.append({**record, "sha256": digest(record)})
    missing = sorted(set(range(begin, end, width)) - {r["open_ms"] for r in records})
    return dict(records=records, missing_opens_ms=missing, start_ms=begin, end_exclusive_ms=end,
                manifest_sha256=manifest_sha256, native_interval=interval)


def correction(old, new):
    """Keep versions separate. A changed slot requires quarantine and explicit review."""
    require(old["native_interval"] == new["native_interval"], "REVISION_SCOPE")
    old_rows = {r["open_ms"]: r for r in old["records"]}
    changed = [r["open_ms"] for r in new["records"] if r["open_ms"] in old_rows
               and r["raw_row_sha256"] != old_rows[r["open_ms"]]["raw_row_sha256"]]
    return dict(status="QUARANTINE_REVISION" if changed else "NO_OVERLAPPING_CHANGE",
                changed_opens_ms=changed, old_manifest=old["manifest_sha256"],
                new_manifest=new["manifest_sha256"])


def validate_envelope(record):
    """Validate the shared source fields on a historical or mock live kline."""
    require(record["market"] == list(MARKET) and record["interval"] in (*FIXED, "1w", "1M"),
            "MARKET_IDENTITY")
    require(type(record["open_ms"]) is int and type(record["end_exclusive_ms"]) is int
            and (record["open_ms"], record["end_exclusive_ms"]) ==
            bounds(record["open_ms"], record["interval"]), "ENVELOPE_GRID")
    require(type(record["is_final"]) is bool and record["actual_fill"] is None
            and record["publisher_first_available_at_ms"] is None
            and record["availability"] == "UNKNOWN" and record["pit"] == "NOT_ATTESTED",
            "UNSUPPORTED_EVIDENCE_PROMOTION")
    require(record["source_version"] and re.fullmatch(r"[0-9a-f]{64}", record["source_manifest_sha256"]),
            "ENVELOPE_SOURCE")
    clocks = [record[key] for key in ("exchange_event_at_ms", "received_at_ms", "committed_at_ms")]
    if record["product"] == "BINANCE_VISION":
        require(record["is_final"] and clocks == [None, None, None]
                and record["evidence_class"] in ("TEST_ONLY", "RETROSPECTIVE_NON_PIT"),
                "ARCHIVE_CLOCK")
    else:
        require(record["product"] in ("BINANCE_SPOT_WS", "BINANCE_SPOT_REST")
                and record["evidence_class"] == "TEST_ONLY", "OFFLINE_CONTRACT_ONLY")
        event, receive, commit = clocks
        require(all(x is None or type(x) is int and x >= 0 for x in clocks)
                and (commit is None or receive is not None and receive <= commit)
                and (not record["is_final"] or event is None or event >= record["end_exclusive_ms"] - 1),
                "MOCK_CLOCK")
    return record


def derive(admission, interval, cutoff_ms):
    require(admission["native_interval"] == "1m" and interval in (*FIXED, "1w", "1M")
            and interval != "1m", "NATIVE_1M_REQUIRED")
    require(type(cutoff_ms) is int, "CUTOFF_UNIT")
    groups = {}
    for row in admission["records"]:
        validate_envelope(row)
        require(row["sha256"] == digest({k: v for k, v in row.items() if k != "sha256"})
                and row["source_manifest_sha256"] == admission["manifest_sha256"]
                and row["product"] == "BINANCE_VISION" and row["interval"] == "1m" and row["is_final"] is True
                and row["end_exclusive_ms"] == row["open_ms"] + MINUTE
                and row["publisher_first_available_at_ms"] is None, "PARENT_ADMISSION")
        start, end = bounds(row["open_ms"], interval)
        groups.setdefault((start, end), []).append(row)
    result, withheld = [], []
    start, end = bounds(admission["start_ms"], interval)
    while start < admission["end_exclusive_ms"]:
        parents = groups.get((start, end), [])
        if end > cutoff_ms or [row["open_ms"] for row in parents] != list(range(start, end, MINUTE)):
            withheld.append(dict(open_ms=start, end_exclusive_ms=end,
                                 reason="AFTER_CUTOFF" if end > cutoff_ms else "INCOMPLETE_GRID"))
        else:
            with localcontext() as context:
                context.prec = 80
                values = {key: format(sum((Decimal(row[key]) for row in parents), Decimal(0)), "f")
                          for key in NUMBERS[4:]}
            values.update(open=parents[0]["open"], close=parents[-1]["close"],
                          high=format(max(Decimal(row["high"]) for row in parents), "f"),
                          low=format(min(Decimal(row["low"]) for row in parents), "f"))
            record = dict(market=list(MARKET), product="BINANCE_VISION", interval=interval,
                          open_ms=start, end_exclusive_ms=end, is_final=True,
                          evidence_class=parents[0]["evidence_class"], availability="UNKNOWN",
                          publisher_first_available_at_ms=None, actual_fill=None,
                          exchange_event_at_ms=None, received_at_ms=None, committed_at_ms=None,
                          pit="NOT_ATTESTED",
                          missingness="OBSERVED" if any(row["trades"] for row in parents)
                          else "OBSERVED_ZERO_TRADES",
                          source_version=parents[0]["source_version"],
                          recipe="UTC_NATIVE_1M_EXACT_DECIMAL_V1",
                          source_manifest_sha256=admission["manifest_sha256"],
                          parent_sha256=[row["sha256"] for row in parents],
                          trades=sum(row["trades"] for row in parents), **values)
            result.append({**record, "sha256": digest(record)})
        start, end = bounds(end, interval)
    return dict(records=result, withheld=withheld)


def compare_native_15m(derived, control):
    require(control["native_interval"] == "15m", "NATIVE_CONTROL")
    native = {r["open_ms"]: r for r in control["records"]}
    mismatches, missing = [], []
    matched = 0
    for row in derived["records"]:
        validate_envelope(row)
        require(row["sha256"] == digest({k: v for k, v in row.items() if k != "sha256"}), "DERIVED_SEAL")
        require(row["interval"] == "15m" and row["recipe"] == "UTC_NATIVE_1M_EXACT_DECIMAL_V1",
                "DERIVED_15M")
        peer = native.get(row["open_ms"])
        if peer is None:
            missing.append(row["open_ms"])
            continue
        validate_envelope(peer)
        require(peer["sha256"] == digest({k: v for k, v in peer.items() if k != "sha256"}), "CONTROL_SEAL")
        require(row["market"] == peer["market"] == list(MARKET)
                and row["evidence_class"] == peer["evidence_class"]
                and row["end_exclusive_ms"] == peer["end_exclusive_ms"], "CONTROL_IDENTITY")
        fields = [key for key in NUMBERS if Decimal(row[key]) != Decimal(peer[key])]
        if row["trades"] != peer["trades"]:
            fields.append("trades")
        if fields:
            mismatches.append(dict(open_ms=row["open_ms"], fields=fields))
        else:
            matched += 1
    return dict(compared=matched + len(mismatches), matched=matched,
                missing_control=missing, mismatches=mismatches,
                withheld_derived=derived["withheld"],
                status="MATCH" if matched and not (missing or mismatches or derived["withheld"])
                else "INCOMPLETE_OR_MISMATCH")
