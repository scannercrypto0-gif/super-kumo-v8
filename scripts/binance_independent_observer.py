"""Standalone public market-data capture. No G1 or trading integration."""
import argparse
import json
import os
from pathlib import Path
import multiprocessing
from aql.observer_runtime import atomic_json, clock_metadata, snapshot_loop
from aql.evidence_outbox import EvidenceOutbox
import time
import urllib.request
import websocket
from aql.binance_observer import ObserverLedger, payload, ws_payload, canonical
REST = 'https://data-api.binance.vision'
WS = 'wss://data-stream.binance.vision/ws/btcusdt@kline_1m'


def get(path):
    start = time.time_ns()//1_000_000; mono = time.monotonic_ns()
    with urllib.request.urlopen(REST+path, timeout=12) as r:
        raw = r.read().decode()
        return raw, dict(start_wall_ms=start, wall_ms=time.time_ns()//1_000_000,
            start_monotonic_ns=mono, monotonic_ns=time.monotonic_ns(), headers=dict(r.headers), status=r.status)


def checkpoint(ledger, outbox):
    """Local only. A full queue/disk error is visible; ledger remains recoverable."""
    try:
        key = ledger.queue_external_evidence(outbox)
        print(json.dumps(dict(outbox_sha256=key, status="LOCAL_PENDING")), flush=True)
        return key
    except Exception as exc:
        print(json.dumps(dict(status="LOCAL_EXPORT_PENDING", error=type(exc).__name__)), flush=True)
        return None


def run(directory, seconds, *, max_uncertainty_ms=100, clock_sample=None):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    ledger = ObserverLedger(directory/'observer.sqlite3')
    atomic_json(directory/'runtime-session.json', {'observer_session': ledger.session})
    ctx = multiprocessing.get_context('spawn')
    stop = ctx.Event()
    worker = ctx.Process(target=snapshot_loop,
        args=(directory/'observer.sqlite3', directory/'outbox', stop), daemon=True)
    try:
        worker.start()
    except Exception as exc:
        print(json.dumps(dict(status='LOCAL_QUEUE_WORKER_FAILED', error=type(exc).__name__)), flush=True)
    clock_sample = clock_sample or directory/'utc-sample.json'
    deadline = time.monotonic()+seconds if seconds is not None else None
    sock = None; next_poll = 0; retry = 1; clock_ref = None
    try:
        while deadline is None or time.monotonic() < deadline:
            def utc_metadata(wall, mono):
                return clock_metadata(ledger, clock_sample, wall, mono,
                                      maximum_ms=max_uncertainty_ms)
            if time.monotonic() >= next_poll:
                next_poll = time.monotonic()+30
                try:
                    raw, timing = get('/api/v3/time'); server_ms = json.loads(raw)['serverTime']
                    clock_ref = ledger.record('CLOCK_SAMPLE', dict(raw=raw, endpoint=REST+'/api/v3/time', timing=timing,
                        authority='BINANCE_SOURCE_REPORTED_ONLY', independent_utc=False, uncertainty_ms=None, utc_status='UNKNOWN'))
                    raw, timing = get('/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=5')
                    for row in json.loads(raw):
                        if row[6] >= min(timing['wall_ms'], server_ms): continue
                        ledger.observe(payload(symbol='BTCUSDT', interval='1m', row=row), raw=raw,
                            endpoint=REST+'/api/v3/klines', transport='REST', wall_ms=timing['wall_ms'],
                            monotonic_ns=timing['monotonic_ns'], clock_ref=clock_ref,
                            metadata=dict(symbol='BTCUSDT', interval='1m', timing=timing,
                                **utc_metadata(timing['wall_ms'], timing['monotonic_ns'])))
                except Exception as e:
                    ledger.record('GAP', dict(reason='REST_OR_CLOCK_FAILURE', error=str(e), coverage='UNKNOWN'))
            try:
                if sock is None:
                    sock = websocket.create_connection(WS, timeout=5)
                    ledger.record('CONNECTED', dict(endpoint=WS, session=ledger.session, coverage='UNKNOWN')); retry = 1
                raw = sock.recv(); wall = time.time_ns()//1_000_000; mono = time.monotonic_ns()
                if not raw: raise ConnectionError('empty stream')
                p, msg = ws_payload(raw, 'BTCUSDT', '1m')
                if p:
                    ledger.observe(p, raw=raw, endpoint=WS, transport='WS', wall_ms=wall, monotonic_ns=mono,
                        clock_ref=clock_ref, source_event_ms=msg['E'], metadata=dict(f=msg['k']['f'], L=msg['k']['L'], x=True, **utc_metadata(wall, mono)))
            except websocket.WebSocketTimeoutException:
                ledger.record('GAP', dict(reason='RECEIVE_TIMEOUT', coverage='UNKNOWN'))
            except Exception as e:
                ledger.record('GAP', dict(reason='DISCONNECT_OR_REJECTED_EVENT', error=str(e), coverage='UNKNOWN'))
                if sock: sock.close(); sock = None
                time.sleep(retry if deadline is None else min(retry, max(0, deadline-time.monotonic()))); retry = min(retry*2, 30)
    finally:
        if sock: sock.close()
        ledger.record('SESSION_STOP', dict(coverage='UNKNOWN', reason='bounded_capture_end'))
        stop.set()
        if worker.pid:
            worker.join(2)
            if worker.is_alive():
                worker.terminate()
                worker.join()
                print(json.dumps(dict(status='LOCAL_QUEUE_FINAL_SNAPSHOT_PENDING')), flush=True)
        bundle = ledger.bundle(); out = directory/f'bundle-{ledger.session}.json'
        with out.open('x') as f:
            f.write(canonical(bundle)+'\n'); f.flush(); os.fsync(f.fileno())
        print(json.dumps(dict(bundle=str(out), head=bundle['ledger_head'], versions=len(ledger.versions()))))
        ledger.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--directory', required=True); p.add_argument('--seconds', type=int, default=None)
    p.add_argument('--clock-sample', default=None)
    p.add_argument('--max-uncertainty-ms', type=float, default=100)
    args = p.parse_args()
    if args.seconds is not None and args.seconds < 1: p.error('positive duration required')
    run(args.directory, args.seconds, clock_sample=args.clock_sample, max_uncertainty_ms=args.max_uncertainty_ms)
