"""Bounded read-only native source diagnosis; no candle correction or skipping.

The admission validator is intentionally unchanged. Quarantine contains a
reference/evidence record, preserving original ZIP and CHECKSUM bytes in raw.
"""
import argparse
import csv
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import time
from zipfile import ZipFile

from .engine import HistoricalWarehouse, parse_archive, DAY, MAX_CSV
from .source import KEY, MAX_ZIP, archive_window
from .storage import canonical, need, seal

SEPT_KEY = 'data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2017-09.zip'
SEPT_PIN = 'b4e525fa0549688dca9e09cc24093f50526db2a255d03961791da3bfd7c24d81'
CHECKSUM_PIN = '50b17e0903e8f657910c08b76b91fddede36fb8584404ff0bebdde627373f683'
AUGUST_PIN = '4f96569190147d64b7ce55f6760dc3e7962aeb3e209c969b200200e3d7045e70'


def _finite_nonnegative(value):
    try:
        number = Decimal(value)
        return number.is_finite() and number >= 0
    except InvalidOperation:
        return False


def diagnose_archive(raw, checksum, key, *, observed_ms):
    """Invoke real admission first; independently localize its native-row error."""
    need(len(raw) <= MAX_ZIP and len(checksum) <= 512, 'DIAGNOSTIC_INPUT_BOUND')
    try:
        projected, meta = parse_archive(raw, checksum, key, observed_ms)
    except (ValueError, InvalidOperation) as exc:
        error = str(exc)
    else:
        return dict(status='STRICT_NATIVE_SOURCE_ACCEPTED', source_key=key,
                    source_zip_sha256=seal(raw), checksum_sha256=seal(checksum),
                    rows=len(projected), **meta)
    base = dict(status='STRICT_NATIVE_SOURCE_REJECTED', source_key=key,
                source_zip_sha256=seal(raw), checksum_sha256=seal(checksum),
                validator_error=error, trading_authority='NONE',
                source_class='RETROSPECTIVE_NON_PIT', rows_imported=0)
    # Never inspect arbitrary ZIP members if outer integrity/safety failed.
    if error not in ('NATIVE_TIME_OR_MARKET_FIELDS', 'NATIVE_MARKET_FIELDS',
                     'NATIVE_DUPLICATE_OR_ORDER', 'PRICE_POSITIVE_REQUIRED',
                     'INVALID_DECIMAL', 'OHLC_INVALID'):
        return base
    with ZipFile(BytesIO(raw)) as archive:
        member = archive.read(archive.infolist()[0])
    need(len(member) <= MAX_CSV, 'DIAGNOSTIC_MEMBER_BOUND')
    start, end = archive_window(key)
    unit = 1000 if start >= 1735689600000 else 1
    failures, previous, count = [], None, 0
    gaps = []
    for number, row in enumerate(csv.reader(StringIO(member.decode('utf-8-sig')), strict=True), 1):
        count += 1
        need(number <= 44640 and len(row) == 12, 'NATIVE_ROW_BOUND_OR_SCHEMA')
        bad = []
        try:
            opened, closed, trades = int(row[0]), int(row[6]), int(row[8])
        except ValueError:
            bad.append(dict(predicate='integer_native_time_and_trade_fields', fields=[0, 6, 8]))
            opened = closed = trades = None
        if opened is not None:
            if opened % (60000*unit):
                bad.append(dict(field=0, value=row[0], predicate='open_time_minute_grid'))
            if closed != opened+60000*unit-1:
                bad.append(dict(field=6, value=row[6], expected=str(opened+60000*unit-1),
                                delta_native_units=closed-(opened+60000*unit-1),
                                predicate='close_time_equals_open_plus_minute_minus_one'))
            if not start*unit <= opened < end*unit:
                bad.append(dict(field=0, value=row[0], predicate='archive_period_membership'))
            if trades < 0:
                bad.append(dict(field=8, value=row[8], predicate='nonnegative_trade_count'))
            if previous is not None:
                if opened <= previous:
                    bad.append(dict(field=0, value=row[0], predicate='strictly_increasing_open_times'))
                elif opened > previous+60000*unit:
                    gaps.append([previous//unit+60000, opened//unit])
            previous = opened
        for index in (7, 9, 10, 11):
            if not _finite_nonnegative(row[index]):
                bad.append(dict(field=index, value=row[index], predicate='finite_nonnegative_auxiliary'))
        for index in (1, 2, 3, 4, 5):
            if not _finite_nonnegative(row[index]) or (index != 5 and Decimal(row[index]) == 0):
                bad.append(dict(field=index, value=row[index], predicate='valid_price_or_volume'))
        if bad:
            failures.append(dict(native_csv_line=number, open_time=row[0], predicates=bad))
    base.update(member_sha256=seal(member), member_bytes=len(member), source_rows=count,
                failed_rows=len(failures), first_failure=failures[0] if failures else None,
                failures=failures, source_open_time_gaps=gaps)
    return base


def _august_snapshot(warehouse):
    hashes, rows = {}, 0
    for path in sorted(warehouse.path('bars').glob('2017-08-??.sqlite')):
        hashes[path.name] = seal(path.read_bytes())
        from datetime import datetime, timezone
        day = int(datetime.strptime(path.stem, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()*1000)
        rows += len(warehouse._existing(day))
    return dict(rows=rows, shard_sha256=hashes)


def resume_or_block(warehouse, *, observed_ms, authorization_file=None,
                    archive_limit=3, expected_source_pin=SEPT_PIN, task_inspection=None):
    """Diagnose retained September; never repeat a known-invalid backfill.

    If publisher actually replaces the original with a strictly valid archive,
    an operator must supply its separately checked new pin. Existing authorization
    is reused only after this gate succeeds. Current known source always blocks.
    """
    need(warehouse.root.is_dir() and warehouse.path('catalog/warehouse-policy.json').is_file(),
         'EXISTING_WAREHOUSE_REQUIRED_NO_REBUILD')
    with warehouse.writer():
        before = _august_snapshot(warehouse)
        need(before['rows'] == 21360, 'ACCEPTED_AUGUST_21360_BASELINE_REQUIRED')
        august = warehouse.path(f'raw/{AUGUST_PIN}.zip')
        need(august.is_file() and august.stat().st_size <= MAX_ZIP
             and seal(august.read_bytes()) == AUGUST_PIN, 'ACCEPTED_AUGUST_SOURCE_PIN_REQUIRED')
        need(len(expected_source_pin) == 64 and all(c in '0123456789abcdef' for c in expected_source_pin),
             'SEPTEMBER_EXTERNAL_PIN_REQUIRED')
        source = warehouse.path(f'raw/{expected_source_pin}.zip')
        need(source.is_file() and source.stat().st_size <= MAX_ZIP, 'RETAINED_SEPTEMBER_SOURCE_REQUIRED')
        checksum = None
        for p in warehouse.path('raw').glob('*.CHECKSUM'):
            need(p.stat().st_size <= 512, 'CHECKSUM_INPUT_BOUND')
            candidate = p.read_bytes()
            if candidate.split()[:1] == [expected_source_pin.encode()]:
                checksum = candidate
                break
        need(checksum is not None and seal(source.read_bytes()) == expected_source_pin,
             'RETAINED_SEPTEMBER_ZIP_CHECKSUM_REQUIRED')
        diagnostic = diagnose_archive(source.read_bytes(), checksum, SEPT_KEY, observed_ms=observed_ms)
        after = _august_snapshot(warehouse)
        need(before == after, 'ACCEPTED_AUGUST_CHANGED')
        result = dict(schema='aql.warehouse.september-recovery.v1', diagnostic=diagnostic,
                      august_unchanged=True, august=after, task_inspection=task_inspection,
                      warehouse=warehouse.report(), scheduler_changes=0,
                      source_class='RETROSPECTIVE_NON_PIT', trading_authority='NONE')
        if diagnostic['status'] != 'STRICT_NATIVE_SOURCE_ACCEPTED':
            result.update(status='BLOCKED_INVALID_PUBLISHER_SOURCE', resume_attempted=False,
                          required_owner_action='PROVIDE_PUBLISHER_CORRECTED_SOURCE_AND_CHECKSUM_OR_APPROVE_EXPLICIT_VERSIONED_CORRECTION_POLICY')
            warehouse.document('quarantine', dict(schema='aql.warehouse.source-quarantine.v1',
                disposition='REJECTED_REFERENCE_RAW_PRESERVED', **diagnostic))
            warehouse.document('receipts', result)
            return result
        need(authorization_file is not None, 'EXISTING_SOURCE_AUTHORIZATION_REQUIRED')
    # Preserve existing source acquisition, budget and resume implementation.
    from .source import VisionHTTP
    from .runner import run
    authority = json.loads(Path(authorization_file).read_bytes())
    result = run(warehouse, VisionHTTP(authority=authority), now_ms=observed_ms,
                 archive_limit=archive_limit)
    result['august_unchanged'] = _august_snapshot(warehouse) == before
    need(result['august_unchanged'], 'ACCEPTED_AUGUST_CHANGED')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('E:/ATLAS/DataWarehouse'))
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--task-inspection', type=Path)
    parser.add_argument('--archive-limit', type=int, default=3)
    parser.add_argument('--source-pin', default=SEPT_PIN)
    args = parser.parse_args()
    need(1 <= args.archive_limit <= 3, 'BOUNDED_RECOVERY_LIMIT')
    inspection = None
    raw_inspection = os.environ.get('ATLAS_WAREHOUSE_RECOVERY_TASK_INSPECTION')
    if raw_inspection:
        need(len(raw_inspection.encode()) <= 65536, 'TASK_INSPECTION_BOUND')
        inspection = json.loads(raw_inspection)
    if args.task_inspection:
        need(args.task_inspection.stat().st_size <= 65536, 'TASK_INSPECTION_BOUND')
        inspection = json.loads(args.task_inspection.read_bytes())
    result = resume_or_block(HistoricalWarehouse(args.root), observed_ms=time.time_ns()//1000000,
        authorization_file=args.authorization, archive_limit=args.archive_limit,
        expected_source_pin=args.source_pin, task_inspection=inspection)
    print(json.dumps(result, sort_keys=True, indent=2))
    if result.get('status') == 'BLOCKED_INVALID_PUBLISHER_SOURCE' or result.get('failures'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
