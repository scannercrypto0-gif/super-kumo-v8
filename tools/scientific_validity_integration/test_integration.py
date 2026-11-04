import copy
from tempfile import TemporaryDirectory
import unittest
from .integration import (call,compare_plan,verify_selection,verify_factory,integrate_one,execute,
                          owner_digest,Frozen)
from .fixture import fixture,chronology
from .gate import dependencies


class ValidityGate(unittest.TestCase):
    roots=None
    @classmethod
    def setUpClass(cls):
        cls.deps=dependencies(cls.roots);cls.n=fixture();cls.full=integrate_one(cls.deps,cls.n)

    def core(self,n,**kw):return call(self.deps,'core',n|kw)
    def factory(self,p):return call(self.deps,'factory',{'plan':p})

    def test_missing_independent_evidence_propagates_null(self):
        a=self.full['core_assessment'];r=self.full['factory_report']
        self.assertEqual(a['chronology']['bar_timestamps_unknown'],2)
        self.assertEqual(a['universe']['evidence_state'],'UNIVERSE_EVIDENCE_NOT_AVAILABLE')
        self.assertIsNone(r['universe_denominator']);self.assertIsNone(r['paired_arm_slots'])
        self.assertIsNone(r['base_shadow_comparison']);self.assertFalse(r['modeled_returns_recomputed'])

    def test_parent_tamper_and_resealed_source_drift(self):
        n=copy.deepcopy(self.n);n['prices']['version']=2
        with self.assertRaisesRegex(ValueError,'SEAL_INVALID'):self.core(n)
        n['prices']['price_query_sha256']=owner_digest({k:v for k,v in n['prices'].items() if k!='price_query_sha256'})
        with self.assertRaisesRegex(ValueError,'SOURCE_PRICE_DRIFT'):self.core(n)

    def test_self_hashed_chronology_does_not_confer_pit(self):
        r=self.core(self.n,chronology=chronology(self.n))
        self.assertEqual(r['chronology']['evidence_state'],'SUPPLIED_CLAIMS_UNVERIFIED')
        self.assertEqual(r['historical_pit'],'NOT_ATTESTED')
        with self.assertRaisesRegex(ValueError,'MISSING_WITNESS'):compare_plan(self.n,r)

    def test_chronology_after_capture_or_before_bar_close(self):
        for value in (1,1706748000000):
            c=chronology(self.n);c['bar_claims'][0]['claimed_known_at_ms']=value
            c['evidence_sha256']=owner_digest({k:v for k,v in c.items() if k!='evidence_sha256'})
            with self.assertRaises(ValueError):self.core(self.n,chronology=c)

    def test_duplicate_chronology_and_forged_parent(self):
        for key in ('duplicate','parent'):
            c=chronology(self.n)
            if key=='duplicate':c['bar_claims'].append(copy.deepcopy(c['bar_claims'][0]))
            else:c['correction_parent_sha256']='a'*64
            c['evidence_sha256']=owner_digest({k:v for k,v in c.items() if k!='evidence_sha256'})
            with self.assertRaises(ValueError):self.core(self.n,chronology=c)

    def test_exact_53_trials_and_seven_families(self):
        p=self.full['factory_input'];self.assertEqual(len(p['trials']),53)
        self.assertEqual(len({x['family_id'] for x in p['trials']}),7)
        for duplicate in (False,True):
            bad=copy.deepcopy(p)
            if duplicate:bad['trials'][1]['attempt_id']=bad['trials'][0]['attempt_id']
            else:bad['trials'].pop()
            with self.assertRaises(ValueError):self.factory(bad)

    def test_selection_drift_even_plausible_census_rejected(self):
        p=copy.deepcopy(self.full['factory_input']);p['trials'][0]['attempt_id']='selected_after_outcomes'
        with self.assertRaisesRegex(ValueError,'FROZEN_SELECTION'):verify_selection(p,self.full['factory_input'])

    def test_preregistration_and_pit_promotion_rejected(self):
        for key,value in [('historical_preregistration',True),('historical_pit','ATTESTED')]:
            p=copy.deepcopy(self.full['factory_input']);p[key]=value
            with self.assertRaises(ValueError):self.factory(p)

    def test_holdout_or_embargo_bypass_rejected(self):
        for key,value in [('holdout','OPEN'),('embargo_ms',0),('holdout_start_ms',1)]:
            p=copy.deepcopy(self.full['factory_input']);p[key]=value
            with self.assertRaises(ValueError):self.factory(p)

    def test_cost_sensitivity_not_return_recalculation(self):
        r=self.full['factory_report'];self.assertFalse(r['modeled_returns_recomputed'])
        p=copy.deepcopy(self.full['factory_input']);p['cost_scenarios_bps'][1]['total_round_trip_bps']='29'
        with self.assertRaises(ValueError):self.factory(p)

    def test_forged_denominator_or_result_even_resealed_rejected(self):
        for k,v in [('paired_arm_slots',0),('base_shadow_comparison',{'uplift':1}),('scientific_result','PASS')]:
            r=copy.deepcopy(self.full['factory_report']);r[k]=v
            r['report_sha256']=owner_digest({k:v for k,v in r.items() if k!='report_sha256'})
            with self.assertRaises(ValueError):verify_factory(r,self.full['factory_input'])

    def test_unknown_universe_not_promoted_or_inferred_from_bars(self):
        a=copy.deepcopy(self.full['core_assessment']);a['independent_opportunity_denominator']=2
        a['assessment_sha256']=owner_digest({k:v for k,v in a.items() if k!='assessment_sha256'})
        with self.assertRaises(ValueError):compare_plan(self.n,a)

    def test_cross_cohort_assessment_join_rejected(self):
        a=copy.deepcopy(self.full['core_assessment']);a['dataset_id']='OTHER_COHORT'
        a['assessment_sha256']=owner_digest({k:v for k,v in a.items() if k!='assessment_sha256'})
        with self.assertRaisesRegex(ValueError,'CORE_PARENT_JOIN'):compare_plan(self.n,a)

    def test_fresh_directory_determinism_without_old_report_execution(self):
        with TemporaryDirectory() as a,TemporaryDirectory() as b:
            x,k=execute(self.deps,[fixture()],a,evidence_class='TEST_ONLY')
            y,l=execute(self.deps,[fixture()],b,evidence_class='TEST_ONLY')
        self.assertEqual(x.payload,y.payload);self.assertEqual(k,l)
        self.assertEqual(x.data['old_factory_reports_rerun'],0)
