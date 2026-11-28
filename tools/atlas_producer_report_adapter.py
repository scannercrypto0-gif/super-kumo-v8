"""Pure bounded producer-report projections, never worker health or source custody.

The caller supplies independently configured code/config pins and a separate
sealed Registry; self-reported verification flags never grant admission.
"""
from datetime import datetime, timezone
import re

import atlas_ops_watchdog as watchdog

DAY = 86_400_000
HEX = re.compile(r'[0-9a-f]{64}\Z')


def need(ok, code):
    if not ok:
        raise ValueError(code)


def pin(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def base(report, expected, now, *, schema, lane, allow_stale=False):
    need(type(report) is dict and report.get('schema') == schema and report.get('lane') == lane,
         'PRODUCER_REPORT_SCHEMA')
    watchdog.sealed_hash(report, 'report_sha256', 'PRODUCER_REPORT_SEAL')
    need(type(expected) is dict and all(pin(expected.get(k)) and report.get(k) == expected[k]
             for k in ('code_sha256', 'config_sha256')), 'PRODUCER_REPORT_EXTERNAL_PIN_REQUIRED')
    for identity_field in ('producer_identity', 'run_id'):
        if expected.get(identity_field) is not None:
            need(report.get(identity_field) == expected[identity_field], 'PRODUCER_REPORT_IDENTITY_PIN')
    observed, published = report.get('observation_ms'), report.get('published_ms')
    need(type(observed) is int and type(published) is int and 0 < observed <= published <= now,
         'PRODUCER_REPORT_CLOCK')
    if not allow_stale:
        need(now - observed <= 300_000, 'PRODUCER_REPORT_STALE')
    need(type(report.get('sequence')) is int and report['sequence'] >= 0,
         'PRODUCER_REPORT_SEQUENCE')
    need(report.get('trading_authority') == 'NONE', 'PRODUCER_REPORT_AUTHORITY')
    return observed


def daily_source(report, registry, expected, now):
    observed = base(report, expected, now, schema='aql.mcp.producer-bounded-report.v1', lane='DAILY')
    need(report.get('source_class') == 'RETROSPECTIVE_NON_PIT'
         and report.get('task_state') is None and report.get('status') == 'SOURCE_IMPORT_COMMITTED',
         'PRODUCER_DAILY_SCOPE')
    day = report.get('source_day_ms')
    need(type(day) is int and day > 0 and day % DAY == 0 and day + DAY <= observed,
         'PRODUCER_DAILY_NOT_FINAL')
    key = 'data/spot/daily/klines/BTCUSDT/1m/' + f'BTCUSDT-1m-{datetime.fromtimestamp(day / 1000, timezone.utc):%Y-%m-%d}.zip'
    need(report.get('source_key') == key, 'PRODUCER_DAILY_DAY_KEY')
    source = report.get('source_receipt')
    imported = report.get('import_receipt')
    need(type(source) is dict and type(imported) is dict, 'PRODUCER_DAILY_RECEIPTS_MISSING')
    watchdog.sealed_hash(source, 'receipt_sha256', 'PRODUCER_SOURCE_RECEIPT_SEAL')
    need(source.get('schema') == 'aql.research.warehouse-source.v1'
         and source.get('publisher_integrity') == 'ZIP_CHECKSUM_MATCH'
         and source.get('key') == key and source.get('source_class') == 'RETROSPECTIVE_NON_PIT'
         and source.get('trading_authority') == 'NONE'
         and source.get('source_zip_sha256') == report.get('source_sha256')
         and source.get('checksum_sha256') == report.get('checksum_sha256')
         and source.get('receipt_sha256') == report.get('source_receipt_sha256')
         and type(source.get('rows')) is int and source['rows'] > 0,
         'PRODUCER_SOURCE_RECEIPT_BINDING')
    need(imported.get('status') == 'ARCHIVE_IMPORTED' and imported.get('key') == key
         and imported.get('source_sha256') == report.get('source_sha256')
         and imported.get('source_class') == 'RETROSPECTIVE_NON_PIT'
         and imported.get('trading_authority') == 'NONE'
         and imported.get('source_rows') == source['rows']
         and type(imported.get('source_rows')) is int
         and report.get('import_receipt_sha256') == watchdog.digest(watchdog.canonical(imported))
         and pin(report.get('receipt_sha256')), 'PRODUCER_IMPORT_RECEIPT_BINDING')
    view = watchdog.registry_view(registry)
    need(type(registry.get('as_of_ms')) is int and 0 <= now - registry['as_of_ms'] <= 300_000,
         'PRODUCER_REGISTRY_STALE')
    need(report.get('registry_sha256') == view['snapshot_sha256']
         and type(report.get('registry_watermark')) is int
         and report['registry_watermark'] == view['counters']['event_watermark'],
         'PRODUCER_REGISTRY_SNAPSHOT_BINDING')
    matches = [row for row in registry['sources'] if row.get('key') == key
               and row.get('source_zip_sha256') == report.get('source_sha256')
               and row.get('source_receipt_sha256') == source['receipt_sha256']]
    need(len(matches) == 1 and matches[0].get('rows') == source['rows'], 'PRODUCER_REGISTRY_SOURCE_BINDING')
    return dict(status='SOURCE_LINK_VERIFIED_WORKER_NOT_INFERRED', source_day_ms=day,
                source_key=key, source_zip_sha256=source['source_zip_sha256'],
                checksum_sha256=source['checksum_sha256'], source_receipt_sha256=source['receipt_sha256'],
                import_receipt_sha256=report['import_receipt_sha256'],
                warehouse_report_sha256=report['receipt_sha256'],
                registry_snapshot_sha256=view['snapshot_sha256'],
                registry_event_watermark=report['registry_watermark'],
                observation_ms=observed, sequence=report['sequence'],
                producer_identity=report.get('producer_identity'),
                worker_health='UNKNOWN', trust_scope='PINNED_PRODUCER_REPORT_NOT_PHYSICAL_REVALIDATION')


def realtime(report, expected, now):
    observed = base(report, expected, now, schema='aql.realtime.producer-bounded-report.v1', lane='REALTIME', allow_stale=True)
    need(report.get('source_class') == 'FORWARD_UNQUALIFIED'
         and report.get('orders') == 0 and type(report.get('orders')) is int
         and report.get('operational_24h_accepted') is False
         and report.get('pit_oos') == 'NOT_ATTESTED'
         and report.get('reporting_scope') == 'COMMITTED_MEMORY_ONLY'
         and report.get('network_calls') == 0 and report.get('source_mutations') == 0,
         'PRODUCER_REALTIME_SCOPE')
    need(type(report.get('run_id')) is str and 0 < len(report['run_id']) <= 128
         and re.fullmatch(r'[A-Za-z0-9_.:-]+', report['run_id']), 'PRODUCER_REALTIME_RUN')
    need(report.get('producer_id') == 'atlas.realtime_market_feed.service.Store.ingest'
         and report.get('source_id') == 'BINANCE_SPOT_PUBLIC_WEBSOCKET', 'PRODUCER_REALTIME_IDENTITY')
    count = report.get('committed_final_bars_this_run')
    need(type(count) is int and count >= 0 and type(report.get('gaps_detected_this_run')) is int
         and report['gaps_detected_this_run'] >= 0
         and report.get('gap_status') == 'UNKNOWN_NOT_RESCANNED', 'PRODUCER_REALTIME_COUNTS')
    committed = report.get('last_committed_ms')
    close = report.get('last_final_close_ms')
    if count:
        need(type(committed) is int and type(close) is int and 0 <= close < committed <= observed
             and report.get('source_finality') == 'FINAL'
             and pin(report.get('last_receipt_sha256')) and pin(report.get('last_source_event_sha256')),
             'PRODUCER_REALTIME_COMMIT')
    else:
        need(committed is None and close is None and report.get('last_receipt_sha256') is None,
             'PRODUCER_REALTIME_EMPTY_CLAIM')
    need(report.get('status') in {'HELD', 'OBSERVED_SOURCE_PROGRESS', 'UNKNOWN', 'STOPPED'},
         'PRODUCER_REALTIME_STATUS')
    return dict(run_id=report['run_id'], producer_id=report['producer_id'],
                code_sha256=report['code_sha256'], config_sha256=report['config_sha256'],
                source_id=report['source_id'], sequence=report['sequence'], observation_ms=observed,
                committed_final_bars_this_run=count, last_committed_ms=committed,
                last_final_close_ms=close, last_receipt_sha256=report.get('last_receipt_sha256'),
                last_source_event_sha256=report.get('last_source_event_sha256'),
                gaps_detected_this_run=report['gaps_detected_this_run'], gap_status='UNKNOWN_NOT_RESCANNED',
                status=report['status'], run_stopped=report.get('run_stopped') is True, hold_reason_present=bool(report.get('hold_reason')),
                source_class='FORWARD_UNQUALIFIED', operational_24h_accepted=False, pit_oos='NOT_ATTESTED')
