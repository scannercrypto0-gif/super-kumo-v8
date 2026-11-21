"""Bounded source recovery for full history; strict admission remains unchanged.

Only pre-import source failures can be deferred. Storage, custody, clock,
conflicts and registry failures stop the writer. Whole rejected archives are
preserved; no timestamp rounding, row dropping or additional derivatives.
"""
import csv
from collections import OrderedDict
from decimal import InvalidOperation
import json
from http.client import IncompleteRead
import time
from urllib.error import HTTPError, URLError

from .engine import parse_archive
from .runner import catalog_index, admitted_gap_ranges, period_covered
from .storage import canonical, need, seal

SOURCE_ERRORS = frozenset((
    'PUBLISHER_CHECKSUM_SCHEMA', 'PUBLISHER_CHECKSUM_MISMATCH',
    'SOURCE_REDIRECT_DENIED', 'SOURCE_HTTP_STATUS', 'SOURCE_RESPONSE_BOUND',
    'RANGE_IDENTITY_INVALID', 'SOURCE_LENGTH_INVALID', 'SOURCE_LENGTH_OVERFLOW',
    'DOWNLOAD_INTERRUPTED', 'ZIP_CORRUPT', 'ZIP_MEMBER_CENSUS', 'ZIP_MEMBER_UNSAFE',
    'NATIVE_ROW_BOUND_OR_SCHEMA', 'NATIVE_MARKET_FIELDS',
    'NATIVE_TIME_OR_MARKET_FIELDS', 'NATIVE_DUPLICATE_OR_ORDER',
    'PRICE_POSITIVE_REQUIRED', 'INVALID_DECIMAL', 'OHLC_INVALID', 'EMPTY_ARCHIVE',
))


def transient(exc):
    if isinstance(exc, HTTPError):
        return exc.code in (408, 429) or 500 <= exc.code <= 599
    return isinstance(exc, (URLError, TimeoutError, ConnectionError, IncompleteRead)) or str(exc) == 'DOWNLOAD_INTERRUPTED'


def source_failure(exc, stage):
    if stage not in ('ACQUIRE', 'VALIDATE'):
        return False
    if isinstance(exc, (HTTPError, URLError, TimeoutError, ConnectionError, IncompleteRead)):
        return stage == 'ACQUIRE'
    if stage == 'VALIDATE' and isinstance(exc, (csv.Error, InvalidOperation, UnicodeError)):
        return True
    return isinstance(exc, ValueError) and str(exc) in SOURCE_ERRORS


def retry(operation, *, event, key=None, sleep=time.sleep):
    for attempt in range(1, 4):
        try:
            return operation(), attempt
        except (OSError, ValueError, IncompleteRead) as exc:
            if not transient(exc) or attempt == 3:
                raise
            event(dict(event='SOURCE_RETRY', key=key, attempt=attempt,
                       reason=str(exc), retry_after_seconds=attempt))
            sleep(attempt)


def run(warehouse, source, *, now_ms, archive_limit, daily_only=False,
        recheck_publisher=False, progress=None, clock_ms=None, sleep=time.sleep):
    need(type(archive_limit) is int and 1 <= archive_limit <= 10000, 'ARCHIVE_RUN_BOUND')
    event = progress or (lambda value: None)
    with warehouse.writer():
        listing, _ = retry(lambda: source.discover(now_ms=now_ms), event=event, sleep=sleep)
        snapshot = dict(schema='aql.warehouse.source-listing.v1', observed_ms=now_ms,
                        archives=listing, authority=source.authority,
                        source_class='RETROSPECTIVE_NON_PIT')
        warehouse.document('catalog', snapshot)
        event(dict(event='SOURCE_LISTING_READY', archive_objects=len(listing),
                   first_period_ms=min(r['start_ms'] for r in listing),
                   latest_complete_period_end_ms=max(r['end_ms'] for r in listing)))
        monthly = sorted((r for r in listing if '/monthly/' in r['key']), key=lambda r:r['start_ms'])
        daily = sorted((r for r in listing if '/daily/' in r['key']), key=lambda r:r['start_ms'])
        candidates = ([] if daily_only else monthly) + daily
        index = catalog_index(warehouse)
        allowed = admitted_gap_ranges(warehouse, index)
        first_period = min(r['start_ms'] for r in listing)
        inception = min((c['first_open_ms'] for records in index.values() for c in records
                         if c['period_start_ms'] == first_period), default=None)
        results, obstacles, fatal, deferred = [], [], [], []
        examined = 0
        scanned = True

        cache = OrderedDict()

        def source_minutes(c):
            pin = c['source_zip_sha256']
            if pin not in cache:
                raw = warehouse.path(f"raw/{pin}.zip").read_bytes()
                checksum = warehouse.path(f"raw/{c['checksum_sha256']}.CHECKSUM").read_bytes()
                need(seal(raw) == pin and seal(checksum) == c['checksum_sha256'],
                     'RETAINED_RAW_CORRUPT')
                rows, meta = parse_archive(raw, checksum, c['key'], c['observed_ms'])
                need(c['rows'] == len(rows) and all(c.get(k) == v for k,v in meta.items()),
                     'SOURCE_CATALOG_FACTS')
                cache[pin] = frozenset(row['open_ms'] for row in rows)
                if len(cache) > 2:
                    cache.popitem(last=False)
            cache.move_to_end(pin)
            return cache[pin]

        def committed_coverage(item):
            # Physical membership alone cannot establish a committed import:
            # interruption may publish the last shard before its source receipt.
            if not covered(item):
                return False
            first = max(item['start_ms'], inception) if inception is not None else item['start_ms']
            expected = {t for t in range(first,item['end_ms'],60000)
                        if not any(a <= t < b for a,b in allowed)}
            for records in index.values():
                for c in records:
                    if c['last_open_ms'] < first or c['first_open_ms'] >= item['end_ms']:
                        continue
                    expected.difference_update(source_minutes(c))
                    if not expected:
                        return True
            return not expected

        def retained_complete(c):
            # Missing source rows require replay; original source gaps belong to
            # the daily fallback queue, not a repeated monthly replay.
            ranges = []
            for t in sorted(source_minutes(c)):
                if ranges and ranges[-1][1] == t:
                    ranges[-1][1] = t+60000
                else:
                    ranges.append([t,t+60000])
            return all(period_covered(warehouse,a,b) for a,b in ranges)

        def covered(item):
            return period_covered(warehouse, item['start_ms'], item['end_ms'],
                                  inception=inception, permitted_gaps=allowed)

        def attempt(item, *, revisit=False):
            nonlocal examined, inception
            if not recheck_publisher and committed_coverage(item):
                return
            receipts = index.get(item['key'], [])
            if receipts and not recheck_publisher:
                # Recovery from committed evidence is a custody operation:
                # errors here are never downgraded to a remote-source obstacle.
                c = receipts[0]
                if retained_complete(c):
                    return
                raw = warehouse.path(f"raw/{c['source_zip_sha256']}.zip").read_bytes()
                need(seal(raw) == c['source_zip_sha256'], 'RETAINED_RAW_CORRUPT')
                checksum = warehouse.path(f"raw/{c['checksum_sha256']}.CHECKSUM").read_bytes()
                result = warehouse.import_archive(raw, checksum, item['key'],
                    observed_ms=c['observed_ms'], derivation=c.get('derivation'))
                results.append(result)
                event(dict(event='RETAINED_ARCHIVE_RECONCILED', **result))
                return
            if examined >= archive_limit:
                return 'LIMIT'
            examined += 1
            path = None
            stage = 'ACQUIRE'
            try:
                (path, checksum), attempts = retry(
                    lambda: source.acquire(warehouse, item['key'], expected_size=item['size']),
                    event=event, key=item['key'], sleep=sleep)
                stage = 'CLOCK'
                imported_at = clock_ms() if clock_ms else now_ms
                need(type(imported_at) is int and imported_at >= now_ms, 'BACKFILL_CLOCK_REGRESSION')
                raw = path.read_bytes()
                stage = 'VALIDATE'
                # Preflight the unchanged parser before any mutation. Its source
                # failures are safe to isolate; importer/registry errors are not.
                parse_archive(raw, checksum, item['key'], imported_at)
                stage = 'IMPORT'
                result = warehouse.import_archive(raw, checksum, item['key'], observed_ms=imported_at)
                results.append(result)
                c = json.loads(warehouse.path(f"catalog/{result['source_sha256']}.json").read_bytes())
                index.setdefault(item['key'], []).append(c)
                if c['period_start_ms'] == first_period:
                    inception = min(inception, c['first_open_ms']) if inception is not None else c['first_open_ms']
                event(dict(event='ARCHIVE_IMPORTED', **result))
            except (OSError, ValueError, csv.Error, InvalidOperation, IncompleteRead) as exc:
                isolated = source_failure(exc, stage)
                failure = dict(schema='aql.warehouse.source-obstacle.v1', key=item['key'],
                    period_start_ms=item['start_ms'], period_end_ms=item['end_ms'],
                    stage=stage, error_type=type(exc).__name__, reason=str(exc),
                    disposition='DEFERRED_SOURCE' if isolated else 'FATAL_WAREHOUSE_STOP',
                    retryable=isolated and transient(exc), final_retry=revisit,
                    source_class='RETROSPECTIVE_NON_PIT', trading_authority='NONE')
                if path is not None and stage == 'VALIDATE':
                    failure.update(source_zip_sha256=seal(raw), checksum_sha256=seal(checksum))
                    if str(exc) == 'NATIVE_TIME_OR_MARKET_FIELDS':
                        from .diagnose import diagnose_archive
                        diagnostic = diagnose_archive(raw, checksum, item['key'], observed_ms=imported_at)
                        diagnostic_path = warehouse.document('quarantine', diagnostic)
                        failure.update(diagnostic_file=diagnostic_path.name,
                            failed_rows=diagnostic['failed_rows'], first_failure=diagnostic['first_failure'])
                evidence = warehouse.document('quarantine', failure)
                failure['obstacle_file'] = evidence.name
                obstacles.append(failure)
                event(dict(event='SOURCE_DEFERRED' if isolated else 'WAREHOUSE_STOPPED', **failure))
                if not isolated:
                    fatal.append(failure)
                    return 'FATAL'
                if failure['retryable'] and not revisit:
                    deferred.append(item)

        for item in candidates:
            outcome = attempt(item)
            if outcome in ('LIMIT', 'FATAL'):
                scanned = False
                break
        # One bounded final pass for transient failures after other periods have
        # progressed. Unchanged invalid originals are not pointlessly retried.
        if not fatal and scanned:
            for item in deferred:
                outcome = attempt(item, revisit=True)
                if outcome in ('LIMIT', 'FATAL'):
                    scanned = False
                    break
        event(dict(event='VERIFYING_FINAL_STORED_COVERAGE'))
        report = warehouse.report()  # Includes full custody/registry verification.
        unresolved, resolved = [], []
        for obstacle in obstacles:
            item = dict(start_ms=obstacle['period_start_ms'], end_ms=obstacle['period_end_ms'])
            complete = committed_coverage(item)
            record = {**obstacle, 'coverage_restored':complete,
                      'resolution':'VERIFIED_ALTERNATIVE_COVERAGE' if complete else 'UNRESOLVED'}
            (resolved if complete else unresolved).append(record)
        pending = []
        for item in candidates:
            # An invalid month can be fully satisfied by original daily data;
            # it need not acquire a false admission receipt to count as covered.
            if item['key'] not in index and not committed_coverage(item):
                pending.append(item['key'])
        source_end = max(r['end_ms'] for r in listing)
        tail = bool(report['stored_last_open_ms'] is not None and report['stored_last_open_ms']+60000 == source_end)
        exhausted = not fatal and not pending and not unresolved
        report.update(source_scan_exhausted=scanned, acquisition_plan_exhausted=exhausted,
            latest_published_close_reached=tail, pending_source_partitions=sorted(set(pending)),
            permitted_missing_ranges=allowed,
            internal_missing_minutes=sum((b-a)//60000 for a,b in report['internal_gaps']),
            source_listing_first_ms=min(r['start_ms'] for r in listing),
            source_listing_last_complete_end_ms=source_end,
            latest_source_daily_end_ms=max((r['end_ms'] for r in daily),default=None),
            listing_snapshot_sha256=seal(canonical(snapshot)), this_run=results,
            failures=fatal, source_obstacles=obstacles, resolved_source_obstacles=resolved,
            unresolved_source_obstacles=unresolved, source_attempts=examined,
            status='RUN_BLOCKED' if fatal else 'SOURCE_SCAN_FINISHED_WITH_OBSTACLES' if unresolved else 'BOUNDED_RUN_FINISHED',
            full_history_verified=bool(exhausted and tail and not report['internal_gaps']),
            history_scope='FIRST_ROW_OF_EARLIEST_LISTED_ARCHIVE_TO_LAST_PUBLISHED_CLOSED_PERIOD',
            recovery_policy='STRICT_ORIGINAL_DAILY_FALLBACK_NO_NEW_CORRECTIONS',
            daily_scheduler='NOT_MODIFIED_BY_RUNNER')
        warehouse.document('receipts', report)
        return report
