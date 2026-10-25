"""Regression for default FrozenAttemptWriter ledger-policy enrollment."""
import tempfile
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sqlite3
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_attempt_writer import FrozenAttemptWriter
from research_wp_r0.test_frozen_attempt_writer import plan


def event(**changes):
    return {**dict(state='PENDING', family_id='Family1', candidate_id='Candidate1',
                   input_digest='f'*64, strategy_digest='a'*64), **changes}


class DefaultAdmissionTests(unittest.TestCase):
    def dump(self,path):
        with closing(sqlite3.connect(path)) as db:
            return '\n'.join(db.iterdump())

    def test_default_writer_seals_ledger_before_any_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=AttemptLedger(Path(d)/'ledger.sqlite');raw,digest=plan()
            FrozenAttemptWriter(ledger,raw,digest)
            with closing(ledger._connect()) as db:
                row=db.execute('SELECT plan_digest,plan_bytes FROM frozen_plan_policy').fetchone()
                self.assertIsNotNone(row)
                self.assertEqual((row[0],bytes(row[1])),(digest,raw))
            self.assertEqual(ledger.snapshot()[0],[])

    def test_direct_permissive_callback_cannot_bypass_default_writer(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=AttemptLedger(Path(d)/'ledger.sqlite');raw,digest=plan()
            FrozenAttemptWriter(ledger,raw,digest)
            with self.assertRaises(ValueError):
                ledger.record_attempt(event(candidate_id='Unplanned'), admission=lambda *_:None)
            self.assertEqual(ledger.snapshot()[0],[])

    def test_reopen_same_plan_idempotent_and_callback_not_membership_authority(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);raw,digest=plan()
            w=FrozenAttemptWriter(l,raw,digest);receipt=w.record_attempt(event())
            before=self.dump(path)
            reopened=AttemptLedger(path);FrozenAttemptWriter(reopened,raw,digest)
            self.assertEqual(self.dump(path),before)
            self.assertEqual(reopened.record_attempt(event(),admission=lambda *_:None),receipt)
            for changes in ({'candidate_id':'Unplanned'},{'strategy_digest':'b'*64},{'family_id':'Other'}):
                with self.subTest(changes=changes),self.assertRaises(ValueError):
                    reopened.record_attempt(event(**changes),admission=lambda *_:None)
            self.assertEqual(self.dump(path),before)

    def test_stale_unsealed_handle_and_mutable_writer_cache_cannot_bypass(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';first=AttemptLedger(path);stale=AttemptLedger(path)
            raw,digest=plan();writer=FrozenAttemptWriter(first,raw,digest)
            writer.allowed['Unplanned']='a'*64;stale.require_admission=False
            with self.assertRaises(ValueError):stale.record_attempt(event(candidate_id='Unplanned'),admission=lambda *_:None)
            with self.assertRaises(ValueError):writer.record_attempt(event(candidate_id='Unplanned'))
            self.assertEqual(first.snapshot()[0],[])

    def test_spawned_direct_bypass_rejected_then_planned_receipt_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);raw,digest=plan()
            FrozenAttemptWriter(l,raw,digest)
            code='''import sys
from research_wp_r0.attempt_ledger import AttemptLedger
e=dict(state='PENDING',family_id='Family1',candidate_id='Unplanned',input_digest='f'*64,strategy_digest='a'*64)
l=AttemptLedger(sys.argv[1])
try:l.record_attempt(e,admission=lambda *_:None)
except ValueError:pass
else:raise AssertionError('bypass admitted')
e['candidate_id']='Candidate1';l.record_attempt(e,admission=lambda *_:None)
'''
            child=subprocess.run([sys.executable,'-B','-c',code,str(path)],cwd=Path(__file__).resolve().parents[1],capture_output=True,timeout=15)
            self.assertEqual(child.returncode,0,child.stderr)
            self.assertEqual(l.snapshot()[0],[event()])

    def test_invalid_raw_digest_or_different_plan_no_policy_or_receipt_change(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);raw,digest=plan()
            before=self.dump(path)
            for bad_raw,bad_digest in ((raw,'0'*64),(raw+b' ',digest),(b'{"bad":1}',digest),(raw,None)):
                with self.subTest(raw=bad_raw),self.assertRaises(ValueError):FrozenAttemptWriter(l,bad_raw,bad_digest)
                self.assertEqual(self.dump(path),before)
            FrozenAttemptWriter(l,raw,digest);before=self.dump(path)
            from research_wp_r0.strategy_definition import canonical,digest as hash_plan
            changed=json.loads(raw);changed['cost_model']['fee_bps']=11
            with self.assertRaises(ValueError):FrozenAttemptWriter(l,canonical(changed),hash_plan(changed))
            self.assertEqual(self.dump(path),before)

    def test_nonempty_unsealed_ledger_rejected_even_for_planned_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);l.record_attempt(event())
            before=self.dump(path);raw,digest=plan()
            with self.assertRaisesRegex(ValueError,'empty ledger'):FrozenAttemptWriter(l,raw,digest)
            self.assertEqual(self.dump(path),before)

    def test_missing_policy_row_or_table_not_repaired_on_bind_or_reopen(self):
        for sql in ('DELETE FROM ledger_policy','DROP TABLE frozen_plan_policy'):
            with self.subTest(sql=sql),tempfile.TemporaryDirectory() as d:
                path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);raw,digest=plan()
                with closing(sqlite3.connect(path)) as db:db.execute(sql);db.commit()
                before=self.dump(path)
                with self.assertRaises((ValueError,sqlite3.DatabaseError)):FrozenAttemptWriter(l,raw,digest)
                with self.assertRaises((ValueError,sqlite3.DatabaseError)):AttemptLedger(path)
                self.assertEqual(self.dump(path),before)

    def test_legacy_delete_mode_database_not_migrated_or_written(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'legacy.sqlite'
            with closing(sqlite3.connect(path)) as db:db.execute('CREATE TABLE legacy(value)');db.commit()
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'no automatic migration'):AttemptLedger(path)
            self.assertEqual(path.read_bytes(),before)

    def test_tampered_sealed_plan_or_disabled_policy_rejects_bind_without_repair(self):
        for sql in ("UPDATE frozen_plan_policy SET plan_digest='corrupt'",'UPDATE ledger_policy SET require_admission=0'):
            with self.subTest(sql=sql),tempfile.TemporaryDirectory() as d:
                path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);raw,digest=plan();FrozenAttemptWriter(l,raw,digest)
                with closing(sqlite3.connect(path)) as db:db.execute(sql);db.commit()
                before=self.dump(path)
                with self.assertRaises(ValueError):FrozenAttemptWriter(l,raw,digest)
                with self.assertRaises(ValueError):l.record_attempt(event(),admission=lambda *_:None)
                self.assertEqual(self.dump(path),before)

    def test_binding_race_waits_out_direct_writer_then_rejects_unplanned(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);stale=AttemptLedger(path);raw,digest=plan()
            acquired,release=threading.Event(),threading.Event();original=l._read
            def paused(db):
                result=original(db);acquired.set()
                if not release.wait(5):raise RuntimeError('test fence expired')
                return result
            l._read=paused
            with ThreadPoolExecutor(max_workers=2) as pool:
                binding=pool.submit(l.bind_frozen_plan,raw,digest);self.assertTrue(acquired.wait(5))
                attempted=threading.Event()
                def direct():attempted.set();return stale.record_attempt(event(candidate_id='Unplanned'),admission=lambda *_:None)
                attack=pool.submit(direct);self.assertTrue(attempted.wait(5));release.set();binding.result(timeout=10)
                with self.assertRaises(ValueError):attack.result(timeout=10)
            l._read=original;self.assertEqual(l.snapshot()[0],[])

    def test_concurrent_different_plans_only_one_enrollment_and_no_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';AttemptLedger(path);raw,digest=plan()
            from research_wp_r0.strategy_definition import canonical,digest as hash_plan
            other=json.loads(raw);other['selection_rule']={'objective':'OTHER'};other_raw=canonical(other)
            barrier=threading.Barrier(2)
            def bind(pair):
                l=AttemptLedger(path);barrier.wait(5)
                try:l.bind_frozen_plan(*pair);return 'bound'
                except ValueError:return 'rejected'
            with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(bind,[(raw,digest),(other_raw,hash_plan(other))]))
            self.assertEqual(sorted(outcomes),['bound','rejected'])
            self.assertEqual(AttemptLedger(path).snapshot()[0],[])

    def test_actual_sqlite_abort_rolls_back_both_enrollment_fields(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);raw,digest=plan()
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TRIGGER fail_policy BEFORE UPDATE ON ledger_policy BEGIN SELECT RAISE(ABORT,'injected failure'); END");db.commit()
            before=self.dump(path)
            with self.assertRaises(sqlite3.DatabaseError):FrozenAttemptWriter(l,raw,digest)
            self.assertEqual(self.dump(path),before)

    def test_process_exit_during_enrollment_leaves_no_partial_plan_or_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);before=self.dump(path)
            code='''import os,sys
from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.test_frozen_attempt_writer import plan
l=AttemptLedger(sys.argv[1]);original=l._connect
class Crash:
 def __init__(self,db):self.db=db
 def __getattr__(self,key):return getattr(self.db,key)
 def execute(self,sql,*args):
  if sql.startswith('UPDATE ledger_policy'):os._exit(87)
  return self.db.execute(sql,*args)
l._connect=lambda:Crash(original())
l.bind_frozen_plan(*plan())
'''
            child=subprocess.run([sys.executable,'-B','-c',code,str(path)],cwd=Path(__file__).resolve().parents[1],capture_output=True,timeout=15)
            self.assertEqual(child.returncode,87,child.stderr)
            self.assertEqual(self.dump(path),before)
            raw,digest=plan();FrozenAttemptWriter(AttemptLedger(path),raw,digest)
            self.assertEqual(l.snapshot()[0],[])

    def test_callback_failure_no_partial_receipt_after_successful_enrollment(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path);raw,digest=plan();FrozenAttemptWriter(l,raw,digest)
            before=self.dump(path)
            def failed(*_):raise RuntimeError('injected callback failure')
            with self.assertRaises(RuntimeError):l.record_attempt(event(),admission=failed)
            self.assertEqual(self.dump(path),before)

    def test_missing_seal_on_protected_ledger_cannot_use_callback_as_authority(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ledger.sqlite';l=AttemptLedger(path,require_admission=True)
            with self.assertRaises(ValueError):l.record_attempt(event(),admission=lambda *_:None)
            raw,digest=plan();FrozenAttemptWriter(l,raw,digest)
            with closing(sqlite3.connect(path)) as db:db.execute('DELETE FROM frozen_plan_policy');db.commit()
            before=self.dump(path)
            with self.assertRaises(ValueError):AttemptLedger(path).record_attempt(event(),admission=lambda *_:None)
            self.assertEqual(self.dump(path),before)

    def test_same_principal_local_export_is_not_independent_custody(self):
        from research_wp_r0.factory_custody_export import export_custody_envelope, verify_exported_custody
        from research_wp_r0.factory_custody_envelope import custody_envelope
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'synthetic-anchor.json';checkpoint=(0,'0'*64)
            export_custody_envelope(path,plan_digest='a'*64,ledger_checkpoint=checkpoint)
            path.write_bytes(custody_envelope(plan_digest='b'*64,ledger_checkpoint=checkpoint))
            with self.assertRaises(ValueError):verify_exported_custody(path,plan_digest='a'*64,ledger_checkpoint=checkpoint)
            self.assertEqual(verify_exported_custody(path,plan_digest='b'*64,ledger_checkpoint=checkpoint)['plan_digest'],'b'*64)


if __name__=='__main__':unittest.main()
