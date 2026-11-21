"""Single resumable backfill/daily catch-up runner. No scheduler or WS mutation."""
import argparse
import json
from pathlib import Path
import time

from .engine import HistoricalWarehouse, DAY
from .source import VisionHTTP
from .storage import canonical, need, seal


def run(warehouse, source, *, now_ms, archive_limit=12, daily_only=False, recheck_publisher=False):
    need(type(archive_limit) is int and 1 <= archive_limit <= 10000, 'ARCHIVE_RUN_BOUND')
    with warehouse.writer():
        listing = source.discover(now_ms=now_ms)
        snapshot = dict(schema='aql.warehouse.source-listing.v1', observed_ms=now_ms,
                        archives=listing, authority=source.authority,
                        source_class='RETROSPECTIVE_NON_PIT')
        warehouse.document('catalog', snapshot)
        monthly = [r for r in listing if '/monthly/' in r['key']]
        latest_month = max((r['end_ms'] for r in monthly), default=0)
        daily = [r for r in listing if '/daily/' in r['key']]
        # Monthly first; daily tail and source-listed missing days fill holes.
        candidates = [] if daily_only else monthly
        for row in daily:
            stored = warehouse._existing(row['start_ms'])
            if row['start_ms'] >= latest_month or len(stored) < 1440:
                candidates.append(row)
        results, failures = [], []
        examined = 0
        for item in candidates:
            # Monthly ingestion earlier in this run may already cover a daily
            # candidate. Recheck now to avoid downloading duplicate originals.
            if ('/daily/' in item['key'] and not recheck_publisher
                    and len(warehouse._existing(item['start_ms'])) == 1440):
                continue
            if examined >= archive_limit:
                break
            # Completed keys are verified against retained bytes. Revisions
            # are detected by subsequent checksum fetch, never overwritten.
            receipts = []
            for p in warehouse.path('catalog').glob('*.json'):
                if len(p.stem) == 64:
                    c = json.loads(p.read_bytes())
                    if c.get('schema') == 'aql.research.warehouse-source.v1' and c['key'] == item['key']:
                        receipts.append(c)
            if receipts and not recheck_publisher:
                c = receipts[0]
                need(seal(warehouse.path(f"raw/{c['source_zip_sha256']}.zip").read_bytes()) ==
                     c['source_zip_sha256'], 'RETAINED_RAW_CORRUPT')
                # Only replay verified complete shard records; an interrupted
                # archive without a receipt is deliberately imported again.
                if all(len(warehouse._existing(t)) == 1440 for t in
                       range(item['start_ms'], item['end_ms'], DAY)):
                    continue
                # Listing month (exchange listing date) can be partial. It is
                # already imported; daily source candidates handle its gaps.
                if '/monthly/' in item['key']:
                    continue
            examined += 1
            try:
                path, checksum = source.acquire(warehouse, item['key'], expected_size=item['size'])
                results.append(warehouse.import_archive(path.read_bytes(), checksum, item['key'],
                                                        observed_ms=now_ms))
            except (ValueError, OSError) as exc:
                failure = dict(key=item['key'], error_type=type(exc).__name__, reason=str(exc))
                warehouse.document('quarantine', failure)
                failures.append(failure)
                # Stop on storage, conflict or integrity errors, preserve partial
                # download for retry. Never silently skip to a success claim.
                break
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
        report.update(source_listing_first_ms=min(r['start_ms'] for r in listing),
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
                     recheck_publisher=a.recheck_publisher)
    print(json.dumps(result, sort_keys=True, indent=2))
    if result.get('failures'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
