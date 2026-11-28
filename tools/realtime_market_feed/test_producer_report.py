"""Generated-fixture commit-memory reports; no provider or active source reads."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.realtime_market_feed import producer_report as reports
from tools.realtime_market_feed import service

NOW = 1_800_000_000_000


def state():
    return dict(run_id='a'*32, code_sha256='b'*64, config_sha256='c'*64,
                committed_final_bars_this_run=1, gaps_detected_this_run=0,
                last_committed_ms=NOW, last_final_close_ms=NOW-1,
                last_receipt_sha256='d'*64, last_source_event_sha256='e'*64,
                hold_reason=None)


def reporter(tmp_path):
    root=tmp_path/'reports';root.mkdir()
    return reports.RealtimeReporter(root,tmp_path/'protected'),root


def packet(opened, *, close='101'):
    return json.dumps(dict(data=dict(e='kline',s='BTCUSDT',E=opened+60_000,
        k=dict(i='1m',x=True,t=opened,T=opened+59_999,o='100',h='102',l='99',
               c=close,v='3',n=2))))


def test_report_is_selfsealed_sanitized_and_no_source_read(tmp_path):
    p,root=reporter(tmp_path)
    with patch('sqlite3.connect',side_effect=AssertionError('NO_DB_READ')):
        result=p.publish(state(),observed_ms=NOW,published_ms=NOW+1)
    doc=json.loads((root/result['name']).read_bytes())
    seal=doc.pop('report_sha256')
    assert seal==hashlib.sha256(reports._canonical(doc)).hexdigest()
    assert doc['gap_status']=='UNKNOWN_NOT_RESCANNED'
    assert doc['operational_24h_accepted'] is False
    assert doc['source_mutations']==doc['network_calls']==doc['orders']==0
    assert doc['source_class']=='FORWARD_UNQUALIFIED'
    assert str(tmp_path) not in json.dumps(doc)
    assert 'ohlcv' not in doc and 'close' not in doc


def test_report_cadence_replay_conflict_and_atomic_failure(tmp_path,monkeypatch):
    p,root=reporter(tmp_path)
    first=p.publish(state(),observed_ms=NOW,published_ms=NOW)
    assert p.publish(state(),observed_ms=NOW+1,published_ms=NOW+1) is None
    replacement=reports.RealtimeReporter(root,tmp_path/'protected')
    assert replacement.publish(state(),observed_ms=NOW,published_ms=NOW)['name']==first['name']
    replacement=reports.RealtimeReporter(root,tmp_path/'protected')
    with pytest.raises(ValueError,match='REPLAY_CONFLICT'):
        replacement.publish(state(),observed_ms=NOW,published_ms=NOW+1)
    before={p.name:p.read_bytes() for p in root.iterdir()}
    monkeypatch.setattr(reports.os,'link',lambda *a:(_ for _ in ()).throw(OSError('injected')))
    with pytest.raises(OSError):
        p.publish(state(),observed_ms=NOW+300_000,published_ms=NOW+300_000)
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before
    assert p.sequence==1


@pytest.mark.parametrize('alter,reason',[
    ({'last_committed_ms':NOW+1},'COMMIT'),
    ({'code_sha256':'wrong'},'PIN'),
    ({'committed_final_bars_this_run':True},'COUNTER'),
    ({'last_receipt_sha256':None},'COMMIT'),
    ({'run_id':'../escape'},'RUN'),
])
def test_report_rejects_unbound_future_and_malformed_state(tmp_path,alter,reason):
    p,_=reporter(tmp_path);body=state();body.update(alter)
    with pytest.raises(ValueError,match=reason):p.publish(body,observed_ms=NOW,published_ms=NOW)


def test_roots_and_publication_bound(tmp_path):
    protected=tmp_path/'protected';protected.mkdir()
    with pytest.raises(ValueError,match='OVERLAP'):reports.RealtimeReporter(protected,protected)
    with pytest.raises(ValueError,match='PREEXIST'):reports.RealtimeReporter(tmp_path/'missing',protected)
    p,_=reporter(tmp_path);p.sequence=reports.MAX_REPORTS_PER_RUN
    with pytest.raises(ValueError,match='REPORT_LIMIT'):p.publish(state(),observed_ms=NOW,published_ms=NOW)
    assert p.sequence==reports.MAX_REPORTS_PER_RUN


def test_linked_report_root_denied(tmp_path):
    target=tmp_path/'target';target.mkdir();link=tmp_path/'link'
    try:link.symlink_to(target,target_is_directory=True)
    except (OSError,NotImplementedError):pytest.skip('symlink unavailable')
    with pytest.raises(ValueError,match='REPARSE'):reports.RealtimeReporter(link,tmp_path/'protected')


def test_actual_store_hook_only_after_commit_and_replay_does_not_inflate(tmp_path):
    root=tmp_path/'reports';root.mkdir();source=tmp_path/'feed'/'market.sqlite'
    with patch.object(service,'utc_ms',return_value=NOW):
        store=service.Store(source,bounded_report_root=root)
        store.begin_run(['btcusdt'],3600)
    try:
        opened=NOW+300_000
        with patch.object(service,'utc_ms',return_value=opened+60_000):
            store.ingest(packet(opened),received_ms=opened+60_000)
        documents=[json.loads(p.read_bytes()) for p in sorted(root.glob('*.json'))]
        assert [d['committed_final_bars_this_run'] for d in documents]==[0,1]
        last=documents[-1]
        receipt=store.db.execute('SELECT receipt_sha256 FROM final_bar_lineage').fetchone()[0]
        assert last['last_receipt_sha256']==receipt
        assert store.db.execute('SELECT count(*) FROM final_bar').fetchone()[0]==1
        with patch.object(service,'utc_ms',return_value=opened+360_000):
            store.ingest(packet(opened),received_ms=opened+360_000)
        assert store._report_state['committed_final_bars_this_run']==1
        # Conflicting duplicate remains committed as an explicit event; its
        # forced report retains the original receipt and does not count a bar.
        with patch.object(service,'utc_ms',return_value=opened+360_001):
            store.ingest(packet(opened,close='100.5'),received_ms=opened+360_001)
        last=json.loads(sorted(root.glob('*.json'))[-1].read_bytes())
        assert last['status']=='HELD' and last['hold_reason']=='FINAL_BAR_CONFLICT'
        assert last['committed_final_bars_this_run']==1
        assert last['last_receipt_sha256']==receipt
    finally:store.db.close()


def test_failed_report_never_rolls_back_source_or_retries_forever(tmp_path,monkeypatch):
    root=tmp_path/'reports';root.mkdir()
    with patch.object(service,'utc_ms',return_value=NOW):
        store=service.Store(tmp_path/'feed'/'db.sqlite',bounded_report_root=root)
        store.begin_run(['btcusdt'],3600)
    monkeypatch.setattr(store._bounded_reporter,'publish',lambda *a,**k:(_ for _ in ()).throw(OSError('injected')))
    try:
        opened=NOW+300_000
        with patch.object(service,'utc_ms',return_value=opened+60_000):
            assert store.ingest(packet(opened),received_ms=opened+60_000)=='final_bar'
        assert store.db.execute('SELECT count(*) FROM final_bar').fetchone()[0]==1
        assert store._report_blocked is True
        assert store.db.execute("SELECT count(*) FROM service_event WHERE kind='PRODUCER_REPORT_BLOCKED'").fetchone()[0]==1
        with patch.object(service,'utc_ms',return_value=opened+120_000):
            store.ingest(packet(opened+60_000),received_ms=opened+120_000)
        assert store.db.execute("SELECT count(*) FROM service_event WHERE kind='PRODUCER_REPORT_BLOCKED'").fetchone()[0]==1
    finally:store.db.close()


def test_producer_counter_and_identity_regression_denied(tmp_path):
    p,_=reporter(tmp_path);body=state()
    p.publish(body,observed_ms=NOW,published_ms=NOW)
    changed=state();changed['last_receipt_sha256']='f'*64
    with pytest.raises(ValueError,match='WITHOUT_PROGRESS'):
        p.publish(changed,observed_ms=NOW+300_000,published_ms=NOW+300_000)
    regressed=state();regressed.update(committed_final_bars_this_run=0,last_committed_ms=None,last_final_close_ms=None,last_receipt_sha256=None,last_source_event_sha256=None)
    with pytest.raises(ValueError,match='COUNTER_REGRESSION'):
        p.publish(regressed,observed_ms=NOW+300_000,published_ms=NOW+300_000)


def test_run_stop_is_committed_before_final_report(tmp_path):
    root=tmp_path/'reports';root.mkdir()
    with patch.object(service,'utc_ms',return_value=NOW):
        store=service.Store(tmp_path/'feed'/'db.sqlite',bounded_report_root=root)
        run=store.begin_run(['btcusdt'],3600)
    try:
        with patch.object(service,'utc_ms',return_value=NOW+1):store.end_run(run)
        last=json.loads(sorted(root.glob('*.json'))[-1].read_bytes())
        assert last['status']=='STOPPED' and last['run_stopped'] is True
        assert store.db.execute('SELECT stopped_ms FROM service_run').fetchone()[0]==NOW+1
        assert last['committed_final_bars_this_run']==0
    finally:store.db.close()


def test_reporting_import_after_pinned_warehouse_isolation(tmp_path):
    """A pinned historical reader in the same process must not hide the hook."""
    import os
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[2]
    code = '''
import pathlib,sys,json
root=pathlib.Path(sys.argv[1]); output=pathlib.Path(sys.argv[2])
sys.path[:0]=[str(root/'.integration/warehouse/src'),str(root)]
import aql.warehouse.engine
from tools.realtime_market_feed.producer_report import RealtimeReporter
output.mkdir()
p=RealtimeReporter(output,output.parent/'protected')
s=dict(run_id='a'*32,code_sha256='b'*64,config_sha256='c'*64,
 committed_final_bars_this_run=0,gaps_detected_this_run=0,last_committed_ms=None,
 last_final_close_ms=None,last_receipt_sha256=None,last_source_event_sha256=None,hold_reason=None)
r=p.publish(s,observed_ms=1800000000000,published_ms=1800000000000)
assert json.loads((output/r['name']).read_bytes())['status']=='UNKNOWN'
'''
    r = subprocess.run([sys.executable,'-B','-c',code,str(root),str(tmp_path/'reports')],
        capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    assert r.returncode == 0, r.stderr
