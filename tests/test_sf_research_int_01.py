"""Synthetic software contracts only. No empirical evaluation or durable sink."""
import dataclasses
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sf_ind_01 import _bars, _lib_with, BASE_MS, IMS
from test_sf_strat_01 import spec
from research_wp_r0.historical_library import DatasetManifest, HistoricalDataError
from research_wp_r0.strategy_definition import AttemptRecorder, StrategyDefinition
from research_wp_r0.historical_evaluation_bridge import (
    EXECUTION_REQUIREMENTS, OfflineProtocol, OfflineInputs, prepare_inputs, prepare_candidate,
)


def protocol(**changes):
    value = dict(schema_version="research-input-1", data_class="SYNTHETIC_TEST",
                 timezone="UTC", session="24X7", price_unit="quote/base",
                 volume_unit="base", symbol_mapping="BTCUSDT",
                 listing_policy="SYNTHETIC_NO_LISTING_CLAIM",
                 adjustment_policy="NONE_SYNTHETIC", evidence_reference="synthetic-test-only",
                 fee_bps=10, slippage_bps=5, max_age_ms=IMS,
                 execution=json.loads(EXECUTION_REQUIREMENTS))
    value.update(changes)
    return OfflineProtocol(value)


def fixture():
    bars = [dataclasses.replace(b, ingest_time_ms=b.bar_close+1) for b in _bars(10, step=1)]
    library, accessor = _lib_with(bars)
    return bars, library, accessor


def inputs(accessor=None, p=None, cutoff=None, end=None, definition=None):
    if accessor is None:
        _, _, accessor = fixture()
    return prepare_inputs(definition or StrategyDefinition(spec()), accessor, "BTC1M", 1,
                          BASE_MS, end or BASE_MS+9*IMS,
                          cutoff or BASE_MS+10*IMS, p or protocol())


def test_immutable_bundle_preserves_existing_instance_hashes_and_records():
    bars, lib, acc = fixture()
    result = inputs(acc)
    assert result.spec["state"] == "INPUTS_ONLY_NOT_EVALUATED"
    assert result.spec["dataset_manifest"] == json.loads(json.dumps(lib.get_manifest("BTC1M", 1).to_dict()))
    assert result.spec["binding"]["binding"]["bar_checksums"] == [b.checksum for b in bars]
    assert result.spec["independent_custody"] == "NOT_VERIFIED"
    value = result.spec
    value["bars"][0]["close"] = 999
    assert result.spec["bars"][0]["close"] == 100
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.payload = b"changed"
    assert inputs(acc).payload == result.payload


def test_retained_commitment_restore_and_tamper():
    result = inputs()
    assert OfflineInputs.restore(result.payload.decode(), expected_digest=result.digest) == result
    tampered = result.spec
    tampered["bars"][0]["close"] += 1
    with pytest.raises(ValueError, match="commitment"):
        OfflineInputs.restore(json.dumps(tampered), expected_digest=result.digest)


@pytest.mark.parametrize("changes", [
    {"timezone":"Europe/London"}, {"session":"NYSE"}, {"data_class":"REAL_PROVEN"},
    {"fee_bps":-1}, {"slippage_bps":float("nan")}, {"max_age_ms":True},
    {"price_unit":""}, {"execution":{}}, {"extra":1},
])
def test_protocol_fail_closed(changes):
    with pytest.raises((ValueError, TypeError)):
        protocol(**changes)


@pytest.mark.parametrize("changes", [{"symbol_mapping":"OTHER"}, {"max_age_ms":0},
                                       {"data_class":"HISTORICAL_RECORDED"}])
def test_metadata_stale_and_synthetic_relabel_rejected(changes):
    with pytest.raises(ValueError):
        inputs(p=protocol(**changes), cutoff=BASE_MS+10*IMS+1)


@pytest.mark.parametrize("mode", ["unknown", "late", "future", "nonfinal", "tamper", "source"])
def test_bad_receipts_and_source_fail_closed(mode):
    bars, _, _ = fixture()
    from research_wp_r0.historical_library import BarQuality
    changes = {"unknown":dict(ingest_time_ms=None),
               "late":dict(ingest_time_ms=BASE_MS+11*IMS),
               "future":dict(observation_cutoff_ms=BASE_MS+11*IMS),
               "nonfinal":dict(quality=BarQuality.NON_FINAL),
               "source":dict(source_label="other")}
    if mode == "tamper":
        object.__setattr__(bars[-1], "close", 999)
    else:
        bars[-1] = dataclasses.replace(bars[-1], **changes[mode])
    with pytest.raises((ValueError, HistoricalDataError)):
        _, acc = _lib_with(bars)
        inputs(acc)


@pytest.mark.parametrize("mode", ["gap", "order", "missing", "warmup", "cutoff"])
def test_temporal_range_fail_closed(mode):
    bars, _, _ = fixture()
    if mode == "gap": del bars[4]
    if mode == "order": bars.reverse()
    if mode == "missing": bars.pop()
    if mode == "warmup": bars = bars[:2]
    with pytest.raises((ValueError, HistoricalDataError)):
        _, acc = _lib_with(bars)
        inputs(acc, cutoff=BASE_MS+9*IMS if mode=="cutoff" else None)


def test_cutoff_and_prefix_change_binding_not_previous_inputs():
    _, _, acc = fixture()
    full = inputs(acc)
    prefix = inputs(acc, end=BASE_MS+8*IMS, cutoff=BASE_MS+9*IMS)
    assert prefix.digest != full.digest
    assert len(prefix.spec["bars"]) == 9
    assert len(full.spec["bars"]) == 10


def test_manifest_tamper_and_two_read_change_rejected():
    bars, lib, acc = fixture()
    object.__setattr__(lib.get_manifest("BTC1M", 1), "timezone", "BAD")
    with pytest.raises(ValueError): inputs(acc)
    bars, _, acc = fixture()
    changed = [*bars[:-1], dataclasses.replace(bars[-1], close=108)]
    original = acc.range_query
    with patch.object(acc, "range_query", side_effect=[original("BTC1M", BASE_MS, BASE_MS+9*IMS,
                      BASE_MS+10*IMS, version=1), bars, changed]):
        # Binding and indicator consume the first two reads; bridge checks third.
        with pytest.raises(ValueError, match="changed"):
            inputs(acc)


class MemorySink:
    """Test double; explicitly NOT a durable/idempotent journal."""
    def __init__(self): self.events = []
    def record_attempt(self, event): self.events.append(dict(event))


def candidate(recorder, raw=None, **changes):
    _, _, acc = fixture()
    return prepare_candidate(recorder, raw or StrategyDefinition(spec()).to_json(),
                             "family", "candidate", acc, "BTC1M", 1, BASE_MS,
                             BASE_MS+9*IMS, BASE_MS+10*IMS,
                             protocol(**changes))


def test_attempt_states_no_fake_complete_and_explicit_abandonment():
    sink = MemorySink(); recorder = AttemptRecorder(sink)
    prepared, bundle = candidate(recorder)
    assert [e["state"] for e in sink.events] == ["PENDING"]
    recorder.finish(prepared, "ABANDONED")
    assert sink.events[-1]["state"] == "ABANDONED"
    assert bundle.spec["state"] == "INPUTS_ONLY_NOT_EVALUATED"


def test_invalid_and_failed_candidates_remain_accounted_for():
    sink = MemorySink(); recorder = AttemptRecorder(sink)
    with pytest.raises(ValueError): candidate(recorder, '{"bad":1}')
    with pytest.raises(ValueError): candidate(recorder, symbol_mapping="OTHER")
    assert [e["state"] for e in sink.events] == ["INVALID", "PENDING", "FAILED"]


def test_sink_failure_raises_and_never_returns_success():
    class Broken:
        def record_attempt(self, event): raise OSError("persist failed")
    with pytest.raises(OSError, match="persist failed"):
        candidate(AttemptRecorder(Broken()))
    sink = MemorySink(); recorder = AttemptRecorder(sink)
    def record(event):
        if event["state"] == "FAILED": raise OSError("terminal persist failed")
        sink.events.append(event)
    sink.record_attempt = record
    with pytest.raises(OSError, match="terminal persist failed"):
        candidate(recorder, symbol_mapping="OTHER")
    assert [e["state"] for e in sink.events] == ["PENDING"]


def test_port_does_not_pretend_to_enforce_uniqueness_or_replay():
    sink = MemorySink(); recorder = AttemptRecorder(sink)
    candidate(recorder); candidate(recorder)
    assert len(sink.events) == 2  # Explicit integration blocker, not exactly-once.
    assert sink.events[0] == sink.events[1]


def test_protocol_costs_change_commitment_not_an_invented_pnl():
    _, _, acc = fixture()
    first = inputs(acc)
    second = inputs(acc, p=protocol(fee_bps=20))
    assert first.digest != second.digest
    assert "pnl" not in first.spec


def test_v2_registry_is_used_without_foreign_imports():
    value = spec()
    value["indicators"][0].update(indicator_id="ROC_v2", version="2")
    value["entry"]["left"]["field"] = "roc"
    value["exit"]["left"]["field"] = "roc"
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
    definition = StrategyDefinition(value, registry=IndicatorRegistryV2())
    result = inputs(definition=definition)
    assert result.spec["binding"]["binding"]["indicators"][0]["indicator_id"] == "ROC_v2"


def test_two_imports_instance_identity_differs_content_commitment_matches():
    bars, lib, _ = fixture()
    first = lib.get_manifest("BTC1M", 1)
    time.sleep(.02)
    _, acc = _lib_with(bars)
    second = acc._library.get_manifest("BTC1M", 1)
    assert first.created_at_ms != second.created_at_ms
    assert first.manifest_integrity_hash != second.manifest_integrity_hash
    assert first.manifest_hash == second.manifest_hash
    assert first.verify_integrity() and second.verify_integrity()


def test_cross_process_replay_retained_manifest_and_independent_commitment(tmp_path):
    bars, lib, acc = fixture()
    retained = lib.get_manifest("BTC1M", 1).to_dict()
    path = tmp_path / "retained.json"
    path.write_text(json.dumps(retained), encoding="utf-8")
    script = '''
import json, sys
from test_sf_research_int_01 import fixture, inputs
from research_wp_r0.historical_library import DatasetManifest, HistoricalLibrary, CustodyAccessor
bars, _, _ = fixture()
manifest = DatasetManifest.from_dict(json.load(open(sys.argv[1], encoding="utf-8")))
library = HistoricalLibrary(); library.register("BTC1M", bars, manifest)
print(inputs(CustodyAccessor(library)).digest)
'''
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(__file__).resolve().parent),
                                                    str(Path(__file__).resolve().parents[1])]))
    expected = inputs(acc).digest  # Retained outside child processes, same trust domain.
    outputs = [subprocess.check_output([sys.executable, "-B", "-c", script, str(path)],
                                      env=env, text=True).strip() for _ in range(2)]
    assert outputs == [expected, expected]


def test_cross_process_reimports_do_not_claim_instance_equality():
    script = '''
import json
from test_sf_research_int_01 import fixture
_, lib, _ = fixture()
m = lib.get_manifest("BTC1M", 1)
print(json.dumps([m.created_at_ms, m.manifest_hash, m.manifest_integrity_hash]))
'''
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(__file__).resolve().parent),
                                                    str(Path(__file__).resolve().parents[1])]))
    first = json.loads(subprocess.check_output([sys.executable, "-B", "-c", script], env=env, text=True))
    time.sleep(.02)
    second = json.loads(subprocess.check_output([sys.executable, "-B", "-c", script], env=env, text=True))
    assert first[0] != second[0]
    assert first[1] == second[1]
    assert first[2] != second[2]


def test_offline_audit_accepts_real_prepared_synthetic_receipt():
    """Positive full bridge -> audit path, without claiming evaluation/custody."""
    from research_wp_r0.offline_input_audit import audit_offline_inputs
    prepared = inputs()
    first = audit_offline_inputs(prepared, expected_digest=prepared.digest)
    second = audit_offline_inputs(OfflineInputs.restore(
        prepared.payload.decode("utf-8"), expected_digest=prepared.digest),
        expected_digest=prepared.digest)
    assert first == second
    assert first["status"] == "INPUTS_AUDITED_NOT_EVALUATED"
    assert first["inputs_digest"] == prepared.digest
    assert first["independent_custody_verified"] is False


def test_offline_audit_rejects_stale_prepared_receipt_with_new_digest():
    from research_wp_r0.offline_input_audit import audit_offline_inputs
    prepared = inputs()
    altered = prepared.spec
    altered["binding"]["binding"]["decision_cutoff_ms"] += 2 * IMS
    from research_wp_r0.strategy_definition import digest
    altered["binding"]["digest"] = digest(altered["binding"]["binding"])
    changed = OfflineInputs(altered)
    with pytest.raises(ValueError, match="Stale"):
        audit_offline_inputs(changed, expected_digest=changed.digest)
