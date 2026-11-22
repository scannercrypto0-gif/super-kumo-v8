"""Two sequential, explicitly invoked reader diagnostics; never service activation."""
from collections import Counter,deque
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

_spec=importlib.util.spec_from_file_location('atlas_net_operator',Path(__file__).with_name('atlas_ws_resilience_operator.py'))
op=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(op)
CONFIG='857bea957d1da3fa1ef1c01ace44a0bfda27f84c2750523184455936a48f2cf2'
ENDPOINT='wss://data-stream.binance.vision/ws/btcusdt@kline_15m'


class Clock:
    def __init__(self):self.utc=time.time_ns()//1000000;self.start=time.monotonic()
    def now(self):
        n=self.utc+round((time.monotonic()-self.start)*1000)
        op.need(abs(n-time.time_ns()//1000000)<=250,'NETWORK_COMPARE_CLOCK_STEP')
        return n
    monotonic=staticmethod(time.monotonic)
    wait=staticmethod(time.sleep)


def reference_frame(connection,timeout,clock):
    """Use canonical library control handling, with the same absolute read bound."""
    import websocket
    recv=connection.frame_buffer.recv;end=clock.monotonic()+timeout
    def bounded(size):
        left=end-clock.monotonic()
        if left<=0:raise websocket.WebSocketTimeoutException('frame deadline')
        connection.settimeout(left)
        return recv(size)
    connection.frame_buffer.recv=bounded
    try:
        opcode,frame=connection.recv_data_frame(control_frame=True)
        return {1:'text',9:'ping',10:'pong',8:'close'}.get(opcode,'unsupported'),frame.data
    finally:connection.frame_buffer.recv=recv


def observe_reader(mode,transport,quota,clock,duration,guard=lambda:None):
    from types import SimpleNamespace
    import websocket
    from tools.atlas_live_research_cycle import read_research_frame,send_research_pong
    from tools.atlas_ws_receive_diagnostics import receive_fault_context,classify_transport_fault
    op.need(mode in ('production','reference') and 0<duration<=900,'NETWORK_COMPARE_SCOPE')
    started=clock.now();end=clock.monotonic()+duration
    counters=Counter();events=deque(maxlen=256);pending=deque(maxlen=8)
    last_frame=started;max_gap=0;stage='CONNECT';connection=None
    def mark(status,**kw):events.append(dict(status=status,utc_ms=clock.now(),**kw))
    result=dict(reader=mode,started_ms=started,endpoint=ENDPOINT,window_seconds=duration)
    op.need(quota.connect('network-compare',started,['btcusdt@kline_15m']),'NETWORK_COMPARE_QUOTA_STOP')
    try:
        guard()
        with transport.stream(ENDPOINT,min(5,duration)) as connection:
            op.need(connection.getstatus()==101,'NETWORK_COMPARE_UPGRADE')
            mark('UPGRADE_101')
            original_frame=connection.recv_frame;original_pong=connection.pong
            def tracked_frame():
                nonlocal last_frame,max_gap
                frame=original_frame();n=clock.now()
                max_gap=max(max_gap,n-last_frame);last_frame=n
                counters['frames']+=1
                counters['nonfinal_frames']+=int(not frame.fin)
                counters[{1:'text_frames',9:'ping_frames',10:'pong_frames',8:'close_frames'}.get(frame.opcode,'other_frames')]+=1
                if frame.opcode==9:
                    pin=hashlib.sha256(bytes(frame.data)).hexdigest();pending.append(pin)
                    mark('PING_RECEIVED',payload_bytes=len(frame.data),payload_sha256=pin)
                elif frame.opcode==8:
                    mark('CLOSE_RECEIVED',close_code=int.from_bytes(frame.data[:2],'big') if len(frame.data)>=2 else None)
                return frame
            def tracked_pong(payload):
                nonlocal stage
                old=stage;stage='PONG'
                if mode=='reference':
                    send_research_pong(quota,'network-compare',clock.now(),SimpleNamespace(pong=original_pong),payload)
                else:original_pong(payload)
                counters['local_pong_returns']+=1
                pin=hashlib.sha256(bytes(payload)).hexdigest()
                matched=bool(pending and pin==pending[-1])
                counters['pong_echo_matches']+=int(matched)
                mark('LOCAL_PONG_RETURNED',echo_matches=matched,payload_bytes=len(payload))
                stage=old
            connection.recv_frame=tracked_frame;connection.pong=tracked_pong
            try:
                while clock.monotonic()<end:
                    guard();stage='FRAME_READ'
                    left=min(30,end-clock.monotonic())
                    if left<=0:break
                    try:
                        if mode=='production':kind,raw=read_research_frame(transport,connection,left)
                        else:kind,raw=reference_frame(connection,left,clock)
                    except (TimeoutError,websocket.WebSocketTimeoutException) as exc:
                        normalized=exc
                        if type(exc) is websocket.WebSocketTimeoutException:
                            normalized=TimeoutError('WS_READ_TIMEOUT');normalized.__cause__=exc
                        context=receive_fault_context(connection,normalized)
                        idle=clock.now()-last_frame
                        if context==dict(receive_phase='FRAME_BOUNDARY',deadline_origin='UNDERLYING_RECEIVE_TIMEOUT') and 0<=idle<90000:
                            mark('EMPTY_BOUNDARY_POLL',idle_ms=idle);continue
                        raise normalized
                    if kind=='ping' and mode=='production':
                        stage='PONG';send_research_pong(quota,'network-compare',clock.now(),connection,raw)
                    elif kind=='close':
                        result['status']='CLOSED_BY_PEER';break
                    elif kind not in ('text','ping','pong'):raise ValueError('NETWORK_COMPARE_UNSUPPORTED_FRAME')
                    # Data are discarded: no price, bar, raw frame or Core receipt is retained.
                    del raw
                else:result['status']='OBSERVATION_WINDOW_COMPLETED'
                result.setdefault('status','OBSERVATION_WINDOW_COMPLETED')
            finally:connection.recv_frame=original_frame;connection.pong=original_pong
    except Exception as exc:
        context=receive_fault_context(connection,exc) if connection is not None else {}
        provider=getattr(exc,'status_code',None)
        result['provider_status']=provider if type(provider) is int and 100<=provider<=599 else None
        result.update(status='READER_INTERRUPTED',error=type(exc).__name__,
                      **context,**classify_transport_fault(exc,context,stage))
        mark('INTERRUPTED',error=type(exc).__name__,stage=stage)
    finally:
        try:quota.disconnect('network-compare',clock.now(),failed=result.get('status')!='OBSERVATION_WINDOW_COMPLETED')
        except Exception as exc:result['cleanup_error']=type(exc).__name__
    result.update(ended_ms=clock.now(),counters=dict(counters),max_complete_frame_gap_ms=max_gap,
                  last_complete_frame_ms=last_frame,events=list(events),
                  pong_delivery='LOCAL_CALL_RETURN_ONLY_NOT_SERVER_ACK')
    return result


def compare_next(result):
    return result.get('status')=='OBSERVATION_WINDOW_COMPLETED' or (
        result.get('status')=='READER_INTERRUPTED' and result.get('retry_eligible') is True
        and result.get('provider_status') not in (401,403,418,429))


def verdict(results):
    if len(results)!=2:return 'COMPARISON_STOPPED_ON_TERMINAL_GATE_NO_SECOND_CONNECTION'
    ok=[r.get('status')=='OBSERVATION_WINDOW_COMPLETED' for r in results]
    if all(ok):return 'BOTH_READER_WINDOWS_COMPLETED_PIPELINE_OR_INTERMITTENT_CAUSE_STILL_UNPROVEN'
    if not any(ok):return 'BOTH_READERS_INTERRUPTED_COMMON_STACK_OR_NETWORK_REQUIRES_HOST_TRACE'
    return 'READER_DIFFERENCE_OBSERVED_SEQUENTIAL_WINDOWS_NOT_CAUSAL_PROOF'


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    p.add_argument('--expected-commit',required=True);p.add_argument('--owner-ref',required=True)
    a=p.parse_args();repo=Path(__file__).resolve().parents[1]
    op.verify_repo(repo,a.expected_commit)
    for name in ('tools/atlas_ws_network_compare.py','tools/ATLAS-WS-NETWORK-COMPARE.ps1'):
        subprocess.run(['git','-C',str(repo),'ls-files','--error-unmatch',name],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['git','-C',str(repo),'diff','--quiet','HEAD','--',name],check=True)
    op.need(bool(a.owner_ref.strip()),'NETWORK_COMPARE_OWNER_SCOPE_REQUIRED')
    cfgpath=op.safe(a.config);root=cfgpath.parent
    op.need(op.digest(op.read(cfgpath))==CONFIG,'NETWORK_COMPARE_CONFIG_DRIFT')
    cfg=op.load(cfgpath);tree=op.safe(cfg['tree'],exists=False)
    for binding in cfg['files']:op.need(op.digest(op.read(binding['path']))==binding['sha256'],'NETWORK_COMPARE_RUNTIME_PIN')
    sys.path[:0]=[str(tree/'src'),str(tree)]
    import websocket
    op.need(websocket.__version__=='1.9.2','NETWORK_COMPARE_WEBSOCKET_VERSION')
    from tools.atlas_single_receipt_runner import BinanceReceiptTransport
    from tools.binance_live_feed.quota import Quota,Limits
    from tools.atlas_ws_continuity import authority,reserve
    authority(root,CONFIG)
    held=op.read(root/'hold.json')
    failed_slot=op.load(root/'hold.json').get('slot_ms')
    op.need(type(failed_slot) is int,'NETWORK_COMPARE_FAILED_SLOT_IDENTITY')
    source_quota=op.quota_view(root/'segments'/str(failed_slot)/'quota.sqlite',time.time_ns()//1000000)
    op.need(source_quota['policy_verified'] and source_quota['ready'],'NETWORK_COMPARE_EXISTING_QUOTA_NOT_READY')
    op.need(op.load(root/'hold.json').get('reason')=='LIVE_SERVICE_CONTINUITY_CIRCUIT_OPEN','NETWORK_COMPARE_HOLD_SCOPE')
    for name in ('operator-resume.authorized.json','operator-recovery.active.json','segment-execution.active.json','operator-deployment.in-progress'):
        op.need(not (root/name).exists(),'NETWORK_COMPARE_CONCURRENT_OR_UNCERTAIN_EXECUTION')
    def guard():
        op.need(op.read(root/'hold.json')==held and op.digest(op.read(cfgpath))==CONFIG,'NETWORK_COMPARE_STATE_DRIFT')
        op.need(not (root/'stop.request').exists(),'NETWORK_COMPARE_OPERATOR_STOP')
    clock=Clock();plan=dict(schema='atlas.ws.reader-comparison-plan.v1',max_connections=2,
        seconds_per_reader=900,endpoint=ENDPOINT,owner_decision_ref=a.owner_ref,config_sha256=CONFIG,
        task_changes=0,source_class='NETWORK_DIAGNOSTIC_ONLY',orders=0,trading_authority='NONE')
    with op.collector_lease(root):
        guard();op.durable(root/('network-comparison.'+CONFIG+'.claimed'),op.canonical(plan),create=True)
        output=root/('network-compare-'+uuid.uuid4().hex);output.mkdir()
        op.durable(output/'plan.json',op.canonical(plan),create=True)
        results=[]
        for mode in ('production','reference'):
            while True:
                guard();delay=reserve(root/'continuous-admission.sqlite',clock.now(),clock.now()//900000*900000)
                if not delay:break
                clock.wait(min(delay/1000,10))
            state=output/mode;state.mkdir()
            quota=Quota(state/'quota.sqlite',Limits(rest_weight=2,connections=4))
            result=observe_reader(mode,BinanceReceiptTransport(),quota,clock,900,guard)
            results.append(result);op.durable(state/'result.json',op.canonical(result),create=True)
            if not compare_next(result):break
        body=dict(schema='atlas.ws.reader-comparison.v1',status=verdict(results),results=results,
            owner_decision_ref=a.owner_ref,hold_preserved=op.read(root/'hold.json')==held,
            task_changes=0,max_connections=2,orders=0,trading_authority='NONE',
            source_class='NETWORK_DIAGNOSTIC_ONLY',core_receipts_created=0,
            root_cause='RESET_ACTOR_NOT_PROVEN',service_restarted=False)
        op.durable(output/'comparison.json',op.canonical(body),create=True)
        print(json.dumps(dict(**body,report_directory=str(output)),sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        import re
        reason=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{1,119}',str(exc)) else 'NETWORK_COMPARE_PRIVATE_PREFLIGHT_OR_IO_FAILED'
        print(json.dumps(dict(status='NETWORK_COMPARISON_BLOCKED',reason=reason,service_restarted=False,orders=0,trading_authority='NONE')))
        raise SystemExit(2)
