"""D3/G1 post-commit interface integration: blocked archive cannot block G1 authority."""
import threading
import time

from aql.d3_g1_sidecopy import G1ArchiveSidecopy
from aql.d3_offline_archive import OfflineArchiveLane
from aql.d3_synthetic_archive import SparseRecord, build_catalog


def catalog(generation):
    return build_catalog(generation=generation, consumer="g1-fixture", epoch=1,
                         rows=(SparseRecord(0, "UNKNOWN", "a" * 64),))


def test_g1_journal_store_contract_unchanged_under_archive_stall(tmp_path, monkeypatch):
    import aql.d3_offline_archive as module

    entered = threading.Event()
    release = threading.Event()
    original = module.publish_generation

    def stalled(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(module, "publish_generation", stalled)
    lane = OfflineArchiveLane(tmp_path, capacity=1)
    sidecopy = G1ArchiveSidecopy(lane)

    # A minimal deterministic authority boundary: core commits and store writes
    # happen BEFORE the optional archive sidecopy, with separate ACK accounting.
    journal = []
    store = []
    source_acks = []

    def g1_core_commit(value):
        journal.append(value)
        store.append(value)
        source_acks.append(value)

    try:
        g1_core_commit("first")
        first = sidecopy.observe_after_core(catalog("g1"), source_committed=True,
                                            target_confirmed=False)
        assert first.accepted
        assert entered.wait(2)
        second = sidecopy.observe_after_core(catalog("g2"), source_committed=True,
                                             target_confirmed=False)
        assert second.accepted
        start = time.monotonic()
        g1_core_commit("second")
        rejected = sidecopy.observe_after_core(catalog("g3"), source_committed=True,
                                               target_confirmed=False)
        assert time.monotonic() - start < 0.5
        assert not rejected.accepted
        assert rejected.reason == "ARCHIVE_UNAVAILABLE_OR_FULL"
        assert journal == store == source_acks == ["first", "second"]
        assert sidecopy.publication_result(first) == "PENDING"
    finally:
        release.set()
        lane.close()
    assert sidecopy.publication_result(first) == "PUBLISHED_LOCAL_ONLY"


def test_no_false_receipt_before_source_or_target(tmp_path):
    lane = OfflineArchiveLane(tmp_path)
    try:
        sidecopy = G1ArchiveSidecopy(lane)
        denied = sidecopy.observe_after_core(catalog("g1"), source_committed=False,
                                             target_confirmed=False)
        assert denied.reason == "SOURCE_NOT_COMMITTED"
        confirmed = build_catalog(generation="g2", consumer="g1-fixture", epoch=1,
                                  rows=(SparseRecord(1, "CONFIRMED", "a"*64, "b"*64),))
        denied = sidecopy.observe_after_core(confirmed, source_committed=True,
                                             target_confirmed=False)
        assert denied.reason == "TARGET_NOT_CONFIRMED"
        assert sidecopy.submitted == 0
    finally:
        lane.close()
