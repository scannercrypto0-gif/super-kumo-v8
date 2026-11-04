"""Focused cross-owner negative/regression gate; synthetic prices only."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from .batch import (FIXTURES,PLAN_SHA,plan,generation,owner_call,owner_digest,verify_core,
                    factory_packet,validate_factory,native_factory_call,execute,original_inputs)
from .test_fixture import source_fixture
from .__main__ import dependencies
from tools.strategy_service_offline.common import Frozen,RunJournal,BoundaryError,decode,read
from tools.strategy_service_offline.research import independent_research
from tools.historical_research_integration.adapters import GenerationOnlyPort


class BatchGate(unittest.TestCase):
    roots=None

    @classmethod
    def setUpClass(cls):
        cls.deps=dependencies(cls.roots);cls.source=source_fixture();cls.g=generation()
        cls.native=owner_call(cls.deps,'core',cls.source)
        cls.packet=factory_packet(cls.native,cls.source,cls.g.data['attempts'][0],cls.g)
        cls.report=owner_call(cls.deps,'factory',{'packet':cls.packet})

    def factory(self,p):return owner_call(self.deps,'factory',{'packet':p})
    def refuse(self,p,reason):
        with self.assertRaisesRegex(BoundaryError,reason):self.factory(p)

    def test_final_factory_owned_native_price_adapter(self):
        port=native_factory_call(self.deps,self.native,self.packet)
        self.assertEqual(port['factory_report']['decision_counts'],self.report['decision_counts'])
        self.assertEqual(port['scientific_result'],'INSUFFICIENT_EVIDENCE')
        self.assertEqual(port['core_admission_sha256'],self.native['admission']['manifest_record_sha256'])

    def test_original_native_price_grid_full_lineage(self):
        q=verify_core(self.native,self.source)
        self.assertEqual(q['available_bar_count'],160)
        self.assertEqual(q['scientific_pit'],'NOT_ATTESTED')
        self.assertTrue(all(b['historical_known_at_ms'] is None for b in q['bars']))

    def test_actual_factory_positive_modeled_cost_and_warmup(self):
        validate_factory(self.report,self.packet)
        self.assertGreater(self.report['decision_counts'].get('WARMUP_UNKNOWN',0),0)
        self.assertTrue(any(t['status']=='MODEL_ONLY' for t in self.report['modeled_outcomes']))
        self.assertEqual(self.report['scientific_result'],'INSUFFICIENT_EVIDENCE')
        self.assertEqual(self.report['source_class'],'TEST_ONLY')

    def test_reproduce_existing_discoverer_53_frozen_candidates(self):
        old=decode(read(Path('tools/historical_research_integration/fixtures/plan.json')))
        with TemporaryDirectory() as tmp:
            g=independent_research(old,RunJournal(tmp,self.deps),GenerationOnlyPort(self.deps),factory_fixture=None)
        self.assertEqual(g.sha256,self.g.sha256)

    def test_tampered_original_zip_denied_by_core(self):
        s=copy.deepcopy(self.source);s['source_hex']+='00'
        with self.assertRaisesRegex(BoundaryError,'ORIGINAL_BYTE_SHA_MISMATCH'):owner_call(self.deps,'core',s)

    def test_tampered_checksum_denied_by_core(self):
        s=copy.deepcopy(self.source);s['checksum_hex']+='20'
        with self.assertRaisesRegex(BoundaryError,'CHECKSUM_FILE_SHA_MISMATCH'):owner_call(self.deps,'core',s)

    def test_forged_core_parent_even_resealed_denied(self):
        n=copy.deepcopy(self.native);n['prices']['source_bytes_sha256']='0'*64
        n['prices']['price_query_sha256']=owner_digest({k:v for k,v in n['prices'].items() if k!='price_query_sha256'})
        with self.assertRaisesRegex(BoundaryError,'ORIGINAL_SOURCE_JOIN'):verify_core(n,self.source)

    def test_resealed_price_drift_cannot_replace_native_source(self):
        n=copy.deepcopy(self.native);n['prices']['bars'][0]['open']+=.001
        n['prices']['price_query_sha256']=owner_digest({k:v for k,v in n['prices'].items() if k!='price_query_sha256'})
        with self.assertRaisesRegex(BoundaryError,'PRICE_PROJECTION_DRIFT'):verify_core(n,self.source)

    def test_pit_promotion_denied_even_resealed(self):
        n=copy.deepcopy(self.native);n['admission']['confirmed_pit']='ATTESTED'
        n['admission']['manifest_record_sha256']=owner_digest({k:v for k,v in n['admission'].items() if k!='manifest_record_sha256'})
        with self.assertRaisesRegex(BoundaryError,'FALSE_PIT'):verify_core(n,self.source)

    def test_missing_or_duplicate_bar_denied(self):
        for duplicate in (False,True):
            p=copy.deepcopy(self.packet)
            if duplicate:p['bars'][4]=p['bars'][3]
            else:del p['bars'][4]
            self.refuse(p,'MISSING_OR_DUPLICATE_BAR')

    def test_missing_and_duplicate_attempts_denied(self):
        p=copy.deepcopy(self.packet);p['trials'].pop();self.refuse(p,'TRIAL_DENOMINATOR')
        p=copy.deepcopy(self.packet);p['trials'][1]['attempt_id']=p['trials'][0]['attempt_id'];self.refuse(p,'TRIAL_ID_DUPLICATE')

    def test_strategy_or_plan_drift_denied(self):
        p=copy.deepcopy(self.packet);p['trials'][0]['candidate_digest']='0'*64;self.refuse(p,'CANDIDATE_DEFINITION_DRIFT')
        p=copy.deepcopy(self.packet);p['trials'][0]['plan_digest']='0'*64;self.refuse(p,'TRIAL_PROVENANCE')

    def test_future_availability_and_holdout_denied(self):
        p=copy.deepcopy(self.packet);b=p['bars'][0];b['known_at_ms']=b['close_ms']+2
        b['bar_sha256']=owner_digest({k:v for k,v in b.items() if k!='bar_sha256'})
        self.refuse(p,'FUTURE_OR_INVALID_AVAILABILITY')
        p=copy.deepcopy(self.packet);p['research_window']['train_end_exclusive_ms']=p['bars'][-1]['open_ms']
        self.refuse(p,'SEALED_HOLDOUT_BAR_ACCESS')

    def test_forged_duplicate_parent_and_missing_arm_denied(self):
        p=copy.deepcopy(self.packet);p['trials'][1].update(state='DUPLICATE',duplicate_of='forged')
        self.refuse(p,'TRIAL_DUPLICATE_PARENT')
        p=copy.deepcopy(self.packet);p['opportunity_count']=1;p['opportunities']=[{'opportunity_id':'test',
            'bar_open_ms':p['bars'][0]['open_ms'],'status':'UNKNOWN','arms':[{'arm':'BASE','status':'UNKNOWN'}]}]
        self.refuse(p,'PAIR_ARMS')

    def test_cross_cohort_source_or_cutoff_denied(self):
        s=copy.deepcopy(self.source);s['spec']['dataset_id']='different'
        with self.assertRaisesRegex(BoundaryError,'CORE_IDENTITY_JOIN'):verify_core(self.native,s)
        s=copy.deepcopy(self.source);s['cutoff_ms']-=900000
        with self.assertRaisesRegex(BoundaryError,'CORE_IDENTITY_JOIN'):verify_core(self.native,s)

    def test_float_owner_seal_is_not_strategy_canonical_seal(self):
        from tools.strategy_service_offline.common import digest
        q=self.native['prices'];body={k:v for k,v in q.items() if k!='price_query_sha256'}
        self.assertNotEqual(digest(body),q['price_query_sha256'])
        self.assertEqual(owner_digest(body),q['price_query_sha256'])

    def test_tampered_factory_source_and_cost_fail_work_join(self):
        for field,value in [('source_bytes_sha256','0'*64),('costs',{**plan()['costs'],'fee_entry_bps':'0'})]:
            r=copy.deepcopy(self.report);r[field]=value
            r['artifact_sha256']=owner_digest({k:v for k,v in r.items() if k!='artifact_sha256'})
            with self.assertRaises(BoundaryError):validate_factory(r,self.packet)

    def test_censored_last_bar_stays_unknown_not_pnl(self):
        p=copy.deepcopy(self.packet);p['bars']=p['bars'][:40]
        r=self.factory(p);validate_factory(r,p)
        self.assertTrue(any(t['status']=='UNKNOWN_END_OF_DATA' and t['modeled_net_return'] is None
                            for t in r['modeled_outcomes']))

    def test_future_price_mutation_does_not_change_prior_decisions(self):
        p=copy.deepcopy(self.packet)
        for b in p['bars'][100:]:
            for k in ('open','high','low','close'):b[k]*=2
            b['bar_sha256']=owner_digest({k:v for k,v in b.items() if k!='bar_sha256'})
        r=self.factory(p)
        self.assertEqual(r['decisions'][:100],self.report['decisions'][:100])

    def test_no_private_source_falls_closed(self):
        inventory,sources=original_inputs(None)
        self.assertFalse(inventory.data['source_available']);self.assertEqual(sources,[])
        self.assertEqual(inventory.data['status'],'SOURCE_NOT_AVAILABLE')

    def test_retrospective_is_not_test_only_or_scientific_pass(self):
        p=copy.deepcopy(self.packet);p['source_kind']='ORIGINAL_UNVERIFIED';p['availability']='RETROSPECTIVE_NON_PIT'
        r=self.factory(p)
        self.assertEqual(r['model_class'],'RETROSPECTIVE_ONLY_UNVERIFIED')
        self.assertFalse(r['historical_pit_verified']);self.assertEqual(r['scientific_result'],'INSUFFICIENT_EVIDENCE')

    def test_deterministic_original_custody_replay_and_factory(self):
        self.assertEqual(self.native,owner_call(self.deps,'core',self.source))
        self.assertEqual(self.report,self.factory(self.packet))
