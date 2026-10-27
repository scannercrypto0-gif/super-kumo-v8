"""Opt-in G1 journal consumer observer cannot override durable ACK."""
from aql.lanes import JournalConsumer


class Bar:
    def stable_key(self):
        return "BTC:1m:0"


class Journal:
    def __init__(self):
        self.events = []
        self.bars = [Bar()]

    def replay(self, *args, **kwargs):
        return self.bars

    def require_eligible(self, key):
        self.events.append("eligible")

    def mark_persisted(self, key):
        self.events.append("persisted")


class Store:
    def __init__(self, journal, fail=False):
        self.journal = journal
        self.fail = fail

    def upsert(self, bar):
        if self.fail:
            raise RuntimeError("store failure")
        self.journal.events.append("stored")


def test_post_persist_observer_fails_without_reversing_ack():
    journal = Journal()
    def observer(bar):
        journal.events.append("observed")
        raise RuntimeError("sidecopy down")
    consumer = JournalConsumer(journal, Store(journal), "BTC", "1m",
                               after_persisted=observer)
    assert consumer.drain_once() == 1
    assert journal.events == ["eligible", "stored", "persisted", "observed"]
    assert consumer.sidecopy_errors == 1


def test_no_observer_before_store_confirmation():
    journal = Journal()
    called = []
    consumer = JournalConsumer(journal, Store(journal, fail=True), "BTC", "1m",
                               after_persisted=lambda bar: called.append(bar))
    try:
        consumer.drain_once()
    except RuntimeError:
        pass
    assert called == []
    assert "persisted" not in journal.events
