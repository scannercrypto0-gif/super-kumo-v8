"""Deterministic stale-worker checkpoint regression tests."""
import pytest
from aql.data_proof import ProofError
from aql.data_proof_g1_sweep_progress import SweepProgress


def test_stale_worker_cannot_regress_or_clear(tmp_path):
    a = SweepProgress(tmp_path / "sweep.sqlite")
    b = SweepProgress(tmp_path / "sweep.sqlite")
    key = ("instance", "BTCUSDT", "1m")
    try:
        assert a.state(*key) is None
        a.save(*key, 0, 100, expected=None)
        old = b.state(*key)
        a.save(*key, 20, 100, expected=old)
        with pytest.raises(ProofError, match="stale"):
            b.save(*key, 10, 100, expected=old)
        with pytest.raises(ProofError, match="stale"):
            b.clear(*key, expected=old)
        assert a.state(*key) == (20, 100)
        with pytest.raises(ProofError, match="regression"):
            a.save(*key, 19, 100, expected=(20, 100))
        with pytest.raises(ProofError, match="stale"):
            b.save(*key, 0, 200, expected=None)
        a.clear(*key, expected=(20, 100))
        assert b.state(*key) is None
    finally:
        a.close()
        b.close()
