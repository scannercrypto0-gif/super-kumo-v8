"""Deterministic offline INPUTS receipt audit, not a trading evaluator.

This layer never produces fills, PnL, COMPLETE or a custody attestation.
"""
import hashlib
import math
import re
from .historical_library import HistoricalBar, DatasetManifest, BarQuality, SourceType, DataAvailabilityKind, _interval_to_ms
from .strategy_definition import canonical, keys
from .historical_evaluation_bridge import OfflineInputs


def check_decision_freshness(last_bar_close, decision_cutoff_ms, max_age_ms):
    """Fail closed on invalid or stale PIT decision-time evidence."""
    from .strategy_definition import integer
    integer(last_bar_close, 0, 2**53-1)
    integer(decision_cutoff_ms, 0, 2**53-1)
    integer(max_age_ms, 0, 2**53-1)
    if decision_cutoff_ms <= last_bar_close or decision_cutoff_ms - (last_bar_close + 1) > max_age_ms:
        raise ValueError("Stale or invalid input receipt at decision cutoff")


def audit_offline_inputs(inputs, *, expected_digest):
    """Fail closed on missing/tampered receipts; return reproducible audit hash."""
    if not isinstance(inputs, OfflineInputs):
        raise ValueError("OfflineInputs required")
    if type(expected_digest) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
        raise ValueError("Separately retained input digest required")
    if inputs.digest != expected_digest:
        raise ValueError("Input commitment mismatch")
    spec = inputs.spec
    keys(spec, "schema_version state strategy protocol protocol_digest binding dataset_manifest bars independent_custody")
    if spec["schema_version"] != "research-input-1" or spec["state"] != "INPUTS_ONLY_NOT_EVALUATED":
        raise ValueError("Only unevaluated input receipts accepted")
    if spec["independent_custody"] != "NOT_VERIFIED":
        raise ValueError("Custody cannot be self-attested")
    from .strategy_definition import digest
    from .historical_evaluation_bridge import OfflineProtocol
    if OfflineProtocol(spec["protocol"]).digest != spec["protocol_digest"]:
        raise ValueError("Protocol digest mismatch")
    keys(spec["strategy"], "definition digest")
    from .strategy_definition import StrategyDefinition
    if StrategyDefinition.from_dict(spec["strategy"]).digest != spec["strategy"]["digest"]:
        raise ValueError("Strategy digest mismatch")
    keys(spec["binding"], "binding digest")
    binding = spec["binding"]["binding"]
    if digest(binding) != spec["binding"]["digest"]:
        raise ValueError("Binding digest mismatch")
    if binding["strategy_digest"] != spec["strategy"]["digest"]:
        raise ValueError("Strategy/binding mismatch")
    manifest = spec["dataset_manifest"]
    if binding["dataset_id"] != manifest["dataset_id"] or binding["dataset_version"] != manifest["version"]:
        raise ValueError("Dataset identity mismatch")
    if binding["dataset_manifest_hash"] != manifest["manifest_integrity_hash"]:
        raise ValueError("Manifest commitment mismatch")
    # OfflineInputs canonical JSON collapses integral floats (100.0 -> 100).
    # The legacy manifest hash encodes coverage_pct as a float; restore that
    # declared field type before verifying the stored, independently bound hash.
    if type(manifest.get("coverage_pct")) not in (int, float) or type(manifest["coverage_pct"]) is bool:
        raise ValueError("Invalid manifest coverage type")
    normalized_manifest = {**manifest, "coverage_pct": float(manifest["coverage_pct"])}
    meta = DatasetManifest.from_dict(normalized_manifest)
    if not meta.provenance_verified or not meta.verify_integrity():
        raise ValueError("Unverified manifest")
    bars = spec["bars"]
    if type(bars) is not list or not bars or len(bars) != len(binding["bar_checksums"]):
        raise ValueError("Missing or partial bar receipts")
    checked = []
    for row, checksum in zip(bars, binding["bar_checksums"]):
        if type(row) is not dict:
            raise ValueError("Invalid bar record")
        required = set(HistoricalBar.__dataclass_fields__)
        if set(row) != required or row["checksum"] != checksum:
            raise ValueError("Bar schema/commitment mismatch")
        try:
            # Restore OHLCV declared float types before checking legacy bar hashes.
            # Canonical input JSON may encode 100.0 as 100.
            normalized_row = {**row, **{k: float(row[k]) for k in
                ("open", "high", "low", "close", "volume")
                if type(row[k]) in (int, float)}}
            original = HistoricalBar(
                **{**normalized_row, "quality": BarQuality(row["quality"]),
                   "source": SourceType(row["source"]),
                   "availability_kind": DataAvailabilityKind(row["availability_kind"])})
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError("Invalid bar provenance") from error
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (original.open, original.high, original.low, original.close, original.volume)) or
            min(original.open, original.close) <= 0 or original.low <= 0 or original.volume < 0 or
            original.high < max(original.open, original.close, original.low) or
            original.low > min(original.open, original.close)):
            raise ValueError("Invalid OHLCV range")
        if original.checksum != checksum:
            raise ValueError("OHLCV/provenance checksum mismatch")
        if original.quality != BarQuality.FINAL or original.availability_kind != DataAvailabilityKind.CONFIRMED:
            raise ValueError("Unconfirmed bar")
        if type(original.ingest_time_ms) is not int or type(original.observation_cutoff_ms) is not int:
            raise ValueError("Missing timestamps")
        if not (original.bar_open <= original.bar_close < original.observation_cutoff_ms <= binding["decision_cutoff_ms"]):
            raise ValueError("Future or invalid bar")
        if not (original.bar_close < original.ingest_time_ms <= original.observation_cutoff_ms):
            raise ValueError("Inconsistent ingestion")
        if original.source_label != meta.source_label or original.symbol != meta.symbol or original.interval != meta.interval:
            raise ValueError("Mixed bar source/identity")
        checked.append(original)
    if any(a.bar_open >= b.bar_open or a.bar_close >= b.bar_open for a, b in zip(checked, checked[1:])):
        raise ValueError("Unsorted or overlapping bars")
    interval_ms = _interval_to_ms(meta.interval)
    if any(b.bar_close != b.bar_open + interval_ms - 1 for b in checked):
        raise ValueError("Invalid candle duration")
    if any(b.bar_open - a.bar_open != interval_ms for a, b in zip(checked, checked[1:])):
        raise ValueError("Missing candle in audited range")
    if meta.gap_count or meta.duplicate_count or meta.non_final_count or meta.coverage_pct != 100:
        raise ValueError("Incomplete or non-final dataset")
    if [b.checksum for b in checked] != binding["bar_checksums"]:
        raise ValueError("Range commitment mismatch")
    if checked[0].bar_open != binding["start_ms"] or checked[-1].bar_open != binding["end_ms"]:
        raise ValueError("Range boundary mismatch")
    # A query can represent a strict subset of the dataset manifest. Recompute
    # full-manifest bar hash only if the receipt covers the entire dataset.
    if len(checked) == meta.bar_count and checked[0].bar_open == meta.min_bar_open and checked[-1].bar_open == meta.max_bar_open:
        if not meta.verify_hash(checked):
            raise ValueError("Dataset bar-manifest hash mismatch")
    check_decision_freshness(checked[-1].bar_close, binding["decision_cutoff_ms"],
                             spec["protocol"]["max_age_ms"])
    if spec["protocol"]["symbol_mapping"] != meta.symbol or spec["protocol"]["timezone"] != meta.timezone:
        raise ValueError("Protocol/dataset identity mismatch")
    if spec["protocol"]["data_class"] == "SYNTHETIC_TEST":
        if any(b.source != SourceType.SYNTHETIC for b in checked):
            raise ValueError("Synthetic provenance mismatch")
    elif (any(b.source == SourceType.SYNTHETIC for b in checked) or
          type(meta.source_hash) is not str or not re.fullmatch("[0-9a-f]{64}", meta.source_hash)):
        raise ValueError("Historical source commitment missing")
    return {"status": "INPUTS_AUDITED_NOT_EVALUATED", "inputs_digest": inputs.digest,
            "audit_sha256": hashlib.sha256(canonical({"schema": "sf-input-audit-1",
                                                       "inputs_digest": inputs.digest})).hexdigest(),
            "independent_custody_verified": False}
