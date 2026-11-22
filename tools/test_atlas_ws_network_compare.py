"""Actual pinned frame parser and canonical reader, generated wire only."""
from contextlib import contextmanager
import json
import socket
from unittest.mock import patch

import pytest
import websocket
from tools import atlas_ws_network_compare as probe
from tools.binance_live_feed.run_pilot import PublicTransport
from tools.binance_live_feed.quota import Quota,Limits


class Clock:
    def __init__(self):self.value=1795335370000
    def now(self):return self.value
    def monotonic(self):return self.value/1000


class Sock:
    def __init__(self,clock,wire,error,step=10):self.clock=clock;self.wire=bytearray(wire);self.error=error;self.step=step;self.sent=bytearray();self.timeout=30
    def recv(self,n):
        self.clock.value+=self.step
        if not self.wire:raise self.error
        b=bytes(self.wire[:n]);del self.wire[:n];return b
    def send(self,b):self.sent.extend(b);return len(b)
    def settimeout(self,n):self.timeout=n
    def gettimeout(self):return self.timeout


class Transport:
    def __init__(self,sock,connect_error=None):self.sock=sock;self.calls=0;self.connect_error=connect_error
    @contextmanager
    def stream(self,endpoint,timeout):
        self.calls+=1
        if self.connect_error:raise self.connect_error
        c=websocket.WebSocket();c.sock=self.sock;c.connected=True;c.getstatus=lambda:101
        yield c
    def frame(self,c,timeout):return PublicTransport().frame(c,timeout)


def packet(data,opcode):
    f=websocket.ABNF.create_frame(data,opcode);f.mask_value=0;return f.format()


def reset():
    e=ConnectionResetError(10054,'DO_NOT_LEAK_RESET_MESSAGE');e.winerror=10054;return e


@pytest.mark.parametrize('mode',['production','reference'])
def test_real_reader_ping_pong_echo_no_price_retention_and_os_reset(tmp_path,mode):
    c=Clock();ping=b'CONTROL_NONCE'
    wire=packet(ping,websocket.ABNF.OPCODE_PING)+packet(b'PRIVATE_MARKET_TEXT',websocket.ABNF.OPCODE_TEXT)
    s=Sock(c,wire,reset());t=Transport(s);q=Quota(tmp_path/'quota.sqlite',Limits(rest_weight=2,connections=4))
    with patch.object(socket,'socket',side_effect=AssertionError('NETWORK_DISABLED')):
        result=probe.observe_reader(mode,t,q,c,900)
    assert result['status']=='READER_INTERRUPTED' and result['fault_stage']=='FRAME_READ'
    assert result['os_codes']==dict(errno=10054,winerror=10054)
    assert result['counters']['ping_frames']==result['counters']['text_frames']==1
    assert result['counters']['local_pong_returns']==result['counters']['pong_echo_matches']==1
    assert t.calls==1 and b'PRIVATE_MARKET_TEXT' not in bytes(s.sent)
    serialized=json.dumps(result)
    assert 'PRIVATE_MARKET_TEXT' not in serialized and 'CONTROL_NONCE' not in serialized and 'DO_NOT_LEAK_RESET_MESSAGE' not in serialized
    # Decode the actual library's outbound masked PONG and verify exact bytes.
    decoder=websocket.WebSocket();decoder.sock=Sock(c,bytes(s.sent),reset())
    frame=decoder.recv_frame()
    assert frame.opcode==websocket.ABNF.OPCODE_PONG and frame.data==ping and frame.mask_value


@pytest.mark.parametrize('mode',['production','reference'])
def test_partial_header_never_continues_on_same_socket(tmp_path,mode):
    c=Clock();s=Sock(c,b'\x81',websocket.WebSocketTimeoutException('injected partial'))
    t=Transport(s);q=Quota(tmp_path/'quota.sqlite',Limits(rest_weight=2,connections=4))
    r=probe.observe_reader(mode,t,q,c,900)
    assert r['status']=='READER_INTERRUPTED' and r['receive_phase']=='PARTIAL_HEADER'
    assert not r['retry_eligible'] and t.calls==1
    assert not any(e['status']=='EMPTY_BOUNDARY_POLL' for e in r['events'])


@pytest.mark.parametrize('mode',['production','reference'])
def test_empty_boundary_silence_is_bounded_to_ninety_seconds(tmp_path,mode):
    c=Clock();s=Sock(c,b'',websocket.WebSocketTimeoutException('silent'),step=30001)
    t=Transport(s);q=Quota(tmp_path/'quota.sqlite',Limits(rest_weight=2,connections=4))
    r=probe.observe_reader(mode,t,q,c,900)
    assert r['status']=='READER_INTERRUPTED' and r['receive_phase']=='FRAME_BOUNDARY'
    assert len([e for e in r['events'] if e['status']=='EMPTY_BOUNDARY_POLL'])==2
    assert t.calls==1


def test_budget_and_state_guards_do_not_create_a_socket(tmp_path):
    c=Clock();t=Transport(Sock(c,b'',reset()));q=Quota(tmp_path/'quota.sqlite',Limits(rest_weight=2,connections=4))
    with q.tx() as db:q.set(db,'ban',1)
    with pytest.raises(ValueError,match='QUOTA_STOP'):probe.observe_reader('production',t,q,c,900)
    assert t.calls==0
    with q.tx() as db:q.set(db,'ban',0)
    def changed():raise ValueError('STATE_DRIFT')
    r=probe.observe_reader('reference',t,q,c,900,changed)
    assert t.calls==0 and r['status']=='READER_INTERRUPTED'


def test_sequential_differences_never_claim_root_cause_or_service_health():
    good=dict(status='OBSERVATION_WINDOW_COMPLETED');bad=dict(status='READER_INTERRUPTED')
    assert 'UNPROVEN' in probe.verdict([good,good])
    assert 'NOT_CAUSAL_PROOF' in probe.verdict([good,bad])
    assert 'REQUIRES_HOST_TRACE' in probe.verdict([bad,bad])


@pytest.mark.parametrize('status,eligible,code,allowed',[
    ('OBSERVATION_WINDOW_COMPLETED',None,None,True),
    ('READER_INTERRUPTED',True,429,False),
    ('READER_INTERRUPTED',False,None,False),
    ('READER_INTERRUPTED',True,None,True),
    ('READER_INTERRUPTED',True,418,False),
    ('READER_INTERRUPTED',True,403,False)])
def test_terminal_ban_protocol_and_clock_faults_do_not_open_second_connection(status,eligible,code,allowed):
    assert probe.compare_next(dict(status=status,retry_eligible=eligible,provider_status=code)) is allowed
    assert 'NO_SECOND_CONNECTION' in probe.verdict([dict(status=status)])
