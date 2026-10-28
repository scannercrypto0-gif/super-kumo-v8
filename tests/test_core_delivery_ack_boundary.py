"""AIARC-026: cross-database store/ACK is replay-safe, not atomic exactly-once."""
from unittest.mock import patch

import pytest

from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.lanes import JournalConsumer
from aql.models.bar import MarketBar


def test_consumer_store_commit_then_ack_failure_recovers_without_duplicate(tmp_path):
    jp = str(tmp_path / "journal.sqlite")
    sp = str(tmp_path / "store.sqlite")
    j = DurableJournal(jp)
    store = OperationalStore(sp)
    bar = MarketBar("BTCUSDT", "1m", 0, 59999, 100., 101., 99.,
                    100., 1., True, "synthetic", 60000).with_checksum()
    assert j.commit(bar)
    consumer = JournalConsumer(j, store, "BTCUSDT", "1m")
    with patch.object(j, "mark_persisted", side_effect=OSError("ACK unavailable")):
        with pytest.raises(OSError, match="ACK unavailable"):
            consumer.drain_once()
    assert store.count("BTCUSDT", "1m") == 1
    assert len(j.replay(pending_only=True)) == 1

    reopened = DurableJournal(jp)
    restarted = JournalConsumer(reopened, OperationalStore(sp), "BTCUSDT", "1m")
    assert restarted.drain_once() == 1
    assert reopened.replay(pending_only=True) == []
    assert OperationalStore(sp).count("BTCUSDT", "1m") == 1
    assert restarted.drain_once() == 0


def test_consumer_store_failure_never_acks(tmp_path):
    j = DurableJournal(str(tmp_path / "journal.sqlite"))
    store = OperationalStore(str(tmp_path / "store.sqlite"))
    bar = MarketBar("BTCUSDT", "1m", 0, 59999, 100., 101., 99.,
                    100., 1., True, "synthetic", 60000).with_checksum()
    assert j.commit(bar)
    consumer = JournalConsumer(j, store, "BTCUSDT", "1m")
    with patch.object(store, "upsert", side_effect=OSError("store unavailable")):
        with pytest.raises(OSError, match="store unavailable"):
            consumer.drain_once()
    assert len(j.replay(pending_only=True)) == 1
    assert store.count("BTCUSDT", "1m") == 0
