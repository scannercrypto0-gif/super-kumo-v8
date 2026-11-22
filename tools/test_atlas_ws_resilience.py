"""Deterministic production-parser recovery tests; no network or host data."""
from contextlib import contextmanager, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import socket
import ssl
import tempfile
import unittest
from unittest.mock import Mock, patch

import websocket
from aql.observation.contracts import digest
from tools import atlas_live_research_cycle as cycle
from tools.atlas_ws_receive_diagnostics import classify_transport_fault, receive_fault_context
from tools.binance_live_feed.run_pilot import PublicTransport

SLOT = 1794654000000
STEP = cycle.STEP
FIXTURE = json.loads(cycle.FIXTURE.read_text())[0]


class Clock:
    def __init__(self): self.current = SLOT + 100
    def now(self): return self.current
    def monotonic_ns(self): return (self.current - SLOT) * 1_000_000
    def wait(self, seconds): self.current += round(seconds * 1000)


def final(opened=SLOT, **changes):
    close = opened + STEP - 1
    candle = dict(s="BTCUSDT", i="15m", t=opened, T=close,
                  o="100", h="102", l="99", c="101", v="3", x=True)
    candle.update(changes)
    return json.dumps(dict(E=close + 10, k=candle)).encode()


class Wire:
    """Replay byte faults through pinned #305 framing, not a replacement parser."""
    def __init__(self, clock, script, connect_faults=()):
        self.clock, self.script = clock, iter(script)
        self.connect_faults = iter(connect_faults)
        self.attempts = 0
        self.pongs = []
        self.connections = []

    @contextmanager
    def stream(self, endpoint, timeout):
        self.attempts += 1
        error = next(self.connect_faults, None)
        if error is not None: raise error
        connection = websocket.WebSocket()
        self.connections.append(connection)
        connection.getstatus = lambda:101
        connection.pong = self.pongs.append
        yield connection

    def frame(self, connection, timeout):
        item = next(self.script)
        delivery = isinstance(item, tuple) and item[0] == "raw"
        packet_delivery = isinstance(item, tuple) and item[0] == "packet"
        if isinstance(item, tuple) and not delivery and not packet_delivery:
            fragments, ticks = item
            connection.frame_buffer.recv = Mock(side_effect=fragments)
            with patch('tools.binance_live_feed.run_pilot.time.monotonic', side_effect=ticks):
                return PublicTransport().frame(connection, timeout)
        if isinstance(item, BaseException): raise item
        if packet_delivery:
            packet = item[1]
            self.clock.current += 1
        elif delivery:
            _, item, received = item
            self.clock.current = received
        else:
            try: opened = json.loads(item).get('k',{}).get('t',SLOT)
            except (ValueError,AttributeError): opened = SLOT
            self.clock.current = max(self.clock.current,opened+STEP+499)
        if not packet_delivery:
            packet = websocket.ABNF.create_frame(item, websocket.ABNF.OPCODE_TEXT)
            packet.mask_value = 0
            packet = packet.format()
        wire = bytearray(packet)
        def recv(n):
            block = bytes(wire[:n]); del wire[:n]; return block
        connection.frame_buffer.recv = recv
        return PublicTransport().frame(connection, timeout)


def boundary_timeout():
    return ([websocket.WebSocketTimeoutException('synthetic socket timeout')], (0, 1))


def boundary_reset(): return ([ConnectionResetError('synthetic reset')], (0, 1))


class ResilienceTests(unittest.TestCase):
    def execute(self, wire, clock, *, root=None, sustained=False):
        owned = tempfile.TemporaryDirectory() if root is None else None
        if owned: self.addCleanup(owned.cleanup); root = Path(owned.name)/'run'
        plan = (cycle.make_plan(SLOT, FIXTURE, 8, sustained_research=True) if sustained else
                cycle.make_plan(SLOT, FIXTURE, 2, bounded_operations=True))
        pin = digest(plan)
        qual = dict(plan_sha256=pin, endpoint=plan['endpoint'], raw_retention_ms=0,
                    source_rights_ref='FIXTURE', region_ref='FIXTURE', custody_ref='FIXTURE',
                    network_permission_ref='FIXTURE', clock_checked_ms=clock.now(),
                    clock_uncertainty_ms=10, state_path=str(root.resolve()))
        self.root = root
        with patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_DISABLED')), \
             patch('time.time', side_effect=lambda:clock.now()/1000), \
             patch('aql.observation.prospective.time_ns', side_effect=lambda:clock.now()*1_000_000), \
             redirect_stdout(StringIO()):
            return cycle.run(root, plan, pin, FIXTURE, verifier=None, clock=clock,
                transport=wire, wait=clock.wait, synthetic=True, pilot_qualification=qual)

    def health(self): return [json.loads(s) for s in (self.root/'health.jsonl').read_text().splitlines()]

    def test_continuous_empty_boundary_polls_do_not_consume_connection(self):
        clock=Clock(); wire=Wire(clock,[boundary_timeout(),final(),final(SLOT+STEP)])
        with patch('tools.atlas_ws_continuity.authority',return_value={'policy':'test'}), \
             patch('tools.atlas_ws_continuity.reserve',return_value=0):
            result=self.execute(wire,clock,sustained=False)
        # Default/bounded operations cannot silently opt into continuous policy.
        self.assertEqual(wire.attempts,2)

    def test_continuous_poll_same_socket_and_eight_bar_completion(self):
        clock=Clock(); wire=Wire(clock,[boundary_timeout(),boundary_timeout(),*[final(SLOT+i*STEP) for i in range(8)]])
        with patch('tools.atlas_ws_continuity.authority',return_value={'policy':'test'}), \
             patch('tools.atlas_ws_continuity.reserve',return_value=0):
            result=self.execute(wire,clock,sustained=True)
        self.assertEqual((wire.attempts,len(result['bars'])),(1,8))
        self.assertEqual(sum(e['status']=='IDLE_READ_POLL' for e in self.health()),2)
        self.assertTrue(all('attempt' in e for e in self.health() if e['status']=='TRANSPORT_INTERRUPTED'))

    def test_continuous_ninety_second_silence_reconnects_but_partial_frame_stops(self):
        for partial in (False,True):
            clock=Clock()
            script=([([b'\x81',websocket.WebSocketTimeoutException('partial')],(0,1,2))] if partial else
                    [boundary_timeout()]*3)+[final(SLOT+i*STEP) for i in range(8)]
            wire=Wire(clock,script);original=wire.frame
            def advance(connection,timeout):
                clock.current+=31000
                return original(connection,timeout)
            wire.frame=advance
            with patch('tools.atlas_ws_continuity.authority',return_value={'policy':'test'}), \
                 patch('tools.atlas_ws_continuity.reserve',return_value=0):
                if partial:
                    with self.assertRaisesRegex(ValueError,'PILOT_STOP_TimeoutError'):self.execute(wire,clock,sustained=True)
                    self.assertEqual(wire.attempts,1)
                else:
                    result=self.execute(wire,clock,sustained=True)
                    self.assertEqual((wire.attempts,len(result['bars'])),(2,8))
                    self.assertEqual(sum(e['status']=='IDLE_READ_POLL' for e in self.health()),2)

    def test_continuous_report_requires_three_real_production_segment_summaries(self):
        import hashlib
        from datetime import datetime, timezone
        from tools import atlas_ws_continuity as policy
        with tempfile.TemporaryDirectory() as tmp:
            owner=Path(tmp)/'owner';owner.mkdir()
            from test_atlas_ws_continuity import install
            config,config_pin=install(owner,activated=SLOT+100)
            origin=SLOT
            for i in range(3):
                opened=origin+i*8*STEP
                with patch.dict(globals(),SLOT=opened):
                    clock=Clock()
                    script=([boundary_reset()] if i==0 else [])+[final(opened+j*STEP) for j in range(8)]
                    self.execute(Wire(clock,script),clock,root=owner/'segments'/str(opened),sustained=True)
                event=dict(utc=datetime.fromtimestamp(clock.now()/1000,timezone.utc).isoformat(),status='COMPLETE',reason='',slot_ms=opened)
                with (owner/'supervisor.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
                result=policy.report(owner,config_pin,clock.now())
                self.assertEqual(result['acceptance_ready'],i==2)
            self.assertEqual((result['verified_receipts'],result['confirmed_rollovers']),(24,2))
            self.assertTrue(result['later_receipt_after_real_fault'])
            self.assertEqual(result['missing_open_ranges'],[])
            (owner/'hold.json').write_text(json.dumps(dict(reason='TERMINAL_GUARD')))
            held=policy.report(owner,config_pin,clock.now())
            self.assertFalse(held['acceptance_ready']);self.assertEqual(held['status'],'HELD')
            receipt=next((owner/'segments'/'receipts').glob('*.json'))
            body=json.loads(receipt.read_text());body['orders']=1;receipt.write_text(json.dumps(body))
            with self.assertRaisesRegex(ValueError,'SERVICE_RECEIPT_INTEGRITY'):policy.report(owner,config_pin,clock.now())

    def test_continuous_report_waits_for_valid_initial_schedule_not_expired_ticket(self):
        from test_atlas_ws_continuity import install
        from tools import atlas_ws_continuity as policy
        with tempfile.TemporaryDirectory() as tmp:
            owner=Path(tmp);(owner/'segments').mkdir()
            config,pin=install(owner,activated=SLOT+100)
            a=json.loads((owner/'continuous-research.authorized.json').read_text())
            (owner/'hold.json').write_text(json.dumps(dict(reason='PILOT_STOP_ConnectionResetError')))
            (owner/'operator-resume.authorized.json').write_text(json.dumps(dict(schema='atlas.ws.operator-resume.v1',
                authorization_sha256=a['authorization_sha256'],config_sha256=pin,issued_ms=SLOT+100,expires_ms=SLOT+600100)))
            r=policy.report(owner,pin,SLOT+200)
            self.assertEqual(r['status'],'AWAITING_EXISTING_SCHEDULE');self.assertTrue(r['initial_resume_pending'])
            self.assertFalse(r['acceptance_ready'])
            expired=policy.report(owner,pin,SLOT+600101)
            self.assertEqual(expired['status'],'HELD');self.assertFalse(expired['initial_resume_pending'])

    def test_clean_and_duplicate_same_bytes_use_one_connection_and_two_logical_acks(self):
        clock=Clock(); wire=Wire(clock,[final(),final(),final(SLOT+STEP)])
        result=self.execute(wire,clock)
        self.assertEqual((wire.attempts,len(result['bars'])),(1,2))
        self.assertEqual(len({r['ack_sha256'] for r in result['bars']}),2)
        self.assertEqual(result['secretary'],'WAIT')
        self.assertEqual(result['orders'],0)
        self.assertFalse(any(self.root.rglob('receipt.sqlite')))

    def test_known_boundary_reset_timeout_and_library_close_recover_once(self):
        for fault in (boundary_reset(), boundary_timeout(),
                      ([websocket.WebSocketConnectionClosedException('not published')],(0,1))):
            with self.subTest(fault=type(fault[0][0]).__name__):
                clock=Clock(); wire=Wire(clock,[fault,final(),final(SLOT+STEP)])
                result=self.execute(wire,clock)
                self.assertEqual((wire.attempts,len(result['bars'])),(2,2))
                event=next(x for x in self.health() if x['status']=='TRANSPORT_INTERRUPTED')
                self.assertTrue(event['retry_eligible'])
                self.assertEqual(event['receive_phase'],'FRAME_BOUNDARY')
                self.assertLessEqual(len(event['exception_chain']),4)

    def test_verified_graceful_close_retries_and_restores_original_parser(self):
        for body in (b'', (1000).to_bytes(2,'big'), (1001).to_bytes(2,'big')+b'private reason'):
            frame=websocket.ABNF(fin=1,opcode=websocket.ABNF.OPCODE_CLOSE,mask_value=0,data=body)
            clock=Clock();wire=Wire(clock,[('packet',frame.format()),final(),final(SLOT+STEP)])
            result=self.execute(wire,clock)
            self.assertEqual((wire.attempts,len(result['bars'])),(2,2))
            self.assertTrue(all(c.recv_frame.__func__ is websocket.WebSocket.recv_frame for c in wire.connections))
            log=(self.root/'health.jsonl').read_text()
            self.assertIn('VERIFIED_GRACEFUL_CLOSE',log)
            self.assertNotIn('private reason',log)

    def test_policy_invalid_masked_and_binary_frames_are_not_graceful_close(self):
        frames=[websocket.ABNF(fin=1,opcode=websocket.ABNF.OPCODE_CLOSE,mask_value=0,
                              data=code.to_bytes(2,'big')) for code in (1002,1007,1008,1011)]
        frames.extend([
            websocket.ABNF(fin=1,opcode=websocket.ABNF.OPCODE_CLOSE,mask_value=1,data=b''),
            websocket.ABNF(fin=1,opcode=websocket.ABNF.OPCODE_CLOSE,mask_value=0,data=b'x'),
            websocket.ABNF(fin=1,opcode=websocket.ABNF.OPCODE_BINARY,mask_value=0,data=b'x'),
        ])
        for frame in frames:
            clock=Clock();wire=Wire(clock,[('packet',frame.format()),final()])
            with self.assertRaises(ValueError):self.execute(wire,clock)
            self.assertEqual(wire.attempts,1)
            self.assertIs(wire.connections[0].recv_frame.__func__,websocket.WebSocket.recv_frame)
            self.assertNotIn('VERIFIED_GRACEFUL_CLOSE',(self.root/'health.jsonl').read_text())

    def test_partial_header_length_payload_and_outer_deadline_never_reconnect(self):
        cases=(
            ([b'\x81',websocket.WebSocketTimeoutException('partial')],(0,1,2),'PARTIAL_HEADER'),
            ([b'\x81\x7e',b'\x01',ConnectionResetError('partial')],(0,1,2,3),'EXTENDED_LENGTH'),
            ([b'\x81\x04',b'ab',websocket.WebSocketTimeoutException('partial')],(0,1,2,3),'FRAME_PAYLOAD'),
            ([b'\x81\x04',b'ab',websocket.WebSocketConnectionClosedException('partial close')],
             (0,1,2,3),'FRAME_PAYLOAD'),
            ([b'\x81'],(0,1,31),'PARTIAL_HEADER'),
        )
        for fragments,ticks,phase in cases:
            with self.subTest(phase=phase):
                clock=Clock();wire=Wire(clock,[(fragments,ticks),final(),final(SLOT+STEP)])
                with self.assertRaisesRegex(ValueError,'PILOT_STOP_(TimeoutError|ConnectionResetError)'):
                    self.execute(wire,clock)
                self.assertEqual(wire.attempts,1)
                event=next(x for x in self.health() if x['status']=='TRANSPORT_INTERRUPTED')
                self.assertFalse(event['retry_eligible']);self.assertEqual(event['receive_phase'],phase)
                self.assertFalse(any(x['status']=='EPHEMERAL_RESEARCH_BAR' for x in self.health()))

    def test_unknown_receive_timeout_and_nontransport_timeout_are_terminal(self):
        clock=Clock();wire=Wire(clock,[TimeoutError('not classified'),final()])
        with self.assertRaisesRegex(ValueError,'PILOT_STOP_TimeoutError'):self.execute(wire,clock)
        self.assertEqual(wire.attempts,1)
        for stage in ('VALIDATE_AND_PERSIST','HANDSHAKE','CLOSE'):
            self.assertFalse(classify_transport_fault(TimeoutError(),{},stage)['retry_eligible'])

    def test_reset_then_timeout_exhausts_two_attempts_and_restart_does_not_reuse_ephemeral_plan(self):
        clock=Clock();wire=Wire(clock,[boundary_reset(),boundary_timeout(),final()])
        with self.assertRaisesRegex(ValueError,'PILOT_STOP_TimeoutError'):self.execute(wire,clock)
        self.assertEqual(wire.attempts,2)
        interruptions=[x for x in self.health() if x['status']=='TRANSPORT_INTERRUPTED']
        self.assertEqual([x['error'] for x in interruptions],['ConnectionResetError','TimeoutError'])
        self.assertTrue(all(x['retry_eligible'] for x in interruptions))
        clock.current=SLOT+100;restart=Wire(clock,[final(),final(SLOT+STEP)])
        with self.assertRaisesRegex(ValueError,'PILOT_STOP_EPHEMERAL_PILOT_ALREADY_CONSUMED'):
            self.execute(restart,clock,root=self.root)
        self.assertEqual(restart.attempts,0)

    def test_connect_faults_are_distinct_and_capped(self):
        clock=Clock();wire=Wire(clock,[final(),final(SLOT+STEP)],connect_faults=[TimeoutError('handshake timeout')])
        result=self.execute(wire,clock)
        event=next(x for x in self.health() if x['status']=='TRANSPORT_INTERRUPTED')
        self.assertEqual(event['fault_class'],'CONNECT_TIMEOUT')
        self.assertEqual((wire.attempts,len(result['bars'])),(2,2))
        for code,eligible in ((418,False),(429,False),(401,False),(403,False),(301,False),(503,True)):
            error=websocket.WebSocketBadStatusException('HTTP_REJECTION',code)
            self.assertEqual(classify_transport_fault(error,{},'CONNECT')['retry_eligible'],eligible)
        self.assertTrue(classify_transport_fault(socket.gaierror(socket.EAI_AGAIN,'temporary'),{},'CONNECT')['retry_eligible'])
        self.assertFalse(classify_transport_fault(socket.gaierror(socket.EAI_NONAME,'permanent'),{},'CONNECT')['retry_eligible'])
        self.assertFalse(classify_transport_fault(ssl.SSLCertVerificationError('certificate'),{},'CONNECT')['retry_eligible'])

    def test_candle_revision_foreign_and_future_frames_stay_terminal(self):
        for script in ([final(),final(c='100')], [final(s='OTHER')], [final(SLOT+STEP)]):
            clock=Clock();wire=Wire(clock,script)
            with self.assertRaises(ValueError):self.execute(wire,clock)
            self.assertEqual(wire.attempts,1)
            self.assertFalse(any(x.get('retry_eligible') for x in self.health()))

    def test_invalid_json_message_time_market_and_local_persistence_never_retry(self):
        future=json.loads(final());future['E']=SLOT+STEP+60_000
        cases=[b'{invalid', b'{"result":null,"id":1}', final(i='1m'),
               json.dumps(future).encode(), ('raw',final(),SLOT+STEP+300_001)]
        for raw in cases:
            with self.subTest(raw_type=type(raw).__name__):
                clock=Clock();wire=Wire(clock,[raw])
                with self.assertRaises(ValueError):self.execute(wire,clock)
                self.assertEqual(wire.attempts,1)
                self.assertFalse(any(x['status']=='EPHEMERAL_RESEARCH_BAR' for x in self.health()))
        clock=Clock();wire=Wire(clock,[final()])
        with patch.object(cycle,'consume_bar',side_effect=TimeoutError('local ACK timeout')):
            with self.assertRaisesRegex(ValueError,'PILOT_STOP_TimeoutError'):self.execute(wire,clock)
        self.assertEqual(wire.attempts,1)
        last=next(x for x in self.health() if x['status']=='FAULT_CLASSIFIED')
        self.assertEqual(last['fault_stage'],'VALIDATE_AND_PERSIST')
        self.assertFalse(last['retry_eligible'])

    def test_clock_drift_and_heartbeat_failure_never_reconnect(self):
        class DriftClock(Clock):
            def monotonic_ns(self):
                return super().monotonic_ns()+(1_000_000_000 if self.current>=SLOT+STEP else 0)
        clock=DriftClock();wire=Wire(clock,[final()])
        with self.assertRaisesRegex(ValueError,'PILOT_STOP_CLOCK_STEP'):self.execute(wire,clock)
        self.assertEqual(wire.attempts,1)
        clock=Clock();wire=Wire(clock,[final(),final(SLOT+STEP)])
        emit=cycle.emit
        def failing_emit(root,status,**kw):
            if status=='OBSERVING':raise TimeoutError('local heartbeat write')
            return emit(root,status,**kw)
        with patch.object(cycle,'emit',side_effect=failing_emit):
            with self.assertRaisesRegex(ValueError,'PILOT_STOP_TimeoutError'):self.execute(wire,clock)
        self.assertEqual(wire.attempts,1)
        event=next(x for x in self.health() if x['status']=='FAULT_CLASSIFIED')
        self.assertEqual(event['fault_stage'],'HEARTBEAT')
        self.assertFalse(event['retry_eligible'])

    def test_unknown_connection_diagnostic_does_not_mask_original(self):
        self.assertEqual(receive_fault_context(None,ConnectionResetError()),{})
        class BrokenDiagnostics:
            @property
            def frame_buffer(self): raise OSError('unavailable parser state')
        self.assertEqual(receive_fault_context(BrokenDiagnostics(),ConnectionResetError()),{})

    def test_deployment_marker_blocks_sustained_collector_before_a_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=Path(tmp);root=service/'segments'/str(SLOT);root.mkdir(parents=True)
            marker=service/'operator-deployment.in-progress';marker.write_text('guard')
            with self.assertRaisesRegex(ValueError,'OPERATOR_DEPLOYMENT_IN_PROGRESS'):
                cycle.operational_guard(root,sustained=True)
            self.assertEqual(marker.read_text(),'guard')
            self.assertFalse((root/'health.jsonl').exists())
            clock=Clock();wire=Wire(clock,[final()])
            with self.assertRaisesRegex(ValueError,'PILOT_STOP_OPERATOR_DEPLOYMENT_IN_PROGRESS'):
                self.execute(wire,clock,root=root,sustained=True)
            self.assertEqual(wire.attempts,0)
            self.assertTrue(marker.is_file())


if __name__=='__main__':unittest.main()
