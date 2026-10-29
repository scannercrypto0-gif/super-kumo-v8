"""Only changed REALDEV guard/contract tests; no market bytes in public tests."""
from dataclasses import replace
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from aql.historical.realdev_integration import (
    RuntimePin, IntegrationCapability, IntegrationDenied, validate_capability,
    validate_receipt, inspect_local_pair, read_pinned_file, sha,
    EXPERIMENT, OWNER_SCOPE, RAW_SHA, RECEIPT_SHA, START, END,
    SCHEMA, FACTORY_SHA, FACTORY_COMPATIBILITY, IntegrationReport, replay_local_report,
)


def capability():
    runtime = RuntimePin("synthetic-host", "synthetic-user", "synthetic-python", "3.12", "fixture", "a"*40)
    return IntegrationCapability(EXPERIMENT, "DEV_INTEGRATION_ONLY", OWNER_SCOPE, runtime,
        RAW_SHA, RECEIPT_SHA, SCHEMA, FACTORY_SHA, FACTORY_COMPATIBILITY, START, END, END, 22)


def receipt_fixture():
    """Synthetic schema fixture, NEVER serialized/labeled as original Work152."""
    return dict(schema="aql-work152-artifact-handoff-receipt-1",
        receipt_id="AQL-CORE-WORK152-BTCUSDT-20240101-001", scope="REAL_SOURCE_DEV_ONLY",
        source_id="binance-vision:spot:BTCUSDT:1m:2024-01-01", payload_version_id="sha256:"+sha(b"fixture"),
        artifact=dict(file_size_bytes=7, file_id="file_00000000084c8208b5d65c8fc803426c",
                      library_file_id="libfile_ae3ca38f8b288191a4c2ee4ea3139292", current_version_number=0),
        acquisition=dict(archive=dict(sha256=sha(b"fixture"),size_bytes=7)),
        normalization=dict(receipt=dict(archive_sha256=sha(b"fixture"),symbol="BTCUSDT",interval_ms=60000,
            first_open_ms=START,last_open_ms=END-60000,count=1440,gap_count=0)),
        correction_history="UNKNOWN",historical_first_known_at=None,issuer_first_available_at=None,
        utc_bound_ms=None,independent_custody="UNVERIFIED",verified_source_timing=False,
        real_pit_accepted=False,empirical_eligible=False)


def test_in_memory_synthetic_contract_positive():
    c = capability()
    validate_capability(c,c.runtime,"DEV_INTEGRATION_ONLY")
    r = receipt_fixture(); before = copy.deepcopy(r)
    validate_receipt(r,raw_sha=sha(b"fixture"),raw_size=7,pinned_original=False)
    assert r == before


@pytest.mark.parametrize("scope_name", ["REAL_SOURCE", "EXECUTE", "PIT", "OOS", "PAPER", "LIVE", "Guardian", ""])
def test_no_scope_elevation_even_without_files(scope_name):
    with pytest.raises(IntegrationDenied,match="DEFAULT_DENY"):
        inspect_local_pair("missing.zip","missing.json",checkout=ROOT,capability=capability(),request=scope_name)


def test_no_capability_or_implicit_opt_in():
    with pytest.raises(IntegrationDenied,match="DEFAULT_DENY"):
        inspect_local_pair("missing","missing",checkout=ROOT)
    with pytest.raises(IntegrationDenied,match="CAPABILITY"):
        inspect_local_pair("missing","missing",checkout=ROOT,request="DEV_INTEGRATION_ONLY")


@pytest.mark.parametrize("field,value", [
    ("experiment_id", ""), ("permission", "EXECUTE"), ("owner_scope", "unsigned:approved=True"),
    ("raw_sha256", "b"*64), ("receipt_sha256", "b"*64),
    ("mapping_schema", "core-factory-dev-map-1"), ("factory_sha", "old"),
    ("compatibility_profile", "other"), ("prefix_start_ms", None),
    ("prefix_start_ms", START+60000), ("prefix_end_ms_exclusive", END+60000),
    ("decision_cutoff_ms", END-1), ("decision_cutoff_ms", None),
    ("warmup_bars", None), ("warmup_bars", 21), ("warmup_bars", True),
])
def test_contract_refusal(field,value):
    c = capability()
    with pytest.raises(IntegrationDenied):
        validate_capability(replace(c,**{field:value}),c.runtime,"DEV_INTEGRATION_ONLY")


@pytest.mark.parametrize("field", ["host","account","python","python_version","checkout","head"])
def test_wrong_or_stale_runtime_and_head(field):
    c=capability()
    with pytest.raises(IntegrationDenied,match="STALE_RUNTIME"):
        validate_capability(c,replace(c.runtime,**{field:"wrong"}),"DEV_INTEGRATION_ONLY")


@pytest.mark.parametrize("domain", ["ZIP","ISSUED_RECEIPT"])
def test_fresh_read_tampered_or_missing_bytes(tmp_path,domain):
    p=tmp_path/domain
    with pytest.raises(IntegrationDenied,match="MISSING"):
        read_pinned_file(p,7,sha(b"fixture"))
    p.write_bytes(b"fixture")
    raw,observed=read_pinned_file(p,7,sha(b"fixture"))
    assert raw==b"fixture" and observed["sha256"]==sha(raw)
    p.write_bytes(b"altered")
    with pytest.raises(IntegrationDenied,match="INTEGRITY"):
        read_pinned_file(p,7,sha(b"fixture"))


@pytest.mark.parametrize("field,value", [("schema","wrong"),("source_id","wrong"),
    ("payload_version_id","sha256:wrong"),("correction_history","ORIGINAL"),
    ("verified_source_timing",True),("real_pit_accepted",True),
    ("historical_first_known_at",START),("utc_bound_ms",0)])
def test_receipt_conflicts_or_false_pit_rejected(field,value):
    r=receipt_fixture();r[field]=value
    with pytest.raises(IntegrationDenied):
        validate_receipt(r,raw_sha=sha(b"fixture"),raw_size=7,pinned_original=False)


@pytest.mark.parametrize("section", ["artifact","normalization","acquisition"])
def test_missing_version_quality_or_chronology(section):
    r=receipt_fixture();del r[section]
    with pytest.raises(IntegrationDenied):
        validate_receipt(r,raw_sha=sha(b"fixture"),raw_size=7,pinned_original=False)


def test_synthetic_receipt_cannot_impersonate_original_pin():
    with pytest.raises(IntegrationDenied,match="ORIGINAL_SOURCE_ONLY"):
        validate_receipt(receipt_fixture(),raw_sha=sha(b"fixture"),raw_size=7,pinned_original=True)


def test_existing_real_source_guard_unchanged():
    from aql.historical.dev_factory_binder import bind_dev
    # Independent source inspection, no H01 suite replay or fake approval flags.
    import inspect
    assert 'if mode == "REAL_SOURCE":' in inspect.getsource(bind_dev)


def test_bad_report_commitment_cannot_be_a_readback():
    r=IntegrationReport(b'{}')
    with pytest.raises(IntegrationDenied,match="REPORT_COMMITMENT"):
        replay_local_report(r,expected_digest="b"*64)
