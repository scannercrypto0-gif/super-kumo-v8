"""Isolated operator drills. No automatic orphan recovery or production custody."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from aql.observation.position_journal import DurablePositionJournal, JournalIntegrityError, _exclusive_writer
from aql.observation.positions import PositionEvent

SRC = str(Path(__file__).resolve().parents[1]/'src')


def inventory(path):
    raw = path.read_bytes()
    replay = DurablePositionJournal(path)
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'events': len(replay.ledger.events), 'tail': replay._tail,
            'positions': replay.ledger.positions}


def verified_copy(source, destination, expected):
    """Test-only operator action after external fencing, never overwrites."""
    if expected is None or inventory(source) != expected:
        raise JournalIntegrityError('missing or conflicting independently retained evidence')
    with _exclusive_writer(source):
        if inventory(source) != expected:
            raise JournalIntegrityError('source changed before lease')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise JournalIntegrityError('copy bytes differ from expected commitment')
        with destination.open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        if inventory(destination) != expected:
            raise JournalIntegrityError('independent restore reconciliation failed')
    return inventory(destination)


class OperatorRecoveryTests(unittest.TestCase):
    def seed(self, root):
        p = root/'primary.jsonl'; j = DurablePositionJournal(p)
        j.append(PositionEvent('p', 'open', 'opened', 1, 2, 'offline'))
        j.append(PositionEvent('p', 'close', 'closed', 3, 4, 'offline', reason='explicit'))
        return p

    def test_coherent_quiescent_backup_independent_restore_and_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); primary = self.seed(root); expected = inventory(primary)
            # Independent expected inventory retained before backup, not derived from its bytes.
            (root/'expected.sha256').write_text(expected['sha256'])
            backup = root/'backup.jsonl'
            self.assertEqual(verified_copy(primary, backup, expected), expected)
            self.assertEqual(inventory(primary), expected)
            restored = root/'isolated-restore.jsonl'
            self.assertEqual(verified_copy(backup, restored, expected), expected)
            self.assertEqual(DurablePositionJournal(restored).ledger.status('p', 9), 'closed')
            with self.assertRaises(FileExistsError): verified_copy(backup, restored, expected)
            for absent in (None, {**expected, 'tail':'f'*64}):
                with self.assertRaises(JournalIntegrityError): verified_copy(backup, root/'not-published', absent)
            self.assertFalse((root/'not-published').exists())

    def test_well_formed_wrong_backup_rejected_by_independent_commitment(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); primary = self.seed(root); expected = inventory(primary)
            other = root/'other.jsonl'
            DurablePositionJournal(other).append(PositionEvent('other', 'open', 'opened', 1, 1, 'offline'))
            with self.assertRaises(JournalIntegrityError): verified_copy(other, root/'restored', expected)
            self.assertFalse((root/'restored').exists())

    def test_corrupted_backup_not_published_source_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); primary = self.seed(root); expected = inventory(primary)
            backup = root/'backup.jsonl'; verified_copy(primary, backup, expected)
            backup.write_bytes(backup.read_bytes()[:-1])
            before = backup.read_bytes()
            with self.assertRaises(JournalIntegrityError): verified_copy(backup, root/'restored', expected)
            self.assertFalse((root/'restored').exists()); self.assertEqual(backup.read_bytes(), before)
            self.assertEqual(inventory(primary), expected)

    def test_live_writer_refused_backup_is_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); p = self.seed(root); expected = inventory(p)
            with _exclusive_writer(p):
                with self.assertRaises(JournalIntegrityError): verified_copy(p, root/'backup', expected)
            self.assertFalse((root/'backup').exists())

    def test_operator_audited_orphan_recovery_with_confirmed_child_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); p = self.seed(root); expected = inventory(p)
            code = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from aql.observation.position_journal import _exclusive_writer
print(os.getpid(),flush=True)
with _exclusive_writer(Path(sys.argv[1])):os._exit(71)
'''
            child = subprocess.Popen([sys.executable, '-B', '-c', code, str(p), SRC], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 71, error)
            writer_pid = int(output.decode().strip())
            lock = p.with_name(p.name+'.writer.lock')
            # Windows venv launcher PID can differ from the actual interpreter.
            self.assertEqual(int(lock.read_text()), writer_pid)
            with self.assertRaises(JournalIntegrityError):
                DurablePositionJournal(p).append(PositionEvent('other', 'open', 'opened', 5, 5, 'offline'))
            evidence = root/'preserved-evidence'; evidence.mkdir()
            shutil.copyfile(p, evidence/'journal.jsonl'); shutil.copyfile(lock, evidence/'writer.lock')
            (evidence/'operator-audit.json').write_text(json.dumps({'writer_pid':writer_pid, 'launcher_pid':child.pid, 'observed_exit_code':child.returncode,
                'executable':sys.executable, 'pid_evidence':'parent-owned child handle waited, not PID lookup',
                'fence':'isolated test has no restart supervisor or other authorized writer',
                'journal_sha256':expected['sha256'], 'lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest()}))
            self.assertEqual(inventory(evidence/'journal.jsonl'), expected)
            self.assertIsNotNone(child.poll())
            # Explicit operator action on disposable fixture ONLY, AFTER evidence and fencing.
            lock.unlink()
            fresh = DurablePositionJournal(p)
            self.assertEqual(fresh.append(PositionEvent('other', 'open', 'opened', 5, 5, 'offline')), 'inserted')
            with _exclusive_writer(p):
                contender = subprocess.run([sys.executable, '-B', '-c',
                    "import sys;sys.path.insert(0,sys.argv[2]);from aql.observation.position_journal import DurablePositionJournal;from aql.observation.positions import PositionEvent;DurablePositionJournal(sys.argv[1]).append(PositionEvent('x','o','opened',6,6,'offline'))",str(p),SRC], capture_output=True, timeout=15)
                self.assertNotEqual(contender.returncode, 0)
                self.assertIn(b'writer lock held', contender.stderr)
            self.assertEqual(len(DurablePositionJournal(p).ledger.events), 3)
            self.assertEqual(inventory(evidence/'journal.jsonl'), expected)


if __name__ == '__main__': unittest.main()
