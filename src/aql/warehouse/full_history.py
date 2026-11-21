"""Continue the existing owner warehouse to one frozen publisher listing.

Source validation, acquisition, storage limits and the one approved correction
are reused. No scheduler/WS mutations or additional data corrections.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import time
import os

from .diagnose import _august_snapshot
from .engine import HistoricalWarehouse
from .runner import run, catalog_index, admitted_gap_ranges, period_covered
from .september_correction import AUGUST_SHARDS, GAP, START, END
from .source import VisionHTTP
from .storage import canonical, need, seal

CONTINUATION = 'https://github.com/scannercrypto0-gif/super-kumo-v8/pull/330#issuecomment-7059048243'
AUTH_FIELDS = ('bulk_download_ref','source_rights_ref','network_permission_ref')


def existing_authority(warehouse, explicit=None):
    if explicit is not None:
        p=Path(explicit)
        need(p.is_file() and p.stat().st_size <= 65536,'AUTHORIZATION_FILE_BOUND')
        authority=json.loads(p.read_bytes())
    else:
        candidates={}
        for p in warehouse.path('catalog').glob('*.json'):
            if len(p.stem) != 64:
                continue
            p=warehouse.path('catalog/'+p.name)
            need(p.stat().st_nlink == 1 and p.stat().st_size <= 8*1024*1024,'CATALOG_OBJECT_BOUND')
            raw=p.read_bytes(); body=json.loads(raw)
            if body.get('schema') != 'aql.warehouse.source-listing.v1':
                continue
            need(seal(raw) == p.stem,'SOURCE_LISTING_SNAPSHOT_PIN')
            a=body.get('authority')
            need(type(a) is dict and all(type(a.get(k)) is str and a[k].strip()
                                        for k in AUTH_FIELDS),'RETAINED_SOURCE_AUTHORIZATION_INVALID')
            selected={k:a[k] for k in AUTH_FIELDS}
            candidates[seal(canonical(selected))]=selected
        need(len(candidates) == 1,'UNIQUE_RETAINED_AUTHORIZATION_OR_EXPLICIT_FILE_REQUIRED')
        authority=next(iter(candidates.values()))
    # References already confirmed by the owner are reused; no rights asserted
    # from public accessibility and no permission values printed to the console.
    need(type(authority) is dict and all(type(authority.get(k)) is str and authority[k].strip()
                                        for k in AUTH_FIELDS),'SOURCE_AUTHORIZATION_REQUIRED')
    return {**authority,'full_history_continuation_ref':CONTINUATION}


def protected_snapshot(warehouse):
    warehouse.used()  # Reject symlink/reparse/hard-link entries before reading snapshots.
    august=_august_snapshot(warehouse)
    need(august['rows'] == 21360 and august['shard_sha256'] == AUGUST_SHARDS,
         'OWNER_ACCEPTED_AUGUST_CHANGED')
    paths=list(warehouse.path('bars').glob('2017-09-??.sqlite'))
    names={f'2017-09-{n:02d}.sqlite' for n in range(1,31)}
    need({p.name for p in paths} == names,'OWNER_ACCEPTED_SEPTEMBER_SHARDS_MISSING')
    rows=0; hashes={}
    for p in paths:
        hashes[p.name]=seal(p.read_bytes())
        con=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True)
        try: rows+=con.execute('SELECT count(*) FROM finalized_bars').fetchone()[0]
        finally: con.close()
    need(rows == 42780 and period_covered(warehouse,START,END,permitted_gaps=[GAP]),
         'OWNER_ACCEPTED_SEPTEMBER_CENSUS_CHANGED')
    return dict(august=august,september=dict(rows=rows,shard_sha256=hashes))


def continue_history(warehouse, source, *, clock_ms, progress=None, archive_limit=10000, task_inspection=None):
    need(warehouse.root.is_dir() and warehouse.path('catalog/warehouse-policy.json').is_file(),
         'EXISTING_WAREHOUSE_REQUIRED_NO_REBUILD')
    before=protected_snapshot(warehouse)
    # Verify the admitted policy/original lineage before recognizing its gap.
    need(admitted_gap_ranges(warehouse,catalog_index(warehouse)) == [GAP],
         'ACCEPTED_SEPTEMBER_DERIVATION_REQUIRED')
    imported=0; inserted=0
    def emit(event):
        nonlocal imported,inserted
        if event['event'] in ('ARCHIVE_IMPORTED','RETAINED_ARCHIVE_RECONCILED'):
            imported+=1; inserted+=event['inserted_rows']
            if imported % 3 == 0:
                need(protected_snapshot(warehouse) == before,'ACCEPTED_PREFIX_CHANGED')
                warehouse.document('receipts',dict(schema='aql.warehouse.full-history-checkpoint.v1',
                    continuation_ref=CONTINUATION,archives_this_run=imported,
                    inserted_rows_this_run=inserted,accepted_prefix_unchanged=True,
                    last_source_key=event['key'],source_class='RETROSPECTIVE_NON_PIT',
                    full_history_verified=False,trading_authority='NONE'))
        if progress: progress(event)
    started=clock_ms()
    report=run(warehouse,source,now_ms=started,archive_limit=archive_limit,
               progress=emit,clock_ms=clock_ms,continue_on_source_error=True)
    after=protected_snapshot(warehouse)
    need(after == before,'ACCEPTED_PREFIX_CHANGED')
    gaps=report['internal_gaps']
    need(GAP in gaps,'ACCEPTED_SEPTEMBER_GAP_CHANGED')
    unknown=[g for g in gaps if g != GAP]
    all_partitions=report['acquisition_plan_exhausted'] and report['latest_published_close_reached']
    if report['failures']:
        state='FULL_HISTORY_BLOCKED_EXACT_SOURCE'
    elif report.get('source_scan_exhausted') and report.get('unresolved_source_obstacles'):
        state='PUBLISHED_SOURCE_SCAN_FINISHED_WITH_QUARANTINED_PARTITIONS'
    elif not all_partitions:
        state='BOUNDED_PROGRESS_MORE_PARTITIONS_PENDING'
    elif unknown:
        state='PUBLISHED_PARTITIONS_IMPORTED_WITH_UNRESOLVED_GAPS'
    else:
        state='PUBLISHED_PARTITIONS_IMPORTED_WITH_DECLARED_420_MINUTE_GAP'
    report.update(schema='aql.warehouse.full-history-continuation.v1',status=state,
        continuation_ref=CONTINUATION,accepted_prefix_unchanged=True,
        protected_before=before,protected_after=after,
        all_published_partitions_ingested=all_partitions,
        unresolved_gap_ranges=unknown,declared_missing_minutes=420,
        full_history_verified=False,started_ms=started,finished_ms=clock_ms(),
        scheduler_changes=0,read_only_task_inspection=task_inspection,trading_authority='NONE')
    with warehouse.writer():
        path=warehouse.document('receipts',report)
    report['receipt_file']=path.name
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('E:/ATLAS/DataWarehouse'))
    p.add_argument('--authorization',type=Path)
    p.add_argument('--archive-limit',type=int,default=10000)
    args=p.parse_args()
    w=HistoricalWarehouse(args.root)
    authority=existing_authority(w,args.authorization)
    print(json.dumps(dict(event='FULL_HISTORY_START',root=str(w.root),
                          continuation_ref=CONTINUATION,archive_limit=args.archive_limit)),flush=True)
    inspection=os.environ.get('ATLAS_WAREHOUSE_RECOVERY_TASK_INSPECTION')
    if inspection: need(len(inspection.encode()) <= 65536,'TASK_INSPECTION_BOUND')
    try:
        report=continue_history(w,VisionHTTP(authority=authority),
            clock_ms=lambda:time.time_ns()//1000000,
            archive_limit=args.archive_limit,task_inspection=json.loads(inspection) if inspection else None,
            progress=lambda event:print(json.dumps(event,sort_keys=True),flush=True))
    except (OSError,ValueError) as exc:
        print(json.dumps(dict(status='FULL_HISTORY_STOPPED_FAIL_CLOSED',
            error_type=type(exc).__name__,reason=str(exc),full_history_verified=False,
            scheduler_changes=0,trading_authority='NONE')),flush=True)
        raise SystemExit(2)
    print(json.dumps(report,sort_keys=True,indent=2),flush=True)
    if (report['failures'] or report['unresolved_gap_ranges']
            or not report['all_published_partitions_ingested']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
