"""Import existing daily task's retained ZIP+CHECKSUM outputs, without network."""
import argparse
import json
from pathlib import Path
import time

from .engine import HistoricalWarehouse
from .storage import need, safe


def import_retained(warehouse, directory, *, observed_ms, archive_limit=10000):
    directory = safe(directory)
    need(directory.is_dir() and not directory.is_relative_to(warehouse.root), 'DAILY_INPUT_ROOT_INVALID')
    results = []
    with warehouse.writer():
        for path in sorted(directory.glob('BTCUSDT-1m-????-??-??.zip'))[:archive_limit]:
            safe(path)
            need(path.stat().st_size <= 64*1024*1024, 'DAILY_INPUT_BOUND')
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('E:/ATLAS/DataWarehouse'))
    p.add_argument('--input-directory', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(import_retained(HistoricalWarehouse(a.root), a.input_directory,
                                    observed_ms=time.time_ns()//1000000), sort_keys=True))


if __name__ == '__main__':
    main()
