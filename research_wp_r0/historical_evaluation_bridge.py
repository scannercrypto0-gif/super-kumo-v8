"""Offline input adapter only: no simulator, durable journal or profitability claim.

Each call binds ONE decision cutoff. Receipts remain instance-specific. No
content_hash contract is introduced (Issue #76 requires an owner decision).
"""
from dataclasses import asdict, dataclass
import json
import re

from .historical_library import CustodyAccessor, SourceType
from .indicator_library_v2 import IndicatorRegistryV2
from .strategy_definition import (
    AttemptRecorder, StrategyDefinition, bind_evaluation,
    canonical, digest, integer, keys, number,
)


@dataclass(frozen=True, init=False)
class OfflineProtocol:
    """Explicit simulator *requirements*, not implemented execution semantics."""
    payload: bytes

    def __init__(self, value):
        keys(value, "schema_version data_class timezone session price_unit volume_unit "
             "symbol_mapping listing_policy adjustment_policy evidence_reference "
             "fee_bps slippage_bps max_age_ms execution")
        if value["schema_version"] != "research-input-1":
            raise ValueError("Unsupported input protocol")
        if value["data_class"] not in ("SYNTHETIC_TEST", "HISTORICAL_RECORDED"):
            raise ValueError("Explicit data class required")
        if value["timezone"] != "UTC" or value["session"] != "24X7":
            raise ValueError("Only explicit UTC/24X7 inputs supported")
        for key in ("price_unit", "volume_unit", "symbol_mapping", "listing_policy",
                    "adjustment_policy", "evidence_reference"):
            if type(value[key]) is not str or not value[key].strip():
                raise ValueError("Explicit metadata required: " + key)
        for key in ("fee_bps", "slippage_bps"):
            number(value[key], 0, 10000)
        integer(value["max_age_ms"], 0, 2**53-1)
        if canonical(value["execution"]) != EXECUTION_REQUIREMENTS:
            raise ValueError("Unsupported execution requirements")
        object.__setattr__(self, "payload", canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return digest(self.spec)


# An immutable canonical constant; spec copies cannot mutate these requirements.
EXECUTION_REQUIREMENTS = canonical({
    "entry": "NEXT_ELIGIBLE_OPEN_STRICTLY_AFTER_DECISION",
    "same_bar_stop_target": "UNRESOLVED_NO_POSITIVE_SCORE",
    "gap_or_delisting": "UNRESOLVED_NO_INVENTED_FILL",
    "ttl": "EXPIRE_AS_NO_FILL",
    "no_signal": "RETAIN_ZERO_EXPOSURE_OPPORTUNITY",
    "costs": "BOTH_SIDES_NOTIONAL_FEE_PLUS_SLIPPAGE",
    "unknown": "REJECT_OR_UNRESOLVED_NEVER_ZERO_LOSS",
})


@dataclass(frozen=True, init=False)
class OfflineInputs:
    """Canonical handoff retaining full instance manifests and input records."""
    payload: bytes

    def __init__(self, value):
        object.__setattr__(self, "payload", canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return digest(self.spec)

    @classmethod
    def restore(cls, raw, *, expected_digest):
        from .strategy_definition import load_json
        value = cls(load_json(raw))
        if value.digest != expected_digest:
            raise ValueError("Inputs differ from separately retained commitment")
        return value


def prepare_inputs(definition, accessor, dataset_id, version, start_ms, end_ms,
                   decision_cutoff_ms, protocol, *, registry=None):
    """Prepare a complete, final, receipt-backed prefix; NEVER evaluate signals.

    Caller metadata assertions are retained, not independently authenticated.
    Historical inputs additionally need an existing source-bytes commitment.
    """
    if not isinstance(definition, StrategyDefinition) or not isinstance(protocol, OfflineProtocol):
        raise ValueError("Validated strategy and offline protocol required")
    if not isinstance(accessor, CustodyAccessor):
        raise ValueError("CustodyAccessor required")
    registry = registry if registry is not None else IndicatorRegistryV2()
    binding = bind_evaluation(definition, accessor, dataset_id, version, start_ms,
                              end_ms, decision_cutoff_ms, registry=registry)
    bars = accessor.range_query(dataset_id, start_ms, end_ms, decision_cutoff_ms,
                                version=version, require_complete=True)
    meta = accessor._library.get_manifest(dataset_id, version)
    p = protocol.spec
    if not meta.verify_integrity() or meta.manifest_integrity_hash != binding.spec["dataset_manifest_hash"]:
        raise ValueError("Dataset changed while preparing inputs")
    if [b.checksum for b in bars] != binding.spec["bar_checksums"]:
        raise ValueError("Input range changed while preparing inputs")
    if any(not b.verify_checksum() for b in bars):
        raise ValueError("Input checksum changed while preparing inputs")
    if meta.timezone != p["timezone"] or p["symbol_mapping"] != meta.symbol:
        raise ValueError("Timezone/symbol mapping mismatch")
    if decision_cutoff_ms - (bars[-1].bar_close + 1) > p["max_age_ms"]:
        raise ValueError("Stale decision inputs")
    if any(type(b.ingest_time_ms) is not int or b.ingest_time_ms < b.bar_close + 1 or
           b.ingest_time_ms > b.observation_cutoff_ms for b in bars):
        raise ValueError("Recorded final-bar receipt required; unknown receipts are not confirmed")
    if any(b.source_label != meta.source_label for b in bars):
        raise ValueError("Mixed source labels")
    synthetic = [b.source == SourceType.SYNTHETIC for b in bars]
    if p["data_class"] == "SYNTHETIC_TEST":
        if not all(synthetic):
            raise ValueError("Synthetic test label requires synthetic bars")
    elif any(synthetic) or type(meta.source_hash) is not str or not re.fullmatch("[0-9a-f]{64}", meta.source_hash):
        raise ValueError("Historical source bytes/provenance evidence required")
    records = []
    for bar in bars:
        # The checksum covers all existing record fields. Retain the fields too.
        record = asdict(bar)
        record["quality"] = bar.quality.value
        record["source"] = bar.source.value
        record["availability_kind"] = bar.availability_kind.value
        records.append(record)
    return OfflineInputs({"schema_version": "research-input-1",
                          "state": "INPUTS_ONLY_NOT_EVALUATED",
                          "strategy": definition.to_dict(), "protocol": p,
                          "protocol_digest": protocol.digest,
                          "binding": binding.to_dict(), "dataset_manifest": meta.to_dict(),
                          "bars": records, "independent_custody": "NOT_VERIFIED"})


def prepare_candidate(recorder, raw_json, family_id, candidate_id, accessor,
                      dataset_id, version, start_ms, end_ms, decision_cutoff_ms,
                      protocol, *, registry=None):
    """Use accepted attempt port; successful preparation stays PENDING.

    Caller must reconcile restart/idempotency/family membership in its ledger.
    No COMPLETE event is manufactured for preparing inputs. Sink failures raise.
    """
    if not isinstance(recorder, AttemptRecorder):
        raise ValueError("Existing AttemptRecorder port required")
    registry = registry if registry is not None else IndicatorRegistryV2()
    prepared, definition = recorder.prepare(raw_json, family_id, candidate_id, registry=registry)
    try:
        inputs = prepare_inputs(definition, accessor, dataset_id, version, start_ms,
                                end_ms, decision_cutoff_ms, protocol, registry=registry)
    except Exception:
        recorder.finish(prepared, "FAILED")
        raise
    return prepared, inputs
