"""One consolidated offline gate; all mutations are disposable TEST_ONLY bytes."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import shutil

from .harness import (BoundaryError, ReceiptStore, canonical, digest, run, sha,
                      strict_json, MAX_BYTES, modules)

FIXTURES = Path(__file__).parent / 'fixtures'


class IntegrationGate(unittest.TestCase):
    roots = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.inputs = self.base / 'inputs'
        shutil.copytree(FIXTURES, self.inputs)
        self.manifest = strict_json((self.inputs / 'manifest.json').read_bytes())
        self.output = self.base / 'output'

    def save(self):
        raw = canonical(self.manifest)
        (self.inputs / 'manifest.json').write_bytes(raw)
        return sha(raw)

    def execute(self):
        return run(self.inputs / 'manifest.json', self.save(), self.roots, self.output)

    def obj(self, name, cohort=0):
        ref = self.manifest['datasets'][cohort]['objects'][name]
        return strict_json((self.inputs / ref['path']).read_bytes())

    def replace(self, name, obj, cohort=0, seal=False):
        if seal:
            obj['artifact_sha256'] = digest({k:v for k,v in obj.items() if k != 'artifact_sha256'})
        ref = self.manifest['datasets'][cohort]['objects'][name]
        raw = canonical(obj)
        (self.inputs / ref['path']).write_bytes(raw)
        ref['sha256'] = sha(raw)
        if name == 'core':
            factory = self.obj('factory', cohort)
            factory['source_schedule_sha256'] = obj['artifact_sha256']
            self.replace('factory', factory, cohort, seal=True)

    def change_core(self, fn):
        obj = self.obj('core'); fn(obj); self.replace('core', obj, seal=True)

    def change_factory(self, fn):
        obj = self.obj('factory'); fn(obj); self.replace('factory', obj, seal=True)

    def change_bars(self, fn):
        bars = self.obj('raw'); fn(bars); self.replace('raw', bars)
        raw_sha = self.manifest['datasets'][0]['objects']['raw']['sha256']
        history = self.obj('history'); history['source_hash'] = raw_sha
        history.pop('manifest_integrity_hash')
        mods = modules(self.manifest, self.roots)
        history = mods['history'].DatasetManifest(**history).to_dict()
        self.replace('history', history)
        core = self.obj('core'); core['source']['source_package_sha256'] = raw_sha
        core['source']['normalized_sha256'] = raw_sha
        core['source']['manifest_sha256'] = self.manifest['datasets'][0]['objects']['history']['sha256']
        for p in core['pairs']: p['opportunity']['source_package_sha256'] = raw_sha
        self.replace('core', core, seal=True)
        factory = self.obj('factory'); factory['source_package_sha256'] = raw_sha
        self.replace('factory', factory, seal=True)
        vault = self.obj('vault'); vault['content_sha256'] = raw_sha
        vault['byte_length'] = len(canonical(bars)); self.replace('vault', vault)

    def fails(self, reason):
        with self.assertRaisesRegex(ValueError, reason): self.execute()
        self.assertFalse(self.output.exists(), 'invalid inputs must not publish a summary')

    def test_00_positive_independent_census_graph_and_restart(self):
        key, summary = self.execute()
        # Independent census over original fixture receipts, not harness summary logic.
        rows = [r for i in range(2) for r in self.obj('factory', i)['modeled_trades']]
        self.assertEqual(len(rows), 8)
        self.assertEqual(summary['census'], {'pairs':4,'arms':8,'null':8,'censored':4,
                                            'rejected':4,'unknown':4})
        self.assertEqual(sum(r['modeled_net_return'] is None for r in rows), summary['census']['null'])
        self.assertEqual(sum(r['censored'] for r in rows), summary['census']['censored'])
        self.assertEqual(summary['unscanned']['count'], None)
        original = {p.name:p.read_bytes() for p in self.output.glob('*.json')}
        for name, raw in original.items():
            # Separate standard-library serializer and hash verification.
            independent = json.dumps(json.loads(raw),sort_keys=True,separators=(',',':'),
                                     ensure_ascii=True,allow_nan=False).encode()
            import hashlib
            self.assertEqual(name, hashlib.sha256(independent).hexdigest()+'.json')
        self.assertEqual(len(original), 4)
        for parent in summary['parents']:
            cohort=json.loads(original[parent+'.json'])
            self.assertEqual(cohort['parent_manifest_sha256'], summary['manifest_content_sha256'])
        (self.output / '.staging-interrupted').write_bytes(b'partial crash bytes')
        key2, summary2 = self.execute()
        self.assertEqual(key, key2); self.assertEqual(summary, summary2)
        self.assertEqual(original,{p.name:p.read_bytes() for p in self.output.glob('*.json')})

    def test_manifest_anchor_mismatch(self):
        with self.assertRaisesRegex(BoundaryError,'MANIFEST_SHA_MISMATCH'):
            run(self.inputs/'manifest.json','f'*64,self.roots,self.output)

    def test_input_sha_mismatch(self):
        ref=self.manifest['datasets'][0]['objects']['raw'];ref['sha256']='f'*64
        self.fails('INPUT_SHA_MISMATCH')

    def test_tampered_receipt_with_updated_raw_hash(self):
        obj=self.obj('factory');obj['pair_count']=9;self.replace('factory',obj)
        self.fails('TAMPERED_RECEIPT')

    def test_forged_parent(self):
        self.change_factory(lambda x:x.update(source_schedule_sha256='f'*64))
        self.fails('FORGED_PARENT')

    def test_missing_arm(self):
        self.change_core(lambda x:x['pairs'][0]['arms'].pop())
        self.fails('MISSING_OR_DUPLICATE_ARM')

    def test_duplicate_opportunity(self):
        self.change_core(lambda x:x['pairs'].append(deepcopy(x['pairs'][0])))
        self.fails('DUPLICATE_OPPORTUNITY')

    def test_conflicting_pair_identity(self):
        self.change_core(lambda x:x['pairs'][0].update(pair_id='f'*64))
        self.fails('CONFLICTING_PAIR_IDENTITY')

    def test_duplicate_factory_identity(self):
        self.change_factory(lambda x:x['modeled_trades'].__setitem__(1,deepcopy(x['modeled_trades'][0])))
        self.fails('DUPLICATE_OR_FOREIGN_FACTORY_IDENTITY')

    def test_missing_factory_arm(self):
        self.change_factory(lambda x:x['modeled_trades'].pop())
        self.fails('ARM_CENSUS_DRIFT')

    def test_cross_cohort_output(self):
        self.change_factory(lambda x:x.update(source_id='TEST_ONLY_ETHUSDT'))
        self.fails('CROSS_COHORT_IDENTITY')

    def test_cross_cohort_opportunity(self):
        self.change_core(lambda x:x['pairs'][0]['opportunity'].update(source_id='TEST_ONLY_ETHUSDT'))
        self.fails('CROSS_COHORT_OPPORTUNITY')

    def test_source_drift(self):
        self.change_factory(lambda x:x.update(source_package_sha256='f'*64))
        self.fails('SOURCE_HASH_DRIFT')

    def test_cutoff_lookahead(self):
        self.manifest['datasets'][0]['decision_cutoff_ms']=0
        self.fails('CUTOFF_LOOKAHEAD')

    def test_future_availability(self):
        self.change_bars(lambda x:x[0].update(available_at_ms=2700000,
                                             availability_evidence_ref='TEST_ONLY_FUTURE'))
        self.fails('FUTURE_AVAILABILITY')

    def test_unfinalized_bar(self):
        self.change_bars(lambda x:x[0].update(finalized=False))
        self.fails('UNFINALIZED_BAR')

    def test_duplicate_bar(self):
        self.change_bars(lambda x:x.__setitem__(1,deepcopy(x[0])))
        self.fails('DUPLICATE_OR_UNSORTED_BAR')

    def test_stale_adapter(self):
        self.manifest['components']['core']['contract']='aql.core.v0'
        self.fails('STALE_ADAPTER_CONTRACT')

    def test_stale_producer_output(self):
        self.change_core(lambda x:x.update(schema='aql.core.v0'))
        self.fails('STALE_OUTPUT_CONTRACT')

    def test_missing_checkout(self):
        roots=dict(self.roots);roots.pop('vault')
        with self.assertRaisesRegex(BoundaryError,'MISSING_ADAPTER_CHECKOUT'):
            run(self.inputs/'manifest.json',self.save(),roots,self.output)

    def test_component_source_drift(self):
        self.manifest['components']['core']['file_sha256']='f'*64
        self.fails('COMPONENT_SOURCE_DRIFT')

    def test_unauthorized_optional_connection(self):
        self.manifest['optional_connections']['bridge']='READY'
        self.fails('UNAUTHORIZED_CONNECTION')

    def test_synthetic_upgrade(self):
        self.manifest['evidence_class']='RETROSPECTIVE'
        self.fails('SYNTHETIC_AS_AUTHENTIC')

    def test_prospective_upgrade(self):
        self.manifest['evidence_class']='PROSPECTIVE_CONFIRMED'
        self.fails('PROSPECTIVE_PROOF_NOT_CONNECTED')

    def test_null_not_zero(self):
        self.change_factory(lambda x:x['modeled_trades'][0].update(modeled_net_return='0'))
        self.fails('NULL_ACCOUNTING_DRIFT')

    def test_censored_result_refused(self):
        self.change_factory(lambda x:x['modeled_trades'][0].update(modeled_net_return='1',status='MODELED_COMPLETE',disposition='TRIGGERED'))
        self.fails('CENSORED_WITH_RESULT')

    def test_history_metadata_tamper(self):
        obj=self.obj('history');obj['coverage_pct']=50;self.replace('history',obj)
        self.fails('manifest_integrity_hash mismatch')

    def test_duplicate_dataset(self):
        self.manifest['datasets'].append(deepcopy(self.manifest['datasets'][0]))
        self.fails('DUPLICATE_DATASET')

    def test_path_escape(self):
        self.manifest['datasets'][0]['objects']['core']['path']='../private.json'
        self.fails('PATH_ESCAPE')

    def test_symlink_input(self):
        ref=self.manifest['datasets'][0]['objects']['raw'];p=self.inputs/ref['path']
        other=self.base/'other';p.rename(other);p.symlink_to(other)
        self.fails('SYMLINK_INPUT')

    def test_resource_limit(self):
        self.manifest['datasets']*=9
        self.fails('RESOURCE_LIMIT_DATASETS')

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(BoundaryError,'DUPLICATE_JSON_KEY'):
            strict_json(b'{"id":1,"id":2}')

    def test_store_tamper_on_replay(self):
        key,_=self.execute();(self.output/(key+'.json')).write_bytes(b'{}')
        with self.assertRaisesRegex(BoundaryError,'EXISTING_OBJECT_TAMPERED'):self.execute()

    def test_status_disposition_drift(self):
        self.change_factory(lambda x:x['modeled_trades'][0].update(disposition='TRIGGERED'))
        self.fails('DISPOSITION_STATUS_DRIFT')

    def test_unknown_availability_preserved(self):
        _,summary=self.execute()
        self.assertEqual([c['availability_unknown_opportunities'] for c in summary['cohorts']], [2,2])
        self.assertTrue(all(c['pit']=='NOT_ATTESTED' for c in summary['cohorts']))

    def test_history_parent_drift(self):
        self.change_core(lambda x:x['source'].update(manifest_sha256='f'*64))
        self.fails('HISTORY_PARENT_DRIFT')

    def test_arm_policy_drift(self):
        self.change_core(lambda x:x['pairs'][0]['arms'][0].update(definition_sha256='f'*64))
        self.fails('ARM_POLICY_DRIFT')

    def test_feature_and_regime_preserved(self):
        _,summary=self.execute()
        for i,cohort in enumerate(summary['cohorts']):
            original={p['pair_id']:p['opportunity'] for p in self.obj('core',i)['pairs']}
            for op in cohort['opportunities']:
                pid=op['pair_id']
                self.assertEqual({k:v for k,v in op.items() if k!='pair_id'},original[pid])

    def test_symlink_receipt_store_object(self):
        store=ReceiptStore(self.output);key=store.put({'test':1})
        target=self.output/(key+'.json');other=self.base/'other.json'
        target.rename(other);target.symlink_to(other)
        with self.assertRaisesRegex(BoundaryError,'SYMLINK_OBJECT'):store.put({'test':1})

    def test_prior_harness_output_reused_without_execution(self):
        _,summary=self.execute()
        self.assertEqual(summary['prior_harness']['status'],'REUSED_READ_ONLY_NOT_REVALIDATED')
        self.assertEqual(summary['prior_harness']['current_contract_coverage'],
                         'NOT_CONNECTED_OLD_CORE216_FACTORY209')

    def test_prior_harness_drift(self):
        self.manifest['prior_harness']['file_sha256']='f'*64
        self.fails('PRIOR_HARNESS_SOURCE_DRIFT')

    def test_missing_output_adapter(self):
        self.manifest['datasets'][0]['objects'].pop('vault')
        self.fails('MISSING_ADAPTER_OBJECT')

    def test_manifest_payload_field_refused(self):
        self.manifest['private_payload']={'unexpected':1}
        self.fails('UNEXPECTED_MANIFEST_FIELD')
