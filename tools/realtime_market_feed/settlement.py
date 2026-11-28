"""Opt-in D14a local receipt protocol; never starts or extends a feed.

The immutable plan predates T. Endpoint and delivery settlement are separate
receipts. A coverage PASS is not the existing 24h operational gate or PIT proof.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from tools.realtime_market_feed.atlas_integration import _verify_lineage

POLICY = 'AQL-D14A-SETTLEMENT-v1'
ALLOWANCE_MS = 120_000
MAX_ROWS = 10_080
CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def clock():
    return time.time_ns()//1_000_000, time.monotonic_ns()//1_000_000


def need(value, reason):
    if not value:
        raise ValueError(reason)


def publish(path, body):
    # Exact output selected by caller; no overwrites, directory walks or feed calls.
    receipt = {'body':body, 'sha256':digest(body)}
    raw = canonical(receipt)
    need(len(raw)<=8_000_000, 'SETTLEMENT_RECEIPT_BOUND')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise
    return receipt


def read(path):
    need(Path(path).stat().st_size<=8_000_000, 'SETTLEMENT_RECEIPT_BOUND')
    raw=Path(path).read_bytes()
    need(len(raw)<=8_000_000, 'SETTLEMENT_RECEIPT_BOUND')
    receipt=json.loads(raw)
    need(set(receipt)=={'body','sha256'} and receipt['sha256']==digest(receipt['body'])
         and raw==canonical(receipt), 'SETTLEMENT_RECEIPT_INTEGRITY')
    return receipt


def open_source(database):
    path=Path(database).resolve()
    need(path.is_file(), 'SETTLEMENT_SOURCE_MISSING')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
    return db


def identity(db, run_id):
    row=db.execute('SELECT * FROM service_run WHERE run_id=?',(run_id,)).fetchone()
    need(row is not None, 'SETTLEMENT_RUN_MISSING')
    keys=('run_id','producer_code_sha256','symbols_json','requested_observe_seconds',
          'started_ms','started_monotonic_ms','config_sha256','source_id')
    result={key:row[key] for key in keys}
    need(row['stopped_ms'] is None or row['stopped_ms']>=row['started_ms']+86_400_000,
         'SETTLEMENT_OBSERVATION_ENDED_EARLY')
    need(result['source_id']=='BINANCE_SPOT_PUBLIC_WEBSOCKET', 'SETTLEMENT_SOURCE_IDENTITY')
    return result


def create_plan(database, run_id, destination, *, owner_decision_ref):
    now,mono=clock()
    with_source=open_source(database)
    try:
        source=identity(with_source,run_id)
        need(type(source['started_ms']) is int and type(source['started_monotonic_ms']) is int
             and source['requested_observe_seconds']==86_400, 'SETTLEMENT_OBSERVATION_PLAN')
        end=source['started_ms']+86_400_000
        need(source['started_ms']<=now<end, 'SETTLEMENT_PLAN_MUST_PRECEDE_ENDPOINT')
        need(abs((now-source['started_ms'])-(mono-source['started_monotonic_ms']))<=2000,
             'SETTLEMENT_PLAN_CLOCK')
        symbols=json.loads(source['symbols_json'])
        need(symbols and len({s.upper() for s in symbols if type(s) is str})==len(symbols) and all(
            type(s) is str and s.isalnum() for s in symbols), 'SETTLEMENT_SYMBOLS')
        lo=(source['started_ms']+59999)//60000*60000;hi=end//60000*60000
        need((hi-lo)//60000*len(symbols)<=MAX_ROWS, 'SETTLEMENT_ROW_LIMIT')
        need(type(owner_decision_ref) is str and bool(owner_decision_ref), 'SETTLEMENT_AUTHORITY_REF')
        return publish(destination, {'schema':'atlas.ws.settlement-plan.v1','policy':POLICY,
            'allowance_ms':ALLOWANCE_MS,'source':source,'eligible_start_ms':lo,
            'eligible_end_ms':hi,'endpoint_ms':end,'deadline_ms':end+ALLOWANCE_MS,
            'created_ms':now,'created_monotonic_ms':mono,'owner_decision_ref':owner_decision_ref,
            'verifier_code_sha256':CODE_SHA256,'orders':0,'trading_authority':'NONE'})
    finally:with_source.close()


def plan_read(path):
    plan=read(path);p=plan['body'];source=p['source']
    need(p['policy']==POLICY and p['allowance_ms']==ALLOWANCE_MS
         and p['deadline_ms']==p['endpoint_ms']+ALLOWANCE_MS
         and p['endpoint_ms']==source['started_ms']+86_400_000
         and p['created_ms']<p['endpoint_ms'] and p['verifier_code_sha256']==CODE_SHA256,
         'SETTLEMENT_POLICY_PIN')
    need(p['eligible_start_ms']==(source['started_ms']+59999)//60000*60000
         and p['eligible_end_ms']==p['endpoint_ms']//60000*60000,'SETTLEMENT_DENOMINATOR')
    return plan


def collect(database, plan, cutoff):
    p=plan['body'];source=p['source'];db=open_source(database)
    deadline=time.monotonic()+5
    db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try:
        need(identity(db,source['run_id'])==source, 'SETTLEMENT_RUN_PIN_CHANGED')
        rows=[];missing=[];conflicts=[]
        for symbol in json.loads(source['symbols_json']):
            found=db.execute('''SELECT f.*,l.receipt_json AS lineage_json,
                l.receipt_sha256 AS lineage_sha256 FROM final_bar f LEFT JOIN final_bar_lineage l
                ON f.symbol=l.symbol AND f.interval=l.interval AND f.open_ms=l.open_ms
                WHERE f.symbol=? AND f.interval='1m' AND f.open_ms>=? AND f.open_ms<?
                  AND f.received_ms>=? AND f.received_ms<=? ORDER BY f.open_ms LIMIT ?''',
                (symbol.upper(),p['eligible_start_ms'],p['eligible_end_ms'],source['started_ms'],cutoff,MAX_ROWS+1)).fetchall()
            need(len(found)<=MAX_ROWS, 'SETTLEMENT_ROW_LIMIT')
            seen=set()
            for row in found:
                need(row['open_ms'] not in seen,'SETTLEMENT_DUPLICATE_ROW');seen.add(row['open_ms'])
                _verify_lineage(row,expected_producer_code_sha256=source['producer_code_sha256'])
                rows.append({'symbol':symbol.upper(),'open_ms':row['open_ms'],
                    'received_ms':row['received_ms'],'lineage_sha256':row['lineage_sha256']})
            missing.extend([symbol.upper(),o,o+60000] for o in range(
                p['eligible_start_ms'],p['eligible_end_ms'],60000) if o not in seen)
        events=[dict(r) for r in db.execute('''SELECT id,run_id,at_ms,monotonic_ms,kind,detail
            FROM service_event WHERE run_id=? AND at_ms<=? ORDER BY id LIMIT ?''',(source['run_id'],cutoff,MAX_ROWS+1))]
        need(len(events)<=MAX_ROWS and all(len(e['detail'])<=4096 for e in events), 'SETTLEMENT_EVENT_LIMIT')
        prior_id=prior_wall=prior_mono=-1
        for event in events:
            need(all(type(event[k]) is int for k in ('id','at_ms','monotonic_ms'))
                 and event['id']>prior_id and event['at_ms']>=prior_wall
                 and event['monotonic_ms']>=prior_mono
                 and source['started_ms']<=event['at_ms']<=cutoff
                 and abs((event['at_ms']-source['started_ms'])-
                         (event['monotonic_ms']-source['started_monotonic_ms']))<=2000,
                 'SETTLEMENT_EVENT_CLOCK')
            prior_id,prior_wall,prior_mono=event['id'],event['at_ms'],event['monotonic_ms']
            if event['kind']=='FINAL_BAR_CONFLICT':
                # A conflict cannot be cured by delivery settlement. Conservative
                # unscoped/malformed conflicts are also a HOLD, never discarded.
                conflicts.append(event['id'])
        commits={(event['detail'],event['at_ms']) for event in events
                 if event['kind']=='FINAL_BAR_RECEIVED'}
        need(all((row['symbol']+':'+str(row['open_ms']),row['received_ms']) in commits
                 for row in rows), 'SETTLEMENT_COMMIT_RUN_UNBOUND')
        return {'rows':rows,'missing':missing,'conflict_event_ids':conflicts,'events':events}
    finally:db.close()


def capture_endpoint(database, plan_path, destination):
    plan=plan_read(plan_path);p=plan['body'];now,mono=clock();end=p['endpoint_ms']
    end_mono=p['source']['started_monotonic_ms']+86_400_000
    need(end<=now<=end+2000 and end_mono<=mono<=end_mono+2000, 'SETTLEMENT_ENDPOINT_CAPTURE_WINDOW')
    need(abs((now-p['source']['started_ms'])-(mono-p['source']['started_monotonic_ms']))<=2000,
         'SETTLEMENT_ENDPOINT_CLOCK')
    snapshot=collect(database,plan,end)
    return publish(destination, {'schema':'atlas.ws.observation-endpoint.v1',
        'plan_sha256':plan['sha256'],'observed_endpoint_ms':end,'captured_ms':now,
        'captured_monotonic_ms':mono,'snapshot':snapshot,
        'coverage_at_endpoint':len(snapshot['rows']),'verifier_code_sha256':CODE_SHA256})


def build_final(database, plan, endpoint, now, mono):
    p=plan['body'];e=endpoint['body']
    need(e['plan_sha256']==plan['sha256'] and e['verifier_code_sha256']==CODE_SHA256,
         'SETTLEMENT_ENDPOINT_PIN')
    end_mono=p['source']['started_monotonic_ms']+86_400_000
    need(e['observed_endpoint_ms']==p['endpoint_ms']
         and p['endpoint_ms']<=e['captured_ms']<=p['endpoint_ms']+2000
         and end_mono<=e['captured_monotonic_ms']<=end_mono+2000,
         'SETTLEMENT_ENDPOINT_CLOCK')
    need(p['endpoint_ms']<=now<=p['deadline_ms'] and end_mono<=mono<=end_mono+ALLOWANCE_MS,
         'SETTLEMENT_DEADLINE')
    need(mono>=e['captured_monotonic_ms'] and now>=e['captured_ms'] and
         abs((now-e['captured_ms'])-(mono-e['captured_monotonic_ms']))<=2000,
         'SETTLEMENT_CLOCK')
    snapshot=collect(database,plan,now)
    original=collect(database,plan,p['endpoint_ms'])
    need(original==e['snapshot'],'SETTLEMENT_ENDPOINT_SOURCE_CHANGED')
    # Original receipt stays untouched; post-T events never become observation
    # rotation/fault recovery evidence. This module only classifies coverage.
    late=[row for row in snapshot['rows'] if row['received_ms']>p['endpoint_ms']]
    passed=not snapshot['missing'] and not snapshot['conflict_event_ids']
    return {'schema':'atlas.ws.delivery-settlement.v1','policy':POLICY,
        'plan_sha256':plan['sha256'],'endpoint_receipt_sha256':endpoint['sha256'],
        'endpoint_ms':p['endpoint_ms'],'deadline_ms':p['deadline_ms'],
        'finished_ms':now,'finished_monotonic_ms':mono,
        'expected_bars':(p['eligible_end_ms']-p['eligible_start_ms'])//60000*len(json.loads(p['source']['symbols_json'])),
        'coverage_at_endpoint':e['coverage_at_endpoint'],'snapshot':snapshot,'late_arrivals':late,
        'status':'FULL_COVERAGE_SETTLED_WITHIN_POLICY' if passed else 'SETTLEMENT_COVERAGE_BLOCKED',
        'verifier_code_sha256':CODE_SHA256,'original_endpoint_receipt_unchanged':True,
        'operational_24h_acceptance':'NOT_ATTESTED','pit_oos':'NOT_ATTESTED',
        'orders':0,'trading_authority':'NONE'}


def finalize(database, plan_path, endpoint_path, destination):
    plan=plan_read(plan_path);endpoint=read(endpoint_path);now,mono=clock()
    return publish(destination,build_final(database,plan,endpoint,now,mono))


def verify(database, plan_path, endpoint_path, final_path, *, expected_plan_sha256,
           expected_endpoint_sha256, expected_verifier_code_sha256):
    plan=plan_read(plan_path);endpoint=read(endpoint_path);final=read(final_path)
    need(expected_verifier_code_sha256==CODE_SHA256 and plan['sha256']==expected_plan_sha256
         and endpoint['sha256']==expected_endpoint_sha256,'SETTLEMENT_EXTERNAL_PIN')
    body=final['body']
    independent=build_final(database,plan,endpoint,body['finished_ms'],body['finished_monotonic_ms'])
    need(independent==body,'SETTLEMENT_SOURCE_RECOMPUTE_MISMATCH')
    return {'status':'SETTLEMENT_COVERAGE_PASS' if body['status']=='FULL_COVERAGE_SETTLED_WITHIN_POLICY'
        else 'SETTLEMENT_COVERAGE_BLOCKED','endpoint_ms':body['endpoint_ms'],
        'coverage_at_endpoint':body['coverage_at_endpoint'],'settled_bars':len(body['snapshot']['rows']),
        'late_bars':len(body['late_arrivals']),'operational_24h_acceptance':'NOT_ATTESTED',
        'orders':0,'trading_authority':'NONE'}
