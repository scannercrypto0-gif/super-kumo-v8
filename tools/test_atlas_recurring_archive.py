"""Changed-delta checks for the explicitly authorized periodic dispatch."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from aql.observation.contracts import digest
from tools.atlas_recurring_research import archive_queue, DAY


class PeriodicArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.state = self.root / "state"
        self.host = patch.dict(os.environ, {"COMPUTERNAME": "fixture-host"})
        self.host.start()
        self.addCleanup(self.host.stop)
        self.jobs = []
        for start in (1715040000000, 1715040000000 + DAY):
            date = datetime.fromtimestamp(start // 1000, timezone.utc).strftime("%Y-%m-%d")
            archive = f"BTCUSDT-1m-{date}.zip"
            for name in (archive, archive + ".CHECKSUM"):
                (self.source / name).touch()
            self.jobs.append(dict(start_ms=start, end_ms=start + DAY, cutoff_ms=start + DAY,
                archive=archive, experiment=f"ATLAS-RETROSPECTIVE-BTCUSDT-{date.replace('-', '')}",
                archive_sha256="a"*64, checksum_sha256="b"*64, source=str(self.source),
                host="fixture-host", rights_ref="fixture", authorization_ref="fixture",
                retention_scope="fixture"))
        self.runner = Mock(side_effect=self.fixture_commit)
        self.reader = Mock(side_effect=lambda target, _: json.loads((target / "result.json").read_text()))

    def fixture_commit(self, target, source, job):
        target.mkdir()
        (target / "result.json").write_text(json.dumps(dict(archive_sha256=job["archive_sha256"],
            checksum_sha256=job["checksum_sha256"], orders=0, current_entry="NO_CURRENT_ENTRY",
            sha256=digest(job))))

    def invoke(self, mode, *, pin=None):
        return archive_queue(self.state, self.jobs, pin or digest(self.jobs), mode,
                             now=1715040000000 + 3*DAY, runner=self.runner, reader=self.reader)

    def test_tick_catches_up_one_window_and_replays_without_original(self):
        self.assertEqual(self.invoke("stop")["status"], "BLOCKED")
        self.invoke("recover")
        self.runner.assert_not_called()
        self.invoke("rearm")
        self.assertEqual(self.invoke("recover")["status"], "READY")
        result = self.invoke("recover")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(self.invoke("recover"), result)
        self.assertEqual(self.runner.call_count, 2)

    def test_unfinished_claim_fails_closed_without_reread(self):
        self.runner.side_effect = RuntimeError("fixture interruption")
        with self.assertRaisesRegex(RuntimeError, "interruption"):
            self.invoke("recover")
        result = self.invoke("recover")
        self.assertEqual(result["windows"][0]["reason"], "ORIGINAL_ALREADY_CLAIMED_INCOMPLETE")
        self.assertEqual(self.runner.call_count, 1)

    def test_wrong_pin_missing_rights_and_missing_file_never_dispatch(self):
        with self.assertRaisesRegex(ValueError, "ARCHIVE_QUEUE_PIN"):
            self.invoke("recover", pin="c"*64)
        self.jobs[0]["authorization_ref"] = ""
        with self.assertRaisesRegex(ValueError, "EXACT_ARCHIVE_AUTHORIZATION_REQUIRED"):
            self.invoke("recover")
        self.jobs[0]["authorization_ref"] = "fixture"
        (self.source / self.jobs[0]["archive"]).unlink()
        self.assertEqual(self.invoke("recover")["reason"], "AUTHORIZED_ARCHIVE_NOT_PRESENT")
        self.runner.assert_not_called()
