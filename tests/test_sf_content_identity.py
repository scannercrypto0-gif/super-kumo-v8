"""Synthetic identity contracts; no market or independent-custody claim."""
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sf_research_int_01 import fixture
from research_wp_r0.content_identity import content_hash_v1, semantic_bytes_v1
from research_wp_r0.historical_library import DatasetManifest, HistoricalDataError

KW = dict(price_unit="USDT/BTC", volume_unit="BTC", session="24X7",
          normalization="NONE", adjustment="NONE")


def value():
    bars, lib, _ = fixture()
    return lib.get_manifest("BTC1M", 1), bars


def rebind(meta, bars):
    return dataclasses.replace(meta, manifest_hash=hashlib.sha256(
        "".join(b.checksum for b in bars).encode()).hexdigest())


def test_canonical_golden():
    assert semantic_bytes_v1({"b": 1.5, "a": None}) == b'["object",[["a",["null"]],["b",["float64","0x1.8000000000000p+0"]]]]'
    assert semantic_bytes_v1(-0.0) != semantic_bytes_v1(0.0)
    assert semantic_bytes_v1(1) != semantic_bytes_v1(1.0)


def test_legacy_unchanged_and_import_ids_excluded():
    m, bars = value(); before = m.to_dict()
    h = content_hash_v1(m, bars, **KW)
    other = dataclasses.replace(m, dataset_id="independent", version=8,
                                created_at_ms=m.created_at_ms+1000,
                                parent_version=7, lineage_reason="correction")
    assert h == content_hash_v1(other, bars, **KW)
    assert before == m.to_dict() and m.verify_hash(bars) and m.verify_integrity()
    assert m.manifest_integrity_hash != other.manifest_integrity_hash
    assert DatasetManifest.from_dict(before).to_dict() == before


def test_cross_process_and_golden_identity():
    m, bars = value()
    expected = content_hash_v1(m, bars, **KW)
    assert expected == "cdd7a7df4dafb3217999ae16f2edfcdb77cc8eadefd99a060762690cf080f0bd"
    code = '''import sys;sys.path.insert(0,'tests')
from test_sf_content_identity import value, KW
from research_wp_r0.content_identity import content_hash_v1
m,b=value();print(content_hash_v1(m,b,**KW))'''
    results = [subprocess.check_output([sys.executable, "-B", "-c", code],
                cwd=Path(__file__).resolve().parents[1], text=True).strip() for _ in range(2)]
    assert results == [expected, expected]


@pytest.mark.parametrize("field,new", [
    ("exchange", "other"), ("market", "perp"), ("timezone", "other"),
    ("source_label", "other"), ("source_hash", "a"*64),
    ("gap_bar_opens", (123,)), ("gap_count", 1), ("coverage_pct", 50.0),
    ("duplicate_count", 1), ("non_final_count", 1),
])
def test_manifest_provenance_sensitivity(field, new):
    m,b=value()
    assert content_hash_v1(m,b,**KW) != content_hash_v1(dataclasses.replace(m,**{field:new}),b,**KW)


@pytest.mark.parametrize("field,new", [
    ("open", 99.), ("high", 102.), ("low", 98.), ("close", 100.25),
    ("volume", 22.), ("ingest_time_ms", None),
    ("observation_cutoff_ms", 1700000000123), ("source_label", "other"),
])
def test_bar_sensitivity(field,new):
    m,b=value(); changed=list(b); changed[0]=dataclasses.replace(b[0],**{field:new})
    assert content_hash_v1(m,b,**KW) != content_hash_v1(rebind(m,changed),changed,**KW)


@pytest.mark.parametrize("field", list(KW))
def test_units_and_policy_sensitivity(field):
    m,b=value(); kw=dict(KW);kw[field]="other"
    assert content_hash_v1(m,b,**KW) != content_hash_v1(m,b,**kw)


@pytest.mark.parametrize("mode", ["partial", "reorder", "duplicate", "bar_tamper", "manifest_tamper", "legacy"])
def test_fail_closed(mode):
    m,b=value(); b=list(b)
    if mode=="partial": b.pop()
    if mode=="reorder": b.reverse()
    if mode=="duplicate": b[1]=b[0]
    if mode=="bar_tamper": object.__setattr__(b[0],"close",999)
    if mode=="manifest_tamper": object.__setattr__(m,"market","tamper")
    if mode=="legacy":
        raw=m.to_dict();raw.pop("manifest_integrity_hash");m=DatasetManifest.from_dict(raw)
    with pytest.raises(HistoricalDataError): content_hash_v1(m,b,**KW)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), object()])
def test_noncanonical_rejected(bad):
    with pytest.raises(ValueError):semantic_bytes_v1(bad)
