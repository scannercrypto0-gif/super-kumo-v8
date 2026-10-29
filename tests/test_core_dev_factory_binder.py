"""Synthetic bytes/policies only. No actual private source or performance study."""
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from aql.historical.dev_source import DevSourceEnvelope, DevSourceError
from aql.historical.dev_factory_binder import (
    ArtifactPin, BinderError, CORE_SHA, FACTORY_SHA, INSPECTOR_SHA, LagPolicy, QuotePolicy,
    SyntheticCandidate, bind_dev, measure_readback, verify_candidate,
)

START = 1704067200000
STEP = 60000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def arguments(count=4, lag=0, quoted=False):
    raw = "\n".join(f"{START+i*STEP},{START+(i+1)*STEP-1},10,12,9,11,2"
                    for i in range(count)).encode()
    raw_pin = ArtifactPin("fixture:only:مصدر", "fixture-v1", len(raw), sha(raw))
    # This is a synthetic issued receipt, NOT fabricated Work152 bytes.
    receipt = canonical({"schema": "synthetic-receipt-1", "raw_sha256": sha(raw)})
    receipt_pin = ArtifactPin("fixture:receipt", "fixture-v1", len(receipt), sha(receipt))
    envelope = DevSourceEnvelope({
        "schema": "core-dev-source-1", "scope": "DEV_ONLY", "origin": "SYNTHETIC",
        "market": "SPOT", "symbol": "BTCUSDT", "interval": "1m", "start_ms": START,
        "end_ms_exclusive": START+count*STEP, "bytes_ref": raw_pin.reference,
        "archive_sha256": raw_pin.sha256, "archive_size": raw_pin.size_bytes,
        "format": "canonical-csv-7-v1", "member": None,
        "checksum_provenance": "SYNTHETIC_FIXTURE", "normalization": "ohlcv-ms-float64-grid-1",
        "source_version": "UNKNOWN", "correction_status": "UNKNOWN",
        "issuer_first_available_at": "UNKNOWN", "bounded_UTC": "UNKNOWN", "independent_custody": "UNKNOWN",
    })
    return dict(envelope=envelope, raw=raw, raw_pin=raw_pin, issued_receipt=receipt,
                receipt_pin=receipt_pin, recipient_ack=measure_readback(
                    raw, receipt, raw_pin=raw_pin, receipt_pin=receipt_pin,
                    consumer_task="synthetic-test159", environment="offline-fixture"),
                consumer_task="synthetic-test159", environment="offline-fixture",
                lag_policy=LagPolicy("retrospective-close-plus-lag-1", "fixture-lag-1", lag,
                                     "fixture:owner-lag", "fixture:review-lag", True),
                quote_policy=QuotePolicy("hypothetical-ohlcv-quote-1", "fixture-quote-1", quoted,
                                         "fixture:owner-quote", "fixture:review-quote", True),
                decision_cutoff_ms=START+count*STEP+lag, mode="SYNTHETIC_CONTRACT_TEST")


def test_exact_mapping_four_distinct_digest_domains_and_stability():
    args = arguments(lag=17)
    result = bind_dev(**args)
    p = result.package
    rows = result.rows
    assert rows[0] == dict(open_ms=START, close_ms=START+STEP-1, open=10., high=12.,
                           low=9., close=11., volume=2., available_ms=START+STEP+17,
                           modeled_quote=False)
    seven = [[r[k] for k in ("open_ms", "close_ms", "open", "high", "low", "close", "volume")]
             for r in rows]
    assert p["raw_archive"]["sha256"] == sha(args["raw"])
    assert p["issued_receipt"]["sha256"] == sha(args["issued_receipt"])
    assert p["normalized_seven_field"]["sha256"] == sha(canonical(seven))
    assert p["normalized_seven_field"]["size_bytes"] == len(canonical(seven))
    assert p["factory_dictionary_rows"]["sha256"] == sha(canonical(rows))
    assert p["factory_dictionary_rows"]["size_bytes"] == len(canonical(rows))
    assert len({p["raw_archive"]["sha256"], p["issued_receipt"]["sha256"],
                p["normalized_seven_field"]["sha256"], p["factory_dictionary_rows"]["sha256"]}) == 4
    assert bind_dev(**args).payload == result.payload
    assert verify_candidate(result)
    assert b"\\u0645" in result.payload  # actual pinned Factory ASCII escaping
    assert result.source["rows_sha256"] == p["factory_dictionary_rows"]["sha256"]
    assert result.source["correction_evidence"] == "PINNED_VERSION_ONLY"
    assert all(v is False for v in p["claims"].values())
    assert all(p[k] == "UNKNOWN" for k in ("source_version", "issuer_first_available_at",
                                          "correction_status", "availability_evidence"))
    rows[0]["open"] = 999
    assert result.rows[0]["open"] == 10


@pytest.mark.parametrize("change,category", [
    ({"raw": None}, "MISSING_BYTES"), ({"issued_receipt": None}, "MISSING_BYTES"),
    ({"raw": b"bad"}, "BYTE_INTEGRITY"), ({"issued_receipt": b"bad"}, "BYTE_INTEGRITY"),
    ({"recipient_ack": None}, "RECIPIENT_ACK"), ({"consumer_task": "owner-work153"}, "RECIPIENT_ACK"),
    ({"environment": "another-session"}, "RECIPIENT_ACK"),
    ({"lag_policy": None}, "MODEL_APPROVAL"), ({"quote_policy": None}, "MODEL_APPROVAL"),
    ({"decision_cutoff_ms": START}, "LOOKAHEAD"), ({"decision_cutoff_ms": True}, "LOOKAHEAD"),
    ({"decision_cutoff_ms": 2**53}, "LOOKAHEAD"),
    ({"mode": "PAPER"}, "MODE"), ({"core_sha": "wrong"}, "CODE_VERSION"),
    ({"factory_sha": "wrong"}, "CODE_VERSION"), ({"require_pit": True}, "PIT_QUALIFICATION"),
    ({"require_pit": 0}, "PIT_QUALIFICATION"),
    ({"inspector_decision": {"accepted": True}}, "FACTORY_INSPECTOR_PENDING"),
])
def test_fail_closed_inputs(change, category):
    args = arguments()
    args.update(change)
    with pytest.raises((BinderError, DevSourceError), match=category):
        bind_dev(**args)


@pytest.mark.parametrize("field,value", [("schema", "new"), ("lag_ms", -1), ("lag_ms", True),
    ("lag_ms", float("nan")), ("lag_ms", 2**53), ("approved", False), ("approved", 1),
    ("version", ""), ("owner_decision_ref", " "), ("council_review_ref", "")])
def test_explicit_lag_approval_and_version(field, value):
    with pytest.raises(BinderError, match="LAG_POLICY"):
        replace(arguments()["lag_policy"], **{field: value})


@pytest.mark.parametrize("field,value", [("schema", "observed-bid-ask"), ("modeled_quote", None),
    ("modeled_quote", 1), ("approved", False), ("approved", 1), ("version", ""),
    ("owner_decision_ref", ""), ("council_review_ref", "")])
def test_separate_quote_approval(field, value):
    with pytest.raises(BinderError, match="QUOTE_POLICY"):
        replace(arguments()["quote_policy"], **{field: value})


def test_raw_receipt_versions_and_identity_are_bound():
    args = arguments()
    original = bind_dev(**args)
    args["receipt_pin"] = replace(args["receipt_pin"], version="fixture-v2")
    with pytest.raises(BinderError, match="RECIPIENT_ACK"):
        bind_dev(**args)
    args["recipient_ack"] = replace(args["recipient_ack"], receipt=args["receipt_pin"])
    changed = bind_dev(**args)
    assert changed.rows == original.rows
    assert changed.package["mapping_sha256"] != original.package["mapping_sha256"]
    args["raw_pin"] = replace(args["raw_pin"], reference="different:source")
    with pytest.raises(BinderError, match="SOURCE_IDENTITY"):
        bind_dev(**args)


@pytest.mark.parametrize("field,value", [("sha256", "ABC"), ("size_bytes", True),
    ("size_bytes", 0), ("version", ""), ("reference", None)])
def test_invalid_artifact_pin(field, value):
    with pytest.raises(BinderError, match="ARTIFACT_PIN"):
        replace(arguments()["raw_pin"], **{field: value})


def test_real_admission_cannot_be_unlocked_by_owner_ack_or_invented_inspector():
    args = arguments()
    args["mode"] = "REAL_SOURCE"
    # Even a measured ACK and supplied policies cannot create the missing API/SR.
    for decision in (None, {"accepted": True, "schema": "invented150"}):
        with pytest.raises(BinderError, match="FACTORY_INSPECTOR_PENDING"):
            bind_dev(**args, inspector_decision=decision)
    args["mode"] = "SYNTHETIC_CONTRACT_TEST"
    args["envelope"] = DevSourceEnvelope({**args["envelope"].spec, "origin": "BINANCE_VISION"})
    with pytest.raises(BinderError, match="SYNTHETIC_SCOPE"):
        bind_dev(**args)


def test_lag_cutoff_boundary_no_truncation_or_future_bars():
    args = arguments(lag=17)
    assert bind_dev(**args).rows[-1]["available_ms"] == args["decision_cutoff_ms"]
    args["decision_cutoff_ms"] -= 1
    with pytest.raises(BinderError, match="LOOKAHEAD"):
        bind_dev(**args)
    args = arguments(lag=2**53-1)
    args["decision_cutoff_ms"] = 2**53-1
    with pytest.raises(BinderError, match="LOOKAHEAD"):
        bind_dev(**args)


@pytest.mark.parametrize("transform", [
    lambda raw: raw.replace(str(START+STEP).encode(), str(START).encode(), 1),
    lambda raw: raw.replace(b",12,", b",1,", 1),
    lambda raw: raw.replace(b",10,", b",nan,", 1),
    lambda raw: raw.split(b"\n", 1)[1],
    lambda raw: raw.replace(b",10,12,9,11,", b",0.0000000000001,0.0000000000002,0.00000000000009,0.00000000000011,", 1),
])
def test_reuses_core_grid_quality_and_factory_price_domain(transform):
    args = arguments()
    args["raw"] = transform(args["raw"])
    pin = replace(args["raw_pin"], size_bytes=len(args["raw"]), sha256=sha(args["raw"]))
    args["raw_pin"] = pin
    args["recipient_ack"] = replace(args["recipient_ack"], raw=pin)
    args["envelope"] = DevSourceEnvelope({**args["envelope"].spec, "archive_size": pin.size_bytes,
                                          "archive_sha256": pin.sha256})
    with pytest.raises((DevSourceError, BinderError), match="SOURCE_QUALITY|FACTORY_PRICE_DOMAIN"):
        bind_dev(**args)


def test_policy_changes_recommit_rows_without_relabeling_provenance():
    a, b, c = (bind_dev(**arguments(lag=lag, quoted=quote)) for lag, quote in
               [(0, False), (1, False), (1, True)])
    assert len({r.package["mapping_sha256"] for r in (a, b, c)}) == 3
    assert len({r.source["rows_sha256"] for r in (a, b, c)}) == 3
    assert len({r.package["normalized_seven_field"]["sha256"] for r in (a, b, c)}) == 1
    assert all(r.source["availability_evidence"] == "UNKNOWN" for r in (a, b, c))


@pytest.mark.parametrize("field", ["rows", "claims", "lag_policy", "factory_source", "mapping_sha256"])
def test_candidate_tamper_is_detected(field):
    p = bind_dev(**arguments()).package
    if field == "rows":
        p[field][0]["available_ms"] += 1
    elif field == "claims":
        p[field]["real_pit_accepted"] = True
    elif field == "lag_policy":
        p[field]["version"] = "tampered"
    elif field == "factory_source":
        p[field]["rows_sha256"] = "0"*64
    else:
        p[field] = "0"*64
    with pytest.raises(BinderError, match="CANDIDATE_INTEGRITY"):
        verify_candidate(SyntheticCandidate(canonical(p)))


@pytest.fixture(scope="module")
def factory148():
    location = os.environ.get("FACTORY148_ROOT")
    if not location:
        pytest.skip("optional exact Factory148 checkout; focused CI supplies it")
    root = Path(location).resolve()
    import subprocess
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    assert head == FACTORY_SHA
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "research_wp_r0"], cwd=root, check=True)
    data = (root / "research_wp_r0" / "historical_dev_exits_v1.py").read_bytes()
    # Git working-tree CRLF can differ; commit blob is authoritative.
    blob = subprocess.check_output(["git", "rev-parse", "HEAD:research_wp_r0/historical_dev_exits_v1.py"],
                                   cwd=root, text=True).strip()
    assert blob == "bbeae9d7f16f4d2b0738072ec35ea4dd9345639b"
    assert data
    package = types.ModuleType("_binder159_factory148")
    package.__path__ = [str(root / "research_wp_r0")]
    sys.modules[package.__name__] = package
    return importlib.import_module(package.__name__ + ".historical_dev_exits_v1")


@pytest.fixture(scope="module")
def inspector157():
    location = os.environ.get("FACTORY157_ROOT")
    if not location:
        pytest.skip("optional exact157 checkout; focused CI supplies it")
    root = Path(location).resolve()
    import subprocess
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() == INSPECTOR_SHA
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "research_wp_r0"], cwd=root, check=True)
    package = types.ModuleType("_binder159_inspector157")
    package.__path__ = [str(root / "research_wp_r0")]
    sys.modules[package.__name__] = package
    return importlib.import_module(package.__name__ + ".post149_source_readiness")


def test_actual157_static_inspector_binding_and_conflicts(inspector157):
    from aql.historical.dev_source import import_bytes
    args = arguments()
    history = import_bytes(args["envelope"], args["raw"])
    normalized = [[b.bar_open, b.bar_close, b.open, b.high, b.low, b.close, b.volume]
                  for b in history.bars]
    expected = dict(source_id=history.envelope.source_id, archive_sha256=args["raw_pin"].sha256,
                    archive_size=len(args["raw"]), normalized7_sha256=sha(canonical(normalized)),
                    core_receipt_sha256=sha(canonical(history.receipt)))
    declarations = dict(availability="UNKNOWN", correction_timing="UNKNOWN", bounded_UTC="UNKNOWN",
                        independent_custody="UNKNOWN", available_ms=None, modeled_quote=None,
                        verified_source_timing=False, real_pit_accepted=False)
    review = inspector157.inspect_source(history.envelope.spec, history.receipt, normalized,
                                          expected=expected, declarations=declarations)
    decision = {"code_sha": INSPECTOR_SHA, "payload": review.payload}
    plain = bind_dev(**args)
    bound = bind_dev(**args, inspector_decision=decision)
    assert bound.rows == plain.rows
    assert bound.package["mapping_sha256"] != plain.package["mapping_sha256"]
    assert bound.package["inspector_decision"]["receipt_sha256"] == review.receipt_sha256
    assert bound.package["inspector_decision"]["receipt"]["factory_execution_eligible"] is False
    assert verify_candidate(bound)
    for field, value in [("factory_execution_eligible", True), ("record_count", 999),
                          ("consumer_status", "ACKNOWLEDGED"), ("real_pit_accepted", 0)]:
        bad = {**review.spec, field: value}
        with pytest.raises(BinderError, match="FACTORY_INSPECTOR_PENDING"):
            bind_dev(**args, inspector_decision={"code_sha": INSPECTOR_SHA, "payload": canonical(bad)})
    with pytest.raises(BinderError, match="FACTORY_INSPECTOR_PENDING"):
        bind_dev(**args, inspector_decision={"code_sha": "wrong", "payload": review.payload})
    with pytest.raises(BinderError, match="FACTORY_INSPECTOR_PENDING"):
        bind_dev(**{**args, "mode": "REAL_SOURCE"}, inspector_decision=decision)


def test_actual_pinned_factory_validator_and_digest(factory148):
    candidate = bind_dev(**arguments())
    factory148._validate(candidate.rows, candidate.source, factory148.Config())
    assert factory148.digest(candidate.rows) == candidate.source["rows_sha256"]
    assert factory148.digest({"ref": "مصدر"}) == sha(canonical({"ref": "مصدر"}))
    bad = candidate.rows
    bad[0]["available_ms"] = START
    with pytest.raises(ValueError, match="MISSING_AVAILABILITY"):
        factory148._validate(bad, {**candidate.source, "rows_sha256": factory148.digest(bad)},
                             factory148.Config())


@pytest.mark.parametrize("lag,latency,offset", [(0, 0, STEP), (0, 1, STEP*2), (1, 0, STEP*2)])
def test_synthetic_factory_scheduling_and_unknown_quotes(factory148, lag, latency, offset):
    candidate = bind_dev(**arguments(lag=lag, quoted=False))
    row = candidate.rows[0]
    receipt = factory148.replay_contract_fixture(candidate.rows, source=candidate.source,
        signals=[{"bar_open_ms": START, "action": "ENTER_LONG", "available_ms": row["available_ms"]}],
        config=factory148.Config(latency_ms=latency, checkpoint_ms=START+4*STEP))
    for path in receipt["paths"].values():
        opportunity = path["opportunities"][0]
        assert opportunity["scheduled_ms"] == START+offset
        assert opportunity["status"] == "UNKNOWN_ENTRY_QUOTE"
        assert opportunity["scored_return"] is None
        assert path["scheduled_denominator"] == 1
        assert path["held_quantity"] == 0
    assert all(value is False for value in receipt["claims"].values())
    assert factory148.verify_receipt(receipt)


@pytest.mark.parametrize("last,latency,expected", [
    (False, STEP+1, "STALE_INDICATOR"), (True, 0, "UNKNOWN_NO_ELIGIBLE_OPEN")])
def test_synthetic_stale_and_missing_open_keep_unknown_denominator(factory148, last, latency, expected):
    candidate = bind_dev(**arguments(quoted=True))
    row = candidate.rows[-1 if last else 0]
    receipt = factory148.replay_contract_fixture(candidate.rows, source=candidate.source,
        signals=[{"bar_open_ms": row["open_ms"], "action": "ENTER_LONG",
                  "available_ms": row["available_ms"]}],
        config=factory148.Config(latency_ms=latency, max_signal_age_ms=STEP))
    for path in receipt["paths"].values():
        assert path["scheduled_denominator"] == 1
        assert path["opportunities"][0]["status"] == expected
        assert path["opportunities"][0]["scored_return"] is None
        assert path["held_quantity"] == 0


def test_synthetic_three_paths_receipt_conservation_and_tamper(factory148):
    candidate = bind_dev(**arguments(quoted=True))
    receipt = factory148.replay_contract_fixture(candidate.rows, source=candidate.source,
        signals=[{"bar_open_ms": b["open_ms"], "action": action, "available_ms": b["available_ms"]}
                 for b, action in zip(candidate.rows[:2], ["ENTER_LONG", "EXIT_LONG"])],
        config=factory148.Config(latency_ms=0))
    for path in receipt["paths"].values():
        assert path["scheduled_denominator"] == 2
        assert path["held_quantity"] == 0
        assert path["cash"] == pytest.approx(1000+path["known_realized_pnl"])
        assert all(e["actual_fill"] is False for e in path["ledger"] if "actual_fill" in e)
    assert factory148.verify_receipt(receipt)
    receipt["input_rows"][0]["modeled_quote"] = False
    assert not factory148.verify_receipt(receipt)


def test_synthetic_delayed_prefix_and_legacy_confirmed_gate(factory148):
    args = arguments(count=30, lag=70000)
    candidate = bind_dev(**args)
    signals = factory148._signals(candidate.rows, factory148.Config())
    for signal in signals:
        prefix = [b["available_ms"] for b in candidate.rows if b["open_ms"] <= signal["bar_open_ms"]]
        assert signal["available_ms"] == max(prefix)
    from aql.historical.dev_source import import_bytes
    from research_wp_r0.historical_library import CustodyAccessor, HistoricalLibrary, HistoricalDataError
    history = import_bytes(args["envelope"], args["raw"])
    lib = HistoricalLibrary()
    lib.register(history.envelope.source_id, list(history.bars), history.manifest)
    with pytest.raises(HistoricalDataError):
        CustodyAccessor(lib).range_query(history.envelope.source_id, START, START+STEP,
                                       args["decision_cutoff_ms"])


def test_h01_current_factory_head_only_and_stale_head_fails_closed():
    current = "eacb5e50150c6e6c64c8a41b8eaa410aebd71532"
    stale = "dee0f088d70122d143118df2e0a0549a564f2380"
    assert FACTORY_SHA == current
    args = arguments()
    candidate = bind_dev(**args, factory_sha=current)
    assert candidate.package["factory_sha"] == current
    assert verify_candidate(candidate)
    with pytest.raises(BinderError, match="CODE_VERSION"):
        bind_dev(**args, factory_sha=stale)
    with pytest.raises(BinderError, match="CODE_VERSION"):
        bind_dev(**args, factory_sha="0" * 40)
