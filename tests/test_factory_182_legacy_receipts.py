"""Legacy compatibility and explicit DEV scoring cutoff; synthetic only."""
from research_wp_r0.historical_dev_exits_v1 import (
    Config, _signals, digest, replay, verify_receipt,
)


def sample(n=270):
    return [
        dict(open_ms=i * 60000, close_ms=(i + 1) * 60000 - 1,
             open=100.0 + i * .01, high=101.0 + i * .01,
             low=99.0 + i * .01, close=100.0 + i * .01,
             volume=1.0, available_ms=(i + 1) * 60000 + 1000,
             modeled_quote=True)
        for i in range(n)
    ]


def pinned_source(bars):
    return dict(version="synthetic-compat", reference="fixture:compat",
                archive_sha256="a" * 64, rows_sha256=digest(bars),
                availability_evidence="UNKNOWN",
                correction_evidence="PINNED_VERSION_ONLY")


def test_default_legacy_signal_at_index_21_is_not_lost():
    bars = sample(270)
    original = _signals(bars, Config())
    assert len(original) == 270 - 21
    assert original[0]["bar_open_ms"] == 21 * 60000
    assert _signals(bars, Config(warmup_bars=22)) == original[1:]


def test_explicit_252_only_scores_after_full_seed_history():
    bars = sample(270)
    legacy = _signals(bars, Config())
    scored = _signals(bars, Config(warmup_bars=252))
    assert len(scored) == 18
    assert scored == legacy[252 - 21:]
    assert scored[0]["bar_open_ms"] == 252 * 60000


def test_default_receipt_preserves_pre_warmup_schema_and_is_verifiable():
    bars = sample(24)
    receipt = replay(bars, source=pinned_source(bars))
    assert "warmup_bars" not in receipt["config"]
    assert verify_receipt(receipt)
    explicit = replay(bars, source=pinned_source(bars),
                      config=Config(warmup_bars=22))
    assert explicit["config"]["warmup_bars"] == 22
    assert explicit["receipt_sha256"] != receipt["receipt_sha256"]
    assert verify_receipt(explicit)


def test_empty_scoring_window_is_distinct_from_default_legacy():
    bars = sample(251)
    assert _signals(bars, Config(warmup_bars=252)) == []
    assert _signals(bars, Config())
