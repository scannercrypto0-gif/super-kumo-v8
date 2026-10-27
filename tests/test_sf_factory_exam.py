"""Falsification of new Factory exam plumbing, no historical data or Core IO."""
import copy
from decimal import Decimal
import unittest

from research_wp_r0.factory_exam import (
    FrozenExam, freeze_manifest, freeze_protocol, run_route, compare_routes, replay_route)
from research_wp_r0.factory_exam_example import fixture, run_fixture
from research_wp_r0.strategy_definition import canonical
from research_wp_r0.strategy_dna_v2 import StrategyDNAV2
from research_wp_r0.strategy_dna_v2_example import example


class FactoryExamTests(unittest.TestCase):
    def setUp(self):
        self.dna, self.events, self.config = fixture()

    def build(self, events=None, config=None, dna=None):
        m = freeze_manifest(dna or self.dna, self.events if events is None else events)
        p = freeze_protocol(m, expected_manifest_digest=m.digest, config=config or self.config)
        return m, p

    def run_arm(self, m, p, arm="ALWAYS"):
        return run_route(m, p, expected_manifest_digest=m.digest, expected_protocol_digest=p.digest, arm=arm)

    def test_eight_opportunity_estimands(self):
        m,p = self.build(); a=self.run_arm(m,p); b=self.run_arm(m,p,"REGIME")
        r=compare_routes(a,b).spec
        self.assertAlmostEqual(r["left"]["ex_ante_policy_mean_per_requested_notional"],-.015375)
        self.assertAlmostEqual(r["right"]["ex_ante_policy_mean_per_requested_notional"],.00525)
        self.assertEqual(r["conditional_both_executed_count"],4)
        self.assertEqual(r["conditional_both_executed_mean_net_return_lift"],0)
        self.assertAlmostEqual(a.spec["portfolio"]["final_equity"],987.7)
        self.assertAlmostEqual(b.spec["portfolio"]["final_equity"],1004.2)
        self.assertEqual(r["right"]["attrition"]["REGIME_ABSTAIN"],4)

    def test_repeat_replay_and_input_preservation(self):
        before=copy.deepcopy(self.events);m,p=self.build();r=self.run_arm(m,p)
        self.assertEqual(r.payload,replay_route(m,p,r,arm="ALWAYS").payload)
        self.assertEqual(self.events,before)
        spec=m.spec;spec["rows"].clear();self.assertEqual(len(m.spec["rows"]),8)

    def test_corrupt_ledger_replay_rejected(self):
        m,p=self.build();r=self.run_arm(m,p);s=r.spec;s["ledger"][0]["details"]={}
        with self.assertRaises(ValueError):replay_route(m,p,FrozenExam(canonical(s)),arm="ALWAYS")

    def test_retained_and_protocol_bindings(self):
        m,p=self.build()
        with self.assertRaises(ValueError):run_route(m,p,expected_manifest_digest="0"*64,expected_protocol_digest=p.digest,arm="ALWAYS")
        self.events[0]["fill_fraction"]=.5;m2,p2=self.build()
        with self.assertRaises(ValueError):self.run_arm(m2,p)
        with self.assertRaises(ValueError):compare_routes(self.run_arm(m,p),self.run_arm(m2,p2))

    def test_monitor_faults_do_not_change_routes(self):
        m,p=self.build();r=self.run_arm(m,p)
        for source in (chr(0xd800),'x'*(17*1024*1024)):
            events=copy.deepcopy(self.events)
            for event in events:event["features"]["observe"]["source_id"]=source
            mm,pp=self.build(events)
            self.assertEqual(mm.spec['rows'],m.spec['rows'])
            rr=self.run_arm(mm,pp)
            self.assertEqual(rr.spec['outcomes'],r.spec['outcomes'])
            self.assertEqual(rr.spec['portfolio'],r.spec['portfolio'])
            self.assertEqual(mm.spec['monitoring'][0]['observation']['observations'][0]['status'],'UNVERIFIED')

    def test_optional_exit_missing_does_not_veto_entry(self):
        v,_,_=example();spec=self.dna.spec
        spec["strategy_version"]="optional_exit"
        spec["decision_profile"]["exit"]["terms"][0]["reference"]="observe"
        dna=StrategyDNAV2(spec,v1_definition=v)
        for event in self.events:del event["features"]["observe"]
        m,p=self.build(dna=dna)
        self.assertTrue(all(o["status"]=="EXECUTED" for o in self.run_arm(m,p).spec["outcomes"]))

    def test_entry_mandatory_missing(self):
        for event in self.events:del event["features"]["strength"]
        m,p=self.build();r=self.run_arm(m,p).spec
        self.assertTrue(all(o["reason"]=="CRITICAL_UNAVAILABLE" for o in r["outcomes"]))
        self.assertEqual(r["portfolio"]["final_equity"],1000)

    def test_ambiguous_and_scanner_excluded(self):
        self.events[0]["features"]["trend"]["values"]["value"]=5
        m,p=self.build();self.assertEqual(self.run_arm(m,p).spec["outcomes"][0]["reason"],"SCANNER_EXCLUDED")
        v,_,_=example();spec=self.dna.spec;spec["decision_profile"]["exit"]["threshold"]=0
        m,p=self.build(dna=StrategyDNAV2(spec,v1_definition=v))
        self.assertEqual(self.run_arm(m,p).spec["outcomes"][1]["reason"],"AMBIGUOUS_REJECTED")

    def test_cross_section_capacity_before_route(self):
        ev=copy.deepcopy(self.events[0]);ev["event_id"]="extra";ev["symbol"]="BBB"
        self.events.append(ev);v,_,_=example();s=self.dna.spec;s["scanner_profile"]["max_candidates"]=1
        m,p=self.build(dna=StrategyDNAV2(s,v1_definition=v));r=self.run_arm(m,p).spec
        self.assertEqual(r["outcomes"][1]["reason"],"SCANNER_EXCLUDED")

    def test_protection_explicit_no_default_stop(self):
        m,p=self.build(config=dict(self.config,protection_required=True))
        self.assertTrue(all(x["reason"]=="REQUIRED_PROTECTION_UNAVAILABLE" for x in self.run_arm(m,p).spec["outcomes"]))
        for e in self.events:e["protection"]=dict(available_at_ms=e["cutoff_ms"],covers_until_ms=e["cutoff_ms"]+101)
        m,p=self.build(config=dict(self.config,protection_required=True))
        self.assertTrue(all(x["status"]=="EXECUTED" for x in self.run_arm(m,p).spec["outcomes"]))

    def test_decimal_conservation_friction_partial_fill(self):
        self.events=self.events[:1];self.events[0]["fill_fraction"]=.5
        m,p=self.build(config=dict(self.config,fee_bps=10,slippage_bps=5,spread_bps=2))
        r=self.run_arm(m,p).spec;D=Decimal
        debit=D('.5')*D('100')*(1+D('6')/10000)*(1+D('10')/10000)
        credit=D('.5')*D('101')*(1-D('6')/10000)*(1-D('10')/10000)
        self.assertAlmostEqual(r["outcomes"][0]["net_quote"],float(credit-debit))
        self.assertAlmostEqual(r["portfolio"]["final_equity"],float(D('1000')+credit-debit))
        self.assertAlmostEqual(r["outcomes"][0]["gross_quote"],.5)
        self.assertTrue(all(x["details"].get("cash",0)>=0 for x in r["ledger"]))

    def test_cash_budget_denial(self):
        m,p=self.build(config=dict(self.config,capital=100,notional=100,fee_bps=10))
        self.assertTrue(all(o["reason"]=="CASH_BUDGET_DENIED" for o in self.run_arm(m,p).spec["outcomes"]))

    def test_no_fill_distinct_from_unknown(self):
        self.events[0]["fill_fraction"]=0;self.events[1]["fill_fraction"]=None
        m,p=self.build();r=self.run_arm(m,p);o=r.spec["outcomes"]
        self.assertEqual(o[0]["status"],"NO_FILL");self.assertEqual(o[0]["net_quote"],0)
        self.assertEqual(o[1]["status"],"UNKNOWN");self.assertIsNone(o[1]["net_quote"])
        self.assertIsNone(r.spec["portfolio"]["final_equity"])

    def test_missing_event_and_regime_not_zero(self):
        self.events[0]["features"]=None;self.events[1]["regime"]=None
        m,p=self.build();r=self.run_arm(m,p,"REGIME");s=compare_routes(self.run_arm(m,p),r).spec
        self.assertEqual(r.spec["outcomes"][0]["reason"],"NOT_SUPPLIED")
        self.assertEqual(r.spec["outcomes"][1]["reason"],"REGIME_UNKNOWN_OR_STALE")
        self.assertIsNone(s["right"]["ex_ante_policy_mean_per_requested_notional"])
        self.assertEqual(s["right"]["scheduled"],8)

    def test_late_or_missing_entry_never_skips_to_better_quote(self):
        self.events[0]["quotes"][0]["available_at_ms"]+=1
        m,p=self.build();self.assertEqual(self.run_arm(m,p).spec["outcomes"][0]["reason"],"UNOBSERVED_FILL")

    def test_missing_exit_halts_and_keeps_unknown(self):
        self.events[0]["quotes"].pop();m,p=self.build();r=self.run_arm(m,p).spec
        self.assertEqual(r["outcomes"][0]["reason"],"UNOBSERVED_NATIVE_EXIT")
        self.assertIsNone(r["portfolio"]["net_quote"]);self.assertFalse(r["portfolio"]["drawdown_complete"])

    def test_mark_to_market_drawdown_not_closed_trade_dd(self):
        e=self.events[0];self.events=self.events[:1]
        e["quotes"].insert(1,dict(at_ms=1050,available_at_ms=1050,price=50))
        m,p=self.build();r=self.run_arm(m,p).spec
        self.assertAlmostEqual(r["portfolio"]["sampled_mtm_drawdown_fraction"],.05)
        self.assertGreater(r["portfolio"]["net_quote"],0)

    def test_late_mark_with_open_exposure_halts(self):
        self.events[0]['quotes'].insert(1,dict(at_ms=1050,available_at_ms=1051,price=50))
        m,p=self.build();r=self.run_arm(m,p).spec
        self.assertTrue(r['portfolio']['halted']);self.assertIsNone(r['portfolio']['final_equity'])
        self.assertTrue(any(x['kind']=='HALT' for x in r['ledger']))

    def test_future_or_oracle_regime_rejected(self):
        for changes in [dict(kind="GENERATOR_TRUTH"),dict(as_of_ms=1001),dict(available_at_ms=1001),dict(score=float('nan'))]:
            events=copy.deepcopy(self.events);events[0]["regime"].update(changes)
            with self.assertRaises(ValueError):self.build(events)

    def test_stale_regime_abstains_unknown_not_zero(self):
        self.events[0]["regime"]["as_of_ms"]=0;m,p=self.build();r=self.run_arm(m,p,"REGIME").spec
        self.assertEqual(r["outcomes"][0]["status"],"UNKNOWN")

    def test_invalid_price_time_fraction_and_duplicates(self):
        for change in ['price','time','fraction','duplicate']:
            events=copy.deepcopy(self.events)
            if change=='price':events[0]['quotes'][0]['price']=float('nan')
            elif change=='time':events[0]['quotes'][0]['at_ms']=1000
            elif change=='fraction':events[0]['fill_fraction']=1.1
            else:events.append(events[0])
            with self.assertRaises(ValueError):self.build(events)

    def test_false_family_match_on_changed_quote(self):
        m,p=self.build();a=self.run_arm(m,p)
        self.events[0]['quotes'][1]['price']=105;mm,pp=self.build();b=self.run_arm(mm,pp)
        self.assertEqual(a.spec['outcomes'][0]['family_id'],b.spec['outcomes'][0]['family_id'])
        with self.assertRaises(ValueError):compare_routes(a,b)

    def test_cost_and_unequal_exposure_sensitivity_explicit(self):
        m,p=self.build();a=self.run_arm(m,p)
        _,pp=self.build(config=dict(self.config,fee_bps=20,notional=200));b=self.run_arm(m,pp)
        with self.assertRaises(ValueError):compare_routes(a,b)
        r=compare_routes(a,b,sensitivity=True).spec
        self.assertIn('notional',r['changed_execution_assumptions'])
        self.assertLess(r['right']['portfolio']['net_quote'],r['left']['portfolio']['net_quote'])

    def test_single_overlay_excludes_overlap_and_counts_trials(self):
        self.events=self.events[:2];e=self.events[1];e['cutoff_ms']=1050
        for obs in e['features'].values():obs.update(as_of_ms=1040,observed_at_ms=1041,available_at_ms=1042)
        e['regime'].update(as_of_ms=1049,available_at_ms=1050)
        e['quotes']=[dict(at_ms=1051,available_at_ms=1051,price=100),dict(at_ms=1151,available_at_ms=1151,price=96)]
        m,p=self.build();_,pp=self.build(config=dict(self.config,trial_id='R1',overlay=dict(name='MAX_CONCURRENT',version='1',max_concurrent=1)))
        r=compare_routes(self.run_arm(m,p),self.run_arm(m,pp)).spec
        self.assertEqual(r['right']['attrition']['OVERLAY_CAPACITY'],1)
        self.assertEqual(r['conditional_both_executed_count'],1)

    def test_native_dna_exit_uses_next_eligible_print_not_cutoff(self):
        self.events=self.events[:2];e=self.events[1];e['cutoff_ms']=1050
        for obs in e['features'].values():obs.update(as_of_ms=1040,observed_at_ms=1041,available_at_ms=1042)
        e['features']['trend']['values']['value']=15
        e['regime'].update(as_of_ms=1049,available_at_ms=1050,score=0)
        e['quotes']=[dict(at_ms=1051,available_at_ms=1051,price=100),dict(at_ms=1151,available_at_ms=1151,price=96)]
        m,p=self.build();r=self.run_arm(m,p,'REGIME').spec
        self.assertEqual(r['outcomes'][0]['reason'],'SYNTHETIC_DNA_EXIT')
        exits=[x for x in r['ledger'] if x['kind']=='SIMULATED_EXIT']
        self.assertEqual(exits[0]['at_ms'],1051)
        self.assertEqual(exits[0]['details']['trigger_event_id'],'E1')

    def test_no_future_trial_selection_or_unsupported_overlay(self):
        for cfg in [dict(self.config,registered_at_ms=1001),dict(self.config,overlay={'name':'STOP_ALL','version':'1','max_concurrent':1})]:
            with self.assertRaises(ValueError):self.build(config=cfg)

    def test_example_metadata_deterministic_no_promotion(self):
        a=run_fixture();b=run_fixture();self.assertEqual(a,b)
        self.assertEqual(len(a['trial_register']),4)
        self.assertEqual(a['r2'],'NOT_IMPLEMENTED_NO_VALIDATED_OVERLAY_COMBINATION')


if __name__ == '__main__':
    unittest.main()
