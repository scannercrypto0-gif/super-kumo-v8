import json

import pytest

from aql.collector import binance_collector as collector_module
from aql.collector.binance_collector import BinanceCollector
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.storage.operational_store import OperationalStore


def candle(open_ms, **overrides):
    return dict(s="BTCUSDT", i="1m", t=open_ms, T=open_ms + 59_999,
                o="10", h="11", l="9", c="10", v="1", x=True) | overrides


@pytest.fixture
def collector(tmp_path):
    journal = DurableJournal(str(tmp_path / "journal.db"))
    store = OperationalStore(str(tmp_path / "store.db"))
    journal.commit(MarketBar.from_binance_ws_kline(candle(600_000)))
    return BinanceCollector("BTCUSDT", "1m", journal, store)


def run_sessions(monkeypatch, collector, sessions):
    remaining = iter(sessions)
    backoffs = []
    connections = []

    class ScriptedSocket:
        def __init__(self, url, *, on_open, on_message, on_close, on_error):
            self.on_open = on_open
            self.on_message = on_message
            self.on_close = on_close

        def run_forever(self, **kwargs):
            connections.append(self)
            messages = next(remaining, None)
            if messages is None:
                # Bound the regression even when the old collector retries forever.
                collector.stop()
                return
            self.on_open(self)
            for message in messages:
                self.on_message(self, json.dumps({"k": message}))
            self.on_close(self, 1006, "fixture disconnect")

        def close(self):
            pass

    monkeypatch.setattr(collector_module.websocket, "WebSocketApp", ScriptedSocket)
    monkeypatch.setattr(collector._stop_event, "wait", backoffs.append)
    collector.run(timeout_s=5)
    return len(connections), backoffs


def test_duplicate_only_connections_exhaust_original_retry_budget(monkeypatch, collector):
    cap = collector_module.MAX_RECONNECT_ATTEMPTS
    connections, backoffs = run_sessions(
        monkeypatch, collector, [[candle(600_000)]] * (cap + 1)
    )
    assert connections == cap
    assert backoffs == collector_module.RECONNECT_BACKOFF_S[:cap - 1]
    assert collector.metrics.duplicate_count == cap
    assert collector.metrics.journal_commit_count == 0


def test_only_advancing_commit_restores_budget_across_reconnects(monkeypatch, collector):
    cap = collector_module.MAX_RECONNECT_ATTEMPTS
    old, first, later = 600_000, 660_000, 720_000
    commit = collector.journal.commit

    def fail_one_commit(bar):
        if bar.bar_open == 780_000:
            raise OSError("fixture journal failure")
        return commit(bar)

    monkeypatch.setattr(collector.journal, "commit", fail_one_commit)
    sessions = [
        [candle(540_000)],  # Unseen but older than the durable startup watermark.
        [candle(old)],
        [candle(old), candle(first), candle(first)],  # First budget reset.
        [candle(first)],
        [candle(480_000)],  # Newly committed, but out of order.
        [candle(780_000)],  # Failed commit.
        [candle(840_000, s="ETHUSDT")],  # Rejected stream.
        [candle(later)],  # Second budget reset, despite the rejected newer inputs.
    ]
    sessions.extend([[candle(later)]] * cap)
    connections, backoffs = run_sessions(monkeypatch, collector, sessions)
    schedule = collector_module.RECONNECT_BACKOFF_S
    assert connections == 7 + cap
    assert backoffs == schedule[:2] + schedule[:5] + schedule[:cap - 1]
    assert collector.metrics.error_count == 2
    assert collector.metrics.journal_commit_count == 4
    assert collector.journal.get_committed_range("BTCUSDT", "1m") == (480_000, later)


def test_store_failure_and_duplicate_retry_do_not_restore_budget(monkeypatch, collector):
    cap = collector_module.MAX_RECONNECT_ATTEMPTS
    upsert = collector.store.upsert

    def fail_first_upsert(bar):
        if bar.bar_open == 660_000 and collector.metrics.duplicate_count == 0:
            raise OSError("fixture store failure")
        return upsert(bar)

    monkeypatch.setattr(collector.store, "upsert", fail_first_upsert)
    connections, backoffs = run_sessions(
        monkeypatch, collector, [[candle(660_000)]] * (cap + 1)
    )
    assert connections == cap
    assert backoffs == collector_module.RECONNECT_BACKOFF_S[:cap - 1]
    assert collector.metrics.error_count == 1
    assert collector.metrics.journal_commit_count == 1
    assert collector.metrics.duplicate_count == cap - 1
