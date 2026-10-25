"""Nonduplicate regressions for compatible #92 journal hardening."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from aql.observation.position_journal import DurablePositionJournal, JournalIntegrityError, _exclusive_writer
from aql.observation.positions import PositionEvent, PositionContractError, PositionLedger


class HardeningTests(unittest.TestCase):
    def event(self, key='open', kind='opened', t=0):
        return PositionEvent('p', key, kind, t, t, 'offline')

    def test_verified_replay_is_single_candidate_and_public_mutation_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events'; j=DurablePositionJournal(p);j.append(self.event())
            j.ledger.events.clear();j.ledger.positions.clear()
            calls=[]; original=PositionLedger.append
            def counted(ledger, event):
                calls.append(event.event_id);return original(ledger,event)
            with patch.object(PositionLedger,'append',counted):j.append(self.event('quote','quote',1))
            self.assertEqual(calls,['open','quote'])
            self.assertEqual(len(DurablePositionJournal(p).ledger.events),2)

    def test_duplicate_json_field_rejected_without_changing_hash_algorithm(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events';j=DurablePositionJournal(p);j.append(self.event())
            raw=p.read_bytes();p.write_bytes(raw.replace(b'{"digest":',b'{"digest":"ignored","digest":',1))
            before=p.read_bytes()
            with self.assertRaises(JournalIntegrityError):DurablePositionJournal(p)
            self.assertEqual(p.read_bytes(),before)

    def test_identical_bytes_at_replaced_path_rejected_by_existing_writer(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events';j=DurablePositionJournal(p);j.append(self.event())
            saved=p.read_bytes();p.rename(Path(d)/'original');p.write_bytes(saved)
            with self.assertRaises(JournalIntegrityError):j.append(self.event('q','quote',1))
            self.assertEqual(p.read_bytes(),saved)

    def test_replaced_lock_never_deleted_by_original_owner(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events';lock=Path(str(p)+'.writer.lock')
            with self.assertRaises(JournalIntegrityError):
                with _exclusive_writer(p):
                    lock.rename(Path(d)/'preserved-original-lock')
                    lock.write_text('replacement-owner')
            self.assertEqual(lock.read_text(),'replacement-owner')
            self.assertTrue((Path(d)/'preserved-original-lock').exists())

    def test_mutable_identity_or_reason_rejected(self):
        for changes in ({'position_id':[]},{'source':['mutable']},{'event_id':1},{'reason':['mutable']}):
            with self.subTest(changes=changes),self.assertRaises(PositionContractError):
                PositionEvent(**{**self.event().__dict__,**changes})

    def test_symlink_reparse_metadata_fails_closed_without_privilege_change(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events';p.touch();original=Path.lstat
            def reparse(path,*a,**kw):
                if path==p:
                    from types import SimpleNamespace
                    return SimpleNamespace(st_file_attributes=0x400)
                return original(path,*a,**kw)
            with patch.object(Path,'lstat',reparse):
                with self.assertRaises(JournalIntegrityError):DurablePositionJournal(p)


if __name__ == '__main__':unittest.main()
