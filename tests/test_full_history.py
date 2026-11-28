"""Generated fixtures only; no historical bulk acquisition on CI runners."""
from pathlib import Path
import json

import pytest

from aql.warehouse import full_history as fh
from aql.warehouse import runner
from aql.warehouse.storage import canonical,seal
from tests.test_warehouse import fixture,warehouse,START,DAY,KEY,AUTH


def source_object(key=KEY,start=START,end=START+DAY,raw=None):
    return dict(key=key,size=len(raw) if raw else 100,start_ms=start,end_ms=end)


class Source:
    authority=AUTH
    def __init__(self,listing,objects):self.listing=listing;self.objects=objects;self.calls=[]
    def discover(self,now_ms):return self.listing
    def acquire(self,w,key,expected_size):
        self.calls.append(key)
        raw,checksum=self.objects[key]
        return w.write_once(f'raw/{seal(raw)}.zip',raw),checksum


def test_unchanged_daily_source_covers_first_native_inception_without_repeat(tmp_path):
    start=START+4*3600000
    raw,checksum=fixture(start,KEY,count=1200)
    w=warehouse(tmp_path)
    with w.writer():w.import_archive(raw,checksum,KEY,observed_ms=START+DAY)
    s=Source([source_object(raw=raw)],{})
    report=runner.run(w,s,now_ms=START+DAY)
    assert s.calls == [] and report['one_minute_rows'] == 1200
    assert report['acquisition_plan_exhausted'] and report['full_history_verified']
    assert report['stored_first_open_ms'] == start


def test_known_approved_gap_is_not_retried_as_daily_repair(tmp_path,monkeypatch):
    gap=[START+60000,START+120000]
    month=KEY.replace('/daily/','/monthly/').replace('2024-01-01.zip','2024-01.zip')
    raw,checksum=fixture(START,month,missing=(1,))
    w=warehouse(tmp_path)
    with w.writer():w.import_archive(raw,checksum,month,observed_ms=START+31*DAY)
    monkeypatch.setattr(runner,'admitted_gap_ranges',lambda *a:[gap])
    s=Source([source_object(month,START,START+31*DAY,raw),source_object()],{})
    # The month is deliberately partial after its first day; reconcile its
    # retained original, but never request the known-gap daily placeholder.
    report=runner.run(w,s,now_ms=START+31*DAY)
    assert s.calls == [] and report['internal_gaps'] == [gap]
    assert not report['full_history_verified']


def test_unapproved_missing_minute_still_requests_original_daily_source(tmp_path):
    month=KEY.replace('/daily/','/monthly/').replace('2024-01-01.zip','2024-01.zip')
    raw,checksum=fixture(START,month,missing=(1,))
    daily,daily_check=fixture()
    w=warehouse(tmp_path)
    with w.writer():w.import_archive(raw,checksum,month,observed_ms=START+31*DAY)
    s=Source([source_object(month,START,START+31*DAY,raw),source_object(raw=daily)],{KEY:(daily,daily_check)})
    report=runner.run(w,s,now_ms=START+31*DAY)
    assert s.calls == [KEY] and report['one_minute_rows'] == 1440
    assert not report['internal_gaps']


def test_bounded_run_does_not_report_unattempted_partitions_complete(tmp_path):
    raw,checksum=fixture()
    key2=KEY.replace('2024-01-01','2024-01-02')
    raw2,check2=fixture(START+DAY,key2)
    s=Source([source_object(raw=raw),source_object(key2,START+DAY,START+2*DAY,raw2)],{KEY:(raw,checksum),key2:(raw2,check2)})
    events=[]
    result=runner.run(warehouse(tmp_path),s,now_ms=START+2*DAY,archive_limit=1,progress=events.append)
    assert not result['acquisition_plan_exhausted']
    assert result['pending_source_partitions'] == [key2]
    assert events[0]['event'] == 'SOURCE_LISTING_READY' and [e for e in events if e['event']=='ARCHIVE_IMPORTED'][-1]['inserted_rows'] == 1440


def test_authority_reused_from_exact_pinned_snapshot_without_secrets_in_output(tmp_path):
    w=warehouse(tmp_path)
    with w.writer():
        w.document('catalog',dict(schema='aql.warehouse.source-listing.v1',authority=AUTH,archives=[]))
    recovered=fh.existing_authority(w)
    assert all(recovered[k] == AUTH[k] for k in AUTH)
    assert recovered['full_history_continuation_ref'] == fh.CONTINUATION


def test_authority_ambiguity_or_tamper_is_not_silently_accepted(tmp_path):
    w=warehouse(tmp_path)
    with w.writer():
        a=w.document('catalog',dict(schema='aql.warehouse.source-listing.v1',authority=AUTH,archives=[]))
        w.document('catalog',dict(schema='aql.warehouse.source-listing.v1',authority={**AUTH,'source_rights_ref':'OTHER'},archives=[]))
    with pytest.raises(ValueError,match='UNIQUE_RETAINED'):
        fh.existing_authority(w)
    a.write_bytes(a.read_bytes()+b' ')
    with pytest.raises(ValueError,match='SNAPSHOT_PIN'):
        fh.existing_authority(w)


def test_import_clock_is_receipt_time_not_listing_time(tmp_path):
    raw,checksum=fixture()
    s=Source([source_object(raw=raw)],{KEY:(raw,checksum)})
    w=warehouse(tmp_path)
    runner.run(w,s,now_ms=START+DAY,clock_ms=lambda:START+2*DAY)
    row=w._existing(START)[0]
    assert row['available_at_ms'] == START+2*DAY


def test_clock_regression_is_a_scoped_failure_and_imports_no_bars(tmp_path):
    raw,checksum=fixture();s=Source([source_object(raw=raw)],{KEY:(raw,checksum)})
    result=runner.run(warehouse(tmp_path),s,now_ms=START+DAY,clock_ms=lambda:START+DAY-1)
    assert result['failures'][0]['reason'] == 'BACKFILL_CLOCK_REGRESSION'
    assert result['one_minute_rows'] == 0


def test_full_driver_reports_declared_gap_and_prefix_preservation(tmp_path,monkeypatch):
    from aql.warehouse.september_correction import GAP
    w=warehouse(tmp_path)
    raw,checksum=fixture()
    s=Source([source_object(raw=raw)],{KEY:(raw,checksum)})
    with w.writer():pass
    before={'august':{'rows':21360},'september':{'rows':42780}}
    monkeypatch.setattr(fh,'protected_snapshot',lambda *a:before)
    monkeypatch.setattr(fh,'admitted_gap_ranges',lambda *a:[GAP])
    # Test driver status mapping with a real confined report/receipt writer;
    # actual prefix hashes and source policy are tested by the correction suite.
    def actual_run(w,s,**kw):
        with w.writer():
            w.import_archive(raw,checksum,KEY,observed_ms=START+DAY)
        result=w.report()
        return {**result,'internal_gaps':[GAP],'failures':[],
                'acquisition_plan_exhausted':True,'latest_published_close_reached':True}
    monkeypatch.setattr(fh,'run',actual_run)
    report=fh.continue_history(w,s,clock_ms=lambda:START+DAY)
    assert report['status'] == 'PUBLISHED_PARTITIONS_IMPORTED_WITH_DECLARED_420_MINUTE_GAP'
    assert report['accepted_prefix_unchanged'] and report['all_published_partitions_ingested']
    assert not report['full_history_verified']


def test_full_driver_stops_if_accepted_prefix_changes(tmp_path,monkeypatch):
    from aql.warehouse.september_correction import GAP
    w=warehouse(tmp_path)
    with w.writer():pass
    states=iter([{'rows':64140},{'rows':64141}])
    monkeypatch.setattr(fh,'protected_snapshot',lambda *a:next(states))
    monkeypatch.setattr(fh,'admitted_gap_ranges',lambda *a:[GAP])
    monkeypatch.setattr(fh,'run',lambda *a,**kw:{'failures':[]})
    with pytest.raises(ValueError,match='ACCEPTED_PREFIX_CHANGED'):
        fh.continue_history(w,Source([],{}),clock_ms=lambda:START+DAY)


def test_new_invalid_source_stops_with_native_field_evidence(tmp_path):
    from tests.test_warehouse_september import native,ROW
    row=list(ROW);row[6]='1504713600000'
    key='data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2017-09.zip'
    raw,checksum=native(row,key)
    s=Source([source_object(key,1504224000000,1506816000000,raw)],{key:(raw,checksum)})
    result=runner.run(warehouse(tmp_path),s,now_ms=1506816000000)
    assert result['status'] == 'RUN_BLOCKED' and len(s.calls) == 1
    assert result['failures'][0]['native_diagnostic']['first_failure']['predicates'][0]['field'] == 6
    assert result['one_minute_rows'] == 0 and not result['acquisition_plan_exhausted']


# Real confined driver integration on the generated approved-prefix cohort.
from tests.test_september_correction import generated_source,policy,initialize


def test_full_driver_three_archives_checkpoint_preserves_accepted_prefix(policy,tmp_path,monkeypatch):
    from aql.warehouse import september_correction as sc
    w=warehouse(tmp_path);initialize(w,policy,monkeypatch)
    sc.apply_correction(w,observed_ms=sc.END)
    monkeypatch.setattr(fh,'AUGUST_SHARDS',sc._august_snapshot(w)['shard_sha256'])
    before=fh.protected_snapshot(w)
    listing=[];objects={}
    for n in range(1,4):
        key=sc.SEPT_KEY.replace('/monthly/','/daily/').replace('2017-09.zip',f'2017-10-{n:02d}.zip')
        opened=sc.END+(n-1)*DAY
        raw,checksum=fixture(opened,key)
        listing.append(source_object(key,opened,opened+DAY,raw));objects[key]=(raw,checksum)
    events=[]
    report=fh.continue_history(w,Source(listing,objects),clock_ms=lambda:sc.END+3*DAY,progress=events.append)
    assert report['all_published_partitions_ingested'] and report['accepted_prefix_unchanged']
    assert report['one_minute_rows'] == 68460
    assert fh.protected_snapshot(w) == before
    assert report['internal_gaps'] == [sc.GAP] and not report['full_history_verified']
    checkpoints=[]
    for p in (tmp_path/'receipts').glob('*.json'):
        body=json.loads(p.read_bytes())
        if body.get('schema') == 'aql.warehouse.full-history-checkpoint.v1':checkpoints.append(body)
    assert len(checkpoints) == 1 and checkpoints[0]['archives_this_run'] == 3
    assert len([e for e in events if e['event']=='ARCHIVE_IMPORTED']) == 3
