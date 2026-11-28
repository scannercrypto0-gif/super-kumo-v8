"""Source obstacles may be deferred; committed-data failures must stop."""
from io import BytesIO
from urllib.error import URLError
from zipfile import ZipFile, ZIP_DEFLATED
import pytest
from aql.warehouse import resilient, runner
from aql.warehouse.storage import seal
from tests.test_full_history import Source, source_object
from tests.test_warehouse import fixture, warehouse, START, DAY, KEY
MONTH = KEY.replace('/daily/','/monthly/').replace('2024-01-01.zip','2024-01.zip')


def malformed(key, start=START):
    raw, _ = fixture(start,key,count=2)
    with ZipFile(BytesIO(raw)) as z:text=z.read(z.namelist()[0]).decode()
    lines=text.splitlines();r=lines[0].split(',');r[6]=str(start+20798);lines[0]=','.join(r)
    r=lines[1].split(',');r[0]=str(start+80799);r[6]=str(start+140798);lines[1]=','.join(r)
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:z.writestr(key.rsplit('/',1)[1][:-4]+'.csv','\n'.join(lines)+'\n')
    raw=out.getvalue();return raw,(seal(raw)+'  '+key.rsplit('/',1)[1]+'\n').encode()


def invoke(w,s,**kw):
    return resilient.run(w,s,now_ms=START+32*DAY,archive_limit=100,sleep=lambda seconds:None,**kw)


def two_days(bad=True):
    raw,c=malformed(KEY) if bad else fixture()
    k2=KEY.replace('2024-01-01','2024-01-02');r2,c2=fixture(START+DAY,k2)
    return [source_object(raw=raw),source_object(k2,START+DAY,START+2*DAY,r2)],{KEY:(raw,c),k2:(r2,c2)},k2


def test_bad_month_falls_back_and_continues_later_period(tmp_path):
    bad,check=malformed(MONTH);good,c=fixture()
    feb=KEY.replace('2024-01-01','2024-02-01');later,lc=fixture(START+31*DAY,feb)
    s=Source([source_object(MONTH,START,START+31*DAY,bad),source_object(raw=good),source_object(feb,START+31*DAY,START+32*DAY,later)],{MONTH:(bad,check),KEY:(good,c),feb:(later,lc)})
    w=warehouse(tmp_path);events=[];r=invoke(w,s,progress=events.append)
    assert s.calls==[MONTH,KEY,feb] and r['one_minute_rows']==2880
    assert r['latest_published_close_reached'] and not r['failures'] and r['source_scan_exhausted']
    assert r['pending_source_partitions']==[MONTH]
    assert r['source_obstacles'][0]['failed_rows']==2
    assert w.path('raw/'+seal(bad)+'.zip').read_bytes()==bad
    assert not w.path('catalog/'+seal(bad)+'.json').exists()
    assert any(e['event']=='SOURCE_DEFERRED' for e in events) and not r['full_history_verified']


def test_failed_day_does_not_block_or_disappear_from_pending(tmp_path):
    listing,objects,k2=two_days();r=invoke(warehouse(tmp_path),Source(listing,objects))
    assert r['one_minute_rows']==1440 and r['pending_source_partitions']==[KEY]
    assert len(r['unresolved_source_obstacles'])==1 and not r['acquisition_plan_exhausted']
    assert not r['unresolved_source_obstacles'][0]['coverage_restored']


def test_daily_originals_can_fully_resolve_rejected_month(tmp_path):
    bad,bc=malformed(MONTH);listing=[source_object(MONTH,START,START+31*DAY,bad)];objects={MONTH:(bad,bc)}
    for n in range(31):
        key=KEY.replace('2024-01-01',f'2024-01-{n+1:02d}');raw,c=fixture(START+n*DAY,key)
        listing.append(source_object(key,START+n*DAY,START+(n+1)*DAY,raw));objects[key]=(raw,c)
    r=invoke(warehouse(tmp_path),Source(listing,objects))
    assert r['acquisition_plan_exhausted'] and not r['pending_source_partitions']
    assert not r['unresolved_source_obstacles'] and len(r['resolved_source_obstacles'])==1
    assert r['resolved_source_obstacles'][0]['resolution']=='VERIFIED_ALTERNATIVE_COVERAGE'
    assert r['one_minute_rows']==44640


def test_network_final_pass_recovers_without_owner(tmp_path):
    listing,objects,k2=two_days(False)
    class Flaky(Source):
        def acquire(self,w,key,expected_size):
            if key==KEY and self.calls.count(KEY)<3:
                self.calls.append(key);raise URLError('temporary outage')
            return super().acquire(w,key,expected_size)
    s=Flaky(listing,objects);events=[];r=invoke(warehouse(tmp_path),s,progress=events.append)
    assert s.calls==[KEY,KEY,KEY,k2,KEY]
    assert r['one_minute_rows']==2880 and r['acquisition_plan_exhausted']
    assert len(r['resolved_source_obstacles'])==1 and not r['unresolved_source_obstacles']
    assert len([e for e in events if e['event']=='SOURCE_RETRY'])==2


@pytest.mark.parametrize('reason',['WAREHOUSE_BUDGET_EXCEEDED','SOURCE_BAR_CONFLICT','REGISTRY_SOURCE_PIN','PATH_ESCAPE','RETAINED_RAW_CORRUPT'])
def test_import_custody_failures_are_fatal(tmp_path,monkeypatch,reason):
    listing,objects,k2=two_days(False);w=warehouse(tmp_path)
    def fail(*a,**kw):raise ValueError(reason)
    monkeypatch.setattr(w,'import_archive',fail);s=Source(listing,objects);r=invoke(w,s)
    assert s.calls==[KEY] and r['failures'][0]['reason']==reason
    assert not r['source_scan_exhausted'] and r['one_minute_rows']==0


def test_restart_preserves_good_shards_and_bad_original(tmp_path):
    listing,objects,k2=two_days();w=warehouse(tmp_path);first=invoke(w,Source(listing,objects))
    before=w.path('bars/2024-01-02.sqlite').read_bytes();s=Source(listing,objects)
    r=invoke(warehouse(tmp_path),s)
    assert s.calls==[KEY] and r['one_minute_rows']==first['one_minute_rows']==1440
    assert w.path('bars/2024-01-02.sqlite').read_bytes()==before
    assert w.path('raw/'+seal(objects[KEY][0])+'.zip').read_bytes()==objects[KEY][0]


def test_bound_keeps_unattempted_sources_pending(tmp_path):
    listing,objects,k2=two_days();s=Source(listing,objects)
    r=resilient.run(warehouse(tmp_path),s,now_ms=START+2*DAY,archive_limit=1,sleep=lambda seconds:None)
    assert set(r['pending_source_partitions'])=={KEY,k2} and not r['source_scan_exhausted']
    assert s.calls==[KEY]


def test_opt_in_and_clock_regression_stays_fatal(tmp_path):
    raw,c=fixture();s=Source([source_object(raw=raw)],{KEY:(raw,c)})
    r=runner.run(warehouse(tmp_path),s,now_ms=START+DAY,continue_on_source_error=True,clock_ms=lambda:START)
    assert r['failures'][0]['reason']=='BACKFILL_CLOCK_REGRESSION' and r['one_minute_rows']==0


def test_december_original_timestamp_patterns_are_rejected_without_rounding():
    from aql.warehouse.engine import parse_archive
    # Native lines 4681/4682 from the checksum-verified December 2017 ZIP.
    lines=(
        '1512367200000,11476.87000000,11478.00000000,11476.87000000,11478.00000000,0.28948500,1512367220798,3322.46567959,4,0.28948500,3322.46567959,37184.18214844',
        '1512367220799,11478.00000000,11478.00000000,11478.00000000,11478.00000000,0.00000000,1512367280798,0.00000000,0,0.00000000,0.00000000,37184.17978073',
    )
    key='data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2017-12.zip'
    for line in lines:
        out=BytesIO()
        with ZipFile(out,'w',ZIP_DEFLATED) as z:z.writestr('BTCUSDT-1m-2017-12.csv',line+'\n')
        raw=out.getvalue();checksum=(seal(raw)+'  BTCUSDT-1m-2017-12.zip\n').encode()
        with pytest.raises(ValueError,match='NATIVE_TIME_OR_MARKET_FIELDS'):
            parse_archive(raw,checksum,key,1514764800000)


def test_corrupt_checksum_is_isolated_and_next_original_is_imported(tmp_path):
    listing,objects,k2=two_days(False);raw,c=objects[KEY]
    objects[KEY]=(raw,c.replace(seal(raw).encode(),b'0'*64))
    r=invoke(warehouse(tmp_path),Source(listing,objects))
    assert r['one_minute_rows']==1440 and not r['failures']
    assert r['source_obstacles'][0]['reason']=='PUBLISHER_CHECKSUM_MISMATCH'
    assert r['pending_source_partitions']==[KEY]


@pytest.mark.parametrize('reason',['WAREHOUSE_BUDGET_EXCEEDED','PATH_ESCAPE','RETAINED_RAW_CORRUPT','UNKNOWN_PROVIDER_ERROR'])
def test_local_or_unknown_acquisition_errors_stop(tmp_path,reason):
    listing,objects,k2=two_days(False)
    class Unsafe(Source):
        def acquire(self,w,key,expected_size):
            self.calls.append(key);raise ValueError(reason)
    s=Unsafe(listing,objects);r=invoke(warehouse(tmp_path),s)
    assert s.calls==[KEY] and r['failures'][0]['reason']==reason


def test_full_history_reports_quarantined_scan_without_full_completion(tmp_path,monkeypatch):
    from aql.warehouse import full_history as fh
    from aql.warehouse.september_correction import GAP
    w=warehouse(tmp_path)
    with w.writer():pass
    monkeypatch.setattr(fh,'protected_snapshot',lambda w:{'rows':64140})
    monkeypatch.setattr(fh,'admitted_gap_ranges',lambda *a:[GAP])
    def result(*a,**kw):
        assert kw['continue_on_source_error'] is True
        return dict(internal_gaps=[GAP],failures=[],source_scan_exhausted=True,
                    unresolved_source_obstacles=[{'key':KEY}],acquisition_plan_exhausted=False,
                    latest_published_close_reached=True)
    monkeypatch.setattr(fh,'run',result)
    r=fh.continue_history(w,Source([],{}),clock_ms=lambda:START+DAY)
    assert r['status']=='PUBLISHED_SOURCE_SCAN_FINISHED_WITH_QUARANTINED_PARTITIONS'
    assert r['accepted_prefix_unchanged'] and not r['all_published_partitions_ingested']
    assert not r['full_history_verified']


def test_permanent_network_outage_is_bounded_and_does_not_claim_success(tmp_path):
    listing,objects,k2=two_days(False)
    class Offline(Source):
        def acquire(self,w,key,expected_size):
            self.calls.append(key);raise URLError('still offline')
    s=Offline(listing,objects);r=invoke(warehouse(tmp_path),s)
    assert len(s.calls)==12  # 3 attempts/key, one final 3-attempt/key pass.
    assert r['source_scan_exhausted'] and not r['failures']
    assert not r['acquisition_plan_exhausted'] and r['one_minute_rows']==0
    assert set(r['pending_source_partitions'])=={KEY,k2}


@pytest.mark.parametrize('repair',[False,True])
def test_interruption_after_final_shard_before_source_receipt_replays(tmp_path,monkeypatch,repair):
    w=warehouse(tmp_path)
    if repair:
        partial,pc=fixture(START,MONTH,missing=(7,))
        with w.writer():w.import_archive(partial,pc,MONTH,observed_ms=START+31*DAY)
    raw,c=fixture();original=w.write_once
    def interrupted(rel,data):
        if rel==f'catalog/{seal(raw)}.json':raise OSError('simulated power loss before receipt')
        return original(rel,data)
    monkeypatch.setattr(w,'write_once',interrupted)
    with w.writer():
        with pytest.raises(OSError,match='simulated power loss'):
            w.import_archive(raw,c,KEY,observed_ms=START+31*DAY)
    assert not w.path(f'catalog/{seal(raw)}.json').exists()
    monkeypatch.setattr(w,'write_once',original)
    listing=[source_object(raw=raw)];objects={KEY:(raw,c)}
    if repair:listing.insert(0,source_object(MONTH,START,START+31*DAY,partial))
    s=Source(listing,objects);r=invoke(w,s)
    assert s.calls==[KEY] and not r['failures'] and r['one_minute_rows']==1440
    assert w.path(f'catalog/{seal(raw)}.json').is_file()
    assert r['this_run'][0]['inserted_rows']==0
