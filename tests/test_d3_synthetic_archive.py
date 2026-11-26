"""D3-only offline acceptance; no D1/D2/Factory suite duplication."""
import copy
import pytest
from aql.d3_synthetic_archive import SparseRecord, build_catalog, verify_catalog, D3IntegrityError

A = "a" * 64
B = "b" * 64
C = "c" * 64


def fixture():
    rows = (SparseRecord(1, "CONFIRMED", A, B),
            SparseRecord(3, "WITHHELD", C),
            SparseRecord(4, "IN_DOUBT", A))
    catalog = build_catalog(generation="gen-1", consumer="sandbox", epoch=7, rows=rows)
    kwargs = dict(pinned_digest=catalog["catalog_digest"],
                  expected_generation="gen-1", expected_consumer="sandbox",
                  minimum_epoch=7, source_digests={1: A, 3: C, 4: A},
                  target_receipts={1: B})
    return catalog, kwargs


def test_sparse_verified_and_gap_not_filled():
    catalog, kwargs = fixture()
    result = verify_catalog(catalog, **kwargs)
    assert [r.sequence for r in result] == [1, 3, 4]
    assert 2 not in [r.sequence for r in result]
    assert result[1].state == "WITHHELD" and result[2].state == "IN_DOUBT"


@pytest.mark.parametrize("mutation", [
    lambda c, k: c["inventory"][0].update(state="WITHHELD"),
    lambda c, k: c["inventory"].pop(),
    lambda c, k: c.update(version="legacy-v1"),
    lambda c, k: c.update(epoch=6),
    lambda c, k: c.update(generation="rollback"),
    lambda c, k: k["target_receipts"].clear(),
    lambda c, k: k["target_receipts"].update({3: B}),
    lambda c, k: k["source_digests"].pop(4),
    lambda c, k: k.update(pinned_digest="0" * 64),
])
def test_fail_closed(mutation):
    catalog, kwargs = fixture()
    mutation(catalog, kwargs)
    with pytest.raises(D3IntegrityError):
        verify_catalog(catalog, **kwargs)


def test_cannot_confirm_without_target_receipt():
    with pytest.raises(D3IntegrityError):
        build_catalog(generation="g", consumer="c", epoch=0,
                      rows=(SparseRecord(1, "CONFIRMED", A),))


def test_duplicate_sequence_rejected():
    with pytest.raises(D3IntegrityError):
        build_catalog(generation="g", consumer="c", epoch=0,
                      rows=(SparseRecord(1, "UNKNOWN", A), SparseRecord(1, "WITHHELD", B)))


def test_catalog_does_not_mutate_evidence():
    catalog, kwargs = fixture()
    before = copy.deepcopy((catalog, kwargs))
    verify_catalog(catalog, **kwargs)
    assert (catalog, kwargs) == before
