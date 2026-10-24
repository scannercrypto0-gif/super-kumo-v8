"""G2 #92: isolated fail-closed recovery regression tests (offline only)."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aql.observation.position_journal import DurablePositionJournal, JournalIntegrityError
from aql.observation.positions import PositionEvent


class RecoveryEvidenceTests(unittest.TestCase):
    def test_subprocess_crash_leaves_torn_append_unmodified(self):
        """Inject a process crash while writing a partial journal record.

        This is a fault injection at the filesystem append boundary, NOT
        evidence of an instrumented crash inside DurablePositionJournal.append.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            journal = DurablePositionJournal(path)
            journal.append(PositionEvent("p1", "open", "opened", 0, 0, "offline"))
            original = path.read_bytes()
            child = (
                "import os,sys; "
                "f=open(sys.argv[1],'ab'); "
                "f.write(b\x27PARTIAL_RECORD\x27); f.flush(); os.fsync(f.fileno()); "
                "os._exit(29)"
            )
            result = subprocess.run([sys.executable, "-c", child, str(path)],
                                    capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 29)
            corrupted = path.read_bytes()
            self.assertTrue(corrupted.startswith(original))
            self.assertGreater(len(corrupted), len(original))
            with self.assertRaises(JournalIntegrityError):
                DurablePositionJournal(path)
            self.assertEqual(path.read_bytes(), corrupted)
            with self.assertRaises(JournalIntegrityError):
                journal.append(PositionEvent("p1", "close", "closed", 1, 1,
                                             "offline", reason="exit"))
            self.assertEqual(path.read_bytes(), corrupted)

    def test_verified_byte_copy_restores_without_mutating_source(self):
        """Baseline byte-copy verification; not a complete backup protocol."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary.jsonl"
            backup = root / "backup.jsonl"
            DurablePositionJournal(primary).append(
                PositionEvent("p1", "open", "opened", 0, 0, "offline"))
            original = primary.read_bytes()
            backup.write_bytes(original)
            self.assertEqual(hashlib.sha256(backup.read_bytes()).digest(),
                             hashlib.sha256(original).digest())
            self.assertEqual(DurablePositionJournal(backup).ledger.status("p1", 1),
                             "open")
            backup.write_bytes(backup.read_bytes()[:-1])
            with self.assertRaises(JournalIntegrityError):
                DurablePositionJournal(backup)
            self.assertEqual(primary.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
