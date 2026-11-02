"""One explicitly approved, bounded public WS engineering pilot; NEVER trading.

No collector.run/pipeline/REST/reconnect; existing collector authority and journal
commit code remain intact. Fresh isolated DBs only; no backlog or witness invented.
Importing this module never opens a network connection. Offline tests inject transport.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import signal
import ssl
import time
from pathlib import Path

from aql.collector.binance_collector import BinanceCollector
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.storage.operational_store import OperationalStore
from aql.delivery.authority import register_legacy_writer
from aql.g1_integrity import require_eligible_db

URL='wss://stream.binance.com:9443/ws/btcusdt@kline_15m'
BAR_MS=900000
DURATION_SECONDS=960
MAX_FINAL_BARS=1
MAX_FRAMES=2048
MAX_BYTES=4*1024*1024
APPROVAL='GO_RUN_R5B_PUBLIC_WS_UNVERIFIED_960S_1BAR'


class PilotStopped(ValueError):
    pass


def require(ok,reason):
    if not ok:
        raise PilotStopped(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return (json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def write_new(path,data):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
    except BaseException:
        raise


def append(path,obj):
    with path.open('ab') as f:
        f.write(canonical(obj));f.flush();os.fsync(f.fileno())


def strict_json(raw):
    def pairs(items):
        out={}
        for k,v in items:
            require(k not in out,'DUPLICATE_JSON_KEY');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,
                      parse_constant=lambda _:(_ for _ in ()).throw(PilotStopped('NONFINITE_JSON')))


def eligible_prefix(journal,cutoff):
    """Read actual final bars + eligible journal/receipt as-of, no REST/backfill."""
    conn=journal._connect()
    try:
        from aql.delivery.authority import deny_legacy
        deny_legacy(conn)
        payloads=conn.execute('SELECT payload_json FROM journal_entries ORDER BY bar_open').fetchall()
        bars=[]
        for row in payloads:
            bar=MarketBar.from_dict(json.loads(row[0]))
            require_eligible_db(conn,bar.stable_key())
            receipt=journal.commit_receipt(bar.stable_key())
            require(bar.compute_checksum()==bar.checksum,'PREFIX_CHECKSUM')
            require(bar.symbol=='BTCUSDT' and bar.interval=='15m' and bar.source=='binance_ws'
                    and bar.is_final is True,'PREFIX_SOURCE')
            if (bar.bar_close>=cutoff or bar.ingested_at>cutoff or receipt.get('version')!=1
                    or receipt['commit_return_observed_at_ms']>cutoff):
                continue
            require(not bars or bar.bar_open==bars[-1][0]+BAR_MS,'PREFIX_GAP')
            bars.append((bar.bar_open,bar.bar_close,bar.open,bar.high,bar.low,bar.close,bar.volume))
        return bars
    finally:
        conn.close()


class _CollectorCloseOnly:
    def close(self):
        pass  # No network callback/reconnect is attached to the collector.


class Pilot:
    def __init__(self,folder,*,operator,authority_ref,clock=time,engineering_scope='OFFLINE_TEST_ONLY'):
        require(operator and authority_ref,'OPERATOR_AND_APPROVAL_REFERENCE_REQUIRED')
        self.clock=clock;self.folder=Path(folder)
        require(not self.folder.exists(),'FRESH_ISOLATED_DIRECTORY_REQUIRED')
        self.folder.mkdir(parents=True)
        self.start_ms=int(clock.time()*1000);self.start_mono=clock.monotonic()
        self.deadline=self.start_mono+DURATION_SECONDS
        self.cutoff=(self.start_ms//BAR_MS+1)*BAR_MS
        self.frames=0;self.bytes=0;self.final_bars=0;self.previous='0'*64
        self.records=[];self.stop_reason='NOT_STARTED'
        self.engineering_scope=engineering_scope
        # Before any message/provider/network: immutable planned C2 BASE/SHADOW.
        # Future raw-content SHA is explicitly UNKNOWN, never replaced by a
        # hash of this locator/schedule and called a source content commitment.
        self.schedule=dict(schema_version='aql.r5b-source-engineering-schedule.v1',
            operator=operator,approval_ref=authority_ref,endpoint=URL,
            scheduled_at_ms=self.start_ms,planned_bar_close_exclusive_ms=self.cutoff,
            decision_status='NOT_EVALUATED',source_content_sha256=None,
            source_version='BINANCE_SPOT_WS_KLINE_15M',correction_generation='UNKNOWN',
            arms=[dict(arm=a,capture_status='MISSING_CAPTURE') for a in ('BASE','SHADOW')],
            hard_seconds=DURATION_SECONDS,max_new_final_bars=MAX_FINAL_BARS,
            witness_status='UNVERIFIED_LOCAL_CLOCK_AND_CUSTODY',
            original_G2_F1_F3='NOT_CONNECTED',trade_execution='DISABLED')
        self.schedule['c2_identity']=dict(trial_id='AQL-R5B-ENGINEERING-ONLY',
            opportunity_id='R5B-'+str(self.cutoff),producer_event_id='UNASSIGNED_NO_G2_EVENT',
            envelope_sha256=sha(canonical(self.schedule)))
        write_new(self.folder/'schedule.json',canonical(self.schedule))
        self.schedule_bytes=(self.folder/'schedule.json').read_bytes()
        self.journal=DurableJournal(str(self.folder/'isolated-journal.db'))
        self.store=OperationalStore(str(self.folder/'isolated-operational.db'))
        # Original collector constructor calls register_legacy_writer and denies
        # v2 activation before any socket; no authority table/token is altered.
        self.collector=BinanceCollector('BTCUSDT','15m',self.journal,self.store,max_bars=1)
        self.collector.background_persistence=True  # no store upsert/background worker

    def remaining(self):
        return max(0,self.deadline-self.clock.monotonic())

    def accept(self,raw):
        require(self.remaining()>0,'HARD_DEADLINE')
        require(self.final_bars<MAX_FINAL_BARS,'FINAL_BAR_CAP')
        require(type(raw) is bytes and len(raw)<=65536,'RAW_PAYLOAD_LIMIT_OR_TYPE')
        require(self.frames<MAX_FRAMES and self.bytes+len(raw)<=MAX_BYTES,'TRANSCRIPT_LIMIT')
        require((self.folder/'schedule.json').read_bytes()==self.schedule_bytes,'SCHEDULE_CHANGED')
        received=int(self.clock.time()*1000)
        self.frames+=1;self.bytes+=len(raw)
        raw_record=dict(seq=self.frames,previous_record_sha256=self.previous,
            raw_message_sha256=sha(raw),raw_message_base64=base64.b64encode(raw).decode(),
            received_at_utc_ms=received,received_monotonic=self.clock.monotonic(),
            raw_kind='EXACT_WS_APPLICATION_PAYLOAD_NOT_TLS_OR_FRAME_BYTES')
        self.previous=sha(canonical(raw_record));raw_record['record_sha256']=self.previous
        append(self.folder/'raw-events.jsonl',raw_record)
        data=strict_json(raw);k=data.get('k')
        require(data.get('e')=='kline' and data.get('s')=='BTCUSDT' and isinstance(k,dict), 'EVENT_IDENTITY')
        require(k.get('s')=='BTCUSDT' and k.get('i')=='15m' and type(k.get('x')) is bool,'KLINE_IDENTITY_FINALITY')
        if not k['x']:
            return False
        for field in ('t','T'):
            require(type(k.get(field)) is int,'KLINE_INTEGER_TIME')
        require(type(data.get('E')) is int,'EVENT_INTEGER_TIME')
        require(k['t']%BAR_MS==0 and k['T']==k['t']+BAR_MS-1,'FINAL_GRID')
        require(k['T']+1==self.cutoff and k['T']+1>self.start_ms,'NOT_NEW_PLANNED_FINAL_BAR')
        require(k['T']<received and k['T']<=data['E']<=received
                and 0<=received-k['T']<=10000 and received-data['E']<=10000,'LATE_OR_FUTURE_SOURCE_CLOCK')
        values=[float(k[f]) for f in ('o','h','l','c','v')]
        o,h,l,c,v=values
        require(all(math.isfinite(x) for x in values) and 0<l<=min(o,c)<=max(o,c)<=h and v>=0,'INVALID_OHLCV')
        # Stop before Collector if a duplicate or conflicting stable key exists.
        conn=self.journal._connect()
        try:
            require(not conn.execute('SELECT 1 FROM journal_entries WHERE stable_key=?',
                    (f'BTCUSDT:15m:{k["t"]}',)).fetchone(),'DUPLICATE_FINAL')
        finally: conn.close()
        errors=self.collector.metrics.error_count
        commits=self.collector.metrics.journal_commit_count
        self.collector._on_message(_CollectorCloseOnly(),raw.decode('utf-8'))
        require(self.collector.metrics.error_count==errors and
                self.collector.metrics.journal_commit_count==commits+1,'COLLECTOR_OR_AUTHORITY_REJECTED')
        receipt=self.journal.commit_receipt(f'BTCUSDT:15m:{k["t"]}')
        require(receipt.get('version')==1 and receipt.get('record_contract_version')==1,'JOURNAL_RECEIPT_MISSING')
        conn=self.journal._connect()
        try:
            stored=MarketBar.from_dict(json.loads(conn.execute(
                'SELECT payload_json FROM journal_entries WHERE stable_key=?',
                (f'BTCUSDT:15m:{k["t"]}',)).fetchone()[0]))
        finally: conn.close()
        expected=MarketBar.from_binance_ws_kline(k).compute_checksum()
        require(stored.compute_checksum()==stored.checksum==expected,'RAW_TO_JOURNAL_CONTENT_MISMATCH')
        record=dict(seq=self.frames,raw_message_sha256=sha(raw),raw_record_sha256=self.previous,
            source_event_ms=data['E'],bar_open_ms=k['t'],bar_close_ms=k['T'],
            received_at_utc_ms=received,stable_key=f'BTCUSDT:15m:{k["t"]}',journal_receipt=receipt,
            bar_checksum=expected,custody_status='LOCAL_UNVERIFIED_NOT_INDEPENDENT_PIT')
        append(self.folder/'receipts.jsonl',record)
        self.records.append(record);self.final_bars+=1
        require(self.remaining()>0,'HARD_DEADLINE_AFTER_COMMIT')
        return True

    def host_status(self):
        rows=eligible_prefix(self.journal,self.cutoff)
        if len(rows)<21:
            return dict(status='SOURCE_PREFIX_INSUFFICIENT',required_bars=21,
                        eligible_asof_bars=len(rows),captured_new_final_bars=self.final_bars,
                        r4_invoked=False,decision_status_by_arm={a:'NOT_EVALUATED' for a in ('BASE','SHADOW')})
        # Fresh one-bar pilot cannot legitimately reach this branch. No future
        # receipt or retrospective backlog may be smuggled into the R4 cutoff.
        require(rows[-1][1]+1==self.cutoff,'PREFIX_NOT_AT_R4_CUTOFF')
        raise PilotStopped('R4_READY_PREFIX_REQUIRES_SEPARATE_FULLY_BOUND_SOURCE_SCHEDULE')

    def finish(self,reason):
        self.stop_reason=reason
        try:
            status=self.host_status()
        except Exception as exc:
            status=dict(status='PREFIX_OR_AUTHORITY_DENIED',reason=type(exc).__name__+':'+str(exc)[:200],
                        r4_invoked=False,decision_status_by_arm={a:'NOT_EVALUATED' for a in ('BASE','SHADOW')})
        files={p.name:sha(p.read_bytes()) for p in self.folder.iterdir() if p.is_file()}
        result=dict(schema_version='aql.r5b-public-source-engineering.v1',
            evidence_scope=self.engineering_scope,stop_reason=reason,
            network_attempted=getattr(self,'network_attempted',False),
            source_live_engineering='UNVERIFIED_CAPTURED' if self.final_bars and self.engineering_scope=='OWNER_APPROVED_NETWORK_ENGINEERING' else 'NOT_ESTABLISHED',
            raw_frames=self.frames,raw_payload_bytes=self.bytes,new_final_bars=self.final_bars,
            scheduled_engineering_pairs=1,engineering_arm_slots=2,genuine_G2_opportunities=0,
            max_final_bars=1,hard_seconds=960,schedule_sha256=sha(self.schedule_bytes),
            endpoint=URL,rest_calls=0,reconnects=0,host=status,
            records=self.records,retained_file_sha256=files,
            r4_host_interface='invoke_g2_nontrading_NOT_CALLED_WITH_INSUFFICIENT_OR_UNBOUND_SOURCE',
            external_pit='BLOCKED_EXTERNAL_EVIDENCE',original_G2_F1_F3='NOT_CONNECTED',
            execution='DISABLED',g0_merge_deployment_authorized=False)
        write_new(self.folder/'result.json',canonical(result))
        return result


def run_session(pilot,connect):
    """Single transport attempt. Failure/deadline/EOF is terminal, never retried."""
    ws=None;reason='INCOMPLETE'
    try:
        require(pilot.remaining()>0,'HARD_DEADLINE_BEFORE_CONNECT')
        register_legacy_writer(pilot.journal,'r5b-before-single-ws')
        require((pilot.folder/'schedule.json').read_bytes()==pilot.schedule_bytes,'SCHEDULE_CHANGED')
        require(pilot.remaining()>0,'HARD_DEADLINE_AFTER_AUTHORITY_CHECK')
        pilot.network_attempted=True
        ws=connect(URL,timeout=min(5,pilot.remaining()),redirect_limit=0,
                   sslopt={'cert_reqs':ssl.CERT_REQUIRED,'check_hostname':True})
        while pilot.remaining()>0 and pilot.final_bars<MAX_FINAL_BARS:
            ws.settimeout(min(2,pilot.remaining()))
            try:
                opcode,raw=ws.recv_data()
            except TimeoutError:
                continue
            # websocket-client uses a distinct timeout type, not TimeoutError.
            except Exception as exc:
                import websocket
                if isinstance(exc,websocket.WebSocketTimeoutException):
                    continue
                raise
            require(pilot.remaining()>0,'HARD_DEADLINE_AFTER_RECEIVE')
            require(opcode==1 and raw,'UNEXPECTED_OPCODE_OR_DISCONNECT')
            pilot.accept(raw)
        reason='FINAL_BAR_CAP_REACHED' if pilot.final_bars==MAX_FINAL_BARS else 'HARD_DEADLINE'
    except Exception as exc:
        reason=type(exc).__name__+':'+str(exc)[:300]
    finally:
        if ws is not None:
            try: ws.close(timeout=0)
            except Exception: pass
    return pilot.finish(reason)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--approval',required=True);p.add_argument('--operator',required=True)
    p.add_argument('--approval-ref',required=True)
    a=p.parse_args()
    require(a.approval==APPROVAL,'EXACT_ONE_TIME_OWNER_APPROVAL_REQUIRED')
    require(os.environ.get('R5B_NETWORK_ENABLED')=='OWNER_APPROVED_MANUAL_DISPATCH','NETWORK_DISABLED_BY_DEFAULT')
    require(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch','MANUAL_DISPATCH_ONLY')
    require(os.environ.get('GITHUB_ACTOR')==a.operator,'OPERATOR_MUST_BE_WORKFLOW_INVOKER')
    require(os.environ.get('R5B_APPROVED_SHA')==os.environ.get('GITHUB_SHA')
            and bool(os.environ.get('R5B_APPROVED_SHA')),'EXACT_APPROVED_COMMIT_REQUIRED')
    # Signal handler unwinds through run_session finally and emits partial result.
    def stop(signum,frame): raise PilotStopped('OPERATOR_OR_OUTER_HARD_STOP')
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    pilot=Pilot(a.out,operator=a.operator,authority_ref=a.approval_ref,
                engineering_scope='OWNER_APPROVED_NETWORK_ENGINEERING')
    import websocket
    report=run_session(pilot,websocket.create_connection)
    print(canonical(report).decode())
    raise SystemExit(0 if report['source_live_engineering']=='UNVERIFIED_CAPTURED' else 2)


if __name__=='__main__': main()
