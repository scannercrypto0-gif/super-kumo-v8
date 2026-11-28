"""Bounded automatic refresh on sanitized generated inputs, no host activation."""
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import atlas_mcp_refresh as refresh
import atlas_mcp_pilot as pilot


def setup(tmp_path):
    inp=tmp_path/'in';out=tmp_path/'out';inp.mkdir();out.mkdir()
    return inp,out


def test_two_finite_automatic_generated_cycles_and_real_mcp_reader(tmp_path):
    inp,out=setup(tmp_path);now=[1_800_000_000_000];waits=[]
    def wait(seconds):waits.append(seconds);now[0]+=seconds*1000
    results=refresh.run_refresh({},cycles=2,interval_seconds=300,first_sequence=1,
        approved_input_root=inp,approved_output_root=out,boot_id='test',clock_uncertainty_ms=100,
        now=lambda:now[0],monotonic=lambda:now[0]*1000000,wait=wait)
    assert waits==[300] and len(results)==2
    assert all(r['state']=='UNKNOWN' and r['host_cycles_attested'] is False for r in results)
    assert len(list(out.glob('*.json')))==4
    for r in results:
        reader=pilot.SnapshotReader(out/r['manifest_name'],r['manifest_sha256'],profile='early',approved_output_root=out)
        assert reader.view['status']=='UNKNOWN'
        assert reader.view['provenance']['host_attested'] is False


def test_conflict_does_not_replace_previous_pair(tmp_path):
    inp,out=setup(tmp_path)
    kw=dict(approved_input_root=inp,approved_output_root=out,sequence=1,now_ms=1000000,
            monotonic_ns=1,boot_id='test')
    refresh.refresh_once({},**kw);before={p.name:p.read_bytes() for p in out.iterdir()}
    with pytest.raises(ValueError,match='CREATE_ONLY'):refresh.refresh_once({},**kw)
    assert before=={p.name:p.read_bytes() for p in out.iterdir()}


def test_failed_manifest_publication_leaves_no_authorizing_manifest(tmp_path,monkeypatch):
    inp,out=setup(tmp_path);original=refresh.atomic_new
    def failing(path,value):
        if '.manifest.' in str(path):raise OSError('injected')
        return original(path,value)
    monkeypatch.setattr(refresh,'atomic_new',failing)
    with pytest.raises(OSError,match='injected'):
        refresh.refresh_once({},approved_input_root=inp,approved_output_root=out,sequence=1,
            now_ms=1000000,monotonic_ns=1,boot_id='test')
    assert len(list(out.glob('*.json')))==1 and not list(out.glob('*.manifest.json'))


@pytest.mark.parametrize('cycles,interval',[(0,300),(3,300),(1,299),(1,1801)])
def test_refresh_budget_boundaries(tmp_path,cycles,interval):
    inp,out=setup(tmp_path)
    with pytest.raises(ValueError,match='BOUND'):
        refresh.run_refresh({},cycles=cycles,interval_seconds=interval,
            approved_input_root=inp,approved_output_root=out,boot_id='test')
    assert not list(out.iterdir())


def test_input_output_overlap_and_linked_input_denied(tmp_path):
    inp,out=setup(tmp_path)
    with pytest.raises(ValueError,match='ROOTS_MUST_BE_SEPARATE'):
        refresh.refresh_once({},approved_input_root=inp,approved_output_root=inp,sequence=1,
            now_ms=1000000,monotonic_ns=1,boot_id='test')


def test_automatic_selector_consumes_next_producer_report_between_cycles(tmp_path):
    from tools.realtime_market_feed.producer_report import RealtimeReporter
    inp,out=setup(tmp_path);now=[1_800_000_000_000]
    p=RealtimeReporter(inp,tmp_path/'protected')
    state=dict(run_id='a'*32,code_sha256='b'*64,config_sha256='c'*64,
        committed_final_bars_this_run=1,gaps_detected_this_run=0,last_committed_ms=now[0],
        last_final_close_ms=now[0]-1,last_receipt_sha256='d'*64,last_source_event_sha256='e'*64,
        hold_reason=None)
    p.publish(state,observed_ms=now[0],published_ms=now[0])
    def wait(seconds):
        now[0]+=seconds*1000
        state.update(committed_final_bars_this_run=2,last_committed_ms=now[0],
            last_final_close_ms=now[0]-1,last_receipt_sha256='f'*64,last_source_event_sha256='1'*64)
        p.publish(state,observed_ms=now[0],published_ms=now[0])
    results=refresh.run_refresh({},cycles=2,interval_seconds=300,first_sequence=1,
        approved_input_root=inp,approved_output_root=out,boot_id='test',clock_uncertainty_ms=100,
        now=lambda:now[0],monotonic=lambda:now[0]*1000000,wait=wait,
        producer_selectors={'live':'realtime-'+('a'*32)+'-'},
        producer_pins={'live':{'code_sha256':'b'*64,'config_sha256':'c'*64}})
    latest=json.loads((out/results[-1]['snapshot_name']).read_bytes())
    assert latest['lanes']['live']['status']=='HEALTHY_PROGRESS'
    assert latest['lanes']['live']['progress_cursor']['verified_receipts']==2
    assert results[-1]['host_cycles_attested'] is False


def test_invalid_newest_selector_payload_does_not_fall_back(tmp_path):
    inp,out=setup(tmp_path)
    (inp/'history-bbbbbbbbbbbbbbbb-0001.json').write_text('{}')
    (inp/'history-bbbbbbbbbbbbbbbb-0002.json').write_text('not-json')
    assert refresh.select_latest(inp,'history-bbbbbbbbbbbbbbbb-').name=='history-bbbbbbbbbbbbbbbb-0002.json'
    result=refresh.refresh_once({},approved_input_root=inp,approved_output_root=out,
        sequence=1,now_ms=1000000,monotonic_ns=1,boot_id='test',
        producer_selectors={'history':'history-bbbbbbbbbbbbbbbb-'})
    assert result['state']=='UNKNOWN'


def test_selector_bounded_names_no_recursion_and_no_traversal(tmp_path):
    inp,out=setup(tmp_path)
    nested=inp/'nested';nested.mkdir();(nested/'history-bbbbbbbbbbbbbbbb-9999.json').write_text('{}')
    assert refresh.select_latest(inp,'history-bbbbbbbbbbbbbbbb-') is None
    with pytest.raises(ValueError,match='PREFIX'):refresh.select_latest(inp,'../history-')
    for index in range(512):(inp/f'unrelated-{index}').touch()
    with pytest.raises(ValueError,match='ENTRY_BOUND'):refresh.select_latest(inp,'history-bbbbbbbbbbbbbbbb-')
