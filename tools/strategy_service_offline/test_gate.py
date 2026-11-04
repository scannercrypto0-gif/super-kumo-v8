"""Consolidated multi-strategy, paper-boundary and independent research gate."""
from collections import Counter
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from .common import Dependencies,Frozen,RunJournal,BoundaryError,decode,digest,raw_sha,canonical,read
from .screening import StrategyScreeningSpec,scan,registry_snapshot
from .routing import route,TestOnlyStrategySink
from .research import independent_research
from .run import FIXTURES,inputs,execute


class PackageGate(unittest.TestCase):
    roots={}

    @classmethod
    def setUpClass(cls):
        cls.deps=Dependencies(FIXTURES/'dependencies.json',
                             (FIXTURES/'dependencies.sha256').read_text().strip(),cls.roots)
        cls.f=inputs()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.specs=[StrategyScreeningSpec.restore_spec(x) for x in self.f['strategies.json']]
        self.source=read(FIXTURES/'source.json');self.m=deepcopy(self.f['source-manifest.json'])
        self.u=deepcopy(self.f['universe.json']);self.plan=deepcopy(self.f['research-plan.json'])

    def scan(self):
        return scan(self.specs,self.source,self.m,self.u,cutoff_ms=self.m['cutoff_ms'],symbol_budget=3,deps=self.deps)

    def rows(self):return [n['payload'] for n in self.scan().data['nominations']]

    def change_bars(self,fn):
        obj=decode(self.source);fn(obj['rows']);self.source=canonical(obj)
        self.m['raw_sha256']=raw_sha(self.source);self.u['source_raw_sha256']=self.m['raw_sha256']

    def unknown_aaa(self):
        rows=[r for r in self.rows() if r['symbol']=='AAA']
        self.assertTrue(rows);self.assertTrue(all(r['status']=='UNKNOWN' for r in rows))
        self.assertTrue(all(r['feature_evidence']=={} for r in rows))

    def research(self,plan=None,journal=None,feedback=None,fixture=None):
        return independent_research(plan or self.plan,journal or RunJournal(self.root/'research',self.deps),
                    self.deps,factory_fixture=fixture or self.f['factory-test-input.json'],
                    optional_scanner_feedback=feedback)

    def selected(self):
        result=self.scan()
        n=next(r for r in result.data['nominations'] if r['payload']['status']=='SELECTED')
        s=next(s for s in self.specs if s.data['strategy_id']==n['payload']['strategy_id'])
        return n,s

    def test_00_full_package_same_bytes_and_independent_census(self):
        one,key1=execute(self.deps,self.root/'one')
        two,key2=execute(self.deps,self.root/'two')
        self.assertEqual(one.payload,two.payload);self.assertEqual(key1,key2)
        (self.root/'one/package/objects/.staging-interrupted').write_bytes(b'incomplete')
        again,key3=execute(self.deps,self.root/'one');self.assertEqual(one.payload,again.payload);self.assertEqual(key1,key3)
        report=one.data;s=Frozen.restore(report['scan']).data
        self.assertEqual(len(s['nominations']),10)
        actual=Counter((r['payload']['strategy_id'],r['payload']['status']) for r in s['nominations'])
        for spec in self.specs:
            sid=spec.data['strategy_id']
            self.assertEqual({state:actual[sid,state] for state in ('SELECTED','REJECTED','UNKNOWN','UNSCANNED','INELIGIBLE')},
                             {'SELECTED':1,'REJECTED':1,'UNKNOWN':1,'UNSCANNED':1,'INELIGIBLE':1})
            rows=[r['payload'] for r in s['nominations'] if r['payload']['strategy_id']==sid]
            self.assertTrue(all(sum(r['strategy_census'].values())==r['denominator']==5 for r in rows))
        self.assertEqual(s['unique_feature_computations'],6);self.assertEqual(s['native_symbol_admissions'],2)
        targets={r['payload']['strategy_id']:r['payload']['symbol'] for r in s['nominations'] if r['payload']['status']=='SELECTED'}
        self.assertEqual(targets,{'test_momentum':'AAA','test_reversion':'BBB'})
        decisions=[Frozen.restore(x).data for x in report['strategy_test_decisions']]
        self.assertEqual({d['decision'] for d in decisions},{'ACCEPT','WAIT'})
        self.assertTrue(all(d['paper_execution']=='NOT_ACTIVATED' for d in decisions))
        research=Frozen.restore(report['research']).data
        self.assertFalse(research['scanner_required']);self.assertEqual(research['attempt_count'],4)
        self.assertEqual(research['status_counts'],{'SUBMITTED_NOT_EVALUATED':4})
        for attempt in research['attempts']:
            self.assertEqual(attempt['factory_handoff']['evaluation_kind'],'EXISTING_FACTORY_TEST_ONLY_DESCRIPTIVE_FIXTURE')
            self.assertEqual(attempt['factory_handoff']['receipt']['modeled_trade_engine'],'NOT_INVOKED')
        # Independent stdlib hash verification of every artifact and indexed receipt.
        for p in (self.root/'one').rglob('objects/*.json'):
            raw=p.read_bytes()
            independent=json.dumps(json.loads(raw),sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
            self.assertEqual(p.stem,hashlib.sha256(independent).hexdigest())
        self.assertEqual(report['real_integrations']['paper_consumer'],'PAPER_CONSUMER_NOT_CONNECTED')

    def test_source_tamper(self):
        self.source+=b' ';r=self.scan().data
        self.assertTrue(all(n['payload']['status']=='UNKNOWN' for n in r['nominations'] if n['payload']['symbol']!='EEE'))
        self.assertEqual(r['unique_feature_computations'],0)

    def test_source_bytes_missing(self):
        self.source=None;r=self.scan().data
        self.assertEqual(r['unique_feature_computations'],0);self.assertEqual(r['native_symbol_admissions'],0)

    def test_unverified_real_source_cannot_enable(self):
        self.m['evidence_class']='RETROSPECTIVE_NON_PIT_VERIFIED';self.m['verifier_boolean']=True
        r=self.scan().data;self.assertEqual(r['unique_feature_computations'],0)
        self.assertEqual(r['source_status'],'REAL_SOURCE_VERIFIER_NOT_CONNECTED')

    def test_unknown_source_availability(self):
        self.change_bars(lambda rows:rows[0].update(available_ms=None));self.unknown_aaa()

    def test_future_available(self):
        self.change_bars(lambda rows:rows[0].update(available_ms=99999999));self.unknown_aaa()

    def test_future_close(self):
        self.change_bars(lambda rows:rows[0].update(close_ms=99999999));self.unknown_aaa()

    def test_nonfinal(self):
        self.change_bars(lambda rows:rows[0].update(finalized=False));self.unknown_aaa()

    def test_gap(self):
        self.change_bars(lambda rows:rows.pop(5));self.unknown_aaa()

    def test_missing_first_warmup_bar(self):
        self.change_bars(lambda rows:rows.pop(0));self.unknown_aaa()

    def test_missing_last_bar(self):
        self.change_bars(lambda rows:rows.pop(23));self.unknown_aaa()

    def test_duplicate(self):
        self.change_bars(lambda rows:rows.insert(5,deepcopy(rows[4])));self.unknown_aaa()

    def test_unordered_not_sorted_away(self):
        def mutate(rows):rows[3],rows[4]=rows[4],rows[3]
        self.change_bars(mutate);self.unknown_aaa()

    def test_mixed_timeframe(self):
        self.change_bars(lambda rows:rows[0].update(timeframe='30m'));self.unknown_aaa()

    def test_mixed_source(self):
        self.change_bars(lambda rows:rows[0].update(source_id='forged'));self.unknown_aaa()

    def test_foreign_symbol_not_filtered(self):
        self.change_bars(lambda rows:rows[0].update(symbol='FOREIGN'))
        self.assertEqual(self.scan().data['unique_feature_computations'],0)

    def test_wrong_ohlcv_geometry(self):
        self.change_bars(lambda rows:rows[0].update(high=0));self.unknown_aaa()

    def test_boolean_price(self):
        self.change_bars(lambda rows:rows[0].update(close=True));self.unknown_aaa()

    def test_negative_volume(self):
        self.change_bars(lambda rows:rows[0].update(volume=-1));self.unknown_aaa()

    def test_stale_source_window(self):
        later=self.m['cutoff_ms']+600001;self.m['cutoff_ms']=later;self.u['cutoff_ms']=later
        self.unknown_aaa()

    def test_future_universe_member(self):
        self.u['members'][0]['membership_available_ms']=99999999;self.unknown_aaa()

    def test_unknown_eligibility(self):
        self.u['members'][0]['eligible']=None;self.unknown_aaa()

    def test_duplicate_universe_identity(self):
        self.u['members'].append(deepcopy(self.u['members'][0]))
        with self.assertRaisesRegex(ValueError,'UNIVERSE_IDENTITY'):self.scan()

    def test_universe_cutoff_mismatch(self):
        self.u['cutoff_ms']+=1
        with self.assertRaisesRegex(ValueError,'UNIVERSE_MANIFEST_CUTOFF'):self.scan()

    def test_universe_source_mismatch(self):
        self.u['source_raw_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'UNIVERSE_SOURCE_BINDING'):self.scan()

    def test_spec_deep_immutable(self):
        s=self.specs[0];data=s.data;data['dna']['dna']['scanner_profile']['filters'].clear()
        self.assertNotEqual(s.data,data)
        with self.assertRaises(FrozenInstanceError):s.payload=b'changed'

    def test_spec_tamper(self):
        r=self.specs[0].receipt();r['payload']['market']='WRONG'
        with self.assertRaisesRegex(ValueError,'FROZEN_DIGEST_DRIFT'):StrategyScreeningSpec.restore_spec(r)

    def test_config_digest_not_caller_boolean(self):
        r=self.specs[0].data;r['config_digest']='f'*64
        with self.assertRaisesRegex(ValueError,'SPEC_VERSION_OR_POLICY_DRIFT'):
            StrategyScreeningSpec.restore_spec(Frozen.build(r).receipt())

    def test_duplicate_strategy_versions(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_STRATEGY'):registry_snapshot([self.specs[0],self.specs[0]])

    def test_indicator_version_mismatch(self):
        r=self.specs[0].data;r['dna']['dna']['indicators'][0]['version']='UNSUPPORTED'
        r['dna']['digest']=digest(r['dna']['dna'])
        with self.assertRaises(ValueError):StrategyScreeningSpec.from_existing(r['definition'],r['dna'],
            timeframe='5m',market='fixture',max_source_age_ms=300000)

    def test_research_profile_score_not_strategy_score(self):
        rows=self.rows();self.assertTrue(all(r['research_profile_score'] is None for r in rows))
        self.assertTrue(any(r['strategy_screening_rank_score'] is not None for r in rows))

    def test_paper_consumer_absent_wait(self):
        n,s=self.selected();r=route(n,s,RunJournal(self.root/'route',self.deps))
        self.assertEqual(r.data['decision'],'WAIT');self.assertEqual(r.data['consumer_status'],'PAPER_CONSUMER_NOT_CONNECTED')

    def test_wrong_strategy_routing(self):
        n,s=self.selected();wrong=next(x for x in self.specs if x.data['strategy_id']!=s.data['strategy_id'])
        with self.assertRaisesRegex(ValueError,'WRONG_STRATEGY_ROUTE'):route(n,wrong,RunJournal(self.root/'route',self.deps))

    def test_wrong_version_routing(self):
        n,s=self.selected();d=Frozen.restore(n).data;d['strategy_version']='v999'
        with self.assertRaisesRegex(ValueError,'WRONG_STRATEGY_ROUTE'):
            route(Frozen.build(d).receipt(),s,RunJournal(self.root/'route',self.deps))

    def test_nomination_nested_tamper(self):
        n,s=self.selected();n['payload']['feature_evidence']['trend']['values']['value']=0
        with self.assertRaisesRegex(ValueError,'FROZEN_DIGEST_DRIFT'):route(n,s,RunJournal(self.root/'route',self.deps))

    def test_no_trading_authority(self):
        n,s=self.selected();d=Frozen.restore(n).data;d['delivery_authorized']=True
        with self.assertRaisesRegex(ValueError,'NOMINATION_AUTHORITY'):
            route(Frozen.build(d).receipt(),s,RunJournal(self.root/'route',self.deps))

    def test_strategy_owns_all_three_decisions(self):
        n,s=self.selected()
        for decision in ('ACCEPT','REJECT','WAIT'):
            sink=TestOnlyStrategySink(s,RunJournal(self.root/('sink'+decision),self.deps),lambda n,d=decision:d,decision_policy_id=decision)
            result=route(n,s,RunJournal(self.root/'route',self.deps),test_sink=sink)
            self.assertEqual(result.data['decision'],decision);self.assertEqual(result.data['trading_authority'],'NONE')

    def test_decision_replay_after_restart_once(self):
        n,s=self.selected();calls=[]
        def decide(n):calls.append(n['attempt_id']);return 'ACCEPT'
        def run():
            sink=TestOnlyStrategySink(s,RunJournal(self.root/'sink',self.deps),decide,decision_policy_id='v1')
            return route(n,s,RunJournal(self.root/'route',self.deps),test_sink=sink)
        a=run();b=run();self.assertEqual(a.payload,b.payload);self.assertEqual(len(calls),1)

    def test_strategy_invalid_decision_no_result(self):
        n,s=self.selected();sink=TestOnlyStrategySink(s,RunJournal(self.root/'sink',self.deps),lambda n:'BUY',decision_policy_id='v1')
        with self.assertRaisesRegex(ValueError,'STRATEGY_DECISION_ENUM'):
            route(n,s,RunJournal(self.root/'route',self.deps),test_sink=sink)

    def test_journal_conflicting_replay(self):
        j=RunJournal(self.root/'j',self.deps);key='a'*64;j.put('claim',key,{'a':1})
        with self.assertRaisesRegex(ValueError,'IMMUTABLE_REPLAY_CONFLICT'):j.put('claim',key,{'a':2})

    def test_journal_tamper(self):
        j=RunJournal(self.root/'j',self.deps);key='a'*64;j.put('claim',key,{'a':1})
        (self.root/'j/index'/(key+'.claim')).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'JOURNAL_CONTENT_TAMPER'):j.get('claim',key)

    def test_independent_research_no_scanner(self):
        r=self.research().data;self.assertFalse(r['scanner_required']);self.assertEqual(r['attempt_count'],4)
        self.assertEqual(r['optional_feedback']['status'],'ABSENT_OPTIONAL')

    def test_optional_scanner_feedback_stays_quarantined(self):
        r=self.research(feedback={'nominated':True,'source_verified':True}).data
        self.assertEqual(r['optional_feedback']['status'],'UNKNOWN_DEFERRED')
        self.assertEqual(r['attempt_count'],4)

    def test_invalid_duplicate_and_budget_attempts_preserved(self):
        self.plan['test_axes']={'F006':{'roc.period':[-1,5,5,10,20,50]}};self.plan['budget']=4
        r=self.research().data
        self.assertEqual(r['attempt_count'],6)
        self.assertEqual(r['status_counts'],{'INVALID':1,'SUBMITTED_NOT_EVALUATED':2,'DUPLICATE':1,'BUDGET_EXHAUSTED':2})
        self.assertTrue(all(a['claim_sha256'] for a in r['attempts']))
        self.assertEqual(sum(r['status_counts'].values()),6)

    def test_research_same_input_fresh_run_and_restart(self):
        a=self.research(journal=RunJournal(self.root/'a',self.deps))
        b=self.research(journal=RunJournal(self.root/'b',self.deps))
        c=self.research(journal=RunJournal(self.root/'a',self.deps))
        self.assertEqual(a.payload,b.payload);self.assertEqual(a.payload,c.payload)

    def test_research_policy_cannot_mutate_frozen_plan(self):
        j=RunJournal(self.root/'a',self.deps);self.research(journal=j)
        self.plan['budget']=3
        with self.assertRaisesRegex(ValueError,'IMMUTABLE_REPLAY_CONFLICT'):self.research(journal=j)

    def test_no_real_research_source_run(self):
        self.plan['evidence_class']='RETROSPECTIVE'
        with self.assertRaisesRegex(ValueError,'AUTHENTIC_RESEARCH_NOT_AUTHORIZED'):self.research()

    def test_no_missing_attempt_on_validation_error(self):
        self.plan['test_axes']={'F006':{'roc.period':[True,5]}}
        r=self.research().data
        self.assertEqual(r['status_counts'],{'INVALID':1,'SUBMITTED_NOT_EVALUATED':1})

    def test_factory_failure_isolated_no_false_evaluation(self):
        f=deepcopy(self.f['factory-test-input.json']);f['envelope']['rows'].pop()
        r=self.research(fixture=f).data
        self.assertEqual(r['status_counts'],{'FACTORY_HANDOFF_BLOCKED':4})
        self.assertTrue(all(a['factory_handoff'] is None for a in r['attempts']))

    def test_candidate_reparsed_with_merged_registry(self):
        from research_wp_r0.strategy_definition import StrategyDefinition
        from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
        for c in self.research().data['candidates']:
            value=Frozen.restore(c).data
            sd=StrategyDefinition.from_dict(value['definition'],registry=IndicatorRegistryV2())
            self.assertEqual(sd.digest,value['definition']['digest'])
            self.assertFalse(value['scanner_nomination_required'])
            self.assertEqual(value['paper_registry_promotion'],'NOT_AUTHORIZED')

    def test_dependency_source_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            lock=decode(read(FIXTURES/'dependencies.json'));key=next(iter(lock['components']['scanner']['files']))
            lock['components']['scanner']['files'][key]='f'*64;p=Path(temp)/'lock.json';raw=canonical(lock);p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'DEPENDENCY_DRIFT'):Dependencies(p,raw_sha(raw),self.roots)

    def test_dependency_lock_anchor(self):
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_LOCK_SHA'):
            Dependencies(FIXTURES/'dependencies.json','f'*64,self.roots)

    def test_no_fake_approved_registry(self):
        r=registry_snapshot(self.specs).data
        self.assertEqual(r['approved_paper_registry'],'NOT_CONNECTED');self.assertEqual(r['approval_records'],[])

    def test_restart_after_target_commit_before_router_ack(self):
        n,s=self.selected();nom=Frozen.restore(n);calls=[]
        def decide(value):calls.append(value['attempt_id']);return 'ACCEPT'
        sink=TestOnlyStrategySink(s,RunJournal(self.root/'target',self.deps),decide,decision_policy_id='test_v1')
        delivery=digest({'nomination':nom.sha256,'strategy':s.data['config_digest'],
                         'consumer_policy':'test_v1','contract':'aql.paper-strategy-handoff.v1'})
        original=sink.receive(nom,delivery)
        # New router journal represents a crash before the source acknowledgment.
        recovered=route(n,s,RunJournal(self.root/'router',self.deps),test_sink=sink)
        self.assertEqual(original.payload,recovered.payload);self.assertEqual(len(calls),1)
