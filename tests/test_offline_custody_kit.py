"""Synthetic temporary bundles only; no owner drives/custody attestation."""
from contextlib import closing, redirect_stdout, redirect_stderr
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import offline_custody_kit as kit
from research_wp_r0.custody_manifest_builder import build_custody_manifest


class OfflineCustodyKitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root/'source'; self.source.mkdir()
        (self.source/'sample.bin').write_bytes(b'SYNTHETIC TEST ONLY')
        self.target = self.root/'restored'; self.anchor = self.root/'retained.sha256'

    def finalize(self):
        result = build_custody_manifest(self.source)
        self.anchor.write_text(result['manifest_sha256'], encoding='ascii')
        return result

    def restore(self, **kw):
        return kit.run('restore', self.source, anchor=self.anchor, target=self.target, **kw)

    def test_manifest_dry_run_no_write_and_explicit_execute_reuses_builder(self):
        before = list(self.source.iterdir())
        report = kit.run('manifest', self.source)
        self.assertEqual(report['mode'], 'DRY_RUN'); self.assertEqual(list(self.source.iterdir()), before)
        with self.assertRaises(ValueError):kit.run('manifest', self.source, execute=True)
        built = kit.run('manifest', self.source, execute=True, quiescent=True)
        self.assertFalse(built['independent_custody_verified'])
        with self.assertRaises(FileExistsError):kit.run('manifest', self.source, execute=True, quiescent=True)

    def test_restore_dry_run_and_cli_report_argument_do_not_create_anything(self):
        self.finalize(); report_path = self.root/'report.json'
        report = self.restore()
        self.assertTrue(report['content_verified']); self.assertFalse(self.target.exists())
        with redirect_stdout(io.StringIO()):
            code = kit.main(['restore','--source',str(self.source),'--anchor',str(self.anchor),
                             '--target',str(self.target),'--report',str(report_path)])
        self.assertEqual(code, 0); self.assertFalse(report_path.exists()); self.assertFalse(self.target.exists())

    def test_real_exclusive_restore_verifies_all_bytes_and_preserves_source_anchor(self):
        nested=self.source/'nested';nested.mkdir();(nested/'data.json').write_text('{"class":"synthetic"}')
        expected=self.finalize();before={p.relative_to(self.source):p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        anchor_bytes=self.anchor.read_bytes();report=self.restore(execute=True,quiescent=True)
        self.assertEqual(report['restored_content']['manifest_sha256'],expected['manifest_sha256'])
        self.assertEqual({p.relative_to(self.target):p.read_bytes() for p in self.target.rglob('*') if p.is_file()},before)
        self.assertEqual(self.anchor.read_bytes(),anchor_bytes)
        self.assertFalse(report['independent_custody_verified'])
        self.assertEqual(report['research_evaluation_replay'],'NOT_PERFORMED_NO_EVALUATOR')
        with self.assertRaises(ValueError):self.restore(execute=True,quiescent=True)

    def test_corrupt_missing_extra_or_wrong_anchor_fail_before_target_publication(self):
        for mode in ('corrupt','missing','extra','wrong_anchor'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                source=Path(d)/'s';source.mkdir();(source/'data').write_bytes(b'synthetic')
                digest=build_custody_manifest(source)['manifest_sha256'];anchor=Path(d)/'a';anchor.write_text(digest)
                if mode=='corrupt':(source/'data').write_bytes(b'changed')
                if mode=='missing':(source/'data').unlink()
                if mode=='extra':(source/'extra').write_bytes(b'extra')
                if mode=='wrong_anchor':anchor.write_text('f'*64)
                with self.assertRaises((ValueError,OSError)):kit.run('restore',source,anchor=anchor,target=Path(d)/'r',execute=True,quiescent=True)
                self.assertFalse((Path(d)/'r').exists())

    def test_missing_or_nested_anchor_and_overlap_rejected(self):
        self.finalize()
        for anchor,target in ((self.source/kit.MANIFEST,self.target),(self.anchor,self.source/'r'),
                              (self.anchor,self.root),(self.root/'absent',self.target)):
            with self.subTest(anchor=anchor,target=target),self.assertRaises((ValueError,OSError)):
                kit.run('restore',self.source,anchor=anchor,target=target)

    def test_interrupted_copy_retains_partial_target_and_originals(self):
        self.finalize();before=(self.source/'sample.bin').read_bytes()
        def interrupted(source,target):target.write_bytes(b'partial');raise OSError('injected interruption')
        with patch.object(kit,'copy_file',interrupted),self.assertRaises(OSError):self.restore(execute=True,quiescent=True)
        self.assertTrue(self.target.exists());self.assertTrue(any(self.target.iterdir()))
        self.assertEqual((self.source/'sample.bin').read_bytes(),before)
        with self.assertRaises(ValueError):self.restore(execute=True,quiescent=True)

    def test_drift_during_copy_and_anchor_replacement_reject_no_acceptance(self):
        self.finalize();original=kit.copy_file
        def changed(source,target):
            original(source,target);self.anchor.write_text('a'*64)
        with patch.object(kit,'copy_file',changed),self.assertRaises(ValueError):self.restore(execute=True,quiescent=True)
        self.assertTrue(self.target.exists())

    def test_windows_aliases_traversal_bounds_and_reparse_metadata(self):
        for name in ('../escape','/absolute','CON.txt','folder/COM1','bad:name','trailing.','trailing ','a\\b'):
            with self.subTest(name=name),self.assertRaises(ValueError):kit.safe_name(name)
        with patch.object(kit,'MAX_FILE',1),self.assertRaises(ValueError):kit.inventory(self.source)
        original=Path.lstat
        def reparse(path,*a,**k):
            if path==self.source:
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=original(path,*a,**k).st_mode,st_file_attributes=0x400)
            return original(path,*a,**k)
        with patch.object(Path,'lstat',reparse),self.assertRaises(ValueError):kit.inventory(self.source)

    def test_report_is_exclusive_outside_bundles_and_never_custody_attestation(self):
        self.finalize();path=self.root/'report.json'
        args=['restore','--source',str(self.source),'--anchor',str(self.anchor),'--target',str(self.target),
              '--execute','--quiescent','--report',str(path)]
        with redirect_stdout(io.StringIO()):self.assertEqual(kit.main(args),0)
        report=json.loads(path.read_text());self.assertFalse(report['independent_custody_verified'])
        self.assertEqual(report['git_repository_recovery'],'NOT_TESTED_FILE_HASHES_ARE_NOT_GIT_FSCK')
        with redirect_stderr(io.StringIO()):self.assertEqual(kit.main(args),1)
        self.assertEqual(json.loads(path.read_text()),report)

    def test_no_bundle_code_execution(self):
        (self.source/'replay.py').write_text("raise RuntimeError('NEVER EXECUTE BUNDLE CODE')")
        self.finalize();self.assertEqual(self.restore(execute=True,quiescent=True)['receipt_replay']['status'],'NOT_REQUESTED')

    def ledger_fixture(self):
        from research_wp_r0.attempt_ledger import AttemptLedger
        from research_wp_r0.frozen_attempt_writer import FrozenAttemptWriter
        from research_wp_r0.frozen_research_plan import commit_research_plan
        raw,digest=commit_research_plan('SyntheticFamily',[('Candidate','a'*64)],protocol_digest='b'*64,
            dataset_digest='c'*64,split_digest='d'*64,baseline_digest='e'*64,metrics=['test'],
            selection_rule={'synthetic':True},cost_model={'synthetic':True})
        ledger=AttemptLedger(self.source/'receipts.sqlite');writer=FrozenAttemptWriter(ledger,raw,digest)
        checkpoint=writer.record_attempt(dict(state='PENDING',family_id='SyntheticFamily',candidate_id='Candidate',
                                             input_digest='f'*64,strategy_digest='a'*64))
        self.finalize();return digest,checkpoint

    def test_observed_restored_receipt_replay_is_read_only_not_research_evaluation(self):
        digest,checkpoint=self.ledger_fixture()
        result=self.restore(execute=True,quiescent=True,ledger='receipts.sqlite',plan_digest=digest,checkpoint=checkpoint)
        self.assertEqual(result['receipt_replay']['events'],1)
        self.assertEqual(result['receipt_replay']['states'],{'PENDING':1})
        self.assertEqual(result['receipt_replay']['evaluation_status'],'NOT_EVALUATED')
        self.assertEqual(result['receipt_replay']['checkpoint'],list(checkpoint))
        self.assertFalse(result['independent_custody_verified'])
        self.assertEqual((self.source/'receipts.sqlite').read_bytes(),(self.target/'receipts.sqlite').read_bytes())

    def test_missing_wrong_replay_commitments_and_sidecars_rejected(self):
        digest,checkpoint=self.ledger_fixture()
        with self.assertRaises(ValueError):self.restore(ledger='receipts.sqlite')
        with self.assertRaises(ValueError):kit.receipt_replay(self.source,'receipts.sqlite','0'*64,checkpoint)
        with self.assertRaises(ValueError):kit.receipt_replay(self.source,'receipts.sqlite',digest,(1,'0'*64))
        (self.source/'receipts.sqlite-wal').write_bytes(b'not a finalized standalone snapshot')
        with self.assertRaises(ValueError):kit.receipt_replay(self.source,'receipts.sqlite',digest,checkpoint)


if __name__=='__main__':unittest.main()
