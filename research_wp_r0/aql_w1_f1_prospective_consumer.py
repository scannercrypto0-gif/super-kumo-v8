"""Prospective F1 Factory research projection; read-only, fail-closed proof boundary.

The Core implementation owns JCS/JSON-Schema/receipt/source-clock verification.
Callbacks below MUST be supplied by a separately trusted, independently anchored
validator. A bool/flag inside F1 or market input is never accepted as authority.
No Paper/order imports, retrofitted P0 F1, inferred fills or realized PnL.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import re

from .aql_w1_opportunity_outcomes import EvidenceError, HORIZONS

ARMS = ("BASE", "SHADOW")
KEYS = ("trial_id", "opportunity_id", "producer_event_id", "envelope_sha256")
SHA = re.compile(r"^[0-9a-f]{64}$")
CAPTURE_SCHEMA = "aql.f1-decision-capture.v1"
VALID_STATES = frozenset(("NO_SIGNAL", "WATCH", "ARMED", "EXPIRED", "UNKNOWN", "BLOCKED"))
COVERAGE = frozenset(("COMPLETE", "ARCHIVE_END_CENSORED", "MISSING_DATA", "UNKNOWN"))


def _key(record):
    if not isinstance(record, dict) or set(record) != set(KEYS):
        raise EvidenceError("invalid immutable C2 composite identity")
    value = tuple(record.get(k) for k in KEYS)
    if any(not isinstance(v, str) or not v for v in value):
        raise EvidenceError("blank C2 composite identity")
    if not SHA.fullmatch(record["envelope_sha256"]):
        raise EvidenceError("invalid envelope digest")
    return value


def _decimal(value):
    if not isinstance(value, str) or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\\.[0-9]*[1-9])?", value):
        raise EvidenceError("noncanonical decimal input")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise EvidenceError("invalid decimal input") from exc
    if value.startswith("-") and parsed == 0:
        raise EvidenceError("negative zero is noncanonical")
    if not parsed.is_finite():
        raise EvidenceError("nonfinite decimal")
    return parsed


def _canon_decimal(number):
    if number == 0:
        return "0"
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _capture_structure(row, expected_pair, expected_identity):
    if not isinstance(row, dict) or row.get("schema_version") != CAPTURE_SCHEMA:
        return False
    if row.get("pair_id") != expected_pair or row.get("arm") not in ARMS:
        return False
    try:
        if _key(row.get("c2_identity")) != expected_identity:
            return False
    except EvidenceError:
        return False
    if row.get("f1_signal_state") not in VALID_STATES or row.get("direction") not in (None, "LONG", "SHORT"):
        return False
    if row.get("predecision_eligibility") not in ("YES", "NO", "NOT_ESTABLISHED"):
        return False
    if not isinstance(row.get("f1_record_sha256"), str) or not SHA.fullmatch(row["f1_record_sha256"]):
        return False
    if not isinstance(row.get("producer_sequence"), int) or isinstance(row["producer_sequence"], bool) or row["producer_sequence"] < 0:
        return False
    if not isinstance(row.get("indicators"), list):
        return False
    indicators = row["indicators"]
    ids = [v.get("indicator_id") for v in indicators if isinstance(v, dict)]
    if len(ids) != len(indicators) or not all(isinstance(x, str) and x for x in ids) or ids != sorted(set(ids)):
        return False
    if any(v.get("role") not in ("DECISION", "OBSERVE_ONLY") for v in indicators):
        return False
    return True


def _verifier_ok(verifier, value):
    # The callback is an integration seam for Core's future strict validator.
    # A self-declared evidence_class/verified flag in the source is never used.
    return verifier is not None and verifier(value) is True


def project_f1_research_slots(scheduled, captures=(), market_windows=(), *,
                              verify_original=None, verify_market=None):
    """Project all scheduled C2 opportunities x BASE/SHADOW x 4/24/72h.

    Both verification callbacks are REQUIRED for any positive original/market
    authority. Missing callbacks result in UNVERIFIED/UNKNOWN, never PIT PASS.
    `market_windows` is a common per-pair/horizon observed range, not fills.
    """
    slots, expected, capture_groups, market = [], {}, {}, {}
    for item in scheduled:
        if not isinstance(item, dict) or not isinstance(item.get("pair_id"), str) or not SHA.fullmatch(item["pair_id"]):
            raise EvidenceError("missing preregistered pair identity")
        identity = _key(item.get("c2_identity"))
        pair = item["pair_id"]
        if pair in expected or identity in (x["identity"] for x in expected.values()):
            raise EvidenceError("duplicate scheduled C2 opportunity")
        if not isinstance(item.get("decision_cutoff_ms"), int) or isinstance(item["decision_cutoff_ms"], bool):
            raise EvidenceError("invalid predeclared cutoff")
        for field in ("source_version", "correction_generation", "source_bytes_sha256"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise EvidenceError("missing preregistered source vintage")
        expected[pair] = {"identity": identity, **item}
    for row in captures:
        if not isinstance(row, dict):
            raise EvidenceError("untyped F1 candidate")
        pair, arm = row.get("pair_id"), row.get("arm")
        if pair not in expected or arm not in ARMS:
            raise EvidenceError("unscheduled arm capture")
        capture_groups.setdefault((pair, arm), []).append(row)
    for item in market_windows:
        if not isinstance(item, dict):
            raise EvidenceError("untyped market window")
        pair, horizon = item.get("pair_id"), item.get("horizon_ms")
        if pair not in expected or horizon not in HORIZONS:
            raise EvidenceError("orphan market window")
        key = (pair, horizon)
        if key in market:
            raise EvidenceError("conflicting market windows")
        market[key] = item

    for pair in sorted(expected):
        plan = expected[pair]
        identity = plan["identity"]
        for arm in ARMS:
            original = capture_groups.get((pair, arm), [])
            distinct = {(r.get("f1_record_sha256"), r.get("producer_sequence"),
                         json.dumps(r, sort_keys=True, ensure_ascii=False)) for r in original}
            one = original[0] if original else None
            if not original:
                status, reason = "MISSING_CAPTURE", "NO_ORIGINAL_CANDIDATE"
            elif len(distinct) != 1 or any(not _capture_structure(r, pair, identity) for r in original):
                status, reason = "QUARANTINED", "INVALID_OR_CONFLICTING_ORIGINAL"
            elif not _verifier_ok(verify_original, one):
                status, reason = "UNVERIFIED", "ORIGINAL_PROVENANCE_NOT_VERIFIED"
            else:
                status, reason = "RECORDED", None
            indicators = tuple({
                "indicator_id": x["indicator_id"], "value_kind": x.get("value_kind"),
                "value": x.get("value"), "missing_reason": x.get("missing_reason")
            } for x in (one.get("indicators", ()) if status == "RECORDED" else ()) if x["role"] == "OBSERVE_ONLY")
            for horizon in HORIZONS:
                source = market.get((pair, horizon))
                valid_market = False
                if source is not None and _verifier_ok(verify_market, source):
                    valid_market = (
                        source.get("source_version") == plan["source_version"]
                        and source.get("source_bytes_sha256") == plan["source_bytes_sha256"]
                        and source.get("correction_generation") == plan["correction_generation"]
                        and source.get("decision_cutoff_ms") == plan["decision_cutoff_ms"]
                        and source.get("coverage_status") in COVERAGE
                    )
                if valid_market:
                    coverage = source["coverage_status"]
                    if coverage == "COMPLETE" and (
                        source.get("expected_bars") != horizon // 900_000
                        or source.get("observed_bars") != source.get("expected_bars")
                    ):
                        coverage = "MISSING_DATA"
                else:
                    coverage = "UNKNOWN"
                signed = None
                reason_metric = "MISSING_F1" if status == "MISSING_CAPTURE" else "UNVERIFIED_PIT"
                first_hit = "NOT_ESTABLISHED"
                if status == "RECORDED":
                    # First-hit is an outcome observation, never original F1 data.
                    tp, sl = one.get("tp"), one.get("sl")
                    if (valid_market and isinstance(tp, dict) and isinstance(sl, dict)
                        and tp.get("status") == "DEFINED_PREDECISION"
                        and sl.get("status") == "DEFINED_PREDECISION"):
                        hit = source.get("tp_sl_first_hit")
                        if hit in ("TP_FIRST", "SL_FIRST", "NEITHER", "UNKNOWN"):
                            first_hit = hit
                    if one.get("direction") not in ("LONG", "SHORT"):
                        reason_metric = "NO_DIRECTION"
                    elif one.get("predecision_eligibility") != "YES":
                        reason_metric = "INELIGIBLE"
                    else:
                        reference = one.get("reference")
                        if not isinstance(reference, dict) or reference.get("price") is None or (
                            not isinstance(reference.get("reference_available_at_ms"), int)
                            or reference["reference_available_at_ms"] > plan["decision_cutoff_ms"]
                        ):
                            reason_metric = "UNKNOWN_REFERENCE"
                        elif coverage == "COMPLETE" and valid_market:
                            try:
                                ref = _decimal(reference["price"])
                                hi, lo = _decimal(source["high"]), _decimal(source["low"])
                                if ref <= 0 or lo <= 0 or hi < lo:
                                    raise EvidenceError("invalid observed market range")
                                favorable = hi - ref if one["direction"] == "LONG" else ref - lo
                                adverse = ref - lo if one["direction"] == "LONG" else hi - ref
                                signed = (_canon_decimal(max(favorable, Decimal(0))),
                                          _canon_decimal(max(adverse, Decimal(0))))
                                reason_metric = "EVALUABLE"
                            except EvidenceError:
                                reason_metric = "UNKNOWN_REFERENCE"
                slots.append({
                    "pair_id": pair, "arm": arm, "c2_identity": dict(zip(KEYS, identity)),
                    "capture_status": status, "capture_reason": reason,
                    "f1_record_sha256": one["f1_record_sha256"] if status == "RECORDED" else None,
                    "f1_signal_state": one.get("f1_signal_state") if status == "RECORDED" else None,
                    "horizon_ms": horizon, "coverage_status": coverage,
                    "measurement_class": "COMMON_PAIRED" if status == "RECORDED" and signed else "MARKET_ONLY",
                    "excursion_status": reason_metric if coverage == "COMPLETE" or reason_metric != "EVALUABLE" else "UNVERIFIED_PIT",
                    "max_favorable": signed[0] if signed and coverage == "COMPLETE" else None,
                    "max_adverse": signed[1] if signed and coverage == "COMPLETE" else None,
                    "tp_sl_first_hit": first_hit,
                    "observe_only_indicators": indicators,
                    "no_fill_or_pnl_inference": True,
                })
    counts = Counter(row["capture_status"] for row in slots if row["horizon_ms"] == HORIZONS[0])
    return {"schema": "AQL-F1-FACTORY-RESEARCH-PROJECTION-v0",
            "evidence_class": "CONSUMER_PROJECTION_NOT_INDEPENDENT_PIT_PROOF",
            "scheduled_total": len(expected), "arm_slots": len(expected) * 2,
            "outcome_rows": len(slots), "capture_status_counts": dict(sorted(counts.items())),
            "outcomes": slots, "research_only": True, "no_fill_or_pnl_inference": True}
