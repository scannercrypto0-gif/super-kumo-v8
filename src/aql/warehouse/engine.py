"""Original ZIP -> validated daily shards -> exact research read interfaces."""
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
from zipfile import ZipFile, BadZipFile, ZIP_STORED, ZIP_DEFLATED

from aql.research_bar_store import ResearchBarStore
from aql.research_timeframes import project_finalized_1m, WIDTHS, MINUTE, WEEK_ORIGIN_MS
from .storage import Warehouse, SHARD_CAP, canonical, need, seal
from .source import KEY, MAX_ZIP, archive_window

DAY = 86_400_000
MAX_CSV = 32 * 1024 * 1024


def parse_archive(raw, checksum, key, observed_ms):
    m = KEY.fullmatch(key)
    need(m is not None and len(raw) <= MAX_ZIP, 'ARCHIVE_BOUND_OR_KEY')
    start, end = archive_window(key)
    need(type(observed_ms) is int and observed_ms >= end, 'INCOMPLETE_SOURCE_PERIOD')
    name = m.group(2)
    check = re.fullmatch(rb'([a-fA-F0-9]{64})[ \t]+\*?' + re.escape(name.encode()) + rb'\s*', checksum)
    need(check is not None and check[1].decode().lower() == seal(raw), 'PUBLISHER_CHECKSUM_MISMATCH')
    from io import BytesIO
    try:
        with ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            need(len(entries) == 1, 'ZIP_MEMBER_CENSUS')
            item = entries[0]
            need(item.filename == name[:-4] + '.csv' and not item.is_dir()
                 and not stat.S_ISLNK(item.external_attr >> 16) and not item.flag_bits & 1
                 and item.compress_type in (ZIP_STORED, ZIP_DEFLATED)
                 and 0 < item.file_size <= MAX_CSV, 'ZIP_MEMBER_UNSAFE')
            member = archive.read(item)
    except (BadZipFile, RuntimeError, EOFError) as exc:
        raise ValueError('ZIP_CORRUPT') from exc
    unit = 1000 if start >= 1735689600000 else 1
    rows, previous = [], None
    for number, record in enumerate(csv.reader(StringIO(member.decode('utf-8-sig')), strict=True), 1):
        need(number <= 44640 and len(record) == 12, 'NATIVE_ROW_BOUND_OR_SCHEMA')
        try:
            opened, closed, trades = int(record[0]), int(record[6]), int(record[8])
            auxiliary = [Decimal(record[i]) for i in (7, 9, 10, 11)]
        except (ValueError, InvalidOperation) as exc:
            raise ValueError('NATIVE_MARKET_FIELDS') from exc
        need(opened % (MINUTE * unit) == 0 and closed == opened + MINUTE * unit - 1
             and start * unit <= opened < end * unit and trades >= 0
             and all(x.is_finite() and x >= 0 for x in auxiliary), 'NATIVE_TIME_OR_MARKET_FIELDS')
        opened //= unit
        need(previous is None or opened > previous, 'NATIVE_DUPLICATE_OR_ORDER')
        previous = opened
        # Native line checksum survives cross-archive row reuse; original bytes
        # and line mapping remain in each source receipt. Canonical times in ms.
        normalized = [str(opened), *record[1:6], str(opened + MINUTE - 1), *record[7:]]
        need(all(Decimal(record[i]).is_finite() and Decimal(record[i]) > 0
                 for i in (1, 2, 3, 4)), 'PRICE_POSITIVE_REQUIRED')
        row = dict(symbol='BTCUSDT', interval='1m', open_ms=opened, final=True,
                   **dict(zip(('o', 'h', 'l', 'c', 'v'), record[1:6])),
                   source_sha256=seal(canonical(normalized)), available_at_ms=observed_ms)
        projected = project_finalized_1m([row], '1m', source_class='RETROSPECTIVE_NON_PIT')
        rows.append(projected)
    need(rows, 'EMPTY_ARCHIVE')
    return rows, dict(member_sha256=seal(member), member_bytes=len(member),
                      period_start_ms=start, period_end_ms=end,
                      timestamp_unit='us' if unit == 1000 else 'ms')


class HistoricalWarehouse(Warehouse):
    def _shard_name(self, opened):
        day = datetime.fromtimestamp(opened // DAY * DAY / 1000, timezone.utc).strftime('%Y-%m-%d')
        return f'bars/{day}.sqlite'

    def _existing(self, opened):
        path = self.path(self._shard_name(opened))
        if not path.exists():
            return []
        need(path.stat().st_size <= SHARD_CAP, 'SHARD_BOUND')
        # Use existing store's digest verifier without invoking migrations/WAL.
        store = object.__new__(ResearchBarStore)
        store.path = path
        store.db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            keys = store.db.execute('SELECT open_ms FROM finalized_bars ORDER BY open_ms').fetchall()
            need(len(keys) <= 1440, 'SHARD_ROW_BOUND')
            rows = [store.read('BTCUSDT', '1m', x[0]) for x in keys]
            need(all(x is not None and self._shard_name(x['open_ms']) == self._shard_name(opened)
                     and x['source_class'] == 'RETROSPECTIVE_NON_PIT' for x in rows), 'SHARD_IDENTITY')
            return rows
        finally:
            store.close()

    def import_archive(self, raw, checksum, key, *, observed_ms):
        need(self.locked, 'WRITER_LOCK_REQUIRED')
        rows, meta = parse_archive(raw, checksum, key, observed_ms)
        pin = seal(raw)
        receipt_rel = f'catalog/{pin}.json'
        old_receipt = self.path(receipt_rel)
        if old_receipt.exists():
            old = json.loads(old_receipt.read_bytes())
            need(old['source_zip_sha256'] == pin and old['key'] == key
                 and old.get('receipt_sha256') == seal(canonical({k:v for k,v in old.items()
                     if k != 'receipt_sha256'})), 'SOURCE_CATALOG_CONFLICT')
            # Replay verifies retained original and every requested row.
        grouped = {}
        for row in rows:
            grouped.setdefault(row['open_ms'] // DAY * DAY, []).append(row)
        plans, duplicate_count = [], 0
        for day, batch in grouped.items():
            existing = {x['open_ms']: x for x in self._existing(day)}
            additions = []
            for row in batch:
                old = existing.get(row['open_ms'])
                if old is not None:
                    need(old['constituent_sha256'] == row['constituent_sha256']
                         and all(old[k] == row[k] for k in ('o', 'h', 'l', 'c', 'v')),
                         'SOURCE_BAR_CONFLICT')
                    duplicate_count += 1
                else:
                    additions.append(row)
            plans.append((day, additions))
        # Validate all source conflicts BEFORE committing any shards.
        self.write_once(f'raw/{pin}.zip', raw)
        self.write_once(f'raw/{seal(checksum)}.CHECKSUM', checksum)
        for day, additions in plans:
            if not additions:
                continue
            self.budget(3 * SHARD_CAP)  # stage + bounded DELETE journal + safety
            target = self.path(self._shard_name(day))
            staging = self.path('bars/staging.sqlite')
            for suffix in ('', '-journal', '-wal', '-shm'):
                scratch = self.path('bars/staging.sqlite' + suffix)
                if scratch.exists():
                    need(scratch.stat().st_nlink == 1, 'SCRATCH_HARDLINK_DENIED')
                    scratch.unlink()
            if target.exists():
                shutil.copyfile(target, staging)
            store = ResearchBarStore(staging)
            try:
                store.db.execute('PRAGMA journal_mode=DELETE')
                store.db.execute('PRAGMA synchronous=FULL')
                page = store.db.execute('PRAGMA page_size').fetchone()[0]
                store.db.execute(f'PRAGMA max_page_count={SHARD_CAP // page}')
                store.insert_batch(additions)
                need(store.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'SHARD_INTEGRITY')
            finally:
                store.close()
            with staging.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(staging, target)
        body = dict(schema='aql.research.warehouse-source.v1', key=key,
                    source_zip_sha256=pin, source_zip_bytes=len(raw),
                    checksum_sha256=seal(checksum), rows=len(rows),
                    first_open_ms=rows[0]['open_ms'], last_open_ms=rows[-1]['open_ms'],
                    observed_ms=observed_ms, source_class='RETROSPECTIVE_NON_PIT',
                    historical_known_at_ms=None, publisher_integrity='ZIP_CHECKSUM_MATCH',
                    independent_origin_attestation='NOT_ATTESTED', trading_authority='NONE', **meta)
        body['receipt_sha256'] = seal(canonical(body))
        # Replays retain original observation time and receipt bytes.
        if not old_receipt.exists():
            self.write_once(receipt_rel, canonical(body))
        else:
            need(seal(self.path(f'raw/{pin}.zip').read_bytes()) == pin, 'RETAINED_RAW_CORRUPT')
        result = dict(status='ARCHIVE_IMPORTED', key=key, source_sha256=pin,
                      source_rows=len(rows), inserted_rows=sum(len(x[1]) for x in plans),
                      duplicate_rows=duplicate_count, conflicts=0, source_class='RETROSPECTIVE_NON_PIT',
                      trading_authority='NONE')
        self.document('receipts', result)
        return result

    def query(self, interval, start_ms, end_ms, *, cutoff_ms, max_bars=10080):
        need(interval in WIDTHS and all(type(x) is int and x >= 0
             for x in (start_ms, end_ms, cutoff_ms)) and start_ms < end_ms,
             'QUERY_INVALID')
        width = WIDTHS[interval] * MINUTE
        origin = WEEK_ORIGIN_MS if interval == '1w' else 0
        need((start_ms - origin) % width == 0 and (end_ms - start_ms) % width == 0
             and 0 < (end_ms - start_ms) // width <= max_bars <= 10080
             and end_ms <= cutoff_ms, 'QUERY_BOUND_OR_FUTURE')
        cache = {}
        result = []
        for opened in range(start_ms, end_ms, width):
            source = []
            for t in range(opened, opened + width, MINUTE):
                day = t // DAY
                if day not in cache:
                    cache[day] = {r['open_ms']: r for r in self._existing(t)}
                row = cache[day].get(t)
                need(row is not None, 'SOURCE_GAP')
                need(row['available_at_ms'] <= cutoff_ms, 'SOURCE_UNAVAILABLE_AT_CUTOFF')
                source.append(dict(symbol='BTCUSDT', interval='1m', open_ms=t, final=True,
                                   **{k: row[k] for k in ('o', 'h', 'l', 'c', 'v')},
                                   source_sha256=row['constituent_sha256'][0],
                                   available_at_ms=row['available_at_ms']))
            result.append(project_finalized_1m(source, interval, source_class='RETROSPECTIVE_NON_PIT'))
            # Queries spanning years keep <=8 daily shards in memory.
            if len(cache) > 8:
                cache = {k: v for k, v in cache.items() if k >= opened // DAY}
        return result

    def report(self):
        segments, count, previous, gaps = [], 0, None, []
        first = last = None
        source_bytes = csv_bytes = 0
        for p in sorted(self.path('bars').glob('????-??-??.sqlite')):
            day = int(datetime.strptime(p.stem, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)
            for row in self._existing(day):
                t = row['open_ms']
                if first is None:
                    first = t
                if previous is not None and t != previous + MINUTE:
                    gaps.append([previous + MINUTE, t])
                    segments.append((segment_start, previous + MINUTE))
                    segment_start = t
                elif previous is None:
                    segment_start = t
                count += 1
                previous = last = t
        if previous is not None:
            segments.append((segment_start, previous + MINUTE))
        coverage = {}
        for interval, size in WIDTHS.items():
            width = size * MINUTE
            origin = WEEK_ORIGIN_MS if interval == '1w' else 0
            coverage[interval] = sum(max(0, (b - origin) // width -
                ((a - origin + width - 1) // width)) for a, b in segments)
        catalog = []
        for p in self.path('catalog').glob('*.json'):
            if re.fullmatch(r'[0-9a-f]{64}', p.stem):
                record = json.loads(p.read_bytes())
                if record.get('schema') == 'aql.research.warehouse-source.v1':
                    need(record['source_zip_sha256'] == p.stem and
                         record.get('receipt_sha256') == seal(canonical({k:v for k,v in record.items()
                             if k != 'receipt_sha256'})), 'CATALOG_IDENTITY')
                    catalog.append(record)
                    source_bytes += record['source_zip_bytes']
                    csv_bytes += record['member_bytes']
        boundary_missing = []
        for record in catalog:
            if record['first_open_ms'] > record['period_start_ms']:
                boundary_missing.append([record['period_start_ms'], record['first_open_ms']])
            if record['last_open_ms'] + MINUTE < record['period_end_ms']:
                boundary_missing.append([record['last_open_ms'] + MINUTE, record['period_end_ms']])
        return dict(schema='aql.research.warehouse-report.v1', root=str(self.root),
                    stored_first_open_ms=first, stored_last_open_ms=last, one_minute_rows=count,
                    available_complete_projections=coverage, internal_gaps=gaps,
                    archive_count=len(catalog), archive_boundary_missing_ranges=boundary_missing,
                    source_zip_bytes=source_bytes,
                    source_csv_bytes=csv_bytes, stored_bytes=self.used(),
                    cap_bytes=self.cap, reserve_bytes=self.reserve,
                    coverage='EMPTY' if not count else 'OBSERVED_STORED_RANGE_ONLY',
                    source_class='RETROSPECTIVE_NON_PIT', forward_lane='SEPARATE_UNMODIFIED',
                    pit_oos='NOT_ATTESTED', trading_authority='NONE', orders_enabled=False)
