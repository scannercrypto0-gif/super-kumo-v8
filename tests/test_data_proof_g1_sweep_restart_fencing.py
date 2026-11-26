"""Restart and crash-boundary regression for durable sweep generation fencing."""
import pytest

from aql.data_proof import ProofError
from aql.data_proof_g1_sweep_progress import SweepProgress


def test_generation_survives_restart_and_rejects_old_worker(tmp_path):
    path = tmp_path / "sweep.sqlite"
    key = ("instance", "BTCUSDT", "1m")
    before = SweepProgress(path)
    try:
        before.save(*key, 0, 100, expected=None, expected_generation=0)
        old_generation = before.generation(*key)
        before.save(*key, 10, 100, expected=(0, 100),
                    expected_generation=old_generation)
    finally:
        before.close()

    after = SweepProgress(path)
    try:
        assert after.state(*key) == (10, 100)
        assert after.generation(*key) == old_generation
        with pytest.raises(ProofError, match="stale"):
            after.save(*key, 5, 100, expected=(0, 100),
                       expected_generation=old_generation)
        after.clear(*key, expected=(10, 100),
                    expected_generation=old_generation)
    finally:
        after.close()

    next_cycle = SweepProgress(path)
    try:
        assert next_cycle.state(*key) is None
        assert next_cycle.generation(*key) == old_generation
        next_cycle.save(*key, 0, 100, expected=None,
                        expected_generation=old_generation)
        assert next_cycle.generation(*key) == old_generation + 1
        with pytest.raises(ProofError, match="stale sweep generation"):
            next_cycle.clear(*key, expected=(0, 100),
                             expected_generation=old_generation)
        assert next_cycle.state(*key) == (0, 100)
    finally:
        next_cycle.close()
