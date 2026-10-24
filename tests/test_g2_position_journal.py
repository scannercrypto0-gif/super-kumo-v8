import sys,unittest,tempfile
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
if __name__=='__main__':unittest.main()
