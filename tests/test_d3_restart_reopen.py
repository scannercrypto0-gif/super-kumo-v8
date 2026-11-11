"""D3 offline crash/restart boundary acceptance using real SQLite G1 custody.

This is process-object restart, not SIGKILL or physical host-loss evidence.
"""
from aql.d3_offline_archive import publish_generation, verify_restore
from aql.d3_synthetic_archive import D3IntegrityError, SparseRecord, build_catalog
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.models.bar import MarketBar
import pytest


def _bar():
    opened = 1_700_000_000_000
    return MarketBar(symbol="ETHUSDT", interval="1m", bar_open=opened,
                     bar_close=opened + 59_999, open=100, high=101,
                     low=99, close=100.5, volume=1, is_final=True,
                     source="binance_ws", ingested_at=opened + 60_000).with_checksum()


def test_restart_reopen_keeps_g1_authority_separate_from_d3_manifest(tmp_path):
    journal_path = tmp_path / "journal.db"
    store_path = tmp_path / "store.db"
    journal = DurableJournal(str(journal_path))
    store = OperationalStore(str(store_path))
    item = _bar()
    journal.commit(item)
    store.upsert(item)
    journal.mark_persisted(item.stable_key())

    # The synthetic archive contains only a separately pinned inventory claim.
    # It cannot substitute for real source/target receipts.
    source_digest = "a" * 64
    target_digest = "b" * 64
    catalog = build_catalog(generation="reboot", consumer="g1-restart",
                            epoch=4, rows=(SparseRecord(0, "CONFIRMED",
                                                       source_digest, target_digest),))
    publish_generation(tmp_path, catalog)
    pinned = catalog["catalog_digest"]

    del journal, store
    reopened_journal = DurableJournal(str(journal_path))
    reopened_store = OperationalStore(str(store_path))
    assert reopened_store.count("ETHUSDT", "1m") == 1
    assert reopened_journal.commit_receipt(item.stable_key())["status"] != "NO_RECORD"

    # Independently supplied pinned evidence is mandatory on restore.
    kw = dict(generation="reboot", pinned_digest=pinned,
              expected_consumer="g1-restart", minimum_epoch=4,
              source_digests={0: source_digest}, target_receipts={0: target_digest})
    assert len(verify_restore(tmp_path, **kw)) == 1
    with pytest.raises(D3IntegrityError):
        verify_restore(tmp_path, **{**kw, "target_receipts": {}})
    with pytest.raises(D3IntegrityError):
        verify_restore(tmp_path, **{**kw, "minimum_epoch": 5})


def test_abandoned_pending_file_cannot_be_mistaken_for_published_generation(tmp_path):
    (tmp_path / "orphan.pending").write_bytes(b"untrusted incomplete manifest")
    kw = dict(generation="orphan", pinned_digest="a" * 64,
              expected_consumer="g1", minimum_epoch=1,
              source_digests={}, target_receipts={})
    with pytest.raises(D3IntegrityError):
        verify_restore(tmp_path, **kw)
    assert not (tmp_path / "orphan.json").exists()
