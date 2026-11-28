from aql.recovery import gap_recovery


def test_empty_eligible_window_is_reported_as_none(monkeypatch):
    monkeypatch.setattr(gap_recovery.time, "time", lambda: 10_000)

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("a window with no eligible bars must not fetch")

    monkeypatch.setattr(gap_recovery, "_fetch_klines", unexpected_fetch)
    bars, report = gap_recovery.recover_gap(
        "BTCUSDT", "1m", 10_000, 20_000, set()
    )

    assert bars == []
    assert report.expected_bars == 0
    assert report.unresolved == 0
    assert report.status == "NONE"


def test_real_missing_bars_remain_unresolved(monkeypatch):
    monkeypatch.setattr(gap_recovery.time, "time", lambda: 10_000)
    monkeypatch.setattr(gap_recovery, "_fetch_klines", lambda *args, **kwargs: ([], 0))

    bars, report = gap_recovery.recover_gap(
        "BTCUSDT", "1m", 0, 120_000, set()
    )

    assert bars == []
    assert report.expected_bars == 2
    assert report.unresolved == 2
    assert report.status == "UNRESOLVED_DATA_GAP"

