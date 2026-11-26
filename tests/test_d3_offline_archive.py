"""Targeted D3 offline archive publication, recovery and isolation tests."""
import json
import threading
import time

import pytest

from aql.d3_synthetic_archive import SparseRecord, build_catalog, D3IntegrityError
from aql.d3_offline_archive import publish_generation, verify_restore, OfflineArchiveLane

A = "a" * 64
B = "b" * 64


def case():
    catalog = build_catalog(generation="g1", consumer="sandbox", epoch=2,
                            rows=(SparseRecord(1, "CONFIRMED", A, B),
                                  SparseRecord(3, "IN_DOUBT", A)))
    kw = dict(generation="g1", pinned_digest=catalog["catalog_digest"],
              expected_consumer="sandbox", minimum_epoch=2,
              source_digests={1: A, 3: A}, target_receipts={1: B})
    return catalog, kw


def test_published_restore_parity_and_no_overwrite(tmp_path):
    catalog, kw = case()
    path = publish_generation(tmp_path, catalog)
    assert path.is_file()
    assert [r.sequence for r in verify_restore(tmp_path, **kw)] == [1, 3]
    with pytest.raises(D3IntegrityError):
        publish_generation(tmp_path, catalog)


def test_corrupt_archive_and_wrong_pin_fail_closed(tmp_path):
    catalog, kw = case()
    path = publish_generation(tmp_path, catalog)
    path.write_text(json.dumps({"generation": "g1"}))
    with pytest.raises(D3IntegrityError):
        verify_restore(tmp_path, **kw)
    path.unlink()
    publish_generation(tmp_path, catalog)
    kw["pinned_digest"] = "f" * 64
    with pytest.raises(D3IntegrityError):
        verify_restore(tmp_path, **kw)


def test_missing_receipt_and_stale_epoch(tmp_path):
    catalog, kw = case()
    publish_generation(tmp_path, catalog)
    kw["target_receipts"] = {}
    with pytest.raises(D3IntegrityError):
        verify_restore(tmp_path, **kw)
    kw["target_receipts"] = {1: B}
    kw["minimum_epoch"] = 3
    with pytest.raises(D3IntegrityError):
        verify_restore(tmp_path, **kw)


def test_nonblocking_submission_while_sink_is_stalled(tmp_path, monkeypatch):
    import aql.d3_offline_archive as module
    entered = threading.Event()
    release = threading.Event()
    original = module.publish_generation

    def blocked(*args):
        entered.set()
        assert release.wait(timeout=5)
        return original(*args)

    monkeypatch.setattr(module, "publish_generation", blocked)
    lane = OfflineArchiveLane(tmp_path, capacity=1)
    try:
        catalog, _ = case()
        first = lane.submit(catalog)
        assert entered.wait(timeout=2)
        start = time.monotonic()
        second = lane.submit(catalog)
        third = lane.submit(catalog)
        elapsed = time.monotonic() - start
        assert second is not None and third is None
        assert elapsed < 0.5  # synthetic bounded admission, not production SLO
    finally:
        release.set()
        lane.close()
    assert first.done()
    assert second.done() and second.exception() is not None  # immutable generation
