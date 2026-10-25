"""Spawned-process replay against the durable Factory ledger (Windows/Linux)."""
import concurrent.futures
import multiprocessing
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_attempt_writer import FrozenAttemptWriter
from research_wp_r0.test_frozen_concurrency_recovery import EVENT, frozen_plan


def _write_from_process(args):
    path, raw, digest = args
    writer = FrozenAttemptWriter(AttemptLedger(path), raw, digest)
    return writer.record_attempt(dict(EVENT))


class SpawnedProcessRecoveryTests(unittest.TestCase):
    def test_process_replay_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "attempts.sqlite")
            raw, digest = frozen_plan()
            AttemptLedger(path, require_admission=True)
            context = multiprocessing.get_context("spawn")
            with concurrent.futures.ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
                results = list(pool.map(_write_from_process, [(path, raw, digest)] * 2))
            self.assertEqual(len(results), 2)
            ledger = AttemptLedger(path)
            events, checkpoint = ledger.snapshot()
            self.assertEqual(len(events), 1)
            self.assertEqual(checkpoint[0], 1)
            reopened = AttemptLedger(path, expected_checkpoint=checkpoint)
            self.assertEqual(reopened.snapshot()[1], checkpoint)


if __name__ == "__main__":
    unittest.main()
