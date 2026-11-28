import hashlib
import json
import sqlite3

from tools.realtime_market_feed.acceptance_gates import evaluate_24h_report
from tools.realtime_market_feed.observation_evidence import (
    VERIFIER_CODE_SHA256, build_observation_evidence,
)


def _database(path, *, subminute=False, repeated_faults=False):
    minute=60_000
    start=1_700_000_000_000 + (30_000 if subminute else 0)
    stop=start+86_400_000
    floor_start=start//minute*minute
    mono_start=1_000_000
    symbols=json.dumps(["BTCUSDT"],separators=(",",":"))
    config="c"*64
    code="d"*64
    db=sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE service_run(run_id TEXT,producer_code_sha256 TEXT,symbols_json TEXT,
            requested_observe_seconds INTEGER,started_ms INTEGER,stopped_ms INTEGER,
            config_sha256 TEXT,source_id TEXT,started_monotonic_ms INTEGER,stopped_monotonic_ms INTEGER);
        CREATE TABLE service_event(id INTEGER PRIMARY KEY,run_id TEXT,at_ms INTEGER,
            monotonic_ms INTEGER,kind TEXT,detail TEXT);
        CREATE TABLE final_bar(symbol TEXT,interval TEXT,open_ms INTEGER,received_ms INTEGER);
        CREATE TABLE final_bar_lineage(symbol TEXT,interval TEXT,open_ms INTEGER,
            receipt_json TEXT,receipt_sha256 TEXT);
        CREATE TABLE open_gap(symbol TEXT,interval TEXT,status TEXT,start_ms INTEGER,end_ms INTEGER,reason TEXT);
        CREATE TABLE latest_trade(symbol TEXT,received_ms INTEGER);
        CREATE TABLE latest_quote(symbol TEXT,received_ms INTEGER);
    """)
    run_id="run-d14"
    db.execute("INSERT INTO service_run VALUES(?,?,?,?,?,?,?,?,?,?)",
        (run_id,code,symbols,86_400,start,stop,config,"BINANCE_SPOT_PUBLIC_WEBSOCKET",mono_start,mono_start+86_400_000))
    events=[("RUN_STARTED",0),("RESTART_REPLAY_VERIFIED",1_000),
            ("PLANNED_ROTATION",80_000_000),("SOCKET_ERROR",80_001_000)]
    if repeated_faults:
        events.append(("SOCKET_ERROR",80_001_500))
    events.extend([("CONNECTED",80_002_000),("SERVICE_STOP",86_400_000)])
    for kind,offset in events:
        db.execute("INSERT INTO service_event(run_id,at_ms,monotonic_ms,kind,detail) VALUES(?,?,?,?,?)",
            (run_id,start+offset,mono_start+offset,kind,""))
    for i in range(1440):
        opened=floor_start+i*minute
        receipt=json.dumps({"open_ms":opened},sort_keys=True,separators=(",",":"))
        db.execute("INSERT INTO final_bar VALUES(?,?,?,?)",("BTCUSDT","1m",opened,start+i*minute))
        db.execute("INSERT INTO final_bar_lineage VALUES(?,?,?,?,?)",
            ("BTCUSDT","1m",opened,receipt,hashlib.sha256(receipt.encode()).hexdigest()))
    db.execute("INSERT INTO latest_trade VALUES(?,?)",("BTCUSDT",stop-1_000))
    db.execute("INSERT INTO latest_quote VALUES(?,?)",("BTCUSDT",stop-1_000))
    db.commit();db.close()


def test_subminute_boundaries_count_only_full_candles(tmp_path):
    path=tmp_path/"subminute.sqlite"
    _database(path,subminute=True)
    report=build_observation_evidence(path,"run-d14")
    assert report["coverage"]["expected_closed_bars"]==1439
    assert report["coverage"]["observed_closed_bars"]==1439
    assert report["coverage"]["missing_open_ranges"]==[]
    result=evaluate_24h_report(report,expected_code_sha256="d"*64,
        expected_symbols=["BTCUSDT"],expected_config_sha256="c"*64,
        provider_terms_cleared=True,quota_headroom_verified=True,
        expected_verifier_code_sha256=VERIFIER_CODE_SHA256,database_path=path)
    assert result["status"]=="24H_ACCEPTANCE_PASS", result["failures"]


def test_repeated_fault_attempts_share_one_causal_recovery(tmp_path):
    path=tmp_path/"faults.sqlite"
    _database(path,repeated_faults=True)
    report=build_observation_evidence(path,"run-d14")
    assert report["natural_fault"]=="OBSERVED_AND_RECOVERED"
    assert len(report["coverage"]["fault_recovery_pairs"])==1
    pair=report["coverage"]["fault_recovery_pairs"][0]
    assert len(pair["fault_event_ids"])==2
    result=evaluate_24h_report(report,expected_code_sha256="d"*64,
        expected_symbols=["BTCUSDT"],expected_config_sha256="c"*64,
        provider_terms_cleared=True,quota_headroom_verified=True,
        expected_verifier_code_sha256=VERIFIER_CODE_SHA256,database_path=path)
    assert result["status"]=="24H_ACCEPTANCE_PASS", result["failures"]


def _gap_events(path, failed, completed, *, kind='GAP_BACKFILL_FAILED'):
    _database(path)
    db=sqlite3.connect(path)
    start,mono=db.execute('SELECT started_ms,started_monotonic_ms FROM service_run').fetchone()
    for event_kind,detail,offset in [(kind,failed,10000),(kind,failed,11000),
                                   ('GAP_BACKFILL_COMPLETED',completed,12000)]:
        db.execute('INSERT INTO service_event(run_id,at_ms,monotonic_ms,kind,detail) VALUES(?,?,?,?,?)',
            ('run-d14',start+offset,mono+offset,event_kind,detail))
    rows=db.execute('SELECT run_id,at_ms,monotonic_ms,kind,detail FROM service_event ORDER BY at_ms,id').fetchall()
    db.execute('DELETE FROM service_event')
    db.executemany('INSERT INTO service_event(run_id,at_ms,monotonic_ms,kind,detail) VALUES(?,?,?,?,?)',rows)
    db.commit();db.close()


def test_gap_recovery_requires_same_symbol_and_range(tmp_path):
    from tools.realtime_market_feed.observation_evidence import recovery_matches
    for index,completed in enumerate(['ETHUSDT:0:60000:bars=1',
            'BTCUSDT:60000:120000:bars=1','BTCUSDT:0:120000:bars=2']):
        path=tmp_path/f'unrelated-{index}.sqlite'
        _gap_events(path,'BTCUSDT:0:60000:TimeoutError',completed)
        report=build_observation_evidence(path,'run-d14')
        assert report['natural_fault']=='OBSERVED_NOT_RECOVERED'
        fault=next(e for e in report['events'] if e['kind']=='GAP_BACKFILL_FAILED')
        recovery=next(e for e in report['events'] if e['kind']=='GAP_BACKFILL_COMPLETED')
        assert not recovery_matches(fault,recovery)
        # A re-signed/mutated envelope must fail causality independently of coverage.
        report['natural_fault']='OBSERVED_AND_RECOVERED'
        report['coverage']['fault_recovery_pairs'].append({
            'fault_event_ids':[e['id'] for e in report['events'] if e['kind']=='GAP_BACKFILL_FAILED'],
            'recovery_event_id':recovery['id']})
        result=evaluate_24h_report(report,expected_code_sha256='d'*64,
            expected_symbols=['BTCUSDT'],expected_config_sha256='c'*64,
            provider_terms_cleared=True,quota_headroom_verified=True,
            expected_verifier_code_sha256=VERIFIER_CODE_SHA256)
        assert 'FAULT_RECOVERY_CAUSALITY_INVALID' in result['failures']


def test_matching_gap_multi_attempts_share_completion(tmp_path):
    path=tmp_path/'same-gap.sqlite'
    _gap_events(path,'BTCUSDT:0:60000:TimeoutError','BTCUSDT:0:60000:bars=1:source=REST')
    report=build_observation_evidence(path,'run-d14')
    assert report['natural_fault']=='OBSERVED_AND_RECOVERED'
    assert any(len(p['fault_event_ids'])==2 for p in report['coverage']['fault_recovery_pairs'])
    result=evaluate_24h_report(report,expected_code_sha256='d'*64,
        expected_symbols=['BTCUSDT'],expected_config_sha256='c'*64,
        provider_terms_cleared=True,quota_headroom_verified=True,
        expected_verifier_code_sha256=VERIFIER_CODE_SHA256,database_path=path)
    assert result['status']=='24H_ACCEPTANCE_PASS',result['failures']


def test_unbound_worker_and_malformed_gap_faults_remain_unrecovered(tmp_path):
    for index,(kind,detail) in enumerate([
        ('GAP_BACKFILL_WORKER_ERROR','BTCUSDT:TimeoutError'),
        ('GAP_BACKFILL_FAILED','BTCUSDT:unknown:60000:TimeoutError'),
        ('GAP_BACKFILL_FAILED','BTCUSDT:1:60000:TimeoutError')]):
        path=tmp_path/f'unbound-{index}.sqlite'
        _gap_events(path,detail,'BTCUSDT:0:60000:bars=1',kind=kind)
        report=build_observation_evidence(path,'run-d14')
        assert report['natural_fault']=='OBSERVED_NOT_RECOVERED'
