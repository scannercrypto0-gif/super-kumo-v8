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
        a.save(*key, 0, 100, expected=None, expected_generation=0)
        old = b.state(*key)
        a.save(*key, 20, 100, expected=old, expected_generation=1)
        with pytest.raises(ProofError, match="stale"):
            b.save(*key, 10, 100, expected=old, expected_generation=1)
        with pytest.raises(ProofError, match="stale"):
            b.clear(*key, expected=old, expected_generation=1)
        assert a.state(*key) == (20, 100)
        with pytest.raises(ProofError, match="regression"):
            a.save(*key, 19, 100, expected=(20, 100), expected_generation=1)
        with pytest.raises(ProofError, match="stale"):
            b.save(*key, 0, 200, expected=None, expected_generation=1)
        a.clear(*key, expected=(20, 100), expected_generation=1)
        assert b.state(*key) is None
    finally:
        a.close()
        b.close()


def test_generation_fences_aba_after_cycle_restart(tmp_path):
    a = SweepProgress(tmp_path / "sweep.sqlite")
    b = SweepProgress(tmp_path / "sweep.sqlite")
    key = ("instance", "BTCUSDT", "1m")
    try:
        old_generation = a.generation(*key)
        a.save(*key, 0, 100, expected=None,
               expected_generation=old_generation)
        first_generation = a.generation(*key)
        assert first_generation == old_generation + 1
        stale_state = b.state(*key)
        a.clear(*key, expected=stale_state,
                expected_generation=first_generation)
        a.save(*key, 0, 100, expected=None,
               expected_generation=first_generation)
        assert a.state(*key) == stale_state
        assert a.generation(*key) == first_generation + 1
        with pytest.raises(ProofError, match="stale sweep generation"):
            b.save(*key, 1, 100, expected=stale_state,
                   expected_generation=first_generation)
        with pytest.raises(ProofError, match="stale sweep generation"):
            b.clear(*key, expected=stale_state,
                    expected_generation=first_generation)
        assert a.state(*key) == stale_state
    finally:
        a.close()
        b.close()


def test_generation_token_cannot_be_omitted(tmp_path):
    progress = SweepProgress(tmp_path / "sweep.sqlite")
    key = ("instance", "BTCUSDT", "1m")
    try:
        with pytest.raises(ProofError, match="generation token required"):
            progress.save(*key, 0, 10, expected=None)
        progress.save(*key, 0, 10, expected=None, expected_generation=0)
        with pytest.raises(TypeError):
            progress.clear(*key, expected=(0, 10))
        assert progress.state(*key) == (0, 10)
    finally:
        progress.close()


def test_snapshot_returns_coherent_state_and_generation(tmp_path):
    path = tmp_path / "sweep.sqlite"
    a = SweepProgress(path)
    b = SweepProgress(path)
    key = ("instance", "BTCUSDT", "1m")
    try:
        assert a.snapshot(*key) == (None, 0)
        a.save(*key, 0, 100, expected=None, expected_generation=0)
        assert b.snapshot(*key) == ((0, 100), 1)
        a.clear(*key, expected=(0, 100), expected_generation=1)
        a.save(*key, 0, 100, expected=None, expected_generation=1)
        assert b.snapshot(*key) == ((0, 100), 2)
    finally:
        a.close()
        b.close()


def test_sweep_stale_worker_fails_closed_without_claiming_complete(tmp_path, monkeypatch):
    import aql.data_proof_g1_sweep_progress as module

    key = ("instance", "BTCUSDT", "1m")
    worker = SweepProgress(tmp_path / "sweep.sqlite")
    winner = SweepProgress(tmp_path / "sweep.sqlite")

    class Journal:
        instance_id = key[0]

        def startup_entry_boundary(self):
            return 100

    def racing_page(*args, **kwargs):
        state, generation = winner.snapshot(*key)
        assert state == (0, 100)
        winner.save(*key, 50, 100, expected=state,
                    expected_generation=generation)
        return {"added": 0, "existing": 0, "next_cursor": 10,
                "failed_key": None, "complete": True}

    try:
        monkeypatch.setattr(module, "reconcile_persisted_page", racing_page)
        with pytest.raises(ProofError, match="stale sweep checkpoint update"):
            module.run_sweep_slice(Journal(), object(), worker,
                                   symbol=key[1], interval=key[2],
                                   page_size=10, max_pages=1)
        assert winner.state(*key) == (50, 100)
    finally:
        worker.close()
        winner.close()
