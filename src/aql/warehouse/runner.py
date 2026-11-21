"""Single resumable backfill/daily catch-up runner. No scheduler or WS mutation."""
import argparse
import json
from pathlib import Path
import time
import sqlite3

from .engine import HistoricalWarehouse, DAY
from .source import VisionHTTP
from .storage import canonical, need, seal


def catalog_index(warehouse):
    index = {}
    for p in warehouse.path('catalog').glob('*.json'):
        if len(p.stem) != 64:
            continue
        need(p.stat().st_size <= 8*1024*1024, 'CATALOG_OBJECT_BOUND')
        c = json.loads(p.read_bytes())
        if c.get('schema') != 'aql.research.warehouse-source.v1':
            continue
        need(c.get('source_zip_sha256') == p.stem and c.get('receipt_sha256') ==
             seal(canonical({k:v for k,v in c.items() if k != 'receipt_sha256'})),
             'SOURCE_CATALOG_INTEGRITY')
        index.setdefault(c['key'], []).append(c)
    return index


def admitted_gap_ranges(warehouse, index):
    gaps = []
    for records in index.values():
        for c in records:
            if c.get('source_kind') != 'OWNER_AUTHORIZED_DERIVATIVE':
                continue
            from .september_correction import verify_derivative
            raw = warehouse.path(f"raw/{c['source_zip_sha256']}.zip")
            checksum = warehouse.path(f"raw/{c['checksum_sha256']}.CHECKSUM")
            need(raw.stat().st_size <= 64*1024*1024 and checksum.stat().st_size <= 512,
                 'DERIVATION_SOURCE_BOUND')
            lineage = verify_derivative(warehouse,raw.read_bytes(),checksum.read_bytes(),
                                        c['key'],c.get('derivation'))
            gaps.extend(lineage['missing_open_time_ranges'])
    return sorted(gaps)


def period_covered(warehouse, start, end, *, inception=None, permitted_gaps=()):
    """Fast membership check; final report still verifies every bar digest.

    Only the source's proven pre-inception prefix and the exactly verified
    owner-authorized gap can be excluded from expected minute membership.
    """
    first = max(start, inception) if inception is not None else start
    for day in range(start//DAY*DAY, end, DAY):
        expected = {t for t in range(max(first,day),min(end,day+DAY),60000)
                    if not any(a <= t < b for a,b in permitted_gaps)}
        if not expected:
            continue
        path = warehouse.path(warehouse._shard_name(day))
        if not path.exists():
            return False
        con = sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            keys = con.execute('SELECT symbol,interval,open_ms FROM finalized_bars').fetchall()
        finally:
            con.close()
        need(len(keys) <= 1440 and all(x[:2] == ('BTCUSDT','1m') and type(x[2]) is int
             and x[2] % 60000 == 0 and day <= x[2] < day+DAY for x in keys)
             and len({x[2] for x in keys}) == len(keys), 'SHARD_ROW_BOUND_OR_IDENTITY')
        if not expected.issubset({x[2] for x in keys}):
            return False
    return True


def run(warehouse, source, *, now_ms, archive_limit=12, daily_only=False, recheck_publisher=False, progress=None, clock_ms=None):
    need(type(archive_limit) is int and 1 <= archive_limit <= 10000, 'ARCHIVE_RUN_BOUND')
    with warehouse.writer():
        listing = source.discover(now_ms=now_ms)
        snapshot = dict(schema='aql.warehouse.source-listing.v1', observed_ms=now_ms,
                        archives=listing, authority=source.authority,
                        source_class='RETROSPECTIVE_NON_PIT')
        warehouse.document('catalog', snapshot)
        if progress: progress(dict(event='SOURCE_LISTING_READY',archive_objects=len(listing),
            first_period_ms=min(r['start_ms'] for r in listing),
            latest_complete_period_end_ms=max(r['end_ms'] for r in listing)))
        monthly = [r for r in listing if '/monthly/' in r['key']]
        latest_month = max((r['end_ms'] for r in monthly), default=0)
        daily = [r for r in listing if '/daily/' in r['key']]
        index = catalog_index(warehouse)
        allowed_gaps = admitted_gap_ranges(warehouse,index)
        admitted = [c for records in index.values() for c in records]
        inception = min((c['first_open_ms'] for c in admitted),default=None)
        # Monthly first. Daily candidates fill only genuine remaining coverage;
        # known source boundaries and the authorized gap are never fabricated.
        candidates = [] if daily_only else list(monthly)
        for row in daily:
            if row['start_ms'] >= latest_month or not period_covered(warehouse,
                    row['start_ms'],row['end_ms'],inception=inception,permitted_gaps=allowed_gaps):
                candidates.append(row)
        results, failures = [], []
        examined = 0
        for item in candidates:
            # Monthly ingestion earlier in this run may already cover a daily
            # candidate. Recheck now to avoid downloading duplicate originals.
            if ('/daily/' in item['key'] and not recheck_publisher
                    and period_covered(warehouse,item['start_ms'],item['end_ms'],
                                       inception=inception,permitted_gaps=allowed_gaps)):
                continue
            if examined >= archive_limit:
                break
            # Completed keys are verified against retained bytes. Revisions
            # are detected by subsequent checksum fetch, never overwritten.
            receipts = index.get(item['key'], [])
            if receipts and not recheck_publisher:
                c = receipts[0]
                need(seal(warehouse.path(f"raw/{c['source_zip_sha256']}.zip").read_bytes()) ==
                     c['source_zip_sha256'], 'RETAINED_RAW_CORRUPT')
                # Only replay verified complete shard records; an interrupted
                # archive without a receipt is deliberately imported again.
                if period_covered(warehouse,item['start_ms'],item['end_ms'],
                                  inception=inception,permitted_gaps=allowed_gaps):
                    continue
                # Recover an absent/partial shard from the retained verified
                # original before trying another network source. Partial listing
                # months replay idempotently; no pre-listing bars are fabricated.
                retained = warehouse.path(f"raw/{c['source_zip_sha256']}.zip")
                checksum = warehouse.path(f"raw/{c['checksum_sha256']}.CHECKSUM")
                result = warehouse.import_archive(retained.read_bytes(), checksum.read_bytes(),
                                                   item['key'], observed_ms=c['observed_ms'],
                                                   derivation=c.get('derivation'))
                results.append(result)
                if progress: progress(dict(event='RETAINED_ARCHIVE_RECONCILED',**result))
                continue
            examined += 1
            path = None
            try:
                path, checksum = source.acquire(warehouse, item['key'], expected_size=item['size'])
                imported_at = clock_ms() if clock_ms else now_ms
                need(type(imported_at) is int and imported_at >= now_ms,'BACKFILL_CLOCK_REGRESSION')
                result = warehouse.import_archive(path.read_bytes(), checksum, item['key'],
                                                  observed_ms=imported_at)
                results.append(result)
                record = json.loads(warehouse.path(f"catalog/{result['source_sha256']}.json").read_bytes())
                index.setdefault(item['key'],[]).append(record)
                inception = min(inception,record['first_open_ms']) if inception is not None else record['first_open_ms']
                if progress: progress(dict(event='ARCHIVE_IMPORTED',**result))
            except (ValueError, OSError) as exc:
                failure = dict(key=item['key'], error_type=type(exc).__name__, reason=str(exc))
                if path is not None and str(exc) == 'NATIVE_TIME_OR_MARKET_FIELDS':
                    from .diagnose import diagnose_archive
                    failure['native_diagnostic'] = diagnose_archive(path.read_bytes(),checksum,
                        item['key'],observed_ms=now_ms)
                warehouse.document('quarantine', failure)
                failures.append(failure)
                # Stop on storage, conflict or integrity errors, preserve partial
                # download for retry. Never silently skip to a success claim.
                break
        if progress: progress(dict(event='VERIFYING_FINAL_STORED_COVERAGE'))
        report = warehouse.report()
        source_end = max(r['end_ms'] for r in listing)
        first_key = min(listing, key=lambda r: (r['start_ms'], -r['end_ms']))['key']
        first_records = []
        for pth in warehouse.path('catalog').glob('*.json'):
            record = json.loads(pth.read_bytes())
            if record.get('schema') == 'aql.research.warehouse-source.v1' and record['key'] == first_key:
                first_records.append(record)
        full = bool(first_records and not failures and report['one_minute_rows']
                    and not report['internal_gaps']
                    and report['stored_last_open_ms'] + 60000 == source_end
                    and report['stored_first_open_ms'] == min(r['first_open_ms'] for r in first_records))
        admitted_keys = set(index)
        required_keys = {r['key'] for r in monthly} if not daily_only else set()
        # Daily partitions are required wherever no monthly partition exists.
        for row in daily:
            if not any(m['start_ms'] <= row['start_ms'] and row['end_ms'] <= m['end_ms'] for m in monthly):
                required_keys.add(row['key'])
        for item in candidates:
            if item['key'] not in admitted_keys and not period_covered(warehouse,
                    item['start_ms'],item['end_ms'],inception=inception,permitted_gaps=allowed_gaps):
                required_keys.add(item['key'])
        pending = sorted(required_keys-admitted_keys)
        exhausted = not failures and not pending
        source_tail_reached = bool(report['stored_last_open_ms'] is not None and
                                   report['stored_last_open_ms']+60000 == source_end)
        report.update(acquisition_plan_exhausted=exhausted, pending_source_partitions=pending,
                      latest_published_close_reached=source_tail_reached,
                      permitted_missing_ranges=allowed_gaps,
                      internal_missing_minutes=sum((b-a)//60000 for a,b in report['internal_gaps']),
                      source_listing_first_ms=min(r['start_ms'] for r in listing),
                      source_listing_last_complete_end_ms=max(r['end_ms'] for r in listing),
                      latest_source_daily_end_ms=max((r['end_ms'] for r in daily), default=None),
                      listing_snapshot_sha256=seal(canonical(snapshot)),
                      this_run=results, failures=failures,
                      status='RUN_BLOCKED' if failures else 'BOUNDED_RUN_FINISHED',
                      full_history_verified=full,
                      history_scope='FIRST_ROW_OF_EARLIEST_LISTED_ARCHIVE_TO_LAST_PUBLISHED_CLOSED_PERIOD',
                      daily_scheduler='NOT_MODIFIED_BY_RUNNER')
        warehouse.document('receipts', report)
        return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('backfill', 'daily', 'report'))
    p.add_argument('--root', type=Path, default=Path('E:/ATLAS/DataWarehouse'))
    p.add_argument('--authorization', type=Path)
    p.add_argument('--recheck-publisher', action='store_true')
    p.add_argument('--archive-limit', type=int, default=12)
    a = p.parse_args()
    warehouse = HistoricalWarehouse(a.root)
    if a.mode == 'report':
        result = warehouse.report()
    else:
        need(a.authorization is not None, 'SOURCE_AUTHORIZATION_REQUIRED')
        source = VisionHTTP(authority=json.loads(a.authorization.read_bytes()))
        result = run(warehouse, source, now_ms=time.time_ns() // 1_000_000,
                     archive_limit=a.archive_limit, daily_only=a.mode == 'daily',
                     recheck_publisher=a.recheck_publisher,clock_ms=lambda:time.time_ns()//1000000)
    print(json.dumps(result, sort_keys=True, indent=2))
    if result.get('failures'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
