"""D3 integration acceptance using actual G1 SQLite journal and operational store.

No network, no production collector, no trading activation.
"""
import threading
import time

from aql.d3_g1_sidecopy import G1ArchiveSidecopy
from aql.d3_offline_archive import OfflineArchiveLane
from aql.d3_synthetic_archive import SparseRecord, build_catalog
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.models.bar import MarketBar


def bar(sequence):
    opened = 1_700_000_000_000 + sequence * 60_000
    return MarketBar(symbol="BTCUSDT", interval="1m", bar_open=opened,
                     bar_close=opened + 59_999, open=100.0, high=101.0,
                     low=99.0, close=100.5, volume=1.0, is_final=True,
                     source="binance_ws", ingested_at=opened + 60_000).with_checksum()


def test_real_g1_journal_store_remain_independent_of_stalled_archive(tmp_path, monkeypatch):
    import aql.d3_offline_archive as archive
    journal = DurableJournal(str(tmp_path / "journal.db"))
    store = OperationalStore(str(tmp_path / "store.db"))
    entered, release = threading.Event(), threading.Event()
    original = archive.publish_generation

    def stalled(*args):
        entered.set()
        assert release.wait(8)
        return original(*args)

    monkeypatch.setattr(archive, "publish_generation", stalled)
    lane = OfflineArchiveLane(tmp_path, capacity=1)
    sidecopy = G1ArchiveSidecopy(lane)

    def core_write(sequence):
        item = bar(sequence)
        journal.commit(item)
        store.upsert(item)
        journal.mark_persisted(item.stable_key())
        return item

    try:
        first = core_write(1)
        manifest = build_catalog(generation="first", consumer="g1-integration", epoch=1,
                                 rows=(SparseRecord(1, "UNKNOWN", "a" * 64),))
        accepted = sidecopy.observe_after_core(manifest, source_committed=True,
                                               target_confirmed=False)
        assert accepted.accepted and entered.wait(3)
        queued = sidecopy.observe_after_core(
            build_catalog(generation="second", consumer="g1-integration", epoch=1,
                          rows=(SparseRecord(2, "UNKNOWN", "b" * 64),)),
            source_committed=True, target_confirmed=False)
        assert queued.accepted
        start = time.monotonic()
        second = core_write(2)
        rejected = sidecopy.observe_after_core(
            build_catalog(generation="third", consumer="g1-integration", epoch=1,
                          rows=(SparseRecord(3, "UNKNOWN", "c" * 64),)),
            source_committed=True, target_confirmed=False)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0  # generous fixture budget, not production SLO
        assert rejected.reason == "ARCHIVE_UNAVAILABLE_OR_FULL"
        assert store.count("BTCUSDT", "1m") == 2
        assert journal.commit_receipt(first.stable_key())["status"] != "NO_RECORD"
        assert journal.commit_receipt(second.stable_key())["status"] != "NO_RECORD"
    finally:
        release.set()
        lane.close()

    # Real SQLite state persists independently across process object recreation.
    reopened = OperationalStore(str(tmp_path / "store.db"))
    assert reopened.count("BTCUSDT", "1m") == 2
