"""NEW R5B offline transport/authority tests only. No actual network/old suites."""
import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import datetime
from research_wp_r0.aql_r5b_run_authorization import verify_comment,deny_previous_runs,approval_body

from research_wp_r0.aql_r5b_public_pilot import (
    APPROVAL, BAR_MS, DURATION_SECONDS, Pilot, PilotStopped, canonical,
    eligible_prefix, main, run_session, sha,
)


class Clock:
    def __init__(self): self.utc=1700000000.;self.elapsed=0.
    def time(self): return self.utc
    def monotonic(self): return self.elapsed


def event(pilot):
    return dict(e='kline',s='BTCUSDT',E=pilot.cutoff+100,
                k=dict(s='BTCUSDT',i='15m',t=pilot.cutoff-BAR_MS,T=pilot.cutoff-1,
                       x=True,o='100',h='102',l='99',c='101',v='3'))


class Socket:
    def __init__(self,clock,events): self.clock=clock;self.events=list(events);self.closed=False
    def settimeout(self,value): self.timeout=value
    def recv_data(self):
        if not self.events:
            self.clock.elapsed+=2
            raise TimeoutError()
        data=self.events.pop(0)
        self.clock.utc=(data['k']['T']+151)/1000
        return 1,canonical(data)
    def close(self,**kwargs): self.closed=True


class R5BOnly(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.clock=Clock()
        self.addCleanup(patch.stopall)
        patch('time.time',self.clock.time).start()
        patch('websocket.create_connection',side_effect=AssertionError('REAL_NETWORK_FORBIDDEN_IN_TEST')).start()
        patch('urllib.request.urlopen',side_effect=AssertionError('REST_FORBIDDEN')).start()
        self.pilot=Pilot(Path(self.tmp.name)/'out',operator='OFFLINE_TEST_OPERATOR',
                         authority_ref='OFFLINE_TEST_NOT_OWNER_RUN',clock=self.clock)

    def receive(self,data):
        self.clock.utc=(self.pilot.cutoff+150)/1000
        return self.pilot.accept(canonical(data))

    def test_actual_collector_journal_receipt_and_raw_correlation_offline_only(self):
        original=event(self.pilot)
        self.assertTrue(self.receive(original))
        raw=json.loads((self.pilot.folder/'raw-events.jsonl').read_bytes())
        self.assertEqual(base64.b64decode(raw['raw_message_base64']),canonical(original))
        receipt=self.pilot.records[0]
        self.assertEqual(receipt['raw_message_sha256'],sha(canonical(original)))
        self.assertEqual(receipt['journal_receipt']['version'],1)
        self.assertEqual(receipt['raw_record_sha256'],raw['record_sha256'])
        self.assertEqual(self.pilot.collector.metrics.journal_commit_count,1)
        self.assertEqual(self.pilot.collector.metrics.store_insert_count,0)

    def test_preregister_before_single_transport_and_stop_at_one_bar(self):
        socket=Socket(self.clock,[event(self.pilot),event(self.pilot)])
        calls=[]
        def connect(url,**kwargs):
            self.assertTrue((self.pilot.folder/'schedule.json').exists())
            self.assertEqual([a['arm'] for a in self.pilot.schedule['arms']],['BASE','SHADOW'])
            self.assertEqual(kwargs['redirect_limit'],0)
            self.assertTrue(kwargs['sslopt']['check_hostname'])
            calls.append(url);return socket
        result=run_session(self.pilot,connect)
        self.assertEqual(len(calls),1);self.assertTrue(socket.closed)
        self.assertEqual(result['new_final_bars'],1)
        self.assertEqual(result['stop_reason'],'FINAL_BAR_CAP_REACHED')
        self.assertEqual(result['source_live_engineering'],'NOT_ESTABLISHED')
        self.assertEqual(len(socket.events),1)

    def test_hard_deadline_no_reconnect_or_rest_on_timeout(self):
        socket=Socket(self.clock,[]);calls=[]
        result=run_session(self.pilot,lambda *a,**k:calls.append(1) or socket)
        self.assertEqual(calls,[1]);self.assertEqual(result['stop_reason'],'HARD_DEADLINE')
        self.assertEqual(self.clock.elapsed,DURATION_SECONDS)
        self.assertEqual(result['new_final_bars'],0);self.assertTrue(socket.closed)

    def test_deadline_before_connect_never_opens_socket(self):
        self.clock.elapsed=DURATION_SECONDS
        calls=[]
        result=run_session(self.pilot,lambda *a,**k:calls.append(1))
        self.assertFalse(calls);self.assertFalse(result['network_attempted'])

    def test_connect_failure_is_terminal_and_emits_blocker(self):
        calls=[]
        def connect(*a,**k): calls.append(1);raise OSError('egress denied')
        result=run_session(self.pilot,connect)
        self.assertEqual(calls,[1]);self.assertIn('egress denied',result['stop_reason'])
        self.assertTrue((self.pilot.folder/'result.json').exists())

    def test_reserved_v2_authority_blocks_before_transport_and_retains_evidence(self):
        conn=self.pilot.journal._connect()
        conn.execute("INSERT INTO journal_meta VALUES('core128_activation_reserved','1')");conn.close()
        calls=[]
        result=run_session(self.pilot,lambda *a,**k:calls.append(1))
        self.assertFalse(calls);self.assertIn('PublicationDenied',result['stop_reason'])
        self.assertEqual(result['host']['status'],'PREFIX_OR_AUTHORITY_DENIED')

    def test_actual_activated_v2_source_refuses_collector_construction(self):
        from aql.delivery.authority import Authority,Limits,PublicationDenied
        from aql.collector.binance_collector import BinanceCollector
        from aql.journal.durable_journal import DurableJournal
        from aql.storage.operational_store import OperationalStore
        root=Path(self.tmp.name)
        journal=DurableJournal(str(root/'v2.db'))
        store=OperationalStore(str(root/'v2-store.db'))
        Authority(journal,limits=Limits(max_records=2,max_bytes=4096,timeout_seconds=1,max_events=128),
                  synthetic=True,stores=(store,))
        with self.assertRaises(PublicationDenied):
            BinanceCollector('BTCUSDT','15m',journal,store,max_bars=1)

    def test_nonfinal_never_committed(self):
        data=event(self.pilot);data['k']['x']=False
        self.assertFalse(self.receive(data))
        self.assertEqual(self.pilot.collector.metrics.journal_commit_count,0)

    def test_bad_identity_finality_grid_and_ohlcv_rejected(self):
        for field,value in [('s','ETHUSDT'),('i','1m'),('x','true'),('T',1),('h','1'),('v','NaN')]:
            with self.subTest(field=field):
                data=event(self.pilot);data['k'][field]=value
                with self.assertRaises(PilotStopped): self.receive(data)
        self.assertEqual(self.pilot.collector.metrics.journal_commit_count,0)

    def test_late_or_future_event_and_old_final_rejected(self):
        data=event(self.pilot);data['E']=self.pilot.cutoff+6000
        with self.assertRaisesRegex(PilotStopped,'CLOCK'): self.receive(data)
        data=event(self.pilot);data['k']['t']-=BAR_MS;data['k']['T']-=BAR_MS
        with self.assertRaisesRegex(PilotStopped,'NOT_NEW'): self.receive(data)
        data=event(self.pilot);self.clock.utc=(self.pilot.cutoff+11000)/1000
        with self.assertRaisesRegex(PilotStopped,'CLOCK'):self.pilot.accept(canonical(data))

    def test_duplicate_final_or_second_new_bar_never_committed(self):
        self.receive(event(self.pilot))
        with self.assertRaisesRegex(PilotStopped,'CAP'):
            self.receive(event(self.pilot))
        self.assertEqual(self.pilot.collector.metrics.journal_commit_count,1)

    def test_future_receipt_cannot_be_backdated_into_r4_cutoff(self):
        self.receive(event(self.pilot))
        self.assertEqual(eligible_prefix(self.pilot.journal,self.pilot.cutoff),[])
        status=self.pilot.host_status()
        self.assertEqual(status['status'],'SOURCE_PREFIX_INSUFFICIENT')
        self.assertEqual(status['required_bars'],21);self.assertFalse(status['r4_invoked'])
        self.assertTrue(all(s=='NOT_EVALUATED' for s in status['decision_status_by_arm'].values()))

    def test_schedule_changed_prevents_source_consumption(self):
        (self.pilot.folder/'schedule.json').write_bytes(b'forged')
        calls=[]
        result=run_session(self.pilot,lambda *a,**k:calls.append(1))
        self.assertFalse(calls);self.assertIn('SCHEDULE_CHANGED',result['stop_reason'])

    def test_frame_size_and_transcript_capacity_are_hard_limits(self):
        with self.assertRaisesRegex(PilotStopped,'RAW_PAYLOAD_LIMIT'):
            self.pilot.accept(b'x'*65537)
        self.pilot.frames=2048
        with self.assertRaisesRegex(PilotStopped,'TRANSCRIPT_LIMIT'):
            self.pilot.accept(canonical(event(self.pilot)))

    def test_cli_requires_exact_approval_and_manual_owner_environment(self):
        with patch('sys.argv',['pilot','--out','unused','--approval','wrong','--operator','x','--approval-ref','x']):
            with self.assertRaisesRegex(PilotStopped,'OWNER_APPROVAL'):
                main()

        with patch('sys.argv',['pilot','--out','unused','--approval',APPROVAL,'--operator','x','--approval-ref','x']),patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(PilotStopped,'NETWORK_DISABLED'):
                main()

    def test_owner_approval_exact_commit_scope_freshness_and_single_use(self):
        now=datetime.datetime(2026,11,2,tzinfo=datetime.timezone.utc)
        comment=dict(user={'login':'owner'},issue_url='https://api.github.com/repos/owner/repo/issues/180',
                     body=approval_body('owner','a'*40),created_at='2026-11-02T00:00:00Z')
        kwargs=dict(repo='owner/repo',actor='owner',approved_sha='a'*40,comment_id='123',now=now)
        title=verify_comment(comment,**kwargs)
        with self.assertRaisesRegex(ValueError,'NOT_APPROVED'):
            verify_comment({**comment,'body':'PROPOSED, NOT APPROVED: '+APPROVAL+' '+('a'*40)},**kwargs)
        for field,value in [('actor','other'),('approved_sha','b'*40),
                            ('now',now+datetime.timedelta(days=2))]:
            bad={**kwargs,field:value}
            with self.assertRaises(ValueError):verify_comment(comment,**bad)
        with self.assertRaisesRegex(ValueError,'ALREADY_CONSUMED'):
            deny_previous_runs([dict(id=1,display_title=title)],title=title,current_run_id=2)
        deny_previous_runs([dict(id=2,display_title=title)],title=title,current_run_id=2)

    def test_workflow_is_manual_owner_exact_sha_only_and_no_old_test_run(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/'.github/workflows/sf-dev-admission.yml').read_text()
        trigger=workflow.split('\non:\n',1)[1].split('\npermissions:',1)[0]
        self.assertIn('  workflow_dispatch:',trigger)
        for forbidden in ('  push:','  pull_request:','  schedule:','  workflow_run:','  repository_dispatch:'):
            self.assertNotIn(forbidden,trigger)
        for condition in ('github.actor == github.repository_owner','inputs.approved_sha == github.sha',
                          'github.run_attempt == 1','timeout --signal=TERM --kill-after=5s 960s'):
            self.assertIn(condition,workflow)
        self.assertNotIn('pytest',workflow)


if __name__=='__main__': unittest.main()
