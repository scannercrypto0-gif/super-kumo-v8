"""Consolidated current-seam gate; negatives mutate disposable TEST_ONLY inputs."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from .harness import BoundaryError, canonical, digest, load_object, sha, strict_json
from .seams_v2 import checkouts, core_call, factory_boundary, run_v2, scanner_boundary, worker

FIXTURES = Path(__file__).parent / 'fixtures_v2'


class SeamIntegrationGate(unittest.TestCase):
    roots = {}

    @classmethod
    def setUpClass(cls):
        cls.lock = strict_json((FIXTURES/'manifest.json').read_bytes())
        checkouts(cls.lock, cls.roots)
        cls.core_outputs = [core_call(FIXTURES,c,cls.roots) for c in cls.lock['cohorts']]

    def setUp(self):
        self.c = deepcopy(self.lock['cohorts'][0])
        self.core = deepcopy(self.core_outputs[0])
        self.schedule = load_object(FIXTURES,self.c['objects']['schedule'])
        self.slots = load_object(FIXTURES,self.c['objects']['slots'])
        self.batch = load_object(FIXTURES,self.c['objects']['scanner'])

    def factory(self):
        return factory_boundary(self.c,self.schedule,self.slots,self.core,self.roots)

    def scanner(self):
        return scanner_boundary(self.c,self.batch,self.core,self.roots,
                                self.lock['components']['scanner']['commit_sha'])

    def fail_factory(self, reason):
        with self.assertRaisesRegex(ValueError,reason):self.factory()

    def fail_scanner(self, reason):
        with self.assertRaisesRegex(ValueError,reason):self.scanner()

    def scanner_snapshots(self):
        # Independent TEST_ONLY mutation helper: native UTF-8 digest domain.
        for a in self.batch['attempts']:
            e,r=a['envelope'],a['receipt']
            native=lambda o:json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            e['digest']=sha(native({k:v for k,v in e.items() if k!='digest'}))
            r['payload_digest']=sha(native(e))
            a['envelope_raw_hex']=native(e).hex();a['receipt_raw_hex']=native(r).hex()

    def test_00_integrated_independent_counts_hashes_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/'receipts'
            expected=(FIXTURES/'manifest.sha256').read_text().strip()
            key,summary=run_v2(FIXTURES/'manifest.json',expected,self.roots,dest)
            rows=[r for c in self.lock['cohorts'] for r in load_object(FIXTURES,c['objects']['slots'])]
            independent=Counter(r['status'] for r in rows)
            self.assertEqual(summary['factory_arm_slots'],len(rows))
            self.assertEqual(summary['factory_arm_slots'],16)
            self.assertEqual(summary['factory_pairs'],8)
            for status,count in summary['factory_status_counts'].items():
                self.assertEqual(count,independent[status])
            self.assertEqual(sum(r['return'] is None for r in rows),16)
            self.assertEqual(summary['scanner_census'],{'NOMINATED':1,'REJECTED':1,'UNKNOWN':1,
                                                       'FAILED':1,'INELIGIBLE':2,'UNSCANNED':2})
            self.assertEqual(summary['discoverer_attempts'],4)
            self.assertEqual(summary['discoverer_eligible'],0)
            self.assertEqual(summary['candidates_generated'],0)
            old={p.name:p.read_bytes() for p in dest.glob('*.json')}
            for name,raw in old.items():
                separate=json.dumps(json.loads(raw),sort_keys=True,separators=(',',':'),
                                    ensure_ascii=True,allow_nan=False).encode()
                self.assertEqual(name,hashlib.sha256(separate).hexdigest()+'.json')
            self.assertEqual(len(old),4)
            for parent in summary['parents']:
                cohort=json.loads(old[parent+'.json'])
                self.assertEqual(cohort['parent_manifest_sha256'],summary['parent_manifest_sha256'])
                for attempt in cohort['scanner_discoverer']['attempts']:
                    self.assertFalse(attempt['eligible'])
                    self.assertEqual(attempt['quarantine'],'UNKNOWN_DEFERRED')
                    self.assertEqual(attempt['evidence']['source_availability'],'UNKNOWN')
            (dest/'.staging-crashed').write_bytes(b'partial')
            key2,again=run_v2(FIXTURES/'manifest.json',expected,self.roots,dest)
            self.assertEqual(key2,key);self.assertEqual(again,summary)
            self.assertEqual(old,{p.name:p.read_bytes() for p in dest.glob('*.json')})

    def test_native_core_query_original_byte_parent(self):
        self.assertEqual(self.core['registration']['source_bytes_sha256'],self.c['objects']['source']['sha256'])
        for q in self.core['queries']:
            self.assertEqual(q['evidence_class'],'SYNTHETIC_TEST')
            self.assertEqual(q['result']['status'],'COMPLETE')
            self.assertTrue(all(b['observation_cutoff_ms']<=q['result']['decision_cutoff_ms'] for b in q['result']['bars']))

    def test_native_factory_statuses_preserved(self):
        _,receipt=self.factory()
        self.assertEqual(receipt['status_counts'],{'NO_SIGNAL':2,'REJECTED':2,'UNKNOWN':1,
                         'UNSCANNED':1,'NOMINATED':1,'NULL':1,'UNRESOLVED':0})
        self.assertEqual(receipt['descriptive_4_24_72h'],'NOT_EVALUATED')
        self.assertEqual(receipt['modeled_trades'],'NOT_EVALUATED')

    def test_native_discoverer_quarantine_and_unknown_availability(self):
        result=self.scanner()
        self.assertEqual(result['candidate_count'],0)
        self.assertEqual(len(result['original_universe']),4)
        self.assertEqual([a['original_state'] for a in result['attempts']],['NOMINATED','REJECTED'])
        self.assertTrue(all(a['quarantine']=='UNKNOWN_DEFERRED' for a in result['attempts']))

    def test_core_partial_and_unknown_are_not_complete(self):
        source=(FIXTURES/self.c['objects']['source']['path']).read_bytes()
        body={'source_hex':source.hex(),'source_sha256':sha(source),'inventory_sha256':self.c['inventory_sha256'],
              'spec':self.c['spec'],'requests':[dict(self.c['requests'][-1],decision_cutoff_ms=cutoff,require_complete=False)
                                               for cutoff in (0,1800000)]}
        out=worker('core',body,self.roots)
        self.assertEqual([q['result']['status'] for q in out['queries']],['UNKNOWN','PARTIAL'])
        self.core['queries'][0]=out['queries'][1]
        self.fail_factory('CORE_COVERAGE_BLOCKED')

    def test_confirmed_only_native_core_refuses_fixture(self):
        source=(FIXTURES/self.c['objects']['source']['path']).read_bytes()
        body={'source_hex':source.hex(),'source_sha256':sha(source),'inventory_sha256':self.c['inventory_sha256'],
              'spec':self.c['spec'],'requests':[dict(self.c['requests'][-1],confirmed_only=True)]}
        q=worker('core',body,self.roots)['queries'][0]
        self.assertEqual(q['status'],'ERROR');self.assertEqual(q['evidence_class'],'NO_EVIDENCE')

    def test_original_source_bytes_tampered(self):
        with tempfile.TemporaryDirectory() as temp:
            shutil.copytree(FIXTURES,Path(temp)/'fixture');root=Path(temp)/'fixture'
            (root/self.c['objects']['source']['path']).write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_SHA'):core_call(root,self.c,self.roots)

    def test_native_core_nonfinal_source(self):
        raw=strict_json((FIXTURES/self.c['objects']['source']['path']).read_bytes())
        raw['records'][0]['bar']['is_final']=False
        record=raw['records'][0];record['envelope_hash']=digest({k:v for k,v in record.items() if k!='envelope_hash'})
        raw['record_content_hash']=digest(raw['records']);encoded=canonical(raw)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_BAR_SOURCE_PROVENANCE'):
            worker('core',{'source_hex':encoded.hex(),'source_sha256':sha(encoded),
                          'inventory_sha256':self.c['inventory_sha256'],'spec':self.c['spec'],
                          'requests':self.c['requests']},self.roots)

    def test_schedule_tamper(self):
        self.schedule['scheduled_total']=99;self.fail_factory('TAMPERED_RECEIPT')

    def test_forged_core_source(self):
        self.core['registration']['source_bytes_sha256']='f'*64;self.fail_factory('CORE_SOURCE_DRIFT')

    def test_forged_core_query_parent(self):
        self.core['queries'][0]['result']['source_bytes_sha256']='f'*64;self.fail_factory('CORE_QUERY_PARENT')

    def test_wrong_manifest(self):
        self.schedule['source']['manifest_sha256']='f'*64
        self.schedule['artifact_sha256']=digest({k:v for k,v in self.schedule.items() if k!='artifact_sha256'})
        self.fail_factory('CORE_MANIFEST_DRIFT')

    def test_missing_arm(self):
        self.slots.pop();self.fail_factory('ARM_DENOMINATOR')

    def test_duplicate_slot(self):
        self.slots[1]=deepcopy(self.slots[0]);self.fail_factory('MISSING_OR_DUPLICATE_SLOT')

    def test_duplicate_attempt(self):
        self.slots[1]['attempt_id']=self.slots[0]['attempt_id'];self.fail_factory('DUPLICATE_ATTEMPT')

    def test_cross_cohort(self):
        self.slots[0]['cohort_id']='TEST_ONLY_V2_ETHUSDT';self.fail_factory('SLOT_COHORT_IDENTITY')

    def test_cutoff_lookahead(self):
        self.slots[0]['decision_cutoff_ms']+=1;self.fail_factory('SLOT_CUTOFF_DRIFT')

    def test_future_source_availability(self):
        self.core['queries'][0]['result']['bars'][0]['observation_cutoff_ms']=99999999
        self.fail_factory('FUTURE_SOURCE_AVAILABILITY')

    def test_unknown_feature_availability_not_filled(self):
        self.slots[0]['feature_available_ms']=None;self.fail_factory('UNKNOWN_FEATURE_AVAILABILITY_BLOCKED')

    def test_future_feature_availability(self):
        self.slots[0]['feature_available_ms']=99999999;self.fail_factory('LATE_FEATURE')

    def test_feature_prefix_mismatch(self):
        self.core['queries'][0]['result']['bars'][0]['checksum']='f'*64;self.fail_factory('FEATURE_PREFIX_DRIFT')

    def test_feature_snapshot_mismatch(self):
        self.slots[0]['feature_snapshot_sha256']='f'*64;self.fail_factory('FEATURE_SNAPSHOT_DRIFT')

    def test_factory_nomination_promotion(self):
        self.slots[0]['status']='NOMINATED';self.fail_factory('STATUS_OR_UNAUTHORIZED_PROMOTION')

    def test_factory_null_not_zero(self):
        self.slots[-1]['return']=0;self.fail_factory('NULL_TO_ZERO_OR_RETURN')

    def test_factory_strategy_mismatch(self):
        self.slots[0]['strategy_version']='WRONG';self.fail_factory('MIXED_STRATEGY')

    def test_scanner_source_parent(self):
        self.batch['source_raw_sha256']='f'*64;self.fail_scanner('SCANNER_SOURCE_PARENT')

    def test_scanner_forged_witness(self):
        self.batch['independent_witness']={'verified':True};self.fail_scanner('FORGED_INDEPENDENT_WITNESS')

    def test_scanner_missing_attempt(self):
        self.batch['attempts'].pop();self.fail_scanner('MISSING_SCANNER_DENOMINATOR')

    def test_scanner_duplicate_attempt(self):
        self.batch['attempts'].append(deepcopy(self.batch['attempts'][0]));self.fail_scanner('MISSING_SCANNER_DENOMINATOR')

    def test_scanner_denominator_drift(self):
        self.batch['census']['UNSCANNED']=0;self.fail_scanner('SCANNER_CENSUS_DRIFT')

    def test_scanner_original_bytes_drift(self):
        self.batch['attempts'][0]['envelope']['reasons'].append('ALTERED');self.fail_scanner('SCANNER_ORIGINAL_BYTES_DRIFT')

    def test_scanner_header_tamper_even_if_payload_valid(self):
        self.batch['attempts'][0]['receipt']['symbol']='ETHUSDT';self.scanner_snapshots()
        self.fail_scanner('SCANNER_HEADER_DRIFT')

    def test_scanner_receipt_identity_tamper(self):
        self.batch['attempts'][0]['receipt']['receipt_id']='f'*64;self.scanner_snapshots()
        self.fail_scanner('SCANNER_NATIVE_RECEIPT_ID')

    def test_scanner_status_promotion(self):
        self.batch['attempts'][1]['envelope']['stage']='NOMINATED';self.scanner_snapshots()
        self.fail_scanner('SCANNER_STATUS_PROMOTION')

    def test_scanner_future_cutoff(self):
        self.batch['attempts'][0]['envelope']['cutoff_at']='1970-01-01T03:00:00+00:00';self.scanner_snapshots()
        self.fail_scanner('SCANNER_CUTOFF_DRIFT')

    def test_scanner_future_features(self):
        self.batch['attempts'][0]['envelope']['coverage']['available_at_ms']=99999999;self.scanner_snapshots()
        self.fail_scanner('FUTURE_FEATURE_AVAILABILITY')

    def test_scanner_false_authority(self):
        self.batch['attempts'][0]['envelope']['publishable']=True;self.scanner_snapshots()
        self.fail_scanner('SCANNER_AUTHORITY')

    def test_scanner_pit_upgrade(self):
        self.batch['attempts'][0]['envelope']['availability_class']='LIVE_PIT';self.scanner_snapshots()
        self.fail_scanner('SCANNER_PIT_UPGRADE')

    def test_scanner_stale_schema(self):
        self.batch['attempts'][0]['envelope']['schema_version']='OLD';self.scanner_snapshots()
        self.fail_scanner('SCANNER_VERSION')

    def test_scanner_cross_symbol(self):
        self.batch['attempts'][0]['envelope']['coverage']['symbol']='ETHUSDT';self.scanner_snapshots()
        self.fail_scanner('SCANNER_SYMBOL_TIMEFRAME')

    def test_component_drift(self):
        lock=deepcopy(self.lock);file=next(iter(lock['components']['scanner']['files']))
        lock['components']['scanner']['files'][file]='f'*64
        with self.assertRaisesRegex(ValueError,'COMPONENT_DRIFT'):checkouts(lock,self.roots)

    def test_missing_component(self):
        roots=dict(self.roots);roots.pop('discoverer')
        with self.assertRaisesRegex(ValueError,'MISSING_COMPONENT_CHECKOUT'):checkouts(self.lock,roots)

    def test_private_manifest_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'manifest.json';lock=deepcopy(self.lock);lock['evidence_class']='RETROSPECTIVE'
            raw=canonical(lock);p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'PRIVATE_OR_VERSION_FORBIDDEN'):
                run_v2(p,sha(raw),self.roots,Path(temp)/'out')
            self.assertFalse((Path(temp)/'out').exists())

    def test_manifest_anchor(self):
        with self.assertRaisesRegex(ValueError,'MANIFEST_SHA_MISMATCH'):
            run_v2(FIXTURES/'manifest.json','f'*64,self.roots,'UNUSED-OUTPUT')

    def test_census_bool_is_not_integer(self):
        self.batch['census']['NOMINATED']=True;self.fail_scanner('INVALID_CENSUS_INTEGER')

    def test_unknown_partial_core_cannot_feed_factory(self):
        self.core['queries'][0]['result']['status']='PARTIAL'
        self.fail_factory('CORE_COVERAGE_BLOCKED')

    def test_scanner_native_digest_forgery(self):
        a=self.batch['attempts'][0];a['envelope']['digest']='f'*64
        a['envelope_raw_hex']=canonical(a['envelope']).hex()
        a['receipt']['payload_digest']=digest(a['envelope'])
        a['receipt_raw_hex']=canonical(a['receipt']).hex()
        self.fail_scanner('SCANNER_ENVELOPE_DIGEST')

    def test_same_receipt_id_conflicting_header(self):
        a,b=self.batch['attempts'];b['receipt']['receipt_id']=a['receipt']['receipt_id']
        self.scanner_snapshots();self.fail_scanner('SCANNER_NATIVE_RECEIPT_ID')

    def test_missing_boundary(self):
        self.c['objects'].pop('scanner')
        with self.assertRaisesRegex(ValueError,'MISSING_INPUT_BOUNDARY'):core_call(FIXTURES,self.c,self.roots)

    def test_native_utf8_and_original_bytes_hash_domains(self):
        self.batch['attempts'][0]['envelope']['reasons'].append('بيانات تجريبية')
        self.scanner_snapshots()
        result=self.scanner()
        evidence=result['attempts'][0]['evidence']
        raw=bytes.fromhex(self.batch['attempts'][0]['envelope_raw_hex'])
        self.assertEqual(evidence['scanner_envelope_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(raw,canonical(self.batch['attempts'][0]['envelope']))
        self.assertFalse(result['attempts'][0]['eligible'])
