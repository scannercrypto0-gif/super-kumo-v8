"""Import retained Daily outputs without network or scheduler changes."""
import argparse
import json
from pathlib import Path
import re
import time

from .engine import HistoricalWarehouse, parse_archive
from .source import archive_window
from .storage import need, safe, seal, canonical

MAX_ZIP = 64 * 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def import_retained(warehouse, directory, *, observed_ms, archive_limit=10000):
    directory = safe(directory)
    need(directory.is_dir() and not directory.is_relative_to(warehouse.root), 'DAILY_INPUT_ROOT_INVALID')
    results = []
    with warehouse.writer():
        for path in sorted(directory.glob('BTCUSDT-1m-????-??-??.zip'))[:archive_limit]:
            safe(path)
            need(path.stat().st_size <= MAX_ZIP, 'DAILY_INPUT_BOUND')
            checksum = safe(path.with_name(path.name + '.CHECKSUM'))
            need(checksum.is_file() and checksum.stat().st_size <= 512, 'DAILY_CHECKSUM_REQUIRED')
            key = 'data/spot/daily/klines/BTCUSDT/1m/' + path.name
            results.append(warehouse.import_archive(path.read_bytes(), checksum.read_bytes(),
                                                    key, observed_ms=observed_ms))
        report = warehouse.report()
        report.update(status='DAILY_RETAINED_IMPORT_FINISHED' if results else 'WAIT_NO_1M_DAILY_ARCHIVES',
                      input_directory=str(directory), this_run=results,
                      source_network_calls=0, scheduler_changes=0)
        warehouse.document('receipts', report)
        return report


def import_one_retained(warehouse, archive, *, source_day_ms, expected_zip_sha256,
                        expected_checksum_sha256, observed_ms, report_root=None):
    """Admit exactly one pinned retained archive after UTC-day and byte preflight."""
    need(type(source_day_ms) is int and source_day_ms > 0 and source_day_ms % 86_400_000 == 0,
         'DAILY_SOURCE_DAY_INVALID')
    need(type(observed_ms) is int and observed_ms >= source_day_ms + 86_400_000,
         'DAILY_SOURCE_NOT_FINAL')
    need(type(expected_zip_sha256) is str and HEX64.fullmatch(expected_zip_sha256),
         'DAILY_ZIP_PIN_INVALID')
    need(type(expected_checksum_sha256) is str and HEX64.fullmatch(expected_checksum_sha256),
         'DAILY_CHECKSUM_PIN_INVALID')
    path = safe(archive)
    need(path.is_file() and path.stat().st_nlink == 1 and not path.is_relative_to(warehouse.root),
         'DAILY_INPUT_FILE_SCOPE')
    day = time.strftime('%Y-%m-%d', time.gmtime(source_day_ms / 1000))
    expected_name = f'BTCUSDT-1m-{day}.zip'
    need(path.name == expected_name, 'DAILY_ARCHIVE_DAY_MISMATCH')
    checksum_path = safe(path.with_name(path.name + '.CHECKSUM'))
    need(checksum_path.is_file() and checksum_path.stat().st_nlink == 1,
         'DAILY_CHECKSUM_FILE_SCOPE')
    need(0 < path.stat().st_size <= MAX_ZIP and 0 < checksum_path.stat().st_size <= 512,
         'DAILY_INPUT_BOUND')
    raw, checksum = path.read_bytes(), checksum_path.read_bytes()
    need(seal(raw) == expected_zip_sha256 and seal(checksum) == expected_checksum_sha256,
         'DAILY_INPUT_PIN_MISMATCH')
    key = 'data/spot/daily/klines/BTCUSDT/1m/' + expected_name
    start, end = archive_window(key)
    need(start == source_day_ms and end == source_day_ms + 86_400_000,
         'DAILY_ARCHIVE_DAY_MISMATCH')
    # Parse the exact captured bytes before opening the writer or mutating storage.
    parse_archive(raw, checksum, key, observed_ms)
    with warehouse.writer():
        imported = warehouse.import_archive(raw, checksum, key, observed_ms=observed_ms)
        report = warehouse.report()
        report.update(status='DAILY_RETAINED_IMPORT_FINISHED', this_run=[imported],
                      source_network_calls=0, scheduler_changes=0)
        receipt_path = warehouse.document('receipts', report)
        report['warehouse_receipt_sha256'] = receipt_path.stem
        source_receipt = None
        if report_root is not None:
            # One exact committed catalog object, never a directory/DB scan.
            # Replay must preserve original receipt observation rather than reconstruct it.
            catalog = warehouse.path(f'catalog/{expected_zip_sha256}.json')
            need(catalog.is_file() and catalog.stat().st_nlink == 1
                 and 0 < catalog.stat().st_size <= 8192, 'DAILY_REPORT_SOURCE_RECEIPT_BOUND')
            source_receipt = json.loads(catalog.read_bytes())
            source_body = {k: v for k, v in source_receipt.items() if k != 'receipt_sha256'}
            need(source_receipt.get('receipt_sha256') == seal(canonical(source_body))
                 and source_receipt.get('key') == key
                 and source_receipt.get('source_zip_sha256') == expected_zip_sha256
                 and source_receipt.get('checksum_sha256') == expected_checksum_sha256,
                 'DAILY_REPORT_SOURCE_RECEIPT_IDENTITY')
    # Outside the writer lock: no additional warehouse scan or mutation.
    if report_root is not None:
        from .producer_report import publish_bounded
        registry = report.get('registry') or {}
        matched = [row for row in registry.get('sources', [])
                   if row.get('source_zip_sha256') == expected_zip_sha256
                   and row.get('key') == key]
        source_receipt_sha = (matched[0].get('source_receipt_sha256')
                              if len(matched) == 1 else None)
        need(source_receipt_sha == source_receipt['receipt_sha256'],
             'DAILY_REPORT_REGISTRY_SOURCE_BINDING')
        publish_bounded(report_root, protected_root=warehouse.root,
            code_sha256=seal(Path(__file__).read_bytes()),
            config_sha256=seal(json.dumps(dict(day=source_day_ms,
                zip=expected_zip_sha256, checksum=expected_checksum_sha256),
                sort_keys=True, separators=(',', ':')).encode()),
            lane='DAILY', identity=seal(expected_zip_sha256.encode())[:16],
            sequence=source_day_ms, observed_ms=observed_ms,
            published_ms=time.time_ns() // 1_000_000,
            status='SOURCE_IMPORT_COMMITTED', reason='REGISTRY_LINK_PRESENT'
                if source_receipt_sha and registry.get('snapshot_sha256')
                else 'REGISTRY_LINK_UNKNOWN',
            counters=dict(source_rows=imported.get('source_rows', 0),
                          inserted_rows=imported.get('inserted_rows', 0),
                          duplicate_rows=imported.get('duplicate_rows', 0),
                          conflicts=imported.get('conflicts', 0)),
            source_sha256=imported.get('source_sha256'),
            checksum_sha256=expected_checksum_sha256,
            source_receipt_sha256=source_receipt_sha,
            source_key=key, source_receipt=source_receipt, import_receipt=imported,
            import_receipt_sha256=seal(canonical(imported)),
            receipt_sha256=receipt_path.stem,
            registry_sha256=registry.get('snapshot_sha256'),
            registry_watermark=registry.get('event_watermark'),
            source_day_ms=source_day_ms,
            task_state=None, reuse_committed_daily=True)  # No retimestamping on replay.
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('E:/ATLAS/DataWarehouse'))
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--input-directory', type=Path)
    group.add_argument('--archive', type=Path)
    p.add_argument('--source-day-ms', type=int)
    p.add_argument('--expected-zip-sha256')
    p.add_argument('--expected-checksum-sha256')
    p.add_argument('--bounded-report-root',type=Path,help='existing isolated MCP report directory; one archive only')
    a = p.parse_args()
    warehouse = HistoricalWarehouse(a.root)
    if a.archive is not None:
        need(a.source_day_ms is not None and a.expected_zip_sha256 is not None
             and a.expected_checksum_sha256 is not None, 'DAILY_SINGLE_ARCHIVE_PINS_REQUIRED')
        result = import_one_retained(warehouse, a.archive, source_day_ms=a.source_day_ms,
            expected_zip_sha256=a.expected_zip_sha256,
            expected_checksum_sha256=a.expected_checksum_sha256,
            observed_ms=time.time_ns() // 1_000_000,
            report_root=a.bounded_report_root)
    else:
        need(a.bounded_report_root is None, 'DAILY_BULK_REPORT_NOT_SUPPORTED')
        need(a.source_day_ms is None and a.expected_zip_sha256 is None
             and a.expected_checksum_sha256 is None, 'DAILY_BULK_MODE_PIN_ARGS_DENIED')
        result = import_retained(warehouse, a.input_directory,
                                 observed_ms=time.time_ns() // 1_000_000)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
