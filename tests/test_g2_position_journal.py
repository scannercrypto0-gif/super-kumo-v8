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
if __name__=='__main__':unittest.main()
