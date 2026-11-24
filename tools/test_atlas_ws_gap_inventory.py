"""Offline native receipt/read seam; no socket, source download or owner E: access."""
from datetime import datetime,timezone
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from aql.observation.contracts import digest as production_digest
from tools import atlas_ws_gap_inventory as gaps

START=1704067200000
STEP=gaps.STEP


def receipt(root, slot, previous=None, *, available=None):
    end=slot+STEP
    row=dict(slot=slot,event_ms=end,received_ms=end+1,committed_ms=end+2,
             plan_sha256='1'*64,payload_sha256='2'*64,source_sha256='3'*64,
             ack_sha256='4'*64,scanner_sha256='5'*64,state='UNKNOWN')
    row['receipt_sha256']=production_digest(row)
    factory=dict(orders_enabled=False,secretary_enqueued=False,status='FIXTURE_ONLY')
    factory['sha256']=production_digest(factory)
    body=dict(schema='atlas.live-research-service.receipt.v1',plan_sha256=row['plan_sha256'],
              observation=row,factory=factory,previous_sha256=previous['sha256'] if previous else None,
              missing_slots=(slot-previous['observation']['slot'])//STEP-1 if previous else 0,
              retention='SANITIZED_RECEIPTS_ONLY',scientific='REAL_PIT_OOS_BLOCKED',
              current_entry='NO_CURRENT_ENTRY',secretary='WAIT',dispatch=None,telegram='NOT_SENT',orders=0)
    body['sha256']=production_digest(body)
    path=root/f'{slot}.json';path.write_text(json.dumps(body))
    return body


class InventoryTests(unittest.TestCase):
    def test_existing_native_receipt_chain_keeps_confirmed_and_outage_gaps_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=receipt(root,START);receipt(root,START+2*STEP,a)
            r=gaps.inventory(root,start_ms=START,end_ms=START+4*STEP,as_of_ms=START+4*STEP+1)
            self.assertEqual([x['open_ms'] for x in r['gaps']],[START+STEP,START+3*STEP])
            self.assertEqual([x['evidence_scope'] for x in r['gaps']],
                ['WITHIN_CONFIRMED_CAPTURE','EXPECTED_CLOSED_SLOT_AFTER_LAST_RECEIPT'])
            self.assertEqual(r['native_core_scanner_admission'],'WAIT_AUTHENTICATED_PARENTS')
            self.assertEqual(r['retention'],'SANITIZED_RECEIPTS_ONLY')

    def test_future_window_and_future_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt(root,START)
            with self.assertRaisesRegex(ValueError,'WINDOW_BOUND_OR_FUTURE'):
                gaps.inventory(root,start_ms=START,end_ms=START+STEP,as_of_ms=START)
            with self.assertRaisesRegex(ValueError,'RECEIPT_TIME_OR_FUTURE'):
                gaps.inventory(root,start_ms=START,end_ms=START+STEP,as_of_ms=START+STEP)

    def test_corruption_missing_chain_parent_and_overlap_rejected(self):
        for failure in ('tamper','missing_parent','overlap'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);a=receipt(root,START);b=receipt(root,START+2*STEP,a)
                if failure=='tamper':
                    path=root/f'{START}.json';x=json.loads(path.read_text());x['orders']=1;path.write_text(json.dumps(x))
                elif failure=='missing_parent':(root/f'{START}.json').unlink()
                else:
                    # Same logical slot under another filename is not a second valid receipt.
                    (root/f'{START+STEP}.json').write_text(json.dumps(b))
                with self.assertRaises(ValueError):
                    gaps.inventory(root,start_ms=START,end_ms=START+3*STEP,as_of_ms=START+4*STEP)

    def test_unverified_caller_json_is_not_archive_authority(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_ARCHIVE_READER_REQUIRED'):
            gaps.reconcile({},object(),max_checks=1)

    def test_month_day_boundary_no_source_yet_and_input_is_immutable(self):
        midnight=1706745600000 # 2024-02-01 UTC
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt(root,midnight-2*STEP)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            report=gaps.inventory(root,start_ms=midnight-2*STEP,end_ms=midnight+STEP,
                                  as_of_ms=midnight+2*STEP)
            self.assertEqual([x['open_ms'] for x in report['gaps']],[midnight-STEP,midnight])
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})

    def test_reported_owner_outage_has_no_invented_source_or_root_cause(self):
        r=gaps.owner_reported_outage()
        self.assertEqual(r['root_cause'],'ROOT_CAUSE_NOT_PROVEN')
        self.assertEqual(r['evidence_grade'],'OWNER_REPORTED_LOCAL')
        self.assertNotIn('gap_count',r)
        self.assertIn('NOT_INDEPENDENTLY_ATTESTED',r['coverage_status'])


@unittest.skipUnless(os.environ.get('ATLAS_WAREHOUSE_FIXTURE_CHECKOUT'),'pinned native warehouse fixture checkout required')
class NativeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tree=Path(os.environ['ATLAS_WAREHOUSE_FIXTURE_CHECKOUT']).resolve()
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'warehouse';self.root.mkdir()
        # Isolated native production importer, generated 1m input, 15m projection.
        code=r'''
import sys,json,hashlib
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
sys.path[:0]=[str(Path(sys.argv[1])/'src'),sys.argv[1]]
from aql.warehouse.engine import HistoricalWarehouse
from aql.warehouse.storage import canonical,seal
root=Path(sys.argv[2]);start=int(sys.argv[3]);mode=sys.argv[4]
w=HistoricalWarehouse(root,reserve=0,test_root=True)
key='data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip'
lines=[]
for i in range(15):
 t=start+i*60000;lines.append(f'{t},1,2,1,1,3,{t+59999},4,1,2,3,0')
z=BytesIO()
with ZipFile(z,'w',ZIP_DEFLATED) as f:f.writestr('BTCUSDT-1m-2024-01-01.csv','\n'.join(lines)+'\n')
raw=z.getvalue();check=(seal(raw)+'  BTCUSDT-1m-2024-01-01.zip\n').encode()
with w.writer():
 if mode=='invalid':
  bad=BytesIO()
  with ZipFile(bad,'w',ZIP_DEFLATED) as f:f.writestr('BTCUSDT-1m-2024-01-01.csv',lines[0].replace(str(start+59999),str(start+20000))+'\n')
  rejected=bad.getvalue();rejected_check=(seal(rejected)+'  BTCUSDT-1m-2024-01-01.zip\n').encode()
  try:w.import_archive(rejected,rejected_check,key,observed_ms=start+86400000)
  except ValueError:pass
 elif mode=='partial':
  w.write_once('raw/'+seal(raw)+'.part',raw[:10]);w.rebuild_registry()
 elif mode!='unpublished':w.import_archive(raw,check,key,observed_ms=start+86400000)
 else:
  w.document('catalog',dict(schema='aql.warehouse.source-listing.v1',observed_ms=start+86400000,archives=[]))
  w.rebuild_registry()
if mode=='corrupt':
 path=w.path('raw/'+seal(raw)+'.zip');path.write_bytes(path.read_bytes()+b'broken')
'''
        self.code=code

    def tearDown(self):self.temp.cleanup()

    def prepare(self,mode='good'):
        subprocess.run([sys.executable,'-I','-B','-c',self.code,str(self.tree),str(self.root),str(START),mode],check=True,capture_output=True,text=True)
        return gaps.NativeArchiveReader(self.tree,self.root,_fixture=True)

    def test_actual_native_query_keeps_live_gap_and_qualified_retro_repair(self):
        reader=self.prepare()
        with tempfile.TemporaryDirectory() as tmp:
            report=gaps.inventory(Path(tmp),start_ms=START,end_ms=START+STEP,as_of_ms=START+86400000)
            r=gaps.reconcile(report,reader,max_checks=1)
            item=r['gaps'][0]
            self.assertEqual(item['live_status'],'MISSING')
            self.assertEqual(item['retrospective_status'],'RECOVERED_FROM_VERIFIED_ARCHIVE')
            self.assertEqual(item['repair']['source_class'],'RETROSPECTIVE_NON_PIT')
            self.assertEqual(item['repair']['verification_scope'],'GENERATED_NATIVE_FIXTURE')
            self.assertEqual(item['consumer_eligibility'],'WAIT_AUTHENTICATED_PARENTS')
            self.assertEqual(item['repair']['available_at_ms'],START+86400000)
            self.assertEqual(report['gaps'][0]['retrospective_status'],'MISSING')

    def test_native_read_timeout_has_no_false_coverage(self):
        reader=self.prepare()
        with patch.object(gaps.subprocess,'run',side_effect=subprocess.TimeoutExpired('fixed native query',120)):
            row=reader.read(START,START+STEP,START+86400000)
        self.assertEqual(row['status'],'QUARANTINED')
        self.assertEqual(row['reason'],'ARCHIVE_READ_TIMEOUT_NO_COVERAGE_ATTESTED')

    def test_invalid_candidate_and_partial_download_stay_unrepaired(self):
        reader=self.prepare('invalid')
        row=reader.read(START,START+STEP,START+86400000)
        self.assertEqual(row['status'],'QUARANTINED')
        self.assertEqual(row['reason'],'QUARANTINED_NATIVE_ARCHIVE_CANDIDATE')
        self.temp.cleanup();self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'warehouse';self.root.mkdir()
        reader=self.prepare('partial')
        self.assertEqual(reader.read(START,START+STEP,START+86400000)['status'],'MISSING')

    def test_unpublished_and_corrupt_original_not_misreported_as_repaired(self):
        reader=self.prepare('unpublished')
        self.assertEqual(reader.read(START,START+STEP,START+86400000)['status'],'SOURCE_NOT_YET_PUBLISHED')
        # Separate fresh generated store for mismatch, original query verifies raw seal.
        self.temp.cleanup();self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'warehouse';self.root.mkdir()
        reader=self.prepare('corrupt')
        self.assertEqual(reader.read(START,START+STEP,START+86400000)['status'],'QUARANTINED')


if __name__=='__main__':unittest.main()
