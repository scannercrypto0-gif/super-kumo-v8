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
    if not isinstance(value, str) or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?", value):
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


def _capture_structure(row, expected_pair, expected_identity, plan):
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
    for field in ("source_version", "source_bytes_sha256", "correction_generation",
                  "decision_cutoff_ms", "experiment_plan_sha256"):
        if row.get(field) != plan.get(field):
            return False
    if not isinstance(row.get("arm_event_sha256"), str) or not SHA.fullmatch(row["arm_event_sha256"]):
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
                              verify_original=None, verify_market=None,
                              f3_effects=None):
    """Project all scheduled C2 opportunities x BASE/SHADOW x 4/24/72h.

    Both verification callbacks are REQUIRED for positive original/market authority.
    verify_original returns a trusted Core verdict RECORDED/UNVERIFIED/QUARANTINED.
    Missing callbacks result in UNVERIFIED/UNKNOWN, never PIT PASS.
    `market_windows` is a common per-pair/horizon observed range, not fills.
    """
    slots, expected, capture_groups, market, f3_by_c2 = [], {}, {}, {}, {}
    for item in scheduled:
        if not isinstance(item, dict) or not isinstance(item.get("pair_id"), str) or not SHA.fullmatch(item["pair_id"]):
            raise EvidenceError("missing preregistered pair identity")
        identity = _key(item.get("c2_identity"))
        pair = item["pair_id"]
        if pair in expected or identity in (x["identity"] for x in expected.values()):
            raise EvidenceError("duplicate scheduled C2 opportunity")
        if not isinstance(item.get("decision_cutoff_ms"), int) or isinstance(item["decision_cutoff_ms"], bool):
            raise EvidenceError("invalid predeclared cutoff")
        for field in ("source_version", "correction_generation", "source_bytes_sha256", "experiment_plan_sha256"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise EvidenceError("missing preregistered source vintage")
        expected[pair] = {"identity": identity, **item}
    if f3_effects is not None:
        for effect in f3_effects:
            if not isinstance(effect, dict):
                raise EvidenceError("untyped downstream F3 effect")
            identity = _key(effect.get("c2_identity"))
            if identity in f3_by_c2 or identity not in (x["identity"] for x in expected.values()):
                raise EvidenceError("duplicate or orphan downstream F3 effect")
            disposition = effect.get("effect_disposition")
            if disposition not in ("NO_SIGNAL", "REJECTED", "TRIGGERED"):
                raise EvidenceError("invalid F3 disposition")
            f3_by_c2[identity] = disposition
        if len(f3_by_c2) != len(expected):
            raise EvidenceError("incomplete downstream F3 denominator")
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
            elif len(distinct) != 1 or any(not _capture_structure(r, pair, identity, plan) for r in original):
                status, reason = "QUARANTINED", "INVALID_OR_CONFLICTING_ORIGINAL"
            else:
                # Independent strict Core validation, never a source self-assertion.
                verdict = verify_original(one) if verify_original is not None else None
                if verdict == "RECORDED":
                    status, reason = "RECORDED", None
                elif verdict == "QUARANTINED":
                    status, reason = "QUARANTINED", "UPSTREAM_ORIGINAL_INVALID"
                else:
                    status, reason = "UNVERIFIED", "ORIGINAL_PROVENANCE_NOT_VERIFIED"
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
                    "f3_effect_disposition": f3_by_c2.get(identity),
                    "horizon_ms": horizon, "coverage_status": coverage,
                    "measurement_class": "ARM_SPECIFIC_POLICY" if signed else "MARKET_ONLY",
                    "excursion_status": reason_metric if coverage == "COMPLETE" or reason_metric != "EVALUABLE" else "UNVERIFIED_PIT",
                    "max_favorable": signed[0] if signed and coverage == "COMPLETE" else None,
                    "max_adverse": signed[1] if signed and coverage == "COMPLETE" else None,
                    "tp_sl_first_hit": first_hit,
                    "observe_only_indicators": indicators,
                    "measurement_policy_sha256": (
                        (one.get("reference") or {}).get("measurement_policy_sha256")
                        if status == "RECORDED" else None
                    ),
                    "reference_price": (
                        (one.get("reference") or {}).get("price")
                        if status == "RECORDED" else None
                    ),
                    "no_fill_or_pnl_inference": True,
                })
    # A one-sided signed observation cannot be called a common paired estimate.
    by_pair_horizon = {}
    for row in slots:
        by_pair_horizon.setdefault((row["pair_id"], row["horizon_ms"]), []).append(row)
    for rows in by_pair_horizon.values():
        if (len(rows) == 2 and {x["arm"] for x in rows} == set(ARMS)
            and all(x["measurement_class"] == "ARM_SPECIFIC_POLICY" for x in rows)
            and all(x["coverage_status"] == "COMPLETE" for x in rows)
            and rows[0]["reference_price"] == rows[1]["reference_price"]
            and rows[0]["measurement_policy_sha256"] is not None
            and rows[0]["measurement_policy_sha256"] == rows[1]["measurement_policy_sha256"]):
            for row in rows:
                row["measurement_class"] = "COMMON_PAIRED"
    counts = Counter(row["capture_status"] for row in slots if row["horizon_ms"] == HORIZONS[0])
    return {"schema": "AQL-F1-FACTORY-RESEARCH-PROJECTION-v0",
            "evidence_class": "CONSUMER_PROJECTION_NOT_INDEPENDENT_PIT_PROOF",
            "scheduled_total": len(expected), "arm_slots": len(expected) * 2,
            "outcome_rows": len(slots), "capture_status_counts": dict(sorted(counts.items())),
            "outcomes": slots, "research_only": True, "no_fill_or_pnl_inference": True}


def project_core_verified_f1_slots(scheduled, captures=(), market_windows=(), *,
                                   indicator_registry, proof_verifier=None,
                                   verify_market=None, f3_effects=None):
    """Read-only Core r1.2a integration; never self-certify original PIT.

    The independent host proof_verifier is deliberately NOT implemented here.
    In its absence Core classifies structurally valid originals UNVERIFIED.
    """
    from .aql_f1_decision_capture_v1 import (
        CaptureError, digest, status_slots, validate_f1,
    )

    schedule = list(scheduled)
    records = list(captures)
    if not schedule:
        if records:
            raise EvidenceError("orphan captures without a preregistered schedule")
        return project_f1_research_slots([], (), market_windows,
                                         verify_market=verify_market, f3_effects=f3_effects)
    plans = set()
    expected_c2 = []
    by_pair = {}
    for item in schedule:
        try:
            identity = dict(item["c2_identity"])
            _key(identity)
            plan_sha = item["experiment_plan_sha256"]
            expected_pair = digest({"experiment_plan_sha256": plan_sha,
                                    "c2_identity": identity})
            if item["pair_id"] != expected_pair:
                raise EvidenceError("Core pair_id does not match preregistered C2")
            if expected_pair in by_pair:
                raise EvidenceError("duplicate Core preregistered pair")
        except (KeyError, TypeError, ValueError, CaptureError) as exc:
            raise EvidenceError("invalid Core schedule identity") from exc
        plans.add(plan_sha)
        expected_c2.append(identity)
        by_pair[expected_pair] = item
    if len(plans) != 1:
        raise EvidenceError("mixed experiment plans require separate projections")

    grouped = {}
    for record in records:
        if not isinstance(record, dict):
            raise EvidenceError("untyped Core original candidate")
        pair, arm = record.get("pair_id"), record.get("arm")
        if pair not in by_pair or arm not in ARMS:
            raise EvidenceError("orphan Core original candidate")
        grouped.setdefault((pair, arm), []).append(record)
    try:
        core_slots = status_slots(expected_c2, next(iter(plans)), grouped,
                                  indicator_registry, proof_verifier)
    except (CaptureError, KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("Core status reconciliation rejected input") from exc
    verdicts = {}
    for slot in core_slots:
        key = (slot["pair_id"], slot["arm"])
        if key in verdicts or slot["pair_id"] not in by_pair:
            raise EvidenceError("duplicate or orphan Core status slot")
        verdicts[key] = slot
    if len(verdicts) != 2 * len(schedule):
        raise EvidenceError("incomplete Core status universe")

    def verified_original(record):
        key = (record["pair_id"], record["arm"])
        slot = verdicts.get(key)
        if slot is None:
            return "QUARANTINED"
        # Core has already reconciled all candidate conflicts. Never trust a
        # caller-supplied status embedded in the candidate itself.
        if slot["capture_status"] != "RECORDED":
            return slot["capture_status"]
        try:
            validate_f1(record, indicator_registry)
        except (CaptureError, KeyError, TypeError, ValueError):
            return "QUARANTINED"
        if record["f1_record_sha256"] != slot["f1_record_sha256"]:
            return "QUARANTINED"
        return "RECORDED"

    result = project_f1_research_slots(
        schedule, records, market_windows,
        verify_original=verified_original, verify_market=verify_market,
        f3_effects=f3_effects,
    )
    # Both engines must agree; fail closed instead of silently downgrading a
    # Core quarantine or treating a missing capture as a synthetic F1 event.
    for row in result["outcomes"]:
        key = (row["pair_id"], row["arm"])
        if row["capture_status"] != verdicts[key]["capture_status"]:
            raise EvidenceError("Core/Factory capture status divergence")
    result["core_verdict_source"] = "CORE_STATUS_SLOTS_PINNED_INTEGRATION"
    result["independent_pit_proof"] = proof_verifier is not None
    return result
