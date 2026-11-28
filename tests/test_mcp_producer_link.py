"""Native producer -> bounded Early consumer with generated source only."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import atlas_early_observation as early
import atlas_producer_report_adapter as adapter
import atlas_ops_watchdog as watchdog
from aql.warehouse.daily import import_one_retained
from aql.warehouse.storage import seal
from tests.test_warehouse import fixture, warehouse, START, DAY


def reseal(doc, field='report_sha256'):
    doc.pop(field,None);doc[field]=watchdog.digest(watchdog.canonical(doc));return doc


@pytest.fixture
def native(tmp_path,monkeypatch):
    from aql.warehouse import daily
    now=START+DAY
    monkeypatch.setattr(daily.time,'time_ns',lambda:now*1_000_000)
    inp=tmp_path/'input';inp.mkdir();out=tmp_path/'reports';out.mkdir()
    raw,check=fixture();archive=inp/'BTCUSDT-1m-2024-01-01.zip'
    archive.write_bytes(raw);archive.with_name(archive.name+'.CHECKSUM').write_bytes(check)
    wh=warehouse(tmp_path/'warehouse')
    report=import_one_retained(wh,archive,source_day_ms=START,expected_zip_sha256=seal(raw),
        expected_checksum_sha256=seal(check),observed_ms=now,report_root=out)
    path=next(out.glob('daily-*.json'));doc=json.loads(path.read_bytes())
    pins={k:doc[k] for k in ('code_sha256','config_sha256')}
    return doc,report['registry'],pins,now,path


def test_native_source_import_registry_projection_without_worker_promotion(native):
    doc,reg,pins,now,_=native
    view=adapter.daily_source(doc,reg,pins,now)
    assert view['status']=='SOURCE_LINK_VERIFIED_WORKER_NOT_INFERRED'
    assert view['worker_health']=='UNKNOWN'
    assert view['source_receipt_sha256']==doc['source_receipt']['receipt_sha256']
    assert doc['import_receipt_sha256']==watchdog.digest(watchdog.canonical(doc['import_receipt']))


@pytest.mark.parametrize('mutate,code',[
    (lambda d:d.update(source_day_ms=START+DAY),'NOT_FINAL'),
    (lambda d:d.update(source_key='data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-02.zip'),'DAY_KEY'),
    (lambda d:d.update(checksum_sha256='f'*64),'SOURCE_RECEIPT_BINDING'),
    (lambda d:d.update(source_receipt_sha256='f'*64),'SOURCE_RECEIPT_BINDING'),
    (lambda d:d['import_receipt'].update(source_sha256='f'*64),'IMPORT_RECEIPT_BINDING'),
    (lambda d:d.update(registry_sha256='f'*64),'REGISTRY_SNAPSHOT_BINDING'),
    (lambda d:d.update(observation_ms=START+DAY+1,published_ms=START+DAY+1),'CLOCK'),
])
def test_wrong_day_checksum_receipt_and_future_rejected(native,mutate,code):
    doc,reg,pins,now,_=native;changed=copy.deepcopy(doc);mutate(changed);reseal(changed)
    with pytest.raises(ValueError,match=code):adapter.daily_source(changed,reg,pins,now)


def test_external_pin_and_fresh_registry_required(native):
    doc,reg,pins,now,_=native
    with pytest.raises(ValueError,match='EXTERNAL_PIN'):adapter.daily_source(doc,reg,None,now)
    with pytest.raises(ValueError,match='STALE'):adapter.daily_source(doc,reg,pins,now+300001)
    changed=copy.deepcopy(reg);changed['sources'][0]['key']='other-day';reseal(changed,'snapshot_sha256')
    doc=copy.deepcopy(doc);doc['registry_sha256']=changed['snapshot_sha256'];reseal(doc)
    with pytest.raises(ValueError,match='REGISTRY_SOURCE_BINDING'):adapter.daily_source(doc,changed,pins,now)


def test_early_keeps_worker_unknown_when_only_source_report_proves_import(native,tmp_path):
    doc,reg,pins,now,path=native
    regpath=tmp_path/'registry.json';regpath.write_bytes(watchdog.canonical(reg))
    result=early.build({'daily_source':path,'registry':regpath},now_ms=now,
        monotonic_ns=1,boot_id='test',clock_uncertainty_ms=100,producer_pins={'daily':pins})
    lane=result['lanes']['daily']
    assert lane['status']=='UNKNOWN'
    assert lane['reported']['source_link_verified'] is True
    assert lane['reported']['producer_source']['worker_health']=='UNKNOWN'
    assert result['measurements']['input_files']==2


def test_realtime_schema_consumed_without_24h_or_gap_completeness_claim(tmp_path):
    from tools.realtime_market_feed.producer_report import RealtimeReporter
    now=1_800_000_000_000;root=tmp_path/'reports';root.mkdir()
    producer=RealtimeReporter(root,tmp_path/'protected')
    state=dict(run_id='a'*32,code_sha256='b'*64,config_sha256='c'*64,
        committed_final_bars_this_run=1,gaps_detected_this_run=0,last_committed_ms=now,
        last_final_close_ms=now-1,last_receipt_sha256='d'*64,last_source_event_sha256='e'*64,
        hold_reason=None)
    first=producer.publish(state,observed_ms=now,published_ms=now)
    pins={'code_sha256':'b'*64,'config_sha256':'c'*64}
    prior=early.build({'live':root/first['name']},now_ms=now,monotonic_ns=1,boot_id='test',
        clock_uncertainty_ms=100,producer_pins={'live':pins})
    state.update(committed_final_bars_this_run=2,last_committed_ms=now+300000,
        last_final_close_ms=now+299999,last_receipt_sha256='f'*64,last_source_event_sha256='1'*64)
    second=producer.publish(state,observed_ms=now+300000,published_ms=now+300000)
    result=early.build({'live':root/second['name']},now_ms=now+300000,monotonic_ns=2,
        boot_id='test',clock_uncertainty_ms=100,producer_pins={'live':pins},previous=prior)
    assert result['lanes']['live']['status']=='HEALTHY_PROGRESS'
    assert result['lanes']['live']['reported']['gap_status']=='UNKNOWN_NOT_RESCANNED'
    assert result['lanes']['live']['reported']['operational_24h_accepted'] is False
    from atlas_mcp_pilot import SnapshotReader
    projected=SnapshotReader.project_early(result,'f'*64)['lanes']['live']
    assert projected['last_validated_committed_progress']['source_class']=='FORWARD_UNQUALIFIED'
    assert projected['gaps']['gap_status']=='UNKNOWN_NOT_RESCANNED'
    assert projected['provenance']['source_identity']['run_id']=='a'*32


def test_stale_genuine_realtime_hold_keeps_hold_precedence(tmp_path):
    from tools.realtime_market_feed.producer_report import RealtimeReporter
    now=1_800_000_000_000;root=tmp_path/'reports';root.mkdir()
    p=RealtimeReporter(root,tmp_path/'protected')
    state=dict(run_id='a'*32,code_sha256='b'*64,config_sha256='c'*64,
        committed_final_bars_this_run=1,gaps_detected_this_run=0,last_committed_ms=now,
        last_final_close_ms=now-1,last_receipt_sha256='d'*64,last_source_event_sha256='e'*64,
        hold_reason='FINAL_BAR_CONFLICT')
    report=p.publish(state,observed_ms=now,published_ms=now)
    result=early.build({'live':root/report['name']},now_ms=now+300001,monotonic_ns=1,
        boot_id='test',clock_uncertainty_ms=100,
        producer_pins={'live':{'code_sha256':'b'*64,'config_sha256':'c'*64}})
    assert result['lanes']['live']['status']=='HELD'
    assert result['lanes']['live']['freshness']=='STALE'


def test_optional_sixth_daily_report_remains_eight_kib_bounded(tmp_path):
    path=tmp_path/'oversize-source.json';path.write_text('{"filler":"'+'x'*8192+'"}')
    with pytest.raises(ValueError,match='INPUT_BUDGET_EXCEEDED'):
        early.build({'daily_source':path},now_ms=1000000,monotonic_ns=1,boot_id='test',clock_uncertainty_ms=100)


def test_daily_import_replay_preserves_original_bounded_report(native,tmp_path,monkeypatch):
    doc,reg,pins,now,path=native
    from aql.warehouse import daily
    before=path.read_bytes()
    archive=tmp_path/'input'/'BTCUSDT-1m-2024-01-01.zip'
    wh=warehouse(tmp_path/'warehouse')
    monkeypatch.setattr(daily.time,'time_ns',lambda:(now+300000)*1_000_000)
    replay=import_one_retained(wh,archive,source_day_ms=START,
        expected_zip_sha256=doc['source_sha256'],expected_checksum_sha256=doc['checksum_sha256'],
        observed_ms=now+300000,report_root=path.parent)
    assert replay['this_run'][0]['inserted_rows']==0
    assert replay['this_run'][0]['duplicate_rows']>0
    assert path.read_bytes()==before
    assert len(list(path.parent.glob('daily-*.json')))==1


def test_stopped_realtime_is_not_healthy_even_with_fresh_commit(tmp_path):
    from tools.realtime_market_feed.producer_report import RealtimeReporter
    now=1_800_000_000_000;root=tmp_path/'reports';root.mkdir()
    p=RealtimeReporter(root,tmp_path/'protected')
    state=dict(run_id='a'*32,code_sha256='b'*64,config_sha256='c'*64,
        committed_final_bars_this_run=1,gaps_detected_this_run=0,last_committed_ms=now,
        last_final_close_ms=now-1,last_receipt_sha256='d'*64,last_source_event_sha256='e'*64,
        hold_reason=None,run_stopped=True)
    report=p.publish(state,observed_ms=now,published_ms=now)
    result=early.build({'live':root/report['name']},now_ms=now+300001,monotonic_ns=1,
        boot_id='test',clock_uncertainty_ms=100,
        producer_pins={'live':{'code_sha256':'b'*64,'config_sha256':'c'*64}})
    assert result['lanes']['live']['status']=='UNKNOWN'
    assert result['lanes']['live']['reason']=='REALTIME_PRODUCER_STOPPED'


def test_history_producer_requires_external_code_and_config_pins(tmp_path):
    from aql.warehouse.producer_report import publish_bounded
    now=START+DAY;root=tmp_path/'reports';root.mkdir();protected=tmp_path/'protected';protected.mkdir()
    report=publish_bounded(root,protected_root=protected,lane='HISTORY',identity='a'*16,
        sequence=3,observed_ms=now,published_ms=now,status='CONTINUING',reason='CONTINUATION_PENDING',
        counters={'archives_this_run':3},continuation_ref='https://github.com/scannercrypto0-gif/super-kumo-v8/pull/330',
        accepted_prefix_unchanged=True,code_sha256='b'*64,config_sha256='c'*64)
    doc=json.loads((root/report['name']).read_bytes())
    assert adapter.base(doc,{'code_sha256':'b'*64,'config_sha256':'c'*64},now,
        schema='aql.warehouse.full-history-checkpoint.v1',lane='HISTORY')==now
    for field in ('code_sha256','config_sha256'):
        pins={'code_sha256':'b'*64,'config_sha256':'c'*64};pins[field]='f'*64
        with pytest.raises(ValueError,match='EXTERNAL_PIN'):
            adapter.base(doc,pins,now,schema='aql.warehouse.full-history-checkpoint.v1',lane='HISTORY')


def test_history_producer_needs_same_run_and_exact_registry_link(tmp_path):
    from aql.warehouse.producer_report import publish_bounded
    from tests.test_atlas_early_observation import registry, NOW
    root=tmp_path/'reports';root.mkdir();protected=tmp_path/'protected';protected.mkdir()
    pins={'code_sha256':'b'*64,'config_sha256':'c'*64}
    def packet(now,identity,watermark,rows):
        reg=registry(now=now,watermark=watermark,rows=rows)
        rp=root/f'reg-{watermark}.json';rp.write_bytes(watchdog.canonical(reg))
        report=publish_bounded(root,protected_root=protected,lane='HISTORY',identity=identity,
            sequence=watermark,observed_ms=now,published_ms=now,status='CONTINUING',reason='CONTINUATION_PENDING',
            counters={'archives_this_run':watermark,'inserted_rows_this_run':rows},
            continuation_ref='https://github.com/scannercrypto0-gif/super-kumo-v8/pull/330',
            accepted_prefix_unchanged=True,registry_sha256=reg['snapshot_sha256'],
            registry_watermark=watermark,**pins)
        return root/report['name'],rp
    first,reg1=packet(NOW,'a'*16,10,100)
    prior=early.build({'history':first,'registry':reg1},now_ms=NOW,monotonic_ns=1,boot_id='test',
        clock_uncertainty_ms=100,producer_pins={'history':pins})
    second,reg2=packet(NOW+300000,'d'*16,11,140)
    current=early.build({'history':second,'registry':reg2},now_ms=NOW+300000,monotonic_ns=2,boot_id='test',
        clock_uncertainty_ms=100,producer_pins={'history':pins},previous=prior)
    assert current['lanes']['history']['status']=='UNKNOWN'
    assert current['lanes']['history']['reason']=='SECOND_OBSERVATION_OR_SOURCE_LINK_REQUIRED'
    doc=json.loads(second.read_bytes());doc['registry_sha256']='f'*64;reseal(doc);second.write_bytes(watchdog.canonical(doc))
    current=early.build({'history':second,'registry':reg2},now_ms=NOW+300000,monotonic_ns=2,boot_id='test',
        clock_uncertainty_ms=100,producer_pins={'history':pins},previous=prior)
    assert current['lanes']['history']['status']=='UNKNOWN'
    assert current['lanes']['history']['reason']=='HISTORY_REGISTRY_LINK_UNPROVEN'


def test_history_duplicate_observation_clocks_must_match(tmp_path):
    from aql.warehouse.producer_report import publish_bounded
    now=START+DAY;root=tmp_path/'reports';root.mkdir();protected=tmp_path/'protected';protected.mkdir()
    pins={'code_sha256':'b'*64,'config_sha256':'c'*64}
    result=publish_bounded(root,protected_root=protected,lane='HISTORY',identity='a'*16,
        sequence=3,observed_ms=now,published_ms=now,status='CONTINUING',reason='CONTINUATION_PENDING',
        counters={'archives_this_run':3},continuation_ref='https://github.com/scannercrypto0-gif/super-kumo-v8/pull/330',
        accepted_prefix_unchanged=True,**pins)
    report=root/result['name']
    doc=json.loads(report.read_bytes())
    assert doc['observed_at_ms']==doc['observation_ms']
    doc['observed_at_ms']=now+1;reseal(doc);report.write_bytes(watchdog.canonical(doc))
    snapshot=early.build({'history':report},now_ms=now+1,monotonic_ns=1,boot_id='test',
        clock_uncertainty_ms=100,producer_pins={'history':pins})
    assert snapshot['lanes']['history']['status']=='UNKNOWN'
    assert snapshot['lanes']['history']['reason']=='HISTORY_EVIDENCE_UNTRUSTED'
