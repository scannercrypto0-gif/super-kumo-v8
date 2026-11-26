"""Tests for G2 — universe.py: eligibility, snapshot, rotating selection."""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from tools.scanner_engine_offline.universe import (
    MarketInfo, UniverseItem, UniverseSnapshot,
    classify_symbol, build_universe_snapshot, select_candidates,
    STATUS_ELIGIBLE, STATUS_REJECTED, STATUS_UNSUPPORTED, STATUS_UNKNOWN,
    MIN_QUOTE_VOLUME_24H, MAX_SPREAD_BPS,
)

UTC = timezone.utc
T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def make_market(symbol="SOLUSDT", **kwargs) -> MarketInfo:
    defaults = dict(
        symbol=symbol,
        quote_asset="USDT",
        spot_enabled=True,
        trading_status="TRADING",
        quote_volume_24h=Decimal("20_000_000"),
        bid=Decimal("100.00"),
        ask=Decimal("100.01"),
        observed_at=T0 - timedelta(seconds=30),
    )
    defaults.update(kwargs)
    return MarketInfo(**defaults)


class TestClassifySymbol:
    def test_eligible_market(self):
        m = make_market()
        item = classify_symbol(m, T0)
        assert item.status == STATUS_ELIGIBLE
        assert not item.reasons

    def test_non_usdt_pair(self):
        m = make_market(symbol="SOLBTC", quote_asset="BTC")
        item = classify_symbol(m, T0)
        assert item.status == STATUS_UNSUPPORTED

    def test_low_volume_rejected(self):
        m = make_market(quote_volume_24h=Decimal("1_000"))
        item = classify_symbol(m, T0)
        assert item.status == STATUS_REJECTED
        assert "LOW_24H_QUOTE_VOLUME" in item.reasons

    def test_high_spread_rejected(self):
        m = make_market(bid=Decimal("100"), ask=Decimal("105"))  # 5% spread
        item = classify_symbol(m, T0)
        assert item.status == STATUS_REJECTED
        assert "SPREAD_ABOVE_LIMIT" in item.reasons

    def test_not_tradable_rejected(self):
        m = make_market(spot_enabled=False)
        item = classify_symbol(m, T0)
        assert item.status == STATUS_REJECTED
        assert "SPOT_NOT_TRADABLE" in item.reasons

    def test_future_snapshot_unknown(self):
        m = make_market(observed_at=T0 + timedelta(seconds=1))
        item = classify_symbol(m, T0)
        assert item.status == STATUS_UNKNOWN
        assert "MARKET_SNAPSHOT_FROM_FUTURE" in item.reasons[0]

    def test_invalid_bid_ask_rejected(self):
        m = make_market(bid=Decimal("0"), ask=Decimal("100"))
        item = classify_symbol(m, T0)
        assert item.status == STATUS_REJECTED
        assert "INVALID_BID_ASK" in item.reasons


class TestBuildUniverseSnapshot:
    def test_snapshot_contains_all_items(self):
        markets = [make_market(f"TOKEN{i}USDT") for i in range(5)]
        snap = build_universe_snapshot(markets, T0)
        assert len(snap.items) == 5

    def test_snapshot_id_deterministic(self):
        markets = [make_market("SOLUSDT"), make_market("AVAXUSDT")]
        s1 = build_universe_snapshot(markets, T0)
        s2 = build_universe_snapshot(markets, T0)
        assert s1.snapshot_id == s2.snapshot_id

    def test_eligible_filter(self):
        markets = [
            make_market("SOLUSDT"),
            make_market("LOWTOKENUSDT", quote_volume_24h=Decimal("100")),
        ]
        snap = build_universe_snapshot(markets, T0)
        assert len(snap.eligible) == 1
        assert snap.eligible[0].symbol == "SOLUSDT"

    def test_summary_structure(self):
        markets = [make_market("SOLUSDT"), make_market("AVAXUSDT")]
        snap = build_universe_snapshot(markets, T0)
        s = snap.summary()
        assert "eligible_count" in s
        assert "snapshot_id" in s
        assert s["total"] == 2


class TestSelectCandidates:
    def _snap(self, n: int) -> UniverseSnapshot:
        markets = [make_market(f"TOKEN{i:02d}USDT") for i in range(n)]
        return build_universe_snapshot(markets, T0)

    def test_select_up_to_limit(self):
        snap = self._snap(10)
        sel = select_candidates(snap, limit=5, offset=0)
        assert len(sel) == 5

    def test_select_all_when_limit_exceeds(self):
        snap = self._snap(3)
        sel = select_candidates(snap, limit=100, offset=0)
        assert len(sel) == 3

    def test_rotation_fairness(self):
        snap = self._snap(10)
        s0 = [x.symbol for x in select_candidates(snap, limit=3, offset=0)]
        s1 = [x.symbol for x in select_candidates(snap, limit=3, offset=1)]
        assert s0 != s1

    def test_rotation_wraps_around(self):
        snap = self._snap(5)
        sel_0 = select_candidates(snap, limit=5, offset=0)
        sel_5 = select_candidates(snap, limit=5, offset=5)
        assert [x.symbol for x in sel_0] == [x.symbol for x in sel_5]

    def test_invalid_limit_raises(self):
        snap = self._snap(3)
        with pytest.raises(ValueError, match="LIMIT_MUST_BE_POSITIVE_INT"):
            select_candidates(snap, limit=0, offset=0)

    def test_invalid_offset_raises(self):
        snap = self._snap(3)
        with pytest.raises(ValueError, match="OFFSET_MUST_BE_NON_NEGATIVE_INT"):
            select_candidates(snap, limit=2, offset=-1)

    def test_empty_universe_returns_empty(self):
        snap = build_universe_snapshot([], T0)
        sel = select_candidates(snap, limit=5, offset=0)
        assert sel == ()

    def test_bool_limit_raises(self):
        snap = self._snap(3)
        with pytest.raises(ValueError):
            select_candidates(snap, limit=True, offset=0)
