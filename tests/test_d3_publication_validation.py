"""Regression: publication rejects malformed inventory before creating any files."""
import pytest

from aql.d3_offline_archive import publish_generation
from aql.d3_synthetic_archive import D3IntegrityError, SparseRecord, build_catalog


def test_reject_tampered_catalog_without_partial_files(tmp_path):
    catalog = build_catalog(generation="g1", consumer="test", epoch=1,
                            rows=(SparseRecord(1, "UNKNOWN", "a" * 64),))
    catalog["inventory"][0]["state"] = "CONFIRMED"
    with pytest.raises(D3IntegrityError):
        publish_generation(tmp_path, catalog)
    assert list(tmp_path.iterdir()) == []


def test_reject_v1_v2_mixed_catalog_without_partial_files(tmp_path):
    catalog = build_catalog(generation="g2", consumer="test", epoch=1, rows=())
    catalog["version"] = "AQL-D3-SYNTHETIC-V2"
    with pytest.raises(D3IntegrityError):
        publish_generation(tmp_path, catalog)
    assert list(tmp_path.iterdir()) == []
