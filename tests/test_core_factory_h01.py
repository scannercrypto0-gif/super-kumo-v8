"""H01 delta only: reuse existing binder fixtures, exact isolated dependencies."""
import copy
import importlib
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_core_dev_factory_binder import (
    arguments, canonical, sha, START, STEP, factory148, inspector157,
    bind_dev, verify_candidate, BinderError, SyntheticCandidate,
)
from aql.historical.dev_source import import_bytes
from aql.historical.dev_factory_binder import SCHEMA, FACTORY_SHA, INSPECTOR_SHA, FACTORY_COMPATIBILITY

OLD = "dee0f088d70122d143118df2e0a0549a564f2380"
CURRENT = "eacb5e50150c6e6c64c8a41b8eaa410aebd71532"
QUALITY = "b8e4c3e9fece8f66f0614041637640c9849e02b3"


@pytest.fixture(scope="module")
def quality150():
    # Mandatory for this targeted integration gate: never skip a missing node.
    root = Path(os.environ["FACTORY150_ROOT"])
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() == QUALITY
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
    package = types.ModuleType("_h01_quality150")
    package.__path__ = [str(root / "research_wp_r0")]
    sys.modules[package.__name__] = package
    return importlib.import_module(package.__name__ + ".historical_input_quality")


def reviewed(args, inspector):
    history = import_bytes(args["envelope"], args["raw"])
    seven = [[b.bar_open,b.bar_close,b.open,b.high,b.low,b.close,b.volume] for b in history.bars]
    static = inspector.inspect_source(history.envelope.spec, history.receipt, seven,
        expected=dict(source_id=history.envelope.source_id, archive_sha256=args["raw_pin"].sha256,
                      archive_size=len(args["raw"]), normalized7_sha256=sha(canonical(seven)),
                      core_receipt_sha256=sha(canonical(history.receipt))),
        declarations=dict(availability="UNKNOWN", correction_timing="UNKNOWN", bounded_UTC="UNKNOWN",
                          independent_custody="UNKNOWN", available_ms=None, modeled_quote=None,
                          verified_source_timing=False, real_pit_accepted=False))
    return {**args, "inspector_decision": dict(code_sha=INSPECTOR_SHA,payload=static.payload)}, static


def test_current_version_acceptance_and_current_engine_validation(factory148):
    assert FACTORY_SHA == CURRENT and SCHEMA == "core-factory-dev-map-2"
    c = bind_dev(**arguments(), factory_sha=CURRENT)
    assert c.package["factory_compatibility"] == FACTORY_COMPATIBILITY
    assert verify_candidate(c)
    factory148._validate(c.rows,c.source,factory148.Config())
    assert c.source["rows_sha256"] == factory148.digest(c.rows)


@pytest.mark.parametrize("pin", [OLD, "0"*40, CURRENT+"x"])
def test_stale_or_unsupported_target_refused(pin):
    with pytest.raises(BinderError, match="CODE_VERSION"):
        bind_dev(**arguments(), factory_sha=pin)


@pytest.mark.parametrize("key,value", [("schema","core-factory-dev-map-1"), ("factory_sha",OLD),
                                        ("factory_compatibility","unreviewed")])
def test_even_rehashed_unsupported_candidate_refused(key,value):
    p = bind_dev(**arguments()).package
    p[key] = value
    body = {k:v for k,v in p.items() if k not in ("factory_source","mapping_sha256")}
    p["mapping_sha256"] = sha(canonical(body))
    p["factory_source"]["version"] = SCHEMA+":"+p["mapping_sha256"]
    with pytest.raises(BinderError, match="CANDIDATE_INTEGRITY"):
        verify_candidate(SyntheticCandidate(canonical(p)))


@pytest.mark.parametrize("field", ["raw","issued_receipt"])
def test_byte_tamper_at_new_target(field):
    args = arguments(); args[field] += b"tampered"
    with pytest.raises(BinderError, match="BYTE_INTEGRITY"):
        bind_dev(**args, factory_sha=CURRENT)


def test_new_target_inspector_receipt_binding(inspector157):
    args,static = reviewed(arguments(),inspector157)
    c = bind_dev(**args)
    assert c.package["inspector_decision"]["receipt_sha256"] == static.receipt_sha256
    bad = static.spec; bad["record_count"] += 1
    args["inspector_decision"]["payload"] = canonical(bad)
    with pytest.raises(BinderError,match="FACTORY_INSPECTOR_PENDING"):
        bind_dev(**args)


@pytest.mark.parametrize("path", ["FACTUAL","TARGET_FIRST","STOP_FIRST"])
def test_bound_current_unknown_entry_masks_policy_preserves_conditional_cash(factory148,path):
    c = bind_dev(**arguments(quoted=False))
    signals = [dict(bar_open_ms=b["open_ms"], action="ENTER_LONG", available_ms=b["available_ms"])
               for b in c.rows[:2]]
    r = factory148.replay_contract_fixture(c.rows,source=c.source,signals=signals,
                                          config=factory148.Config(latency_ms=0))
    p = r["paths"][path]
    assert p["opportunities"][0]["status"] == "UNKNOWN_ENTRY_QUOTE"
    assert p["opportunities"][1]["status"] == "BLOCKED_PRIOR_UNKNOWN"
    assert p["cash"] == 1000 and p["held_quantity"] == 0 and p["known_realized_pnl"] == 0
    assert p["scheduled_denominator"] == 2
    assert all(p[k] is None for k in ("realized_pnl","settled_equity","modeled_equity_return","sampled_mtm_drawdown"))
    assert factory148.verify_receipt(r)


def test_bound_current_three_paths_stay_separate(factory148):
    c = bind_dev(**arguments(quoted=True))
    signals = [dict(bar_open_ms=c.rows[0]["open_ms"],action="ENTER_LONG",available_ms=c.rows[0]["available_ms"])]
    r = factory148.replay_contract_fixture(c.rows,source=c.source,signals=signals,
        config=factory148.Config(latency_ms=0,tp_fraction=.1,sl_fraction=.1,fee_bps=0,spread_bps=0,slippage_bps=0))
    f,t,s = [r["paths"][p] for p in factory148.PATHS]
    assert f["realized_pnl"] is None and t["known_realized_pnl"] > 0 and s["known_realized_pnl"] < 0
    assert factory148.verify_receipt(r)
    altered = copy.deepcopy(r); altered["paths"]["FACTUAL"]["cash"] += 1
    assert not factory148.verify_receipt(altered)


@pytest.mark.parametrize("lag", [0,17])
def test_current_mapping_cutoff_availability(lag,factory148):
    args = arguments(count=30,lag=lag)
    c = bind_dev(**args)
    for s in factory148._signals(c.rows,factory148.Config()):
        assert s["available_ms"] == max(b["available_ms"] for b in c.rows if b["open_ms"] <= s["bar_open_ms"])
    args["decision_cutoff_ms"] -= 1
    with pytest.raises(ValueError, match="LOOKAHEAD"):
        bind_dev(**args)


def test_full_five_node_synthetic_link_and_deterministic_replay(factory148,inspector157,quality150):
    args,static = reviewed(arguments(count=30,lag=17,quoted=False),inspector157)
    provenance = dict(observed_at_ms=None,publisher_available_at_ms=None,first_known_at_ms=None,vintage_id=None,
        supersedes_version=None,correction_history_ref=None,independent_utc_ref=None,independent_anchor_ref=None,
        source_ack_ref=None,target_ack_ref=None,verified_source_timing=False,real_pit_accepted=False)
    spec = quality150.HistoricalInputSpec(dict(schema="historical-input-quality-1",scope="DEV_INPUT_QUALITY_ONLY",
        provider="SYNTHETIC",venue="SPOT",symbol="BTCUSDT",timeframe="1m",timezone="UTC",price_unit="SYNTH_QUOTE",
        volume_unit="SYNTH_BASE",source_uri=args["raw_pin"].reference,license_reference="SYNTHETIC_TEST_ONLY",
        container="CSV",csv_format="NORMALIZED_7",timestamp_unit="ms",member_name=None,
        version_sha256=args["raw_pin"].sha256,publisher_checksum_sha256=None,start_ms=START,
        end_exclusive_ms=START+30*STEP,review_cutoff_ms=args["decision_cutoff_ms"],provenance=provenance))
    q = quality150.inspect_historical_input(args["raw"],spec,expected_spec_digest=spec.digest)
    assert q.spec["quality_status"] == "SOURCE_QUALITY_ACCEPTED"
    assert static.spec["source_quality"] == "PASS_SOURCE_QUALITY"
    c = bind_dev(**args,factory_sha=CURRENT)
    r = factory148.replay(c.rows,source=c.source,config=factory148.Config(latency_ms=1))
    assert r == factory148.replay(c.rows,source=c.source,config=factory148.Config(latency_ms=1))
    assert factory148.verify_receipt(r) and verify_candidate(c)
    assert all(v is False for v in c.package["claims"].values())
    assert all(v is False for v in r["claims"].values())
    assert c.package["inspector_decision"]["receipt_sha256"] == static.receipt_sha256
    # Quality163 is an independent source-quality result, not a substitute for162.
    with pytest.raises(BinderError,match="FACTORY_INSPECTOR_PENDING"):
        bind_dev(**{**args,"inspector_decision":dict(code_sha=QUALITY,payload=q.payload)})
    with pytest.raises(BinderError,match="FACTORY_INSPECTOR_PENDING"):
        bind_dev(**{**args,"mode":"REAL_SOURCE"})
