import sys,unittest,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from aql.observation.positions import PositionEvent
from aql.observation.position_journal import DurablePositionJournal,JournalIntegrityError

class JournalTests(unittest.TestCase):
    def e(self,key,kind,ms,reason=None):
        return PositionEvent('p1',key,kind,ms,ms,'offline',reason=reason)
    def test_restart_keeps_year_long_position_open(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            j=DurablePositionJournal(p);j.append(self.e('start','opened',0))
            self.assertEqual(DurablePositionJournal(p).ledger.status('p1',366*86400000),'open')
    def test_explicit_close_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            j=DurablePositionJournal(p);j.append(self.e('start','opened',0))
            j.append(self.e('exit','closed',8*86400000,'exit'))
            self.assertEqual(DurablePositionJournal(p).ledger.status('p1',9*86400000),'closed')
    def test_duplicate_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl';j=DurablePositionJournal(p);e=self.e('start','opened',0)
            self.assertEqual(j.append(e),'inserted');before=p.read_bytes()
            self.assertEqual(j.append(e),'duplicate');self.assertEqual(p.read_bytes(),before)
    def test_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl';j=DurablePositionJournal(p);j.append(self.e('start','opened',0))
            p.write_bytes(p.read_bytes().replace(b'opened',b'closed'))
            with self.assertRaises(JournalIntegrityError): DurablePositionJournal(p)
    def test_torn_tail_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl';j=DurablePositionJournal(p);j.append(self.e('start','opened',0))
            with p.open('ab') as f:f.write(b'{"partial":')
            with self.assertRaises(JournalIntegrityError): DurablePositionJournal(p)
    def test_stale_writer_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            first=DurablePositionJournal(p)
            second=DurablePositionJournal(p)
            first.append(self.e('start','opened',0))
            with self.assertRaises(JournalIntegrityError):
                second.append(self.e('other','opened',1))
            self.assertEqual(DurablePositionJournal(p).ledger.status('p1',10),'open')
    def test_same_size_tamper_rejected_before_append(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            j=DurablePositionJournal(p)
            j.append(self.e('start','opened',0))
            data=p.read_bytes()
            self.assertIn(b'opened',data)
            p.write_bytes(data.replace(b'opened',b'closed'))
            with self.assertRaises(JournalIntegrityError):
                j.append(self.e('later','closed',10,'exit'))
    def test_existing_writer_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            lock=p.with_name(p.name+'.writer.lock')
            lock.write_text('other-process')
            with self.assertRaises(JournalIntegrityError):
                DurablePositionJournal(p).append(self.e('start','opened',0))
            self.assertFalse(p.exists())
            self.assertTrue(lock.exists())

    def test_writer_lock_released_after_append(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            DurablePositionJournal(p).append(self.e('start','opened',0))
            self.assertFalse(p.with_name(p.name+'.writer.lock').exists())
            self.assertEqual(DurablePositionJournal(p).ledger.status('p1',1),'open')
    def test_independent_process_respects_lock(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            lock=p.with_name(p.name+'.writer.lock')
            lock.write_text('owner-process')
            child_code = (
                "import sys; from pathlib import Path; "
                "sys.path.insert(0,sys.argv[2]); "
                "from aql.observation.positions import PositionEvent; "
                "from aql.observation.position_journal import DurablePositionJournal,JournalIntegrityError; "
                "p=Path(sys.argv[1]); "
                "j=DurablePositionJournal(p); "
                "e=PositionEvent('p1','open','opened',0,0,'offline'); "
                "j.append(e)"
            )
            result=subprocess.run(
                [sys.executable,'-c',child_code,str(p),
                 str(Path(__file__).resolve().parents[1]/'src')],
                capture_output=True,text=True,timeout=15)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('writer lock held',result.stderr)
            self.assertFalse(p.exists())
            lock.unlink()
            DurablePositionJournal(p).append(self.e('start','opened',0))
            self.assertEqual(DurablePositionJournal(p).ledger.status('p1',1),'open')
    def test_crashed_process_orphan_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            child_code=(
                "import sys,os; from pathlib import Path; "
                "sys.path.insert(0,sys.argv[2]); "
                "from aql.observation.position_journal import _exclusive_writer; "
                "p=Path(sys.argv[1]); "
                "with_open='unused'; "
                "lock=p.with_name(p.name+'.writer.lock'); "
                "fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); "
                "os.write(fd,b'crashed'); os.fsync(fd); os._exit(17)"
            )
            result=subprocess.run(
                [sys.executable,'-c',child_code,str(p),
                 str(Path(__file__).resolve().parents[1]/'src')],
                capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,17)
            lock=p.with_name(p.name+'.writer.lock')
            self.assertTrue(lock.exists())
            with self.assertRaises(JournalIntegrityError):
                DurablePositionJournal(p).append(self.e('start','opened',0))
            self.assertFalse(p.exists())
    def test_partial_event_after_valid_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            j=DurablePositionJournal(p)
            j.append(self.e('start','opened',0))
            intact=p.read_bytes()
            with p.open('ab') as handle:
                handle.write(b'{"previous":"incomplete"')
                handle.flush()
            with self.assertRaises(JournalIntegrityError):
                DurablePositionJournal(p)
            self.assertEqual(p.read_bytes()[:len(intact)],intact)
            self.assertEqual(len(p.read_bytes()),len(intact)+len(b'{"previous":"incomplete"'))
    def test_partial_event_does_not_silently_repair_on_append(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            j=DurablePositionJournal(p)
            j.append(self.e('start','opened',0))
            with p.open('ab') as handle:
                handle.write(b'{"partial":')
            before=p.read_bytes()
            with self.assertRaises(JournalIntegrityError):
                j.append(self.e('exit','closed',10,'exit'))
            self.assertEqual(p.read_bytes(),before)
    def test_lock_released_after_validation_error(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            j=DurablePositionJournal(p)
            with self.assertRaises(Exception):
                j.append(self.e('close','closed',1,'exit'))
            self.assertFalse(p.with_name(p.name+'.writer.lock').exists())
            self.assertFalse(p.exists())
            self.assertEqual(j.append(self.e('start','opened',0)),'inserted')
    def test_reopen_after_other_writer_preserves_history(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            stale=DurablePositionJournal(p)
            DurablePositionJournal(p).append(self.e('start','opened',0))
            with self.assertRaises(JournalIntegrityError):
                stale.append(self.e('close','closed',10,'exit'))
            fresh=DurablePositionJournal(p)
            self.assertEqual(fresh.append(self.e('close','closed',10,'exit')),'inserted')
            self.assertEqual(DurablePositionJournal(p).ledger.status('p1',11),'closed')
    def test_deleted_journal_rejected_by_existing_writer(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            j=DurablePositionJournal(p)
            j.append(self.e('start','opened',0))
            p.unlink()
            with self.assertRaises(JournalIntegrityError):
                j.append(self.e('exit','closed',10,'exit'))
            self.assertFalse(p.exists())
    def test_empty_journal_first_event(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl'
            p.touch()
            j=DurablePositionJournal(p)
            self.assertEqual(j.append(self.e('start','opened',0)),'inserted')
            self.assertEqual(DurablePositionJournal(p).ledger.status('p1',1),'open')
if __name__=='__main__':unittest.main()
