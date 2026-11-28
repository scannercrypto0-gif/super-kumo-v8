import dataclasses

import pytest

from research_wp_r0.historical_library import (
    HistoricalDataError,
    HistoricalLibrary,
    make_test_bar,
    validate_bars,
)


def _early_cutoff_bar():
    bar = make_test_bar(0)
    object.__setattr__(bar, "observation_cutoff_ms", bar.bar_close)
    object.__setattr__(bar, "checksum", bar._compute_checksum())
    return bar


def test_final_bar_cannot_be_constructed_as_available_before_close():
    bar = make_test_bar(0)
    with pytest.raises(ValueError, match="final-bar availability"):
        dataclasses.replace(bar, observation_cutoff_ms=bar.bar_close)


def test_register_rejects_early_cutoff_without_mutating_library():
    bar = _early_cutoff_bar()
    _, manifest = validate_bars([bar], bar.symbol, bar.interval)
    lib = HistoricalLibrary()

    with pytest.raises(HistoricalDataError, match="point-in-time availability"):
        lib.register("bad", [bar], manifest)

    assert "bad" not in lib._datasets


def test_snapshot_rechecks_temporal_gate_on_stored_rows():
    good = make_test_bar(0)
    _, manifest = validate_bars([good], good.symbol, good.interval)
    bad = _early_cutoff_bar()
    lib = HistoricalLibrary()
    # Simulate a pre-existing or externally altered stored row. Retrieval must
    # enforce the causal rule independently of construction and registration.
    lib._datasets["bad"] = {1: ([bad], manifest)}

    with pytest.raises(HistoricalDataError, match="point-in-time availability"):
        lib.snapshot("bad", bad.bar_close + 10)

