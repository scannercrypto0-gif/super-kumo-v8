"""Read-only sanitized WS outage inventory; never a live candle repair writer.

Optional retrospective checks invoke the existing pinned #330 native reader in
an isolated process. A caller JSON object is never accepted as archive proof.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

STEP = 900_000
MAX_RECEIPTS = 10000
MAX_RECEIPT_BYTES = 256 * 1024
MAX_WINDOW_SLOTS = 10080
MAX_ARCHIVE_CHECKS = 16
WAREHOUSE_COMMIT = '5df7f6c9e0d6448db6aa700fa80158b443c5b3db'


def need(ok, code):
    if not ok:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def safe_file(path, maximum):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
         'GAP_EVIDENCE_FILE_REQUIRED')
    need(path.stat().st_size <= maximum, 'GAP_EVIDENCE_BOUND')
    return path


def inventory(receipts, *, start_ms, end_ms, as_of_ms):
    """Enumerate closed slots only, verifying native receipt hashes and chain.

    end_ms is exclusive and explicitly bounded by the caller's observation
    cutoff. Missing slots beyond the latest authentic receipt are expected
    outage slots, not a claim that later capture has been confirmed.
    """
    need(all(type(x) is int and x >= 0 for x in (start_ms,end_ms,as_of_ms))
         and start_ms % STEP == end_ms % STEP == 0 and start_ms < end_ms <= as_of_ms
         and (end_ms-start_ms)//STEP <= MAX_WINDOW_SLOTS, 'GAP_WINDOW_BOUND_OR_FUTURE')
    root = Path(receipts)
    need(root.is_dir() and not root.is_symlink(), 'GAP_RECEIPT_DIRECTORY_REQUIRED')
    paths = []
    for path in root.glob('*.json'):
        need(len(paths) < MAX_RECEIPTS, 'GAP_RECEIPT_CENSUS_BOUND')
        need(re.fullmatch(r'[0-9]+\.json',path.name) is not None,
             'GAP_RECEIPT_NAME_NOT_ALLOWLISTED')
        paths.append(safe_file(path,MAX_RECEIPT_BYTES))
    paths.sort(key=lambda p:int(p.stem))
    # Validate the complete filename allowlist before importing the larger
    # consumer stack or attempting any receipt interpretation.
    from tools.atlas_live_research_cycle import read_service_receipt
    previous = None
    accepted = {}
    for path in paths:
        try:
            row = read_service_receipt(path)
            slot = row['observation']['slot']
            close = slot + STEP
            obs = row['observation']
            need(type(slot) is int and slot >= 0 and slot % STEP == 0,
                 'GAP_RECEIPT_SLOT')
            need(all(type(obs.get(k)) is int for k in ('event_ms','received_ms','committed_ms'))
                 and close <= obs['event_ms'] <= obs['received_ms'] + 250
                 and obs['received_ms'] <= obs['committed_ms'] <= as_of_ms,
                 'GAP_RECEIPT_TIME_OR_FUTURE')
            need(row.get('retention') == 'SANITIZED_RECEIPTS_ONLY'
                 and row.get('scientific') == 'REAL_PIT_OOS_BLOCKED', 'GAP_LIVE_RECEIPT_CLASS')
            need(row.get('previous_sha256') == (previous['sha256'] if previous else None),
                 'GAP_RECEIPT_CHAIN')
            expected_missing = (slot-previous['observation']['slot'])//STEP-1 if previous else 0
            need(expected_missing >= 0 and row['missing_slots'] == expected_missing,
                 'GAP_RECEIPT_SEQUENCE')
        except (KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
            raise ValueError('GAP_RECEIPT_MALFORMED') from exc
        accepted[slot] = row
        previous = row
    latest = max(accepted,default=None)
    missing = []
    for slot in range(start_ms,end_ms,STEP):
        if slot not in accepted:
            missing.append(dict(open_ms=slot,close_exclusive_ms=slot+STEP,
                live_status='MISSING',retrospective_status='MISSING',
                source_class='LIVE_CAPTURE',native_market_bytes_retained=False,
                evidence_scope='WITHIN_CONFIRMED_CAPTURE' if latest is not None and slot < latest
                               else 'EXPECTED_CLOSED_SLOT_AFTER_LAST_RECEIPT',
                consumer_eligibility='WAIT_LIVE_SOURCE_GAP',repair=None))
    body = dict(schema='atlas.ws.gap-inventory.v1',window=[start_ms,end_ms],as_of_ms=as_of_ms,
        latest_confirmed_capture_open_ms=latest,receipt_count=len(accepted),
        receipt_head_sha256=previous['sha256'] if previous else None,
        live_missing_slots=len(missing),gaps=missing,source_class='LIVE_CAPTURE',
        retention='SANITIZED_RECEIPTS_ONLY',historical_repair_lane='RETROSPECTIVE_NON_PIT',
        native_core_scanner_admission='WAIT_AUTHENTICATED_PARENTS',
        scientific='REAL_PIT_OOS_BLOCKED',orders=0,trading_authority='NONE')
    return {**body,'sha256':digest(body)}


# Fixed code imports only the pinned existing implementation. No writes,
# downloads, scheduler calls, raw market output or source materialization.
_NATIVE_READ = r'''
import json,sys,hashlib,re
from pathlib import Path
checkout,root,start,end,cutoff,fixture=sys.argv[1:]
sys.path[:0]=[str(Path(checkout)/'src'),checkout]
from aql.warehouse.engine import HistoricalWarehouse
w=HistoricalWarehouse(Path(root),test_root=fixture=='fixture',**({'reserve':0} if fixture=='fixture' else {}))
try:
 r=w.query('15m',int(start),int(end),cutoff_ms=int(cutoff),max_bars=1,include_registry=True)
 b=r['bars'][0]
 body=dict(status='RECOVERED_FROM_VERIFIED_ARCHIVE',source_class=b['source_class'],
           open_ms=b['open_ms'],close_exclusive_ms=b['close_exclusive_ms'],
           available_at_ms=b['available_at_ms'],snapshot_sha256=r['registry']['snapshot_sha256'],
           event_watermark=r['registry']['event_watermark'],constituent_sha256=b['constituent_sha256'])
except (ValueError,OSError,KeyError) as exc:
 reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
 body=dict(status='MISSING' if reason=='SOURCE_GAP' else 'QUARANTINED',reason=reason)
 if reason=='SOURCE_GAP':
  from aql.warehouse.source import KEY,archive_window
  rejected=list(w.path('quarantine').glob('*.json'))
  if len(rejected)>4096:raise ValueError('ARCHIVE_QUARANTINE_CENSUS_BOUND')
  for path in rejected:
   if path.stat().st_size>8*1024*1024:raise ValueError('ARCHIVE_QUARANTINE_OBJECT_BOUND')
   raw=path.read_bytes()
   if hashlib.sha256(raw).hexdigest()!=path.stem:raise ValueError('ARCHIVE_QUARANTINE_PIN')
   x=json.loads(raw);key=x.get('key',x.get('source_key',''))
   if not KEY.fullmatch(key):continue
   a,b=archive_window(key)
   if a<=int(start) and int(end)<=b:
    body.update(status='QUARANTINED',reason='QUARANTINED_NATIVE_ARCHIVE_CANDIDATE',
                quarantine_evidence_sha256=path.stem)
  latest=None
  paths=list(w.path('catalog').glob('*.json'))
  if len(paths)>10000:raise ValueError('ARCHIVE_LISTING_CENSUS_BOUND')
  for path in paths:
   if not re.fullmatch('[0-9a-f]{64}',path.stem):continue
   if path.stat().st_size>8*1024*1024:raise ValueError('ARCHIVE_LISTING_OBJECT_BOUND')
   raw=path.read_bytes();x=json.loads(raw)
   if x.get('schema')!='aql.warehouse.source-listing.v1':continue
   if hashlib.sha256(raw).hexdigest()!=path.stem:raise ValueError('ARCHIVE_LISTING_PIN')
   if latest is None or x['observed_ms']>latest['observed_ms']:latest=x
  if latest is not None and latest['observed_ms']>=int(end):
   present=any(x['start_ms']<=int(start) and int(end)<=x['end_ms'] for x in latest['archives'])
   if not present and body['status']=='MISSING':body.update(status='SOURCE_NOT_YET_PUBLISHED',publisher_listing_as_of_ms=latest['observed_ms'])
body['verification_scope']='GENERATED_NATIVE_FIXTURE' if fixture=='fixture' else 'NATIVE_LOCAL_READ_NOT_EXTERNAL_CUSTODY_ATTESTED'
print(json.dumps(body,sort_keys=True))
'''


class NativeArchiveReader:
    """Explicit optional readback, bound to existing reviewed warehouse commit."""
    def __init__(self, checkout, root, *, _fixture=False):
        self.checkout = Path(checkout).resolve()
        self.root = Path(root).resolve()
        self.fixture = _fixture
        need(self.checkout.is_dir() and self.root.is_dir(),'ARCHIVE_READER_PATHS_REQUIRED')
        head = subprocess.run(['git','-C',str(self.checkout),'rev-parse','HEAD'],
                              check=True,capture_output=True,text=True,timeout=10).stdout.strip()
        need(head == WAREHOUSE_COMMIT,'ARCHIVE_READER_EXACT_COMMIT')
        clean = subprocess.run(['git','-C',str(self.checkout),'status','--porcelain',
                                '--untracked-files=all','--','src/aql','research_wp_r0'],
                               check=True,capture_output=True,text=True,timeout=10).stdout
        need(not clean,'ARCHIVE_READER_CODE_MODIFIED')
        if not _fixture:
            need(os.name=='nt' and str(self.root).casefold()==r'E:\ATLAS\DataWarehouse'.casefold(),
                 'ARCHIVE_READER_APPROVED_ROOT_REQUIRED')

    def read(self, start_ms, end_ms, cutoff_ms):
        need(end_ms-start_ms == STEP and start_ms % STEP == 0 and end_ms <= cutoff_ms,
             'ARCHIVE_READER_WINDOW')
        try:
            result = subprocess.run([sys.executable,'-I','-B','-c',_NATIVE_READ,str(self.checkout),
                str(self.root),str(start_ms),str(end_ms),str(cutoff_ms),'fixture' if self.fixture else 'native'],
                cwd=self.checkout,capture_output=True,text=True,timeout=120)
        except subprocess.TimeoutExpired:
            return dict(status='QUARANTINED',reason='ARCHIVE_READ_TIMEOUT_NO_COVERAGE_ATTESTED')
        need(result.returncode==0,'ARCHIVE_READER_PROCESS_FAILED')
        need(len(result.stdout.encode()) <= 65536,'ARCHIVE_READER_RESPONSE_BOUND')
        row = json.loads(result.stdout)
        need(row.get('status') in ('RECOVERED_FROM_VERIFIED_ARCHIVE','MISSING','SOURCE_NOT_YET_PUBLISHED','QUARANTINED'),
             'ARCHIVE_READER_RESPONSE')
        if row['status']=='RECOVERED_FROM_VERIFIED_ARCHIVE':
            need(row.get('source_class')=='RETROSPECTIVE_NON_PIT'
                 and row.get('open_ms')==start_ms and row.get('close_exclusive_ms')==end_ms
                 and type(row.get('available_at_ms')) is int and end_ms <= row['available_at_ms'] <= cutoff_ms
                 and re.fullmatch('[0-9a-f]{64}',row.get('snapshot_sha256','')) is not None,
                 'ARCHIVE_READER_PROVENANCE')
        return row


def reconcile(report, reader, *, max_checks=0):
    """Append qualified retrospective coverage; never change LIVE MISSING."""
    need(type(max_checks) is int and 0 <= max_checks <= MAX_ARCHIVE_CHECKS,'ARCHIVE_CHECK_BOUND')
    need(type(reader) is NativeArchiveReader,'NATIVE_ARCHIVE_READER_REQUIRED')
    result = json.loads(json.dumps(report))
    need(result.pop('sha256') == digest(result),'GAP_INVENTORY_PIN')
    for item in result['gaps'][:max_checks]:
        row = reader.read(item['open_ms'],item['close_exclusive_ms'],result['as_of_ms'])
        item['retrospective_status'] = row['status']
        item['repair'] = row
        # Even verified archive coverage is not an original forward observation.
        item['consumer_eligibility'] = 'WAIT_AUTHENTICATED_PARENTS'
    result['archive_checks_performed'] = min(max_checks,len(result['gaps']))
    result['archive_checks_remaining'] = max(0,len(result['gaps'])-max_checks)
    result['sha256'] = digest(result)
    return result


def owner_reported_outage():
    """Static reported facts; no private receipts or root cause are fabricated."""
    body = dict(schema='atlas.ws.owner-reported-outage.v1',evidence_grade='OWNER_REPORTED_LOCAL',
        diagnostic_riyadh='2026-11-22T08:38:59+03:00',task_state='Ready',hold=True,
        hold_reason='PILOT_STOP_TimeoutError',last_receipt_riyadh='2026-11-21T14:00:00.116+03:00',
        root_cause='ROOT_CAUSE_NOT_PROVEN',missing_evidence=[
            'second failure receive_phase and deadline_origin','original exception cause chain',
            'hash-verified private receipt inventory and health trace'],
        coverage_status='MISSING_PRIVATE_RECEIPT_INVENTORY_NOT_INDEPENDENTLY_ATTESTED',
        archive_repair_status='DEFERRED_NO_ORIGINAL_SOURCE_ACQUISITION_AUTHORITY',
        orders=0,trading_authority='NONE')
    return {**body,'sha256':digest(body)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipts',type=Path)
    parser.add_argument('--start-ms',type=int)
    parser.add_argument('--end-ms',type=int)
    parser.add_argument('--as-of-ms',type=int)
    parser.add_argument('--reported-outage',action='store_true')
    parser.add_argument('--warehouse-checkout',type=Path)
    parser.add_argument('--warehouse-root',type=Path)
    parser.add_argument('--max-archive-checks',type=int,default=0)
    args=parser.parse_args()
    if args.reported_outage:
        result=owner_reported_outage()
    else:
        need(args.receipts is not None,'GAP_RECEIPT_DIRECTORY_REQUIRED')
        result=inventory(args.receipts,start_ms=args.start_ms,end_ms=args.end_ms,as_of_ms=args.as_of_ms)
        if args.max_archive_checks:
            need(args.warehouse_checkout is not None and args.warehouse_root is not None,
                 'EXPLICIT_ARCHIVE_PATHS_REQUIRED')
            result=reconcile(result,NativeArchiveReader(args.warehouse_checkout,args.warehouse_root),
                             max_checks=args.max_archive_checks)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':
    main()

