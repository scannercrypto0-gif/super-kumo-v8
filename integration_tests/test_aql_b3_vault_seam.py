"""Only B3 new API/readback/consumer path; original pinned B2 bytes are inputs.

No B1/B2 test suite, original fixture builder, market download or True witness.
"""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from integration_tests.aql_b3_vault_seam import pinned_modules, project_readback, run
from tools.raw_vault_offline.b3_handoff import (
    admit_core_container, canonical, sha, verify_local_readback,
)
from tools.raw_vault_offline.schema import ChecksumMismatch


class B3ActualVaultSeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=Path(os.environ['AQL_B3_CORE_JSON']).read_bytes()
        cls.modules=pinned_modules(os.environ['AQL_B3_CORE_ROOT'],os.environ['AQL_B3_FACTORY_ROOT'])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'vault'
        self.receipt,_,_=admit_core_container(self.raw,self.root)

    def test_actual_admit_read_manifest_to_real_factory_and_replay(self):
        first=Path(self.tmp.name)/'first'; second=Path(self.tmp.name)/'second'
        r=run(self.raw,self.root,first,self.modules)
        run(self.raw,self.root,second,self.modules)
        self.assertEqual(r['capture_statuses'],{'UNVERIFIED':4})
        self.assertEqual(r['outcome_rows_6n'],12)
        for name in ('system-integrity.json','readback-receipt.json','parent-manifest.jsonl','original-core-container.json'):
            self.assertEqual((first/name).read_bytes(),(second/name).read_bytes())
        self.assertEqual(verify_local_readback(self.root,self.receipt),self.raw)

    def test_changed_input_bytes_refused_before_admission(self):
        with self.assertRaisesRegex(ValueError,'PINNED_BYTES_CHANGED'):
            admit_core_container(self.raw+b' ',Path(self.tmp.name)/'changed')

    def test_altered_stored_parent_is_not_readback(self):
        digest=self.receipt['object_content_sha256']
        (self.root/'objects'/digest[:2]/digest[2:]).write_bytes(b'forged')
        with self.assertRaises(ChecksumMismatch):
            project_readback(self.root,self.receipt,self.modules)

    def test_missing_or_altered_exact_manifest_denied(self):
        path=self.root/'manifest.jsonl'; data=path.read_bytes()
        path.write_bytes(data+b'\n')
        with self.assertRaisesRegex(ValueError,'MANIFEST_BYTES_CHANGED'):
            verify_local_readback(self.root,self.receipt)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            verify_local_readback(self.root,self.receipt)

    def test_forged_rehashed_external_authority_refused(self):
        receipt=copy.deepcopy(self.receipt)
        receipt['external_issuer_custody_clock_proven']=True
        receipt['receipt_sha256']=sha(canonical({k:v for k,v in receipt.items() if k!='receipt_sha256'}))
        with self.assertRaisesRegex(ValueError,'CANNOT_ASSERT_EXTERNAL'):
            verify_local_readback(self.root,receipt)

    def test_missing_shadow_preserves_schedule_and_horizons(self):
        def mutate(rows,validator):
            rows.pop(1)
        result=project_readback(self.root,self.receipt,self.modules,mutate)
        self.assertEqual(result['capture_status_counts'],{'MISSING_CAPTURE':1,'UNVERIFIED':3})
        self.assertEqual(len(result['outcomes']),12)

    def test_wrong_source_vintage_stays_quarantined_after_rehash(self):
        def mutate(rows,validator):
            rows[0]['source_version']='other-vintage'
            rows[0]['f1_record_sha256']=validator.hash_f1(rows[0])
        result=project_readback(self.root,self.receipt,self.modules,mutate)
        self.assertEqual(result['capture_status_counts'],{'QUARANTINED':1,'UNVERIFIED':3})

    def test_late_original_availability_stays_quarantined_after_rehash(self):
        def mutate(rows,validator):
            rows[0]['source_available_at_ms']=rows[0]['decision_cutoff_ms']+1
            rows[0]['f1_record_sha256']=validator.hash_f1(rows[0])
        result=project_readback(self.root,self.receipt,self.modules,mutate)
        self.assertEqual(result['capture_status_counts'],{'QUARANTINED':1,'UNVERIFIED':3})

    def test_changed_original_cutoff_does_not_rewrite_schedule(self):
        def mutate(rows,validator):
            rows[0]['decision_cutoff_ms']+=900000
            rows[0]['f1_record_sha256']=validator.hash_f1(rows[0])
        result=project_readback(self.root,self.receipt,self.modules,mutate)
        self.assertEqual(result['capture_status_counts'],{'QUARANTINED':1,'UNVERIFIED':3})

    def test_core_parent_witness_missing_forged_or_late_never_certifies_container(self):
        _,validator,parent=self.modules
        record=json.loads(self.raw)['original_candidates_test_only'][0]
        manifest=(self.root/'manifest.jsonl').read_bytes()
        binding=dict(schema_version='aql.f1-raw-parent-binding.v1',
            parent_source_id='TEST_ONLY_CAPTURE_CONTAINER_NOT_MARKET',parent_source_version='B2',
            parent_source_bytes_sha256=sha(self.raw),parent_manifest_sha256=sha(manifest),
            parent_receipt_ref='LOCAL_ONLY_NOT_ISSUER')
        for field in ('source_id','source_version','source_bytes_sha256',
                      'correction_generation','correction_lineage_sha256'):
            binding[field]=record[field]
        for field in ('source_published_at_ms','correction_published_at_ms','source_finalized_at_ms'):
            binding[field]=record['decision_cutoff_ms']
        def check(witness):
            binding['parent_binding_sha256']=validator.digest({k:v for k,v in binding.items() if k!='parent_binding_sha256'})
            return parent.validate_parent_binding(record,binding,parent_manifest_bytes=manifest,
                parent_bytes=self.raw,parent_witness=witness)
        self.assertFalse(check(None))
        self.assertFalse(check({'verified':True}))  # untrusted flag is not a witness
        binding['source_published_at_ms']=record['decision_cutoff_ms']+1
        calls=[]
        self.assertFalse(check(lambda _:calls.append('called') or False))
        self.assertEqual(calls,[])  # source-clock check runs before external callback


if __name__=='__main__':
    unittest.main()
