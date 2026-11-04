from copy import deepcopy
from collections import Counter
from pathlib import Path
import tempfile
import unittest
import json
import hashlib
from tools.strategy_service_offline.common import Dependencies,Frozen,RunJournal,canonical,decode,digest,read,raw_sha
from tools.strategy_service_offline.research import independent_research
from .adapters import Ports,source_call,GenerationOnlyPort,join_factory_packets,integrate
from .inventory import inspect_retained_package
from .run import FIXTURES,locked_inputs,execute_test_only


class HistoricalGate(unittest.TestCase):
    roots={}

    @classmethod
    def setUpClass(cls):
        cls.deps=Dependencies(FIXTURES/'dependencies.json',(FIXTURES/'dependencies.sha256').read_text().strip(),cls.roots)
        cls.f=locked_inputs()
        cls.shared=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.shared.cleanup)
        cls.core=source_call(Ports(cls.deps),cls.f['core-source.json'])
        plan=deepcopy(cls.f['plan.json']);plan.update(families=['F006'],plan_id='test239_negative_F006')
        cls.gen=independent_research(plan,RunJournal(Path(cls.shared.name)/'gen',cls.deps),
                                    GenerationOnlyPort(cls.deps),factory_fixture=None)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=deepcopy(self.f['core-source.json'])
        self.generation=self.gen.receipt();self.boundary=self.core.receipt()

    def join(self):return join_factory_packets(self.generation,self.boundary)

    def packet(self):return self.join()[0][0]

    def factory(self,packet):return Ports(self.deps).call('factory',{'packet':packet})

    def reseal_core(self):
        core=self.boundary['payload']['receipt']
        core['manifest_record_sha256']=digest({k:v for k,v in core.items() if k!='manifest_record_sha256'})
        self.boundary=Frozen.build(self.boundary['payload']).receipt()

    def test_00_all_seven_families_to_actual_core_factory_gate_and_replay(self):
        one,key=execute_test_only(self.deps,self.root/'one')
        two,key2=execute_test_only(self.deps,self.root/'two')
        self.assertEqual(one.payload,two.payload);self.assertEqual(key,key2)
        (self.root/'one/result/objects/.staging-crash').write_bytes(b'partial')
        repeat,key3=execute_test_only(self.deps,self.root/'one')
        self.assertEqual(one.payload,repeat.payload);self.assertEqual(key,key3)
        data=one.data;g=Frozen.restore(data['generation']).data
        self.assertEqual(data['trial_count'],53);self.assertEqual(data['candidate_count'],53)
        self.assertEqual(data['native_factory_attempt_slots'],53)
        self.assertEqual({Frozen.restore(c).data['family_id'] for c in g['candidates']},
                         {'F001','F002','F003','F004','F005','F006','F007'})
        self.assertEqual(g['status_counts'],dict(Counter(a['state'] for a in g['attempts'])))
        self.assertEqual(sum(g['status_counts'].values()),g['attempt_count'])
        self.assertTrue(all(c['receipt']['scientific_result']=='INSUFFICIENT_EVIDENCE' for c in data['factory_calls']))
        self.assertTrue(all(c['receipt']['strategy_rule_trigger_evaluation']=='NOT_PERFORMED' for c in data['factory_calls']))
        self.assertIsNone(data['opportunity_count']);self.assertIsNone(data['observation_count'])
        for c in data['factory_calls']:
            p,r=c['packet'],c['receipt']
            self.assertEqual(p['strategy_definition_digest'],p['candidate_definition']['digest'])
            self.assertEqual(r['input_sha256'],p['artifact_sha256'])
            self.assertEqual(p['global_trial_count'],53)
            self.assertTrue(all(a['feature_available_ms'] is None and a['result'] is None for a in p['attempts']))
        for path in (self.root/'one').rglob('objects/*.json'):
            raw=path.read_bytes();independent=json.dumps(json.loads(raw),sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
            self.assertEqual(path.stem,hashlib.sha256(independent).hexdigest())
        self.assertEqual(data['scientific_result'],'INSUFFICIENT_EVIDENCE')
        self.assertEqual(data['authentic_e2e'],'NOT_CONNECTED')

    def test_original_byte_tamper(self):
        self.source['source_hex']=(bytes.fromhex(self.source['source_hex'])+b' ').hex()
        r=source_call(Ports(self.deps),self.source).data
        self.assertEqual(r['status'],'CORE_ADMISSION_REFUSED');self.assertEqual(r['core_error'],'ORIGINAL_BYTE_SHA_MISMATCH')

    def test_no_source_no_fabricated_sha(self):
        self.source['source_hex']=None;r=source_call(Ports(self.deps),self.source).data
        self.assertEqual(r['status'],'SOURCE_NOT_AVAILABLE');self.assertIsNone(r['receipt']['source_bytes_sha256'])
        self.boundary=Frozen.build(r).receipt();self.assertEqual(self.join()[0],[])

    def test_missing_retained_source(self):
        r=inspect_retained_package(None,None).data
        self.assertFalse(r['source_available']);self.assertEqual(r['status'],'SOURCE_NOT_AVAILABLE')

    def test_sealed_holdout_denied_before_any_source_read(self):
        with self.assertRaisesRegex(ValueError,'SEALED_OR_UNDECLARED_WINDOW_DENIED'):
            inspect_retained_package('/must-not-read',None,requested_archives=['BTCUSDT-15m-2025-11.zip'])

    def test_holdout_packet_denied(self):
        with self.assertRaisesRegex(ValueError,'SEALED_HOLDOUT_ACCESS_DENIED'):
            join_factory_packets(self.generation,self.boundary,holdout='OPEN')

    def test_future_source_claim(self):
        self.source['pin']['claimed_available_at_ms']=self.source['cutoff_ms']+1
        r=source_call(Ports(self.deps),self.source).data
        self.assertEqual(r['core_error'],'CLAIMED_SOURCE_UNAVAILABLE_AT_CUTOFF')

    def test_missing_grid_original_payload(self):
        raw=decode(bytes.fromhex(self.source['source_hex']));raw['records'].pop(1)
        raw['count']=len(raw['records']);raw['record_content_hash']=digest(raw['records'])
        self.source['source_hex']=canonical(raw).hex();self.source['pin']['original_sha256']=digest(raw)
        self.assertEqual(source_call(Ports(self.deps),self.source).data['status'],'CORE_ADMISSION_REFUSED')

    def test_nonfinal_original(self):
        raw=decode(bytes.fromhex(self.source['source_hex']));r=raw['records'][0];r['bar']['is_final']=False
        r['envelope_hash']=digest({k:v for k,v in r.items() if k!='envelope_hash'})
        raw['record_content_hash']=digest(raw['records']);self.source['source_hex']=canonical(raw).hex()
        self.source['pin']['original_sha256']=digest(raw)
        self.assertEqual(source_call(Ports(self.deps),self.source).data['status'],'CORE_ADMISSION_REFUSED')

    def test_partial_query_not_scored(self):
        self.source['cutoff_ms']=self.source['spec']['start_ms']+61000
        boundary=source_call(Ports(self.deps),self.source)
        self.assertEqual(boundary.data['receipt']['coverage'],'PARTIAL')
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PRICE_SOURCE_GRID'):
            join_factory_packets(self.generation,boundary.receipt())

    def test_unknown_query_not_scored(self):
        self.source['cutoff_ms']=0;boundary=source_call(Ports(self.deps),self.source)
        self.assertEqual(boundary.data['receipt']['coverage'],'UNKNOWN')
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PRICE_SOURCE_GRID'):
            join_factory_packets(self.generation,boundary.receipt())

    def test_correction_parent_conflict(self):
        self.source['spec'].update(version=2,parent_source_sha256='f'*64,correction_reason='TEST_CORRECTION')
        self.assertEqual(source_call(Ports(self.deps),self.source).data['status'],'CORE_ADMISSION_REFUSED')

    def test_actual_correction_keeps_earlier_version(self):
        c=deepcopy(self.source);c['source_hex']=self.f['correction-source.json']['source_hex']
        c['pin']['original_sha256']=raw_sha(bytes.fromhex(c['source_hex']))
        c['spec'].update(version=2,parent_source_sha256=self.source['pin']['original_sha256'],correction_reason='TEST_CORRECTION')
        out=Ports(self.deps).call('core',{'sources':[self.source,c,self.source]})['results']
        self.assertTrue(all(r['status']=='RETURNED' for r in out));self.assertEqual(out[0]['receipt'],out[2]['receipt'])
        self.assertEqual(out[1]['receipt']['correction_parent_source_sha256'],out[0]['receipt']['source_bytes_sha256'])

    def test_forged_source_authority(self):
        self.boundary['payload']['receipt']['authenticated_source']='VERIFIED';self.reseal_core()
        with self.assertRaisesRegex(ValueError,'FORGED_SCIENTIFIC_AUTHORITY'):self.join()

    def test_nested_core_tamper(self):
        self.boundary['payload']['receipt']['dataset_id']='FORGED';self.boundary=Frozen.build(self.boundary['payload']).receipt()
        with self.assertRaisesRegex(ValueError,'CORE_RECORD_TAMPER'):self.join()

    def test_wrong_core_query_parent(self):
        self.boundary['payload']['receipt']['query']['result']['source_bytes_sha256']='f'*64;self.reseal_core()
        with self.assertRaisesRegex(ValueError,'CORE_QUERY_PARENT'):self.join()

    def test_duplicate_attempts(self):
        g=self.generation['payload'];g['attempts'][1]=deepcopy(g['attempts'][0]);self.generation=Frozen.build(g).receipt()
        with self.assertRaisesRegex(ValueError,'DUPLICATE_ATTEMPT_ID'):self.join()

    def test_missing_attempt_denominator(self):
        g=self.generation['payload'];g['attempts'].pop();self.generation=Frozen.build(g).receipt()
        with self.assertRaisesRegex(ValueError,'TRIAL_DENOMINATOR'):self.join()

    def test_candidate_plan_mismatch(self):
        g=self.generation['payload'];c=g['attempts'][0]['candidate']['payload'];c['plan_sha256']='f'*64
        g['attempts'][0]['candidate']=Frozen.build(c).receipt();self.generation=Frozen.build(g).receipt()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_ATTEMPT_PLAN'):self.join()

    def test_factory_feature_lookahead(self):
        p=self.packet();p['attempts'][0]['feature_available_ms']=p['decision_cutoff_ms']+1
        with self.assertRaisesRegex(ValueError,'FEATURE_LOOKAHEAD'):self.factory(p)

    def test_factory_duplicate_attempt(self):
        p=self.packet();p['attempts']*=2;p['expected_attempts']=2
        with self.assertRaisesRegex(ValueError,'DUPLICATE_ATTEMPT_ID'):self.factory(p)

    def test_factory_strategy_version(self):
        p=self.packet();p['attempts'][0]['strategy_version']='WRONG'
        with self.assertRaisesRegex(ValueError,'ATTEMPT_BINDING'):self.factory(p)

    def test_factory_invented_result(self):
        p=self.packet();p['attempts'][0]['result']=0
        with self.assertRaisesRegex(ValueError,'RESULT_OR_HOLDOUT_PROMOTION'):self.factory(p)

    def test_factory_holdout(self):
        p=self.packet();p['attempts'][0]['holdout_access']=True
        with self.assertRaisesRegex(ValueError,'RESULT_OR_HOLDOUT_PROMOTION'):self.factory(p)

    def test_factory_source_verified_boolean_does_not_attest(self):
        p=self.packet();p.update(source_kind='ORIGINAL_UNVERIFIED',verified=True)
        r=self.factory(p)['receipt'];self.assertEqual(r['admission'],'AUTHENTIC_SOURCE_NOT_CONNECTED')
        self.assertFalse(r['pit_verified']);self.assertFalse(r['source_original_bytes_verified'])

    def test_unknown_feature_preserved_not_cutoff_filled(self):
        p=self.packet();self.assertTrue(all(a['feature_available_ms'] is None for a in p['attempts']))
        self.assertEqual(self.factory(p)['receipt']['scientific_result'],'INSUFFICIENT_EVIDENCE')

    def test_invalid_duplicate_budget_full_census(self):
        plan=deepcopy(self.f['plan.json']);plan.update(families=['F006'],plan_id='negative239',budget=4,
                          test_axes={'F006':{'roc.period':[-1,5,5,10,20,50]}})
        g=independent_research(plan,RunJournal(self.root/'gen',self.deps),GenerationOnlyPort(self.deps),factory_fixture=None)
        packets,unrouted,status=join_factory_packets(g.receipt(),self.boundary)
        self.assertEqual(g.data['attempt_count'],6)
        self.assertEqual(len(unrouted),3);self.assertEqual(sum(p['expected_attempts'] for p in packets),3)
        self.assertTrue(all(self.factory(p)['receipt']['attempt_count']==p['expected_attempts'] for p in packets))

    def test_all_scientific_denominators_unknown_not_zero(self):
        p=self.packet();self.assertIsNone(p['market_universe_denominator'])
        self.assertIsNone(p['base_shadow_opportunity_denominator'])

    def test_real_source_not_relabelled_test_only(self):
        s=deepcopy(self.source);s['spec']['test_only']=False;s['pin']['test_only']=False
        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_NOT_TEST_INPUT'):
            integrate(self.deps,s,self.f['plan.json'],self.root/'out')

    def test_recorded_original_observation_not_ci_authentication(self):
        p=Path(__file__).parent/'SOURCE_ACCESS_OBSERVATION.json';data=Frozen.restore(decode(read(p))).data
        self.assertTrue(data['inventory']['payload']['source_available'])
        self.assertEqual([a['bar_count'] for a in data['inventory']['payload']['archives']],[2784,2976])
        self.assertFalse(data['real_strategy_evaluated']);self.assertFalse(data['raw_data_published'])
        self.assertTrue(all(p['core_probe']['payload']['core_error']=='UNSUPPORTED_ORIGINAL_SOURCE'
                            for p in data['actual_core_probes']))

    def test_dependency_pin_mismatch(self):
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_LOCK_SHA'):
            Dependencies(FIXTURES/'dependencies.json','f'*64,self.roots)
