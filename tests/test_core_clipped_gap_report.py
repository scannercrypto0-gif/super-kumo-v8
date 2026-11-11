"""AIARC-025: a >8000-bar gap must remain explicitly unresolved and bounded."""
from unittest.mock import patch

from aql.recovery.gap_recovery import recover_gap


def test_clipped_gap_exposes_bounded_remainder_without_false_full():
    interval_ms = 60000
    with patch("aql.recovery.gap_recovery._fetch_klines", return_value=([], 0)):
        bars, report = recover_gap("BTCUSDT", "1m", 0, 20000 * interval_ms, set())
    assert bars == []
    assert report.status == "UNRESOLVED_DATA_GAP"
    assert report.remaining_start_ms == 8000 * interval_ms
    assert report.remaining_end_ms == 20000 * interval_ms
    assert report.expected_bars == 20000
    assert report.unresolved == 20000
    assert len(report.missing_opens) <= 8000


def test_short_gap_has_no_continuation():
    with patch("aql.recovery.gap_recovery._fetch_klines", return_value=([], 0)):
        _, report = recover_gap("BTCUSDT", "1m", 0, 10 * 60000, set())
    assert report.remaining_start_ms is None
    assert report.remaining_end_ms is None


def test_bounded_continuation_advances_and_stops_after_three(monkeypatch):
    from types import SimpleNamespace
    import aql.pipeline as pipeline

    starts = []

    def fake_slice(journal, store, symbol, interval, start, end, stop):
        starts.append(start)
        return {"gap_report": SimpleNamespace(remaining_start_ms=start + 8000 * 60000,
                                               http_error=None),
                "recovery_errors": 0}

    monkeypatch.setattr(pipeline, "_run_gap_recovery", fake_slice)
    result = pipeline._recover_bounded_slices(None, None, "BTCUSDT", "1m",
                                              0, 40000 * 60000)
    assert len(result) == 3
    assert starts == [0, 8000 * 60000, 16000 * 60000]


def test_bounded_continuation_stops_on_error(monkeypatch):
    from types import SimpleNamespace
    import aql.pipeline as pipeline
    calls = []

    def failed_slice(journal, store, symbol, interval, start, end, stop):
        calls.append(start)
        return {"gap_report": SimpleNamespace(remaining_start_ms=8000 * 60000,
                                               http_error=None),
                "recovery_errors": 1}

    monkeypatch.setattr(pipeline, "_run_gap_recovery", failed_slice)
    assert len(pipeline._recover_bounded_slices(None, None, "BTCUSDT", "1m",
                                                0, 20000 * 60000)) == 1
    assert calls == [0]
