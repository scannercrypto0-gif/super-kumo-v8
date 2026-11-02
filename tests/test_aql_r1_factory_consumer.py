"""NEW R1 consumer checks on actual pinned Core/B1 artifacts, no old suites.

Adversarial documents are re-sealed to exercise structural validation beyond
the transport hash. They are never emitted as original research observations.
"""
import copy
import json
import os
import unittest
from pathlib import Path

from research_wp_r0.aql_r1_factory_consumer import (
    BAR_MS, CORE_BYTES_SHA, build_evaluation, canonical, evaluate, load_market,
    market_window, sha, strict_json, validate_handoff,
)


class FactoryR1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=Path(os.environ['AQL_R1_CORE']).read_bytes()
        cls.market_raw=Path(os.environ['AQL_R1_B1']).read_bytes()
        cls.doc=strict_json(cls.raw)
        cls.months=load_market(cls.market_raw)

    def reseal(self,change):
        doc=copy.deepcopy(self.doc);change(doc)
        doc['handoff_sha256']=sha(canonical({k:v for k,v in doc.items() if k!='handoff_sha256'}))
        return doc

    def test_actual_producer_to_consumer_all_identities_and_counts(self):
        self.assertEqual(sha(self.raw),CORE_BYTES_SHA)
        result=evaluate(self.raw,self.market_raw)
        c=result['counts']
        self.assertEqual((c['opportunities'],c['arm_slots_2n'],c['outcome_rows_6n']),(32,64,192))
        self.assertEqual(c['coverage'],{'COMPLETE':192})
        self.assertEqual(c['missing_capture'],64)
        self.assertEqual([r['original_core_opportunity'] for r in result['opportunity_ledger']],
                         self.doc['opportunities'])
        self.assertEqual(sum(s['n_opportunities'] for s in result['feature_regime_strata']),32)

    def test_transport_drift_and_duplicate_json_keys_denied(self):
        with self.assertRaisesRegex(ValueError,'CORE_TRANSPORT_PIN'):
            evaluate(self.raw+b' ',self.market_raw)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):
            strict_json(b'{"a":1,"a":2}')

    def test_rehashed_duplicate_opportunity_denied(self):
        doc=self.reseal(lambda d:d['opportunities'].__setitem__(1,copy.deepcopy(d['opportunities'][0])))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OPPORTUNITY'):
            validate_handoff(doc,self.months)

    def test_missing_opportunity_and_missing_id_never_silently_dropped(self):
        doc=self.reseal(lambda d:d['opportunities'].pop())
        with self.assertRaisesRegex(ValueError,'MISSING_OPPORTUNITY'):
            validate_handoff(doc,self.months)
        doc=self.reseal(lambda d:d['opportunities'][0].pop('opportunity_id'))
        with self.assertRaises((ValueError,KeyError)):
            validate_handoff(doc,self.months)

    def test_cutoff_lookahead_denied(self):
        def change(d): d['opportunities'][0]['feature_last_bar_close_exclusive_ms']+=BAR_MS
        with self.assertRaisesRegex(ValueError,'CUTOFF_LOOKAHEAD'):
            validate_handoff(self.reseal(change),self.months)

    def test_rehashed_source_version_drift_denied(self):
        doc=self.reseal(lambda d:d['opportunities'][0].__setitem__('source_version','other'))
        with self.assertRaisesRegex(ValueError,'ROW_SOURCE_DRIFT'):
            validate_handoff(doc,self.months)

    def test_late_source_and_correction_clock_denied(self):
        for field in ('source_available_at_ms','correction_published_at_ms'):
            with self.subTest(field=field):
                def change(d): d['opportunities'][0][field]=d['opportunities'][0]['decision_cutoff_ms']+1
                with self.assertRaisesRegex(ValueError,'SOURCE_CLOCK_LOOKAHEAD'):
                    validate_handoff(self.reseal(change),self.months)

    def test_feature_version_and_value_mismatch_denied(self):
        doc=self.reseal(lambda d:d['opportunities'][0].__setitem__('feature_version','other'))
        with self.assertRaisesRegex(ValueError,'FEATURE_REGIME_ROW_VERSION'):
            validate_handoff(doc,self.months)
        doc=self.reseal(lambda d:d['opportunities'][0]['features'].__setitem__('ema8','1'))
        with self.assertRaisesRegex(ValueError,'FEATURE_VALUE'):
            validate_handoff(doc,self.months)

    def test_regime_version_and_state_mismatch_denied(self):
        doc=self.reseal(lambda d:d['opportunities'][0]['regime'].__setitem__('version','other'))
        with self.assertRaisesRegex(ValueError,'FEATURE_REGIME_ROW_VERSION'):
            validate_handoff(doc,self.months)
        doc=self.reseal(lambda d:d['opportunities'][0]['regime'].__setitem__('state','UNKNOWN'))
        with self.assertRaisesRegex(ValueError,'REGIME_VALUE_MISMATCH'):
            validate_handoff(doc,self.months)

    def test_missing_arm_retains_expected_slot_and_horizons(self):
        doc=self.reseal(lambda d:d['opportunities'][0]['arms'].pop())
        result=build_evaluation(doc,self.months)
        arms=result['opportunity_ledger'][0]['arm_slots']
        self.assertEqual([a['arm'] for a in arms],['BASE','SHADOW'])
        self.assertEqual(arms[1]['capture_status'],'MISSING_CAPTURE')
        self.assertFalse(arms[1]['supplied'])
        self.assertEqual(result['counts']['outcome_rows_6n'],192)

    def test_duplicate_arm_denied(self):
        doc=self.reseal(lambda d:d['opportunities'][0]['arms'].append(copy.deepcopy(d['opportunities'][0]['arms'][0])))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_UNKNOWN_ARM'):
            validate_handoff(doc,self.months)

    def test_missing_independent_witness_never_becomes_direction_or_uplift(self):
        result=build_evaluation(self.doc,self.months)
        self.assertTrue(all(r['status']=='NOT_EVALUABLE' and r['base_shadow_uplift'] is None
                            for r in result['paired_comparisons']))
        self.assertTrue(all(all(r[k] is None for k in ('signed_mfe','signed_mae','tp_sl_ordering','fills','pnl','alpha'))
                            for r in result['outcomes']))
        forged=self.reseal(lambda d:d['source'].__setitem__('external_evidence','VERIFIED'))
        with self.assertRaisesRegex(ValueError,'MISSING_WITNESS'):
            validate_handoff(forged,self.months)

    def test_forged_parent_and_actual_archive_tamper_denied(self):
        doc=self.reseal(lambda d:d['source']['months'][0].__setitem__('archive_sha256','0'*64))
        with self.assertRaisesRegex(ValueError,'FORGED_PARENT'):
            validate_handoff(doc,self.months)
        with self.assertRaisesRegex(ValueError,'B1_ARTIFACT_PIN'):
            load_market(self.market_raw[:-1]+b'x')

    def test_censored_source_end_keeps_counts_but_no_complete_extrema(self):
        row=self.doc['opportunities'][0];cut=row['decision_cutoff_ms']
        bars=self.months[row['source_member_sha256']]['bars']
        truncated={t:v for t,v in bars.items() if t<cut+3*BAR_MS}
        result=market_window(truncated,cut,4)
        self.assertEqual((result['coverage_status'],result['observed_bars'],result['expected_bars']),('CENSORED',3,16))
        self.assertTrue(result['censored']);self.assertIsNone(result['observed_high'])

    def test_internal_missing_bar_unknown_not_end_censor(self):
        row=self.doc['opportunities'][0];cut=row['decision_cutoff_ms']
        bars=dict(self.months[row['source_member_sha256']]['bars']);bars.pop(cut+BAR_MS)
        result=market_window(bars,cut,4)
        self.assertEqual((result['coverage_status'],result['observed_bars']),('UNKNOWN',15))
        self.assertFalse(result['censored'])

    def test_missing_market_source_explicit_unknown(self):
        result=market_window(None,self.doc['opportunities'][0]['decision_cutoff_ms'],4)
        self.assertEqual(result['coverage_status'],'UNKNOWN')
        self.assertEqual(result['expected_bars'],16)

    def test_later_market_bar_does_not_change_consumed_features_or_regimes(self):
        markets=copy.deepcopy(self.months)
        row=self.doc['opportunities'][-1]
        bars=markets[row['source_member_sha256']]['bars']
        later=row['decision_cutoff_ms']+BAR_MS
        hi,lo,o,c=bars[later]
        bars[later]=(hi+Decimal('10'),lo,o,c)
        original=build_evaluation(self.doc,self.months)
        changed=build_evaluation(self.doc,markets)
        self.assertEqual(original['opportunity_ledger'],changed['opportunity_ledger'])


from decimal import Decimal

if __name__=='__main__':
    unittest.main()
