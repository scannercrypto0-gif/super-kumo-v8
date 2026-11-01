"""Prospective Core F1 capture, r1.2a: never backfill historical P0.

A prospective decision host MUST invoke this before F3 or post-cutoff reads.
C2 historical envelopes are RETROSPECTIVE_NON_PIT and must not be promoted.
The producer has no independent clock/custody oracle: missing proof stays UNVERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Mapping

SCHEMA = "aql.f1-decision-capture.v1"
JCS = "JCS-RFC8785-v1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
ARMS = ("BASE", "SHADOW")
F1_STATES = ("NO_SIGNAL","WATCH","ARMED","EXPIRED","UNKNOWN","BLOCKED")
C2_FIELDS = {"trial_id","opportunity_id","producer_event_id","envelope_sha256"}
IND_FIELDS = {"indicator_id","role","definition_version","parameters_sha256","unit","lookback_bars","value_kind","value","missing_reason","source_asof_ms","available_at_ms","input_prefix_sha256","availability_evidence_ref"}
REF_FIELDS = {"reference_kind","price","unit","tick_size","decimal_scale","rounding_mode","reference_asof_ms","reference_available_at_ms","reference_evidence_ref","measurement_policy_sha256"}
RISK_FIELDS = {"status","level","unit","basis","reference_price_kind","defined_at_ms","tick_size","decimal_scale","rounding_mode"}
FIELDS = {
 "schema_version","canonicalization_id","trial_id","opportunity_id","producer_event_id","envelope_sha256",
 "run_manifest_sha256","experiment_plan_sha256","c2_identity","pair_id","arm","arm_event_id","arm_event_sha256",
 "arm_strategy_version","strategy_id","strategy_digest","decision_cutoff_ms","decision_ms","capture_ms","producer_sequence",
 "previous_event_sha256","source_asof_ms","source_available_at_ms","prefix_start_ms","prefix_end_exclusive_ms",
 "source_availability_evidence_ref","prefix_bar_checksums_sha256","source_id","source_version",
 "correction_generation","input_disposition","dataset_version","source_bytes_sha256","gap_inventory_sha256",
 "correction_lineage_sha256","feature_policy_version","selection_policy_version","indicator_inventory_manifest_sha256",
 "indicators","f1_signal_state","f1_reason_code","direction","predecision_eligibility",
 "eligibility_reason_code","eligibility_evidence_ref","eligibility_available_at_ms",
 "target_policy_id","target_policy_version","stop_policy_id","stop_policy_version",
 "target_policy_sha256","stop_policy_sha256","execution_assumptions_sha256","reference","tp","sl","f1_record_sha256",
}
HASH_FIELDS = {x for x in FIELDS if x.endswith("_sha256")} - {"f1_record_sha256", "previous_event_sha256"}
TIMES = {"decision_cutoff_ms","decision_ms","capture_ms","source_asof_ms","source_available_at_ms","prefix_start_ms","prefix_end_exclusive_ms"}
NUMBERS = {"producer_sequence","dataset_version"}
NULLABLE = {"previous_event_sha256","source_availability_evidence_ref","f1_reason_code","direction","eligibility_reason_code","eligibility_evidence_ref","eligibility_available_at_ms"}

class CaptureError(ValueError):
    """Invalid original capture, hash, origin or consumer boundary."""

def _fail(message: str) -> None:
    raise CaptureError(message)

def _is_hash(x: Any) -> bool:
    return isinstance(x, str) and HASH.fullmatch(x) is not None

def _int(x: Any, minimum: int = -(2**53-1)) -> bool:
    # JCS numeric interoperability: exactly representable integers only.
    return type(x) is int and minimum <= x <= 2**53-1

def _id(x: Any) -> bool:
    return type(x) is str and bool(x)

def _check_jcs(v: Any) -> None:
    if v is None or isinstance(v,(str,bool)):
        if isinstance(v,str) and any(0xD800 <= ord(c) <= 0xDFFF for c in v):
            _fail("JCS_LONE_SURROGATE")
    elif type(v) is int:
        if not _int(v): _fail("JCS_INTEGER_RANGE")
    elif type(v) is list:
        for x in v: _check_jcs(x)
    elif type(v) is dict:
        for key,value in v.items():
            if not isinstance(key,str): _fail("JCS_OBJECT_KEY")
            _check_jcs(key); _check_jcs(value)
    else:
        _fail("JCS_UNSUPPORTED_FLOAT_OR_TYPE")

def jcs_bytes(value: Any) -> bytes:
    """RFC8785 canonical bytes for this schema's null/bool/string/safe-integer subset.

    Floating point numbers are forbidden: financial values are decimal strings.
    Object keys are UTF-16-ordered as ECMAScript sorts them.
    """
    _check_jcs(value)
    def encode(v: Any) -> str:
        if isinstance(v,dict):
            keys=sorted(v,key=lambda k:k.encode("utf-16-be"))
            return "{" + ",".join(encode(k)+":"+encode(v[k]) for k in keys) + "}"
        if isinstance(v,list): return "[" + ",".join(encode(x) for x in v) + "]"
        if isinstance(v,str): return json.dumps(v,ensure_ascii=False,separators=(",",":"))
        if v is None: return "null"
        if v is True: return "true"
        if v is False: return "false"
        return str(v)
    return encode(value).encode("utf-8")

def digest(value: Any) -> str:
    return hashlib.sha256(jcs_bytes(value)).hexdigest()

def hash_f1(record: Mapping[str,Any]) -> str:
    return digest({k:v for k,v in record.items() if k!="f1_record_sha256"})

def canonical_decimal(raw: str, scale: int, rounding: str, tick: str|None=None) -> str:
    if type(raw) is not str or not re.fullmatch(r"[+-]?(?:\d+)(?:\.\d+)?",raw): _fail("DECIMAL_INVALID")
    if not _int(scale,0) or scale>18: _fail("DECIMAL_SCALE")
    mode={"HALF_EVEN":ROUND_HALF_EVEN,"FLOOR":ROUND_FLOOR,"CEILING":ROUND_CEILING}.get(rounding)
    if mode is None: _fail("DECIMAL_ROUNDING")
    try:
        val=Decimal(raw).quantize(Decimal(1).scaleb(-scale),rounding=mode)
        if not val.is_finite(): _fail("DECIMAL_NONFINITE")
        if tick is not None:
            t=Decimal(tick)
            if not t.is_finite() or t<=0 or val%t: _fail("DECIMAL_TICK_MISMATCH")
    except (InvalidOperation,ValueError) as exc:
        raise CaptureError("DECIMAL_INVALID") from exc
    output=format(val,"f")
    if "." in output: output=output.rstrip("0").rstrip(".")
    if val==0: output="0"
    if not DECIMAL.fullmatch(output): _fail("DECIMAL_CANONICALIZATION_FAILED")
    return output

def _decimal_valid(raw: Any) -> bool:
    return type(raw) is str and DECIMAL.fullmatch(raw) is not None

def _fields(obj: Any, keys: set[str], label: str) -> None:
    if type(obj) is not dict or set(obj)!=keys: _fail(label+"_FIELDS")

def _decimal_context(v: Mapping[str,Any]) -> None:
    if not _decimal_valid(v["tick_size"]) or Decimal(v["tick_size"])<=0: _fail("INVALID_TICK")
    if not _int(v["decimal_scale"],0) or v["decimal_scale"]>18: _fail("INVALID_SCALE")
    if v["rounding_mode"] not in ("HALF_EVEN","FLOOR","CEILING"): _fail("INVALID_ROUNDING")

def _risk(r: Any, cutoff: int, direction: str|None, reference: Any, kind: str) -> None:
    _fields(r,RISK_FIELDS,kind)
    if r["status"]=="NOT_ESTABLISHED":
        if any(v is not None for k,v in r.items() if k!="status"): _fail(kind+"_NOT_ESTABLISHED_NON_NULL")
        return
    if r["status"]!="DEFINED_PREDECISION": _fail(kind+"_STATUS")
    if any(r[k] is None for k in RISK_FIELDS if k!="status"): _fail(kind+"_MISSING_LEVEL")
    if not all(_id(r[k]) for k in ("unit","basis","reference_price_kind")): _fail(kind+"_UNIT_BASIS")
    if not _int(r["defined_at_ms"]) or r["defined_at_ms"]>cutoff: _fail(kind+"_LATE")
    _decimal_context(r)
    if not _decimal_valid(r["level"]) or canonical_decimal(r["level"],r["decimal_scale"],r["rounding_mode"],r["tick_size"])!=r["level"]: _fail(kind+"_DECIMAL")
    if r["unit"]!=reference["unit"] or r["reference_price_kind"]!=reference["reference_kind"]: _fail(kind+"_REFERENCE_MISMATCH")
    if reference["price"] is not None and direction in ("LONG","SHORT"):
        v=Decimal(r["level"]);p=Decimal(reference["price"])
        above=(kind,direction) in (("TP","LONG"),("SL","SHORT"))
        if not (v>p if above else v<p): _fail(kind+"_DIRECTION")

def validate_f1(record: Any, registry: Mapping[str,str]) -> None:
    """Schema/type/nullability, source-as-of, indicator and immutable ID validation.

    Validity is NOT proof of prospective timing; custody must be independently verified.
    """
    _fields(record,FIELDS,"F1")
    if record["schema_version"]!=SCHEMA or record["canonicalization_id"]!=JCS: _fail("F1_SCHEMA")
    for k in HASH_FIELDS:
        if not _is_hash(record[k]): _fail("HASH_"+k)
    for k in TIMES:
        if not _int(record[k]): _fail("TIME_"+k)
    for k in NUMBERS:
        if not _int(record[k],0): _fail("INTEGER_"+k)
    complex_fields={"schema_version","canonicalization_id","c2_identity","indicators","reference","tp","sl","arm","f1_signal_state","predecision_eligibility","f1_record_sha256","pair_id"}
    for k in FIELDS-HASH_FIELDS-TIMES-NUMBERS-NULLABLE-complex_fields:
        if not _id(record[k]): _fail("ID_"+k)
    for k in NULLABLE-{"previous_event_sha256","direction","eligibility_available_at_ms"}:
        if record[k] is not None and not _id(record[k]): _fail("OPTIONAL_ID_"+k)
    if record["previous_event_sha256"] is not None and not _is_hash(record["previous_event_sha256"]): _fail("PREDECESSOR_HASH")
    if (record["producer_sequence"]==0)!=(record["previous_event_sha256"] is None): _fail("GENESIS_SEQUENCE")
    if record["arm"] not in ARMS or record["f1_signal_state"] not in F1_STATES: _fail("ARM_OR_STATE")
    if record["direction"] not in ("LONG","SHORT",None): _fail("DIRECTION")
    if record["predecision_eligibility"] not in ("YES","NO","NOT_ESTABLISHED"): _fail("ELIGIBILITY")
    if record["eligibility_available_at_ms"] is not None and not _int(record["eligibility_available_at_ms"]): _fail("ELIGIBILITY_CLOCK")
    cutoff=record["decision_cutoff_ms"]
    if not (record["prefix_start_ms"]<record["prefix_end_exclusive_ms"]<=cutoff<=record["decision_ms"]): _fail("PREFIX_CUTOFF")
    if record["source_asof_ms"]>cutoff or record["source_available_at_ms"]>cutoff: _fail("SOURCE_LATE")
    if record["predecision_eligibility"]=="YES" and (not record["eligibility_evidence_ref"] or record["eligibility_available_at_ms"] is None or record["eligibility_available_at_ms"]>cutoff): _fail("ELIGIBILITY_PROOF_MISSING")
    _fields(record["c2_identity"],C2_FIELDS,"C2")
    if any(record["c2_identity"][k]!=record[k] for k in C2_FIELDS): _fail("C2_IDENTITY_MISMATCH")
    if record["pair_id"]!=digest({"experiment_plan_sha256":record["experiment_plan_sha256"],"c2_identity":record["c2_identity"]}): _fail("PAIR_ID")
    if type(registry) is not dict or not registry: _fail("INDICATOR_REGISTRY_MISSING")
    indicators=record["indicators"]
    if type(indicators) is not list or [i.get("indicator_id") for i in indicators if type(i) is dict]!=sorted(registry): _fail("INDICATOR_INVENTORY")
    if record["indicator_inventory_manifest_sha256"]!=digest(registry): _fail("INDICATOR_REGISTRY_HASH")
    if len(indicators)!=len(registry): _fail("INDICATOR_COUNT")
    for item in indicators:
        _fields(item,IND_FIELDS,"INDICATOR")
        if item["role"] not in ("DECISION","OBSERVE_ONLY") or item["role"]!=registry[item["indicator_id"]]: _fail("INDICATOR_ROLE")
        if not all(_id(item[k]) for k in ("indicator_id","definition_version","unit")) or not _is_hash(item["parameters_sha256"]): _fail("INDICATOR_METADATA")
        if item["lookback_bars"] is not None and not _int(item["lookback_bars"],0): _fail("LOOKBACK")
        kind=item["value_kind"]
        if kind not in ("NUMBER","BOOLEAN","STRING","UNKNOWN","NOT_APPLICABLE"): _fail("INDICATOR_KIND")
        if kind in ("UNKNOWN","NOT_APPLICABLE"):
            if item["value"] is not None or item["missing_reason"] not in ("INPUT_NOT_FINAL","SOURCE_GAP","NOT_AVAILABLE","NOT_APPLICABLE","UNVERIFIED"): _fail("MISSING_INDICATOR_ENCODING")
        else:
            if item["missing_reason"] is not None: _fail("KNOWN_WITH_MISSING_REASON")
            if kind=="NUMBER" and not _decimal_valid(item["value"]): _fail("NUMBER_DECIMAL")
            if kind=="BOOLEAN" and type(item["value"]) is not bool: _fail("BOOLEAN")
            if kind=="STRING" and not _id(item["value"]): _fail("STRING")
            if any(item[k] is None for k in ("source_asof_ms","available_at_ms","input_prefix_sha256","availability_evidence_ref")): _fail("INDICATOR_PIT_MISSING")
        if item["source_asof_ms"] is not None and (not _int(item["source_asof_ms"]) or item["source_asof_ms"]>cutoff): _fail("INDICATOR_ASOF_LATE")
        if item["available_at_ms"] is not None and (not _int(item["available_at_ms"]) or item["available_at_ms"]>cutoff): _fail("INDICATOR_AVAIL_LATE")
        if item["input_prefix_sha256"] is not None and not _is_hash(item["input_prefix_sha256"]): _fail("INDICATOR_PREFIX")
        if item["availability_evidence_ref"] is not None and not _id(item["availability_evidence_ref"]): _fail("INDICATOR_EVIDENCE_REF")
    ref=record["reference"]
    _fields(ref,REF_FIELDS,"REFERENCE")
    if not _id(ref["reference_kind"]) or not _id(ref["unit"]) or not _is_hash(ref["measurement_policy_sha256"]): _fail("REFERENCE_METADATA")
    _decimal_context(ref)
    if ref["price"] is not None and (not _decimal_valid(ref["price"]) or canonical_decimal(ref["price"],ref["decimal_scale"],ref["rounding_mode"],ref["tick_size"])!=ref["price"]): _fail("REFERENCE_PRICE")
    if ref["price"] is not None and any(ref[k] is None for k in ("reference_asof_ms","reference_available_at_ms","reference_evidence_ref")): _fail("REFERENCE_PIT_PROOF")
    for k in ("reference_asof_ms","reference_available_at_ms"):
        if ref[k] is not None and (not _int(ref[k]) or ref[k]>cutoff): _fail("REFERENCE_LATE")
    if ref["reference_evidence_ref"] is not None and not _id(ref["reference_evidence_ref"]): _fail("REFERENCE_PROOF_FORMAT")
    for kind in ("tp","sl"): _risk(record[kind],cutoff,record["direction"],ref,kind.upper())
    if not _is_hash(record["f1_record_sha256"]) or record["f1_record_sha256"]!=hash_f1(record): _fail("F1_DIGEST_MISMATCH")
    jcs_bytes(record)

def status_slots(expected_c2: list[Mapping[str,Any]],plan_sha: str,candidates: Mapping[tuple[str,str],list[Mapping[str,Any]]],
                 registry: Mapping[str,str],proof_verifier: Callable[[Mapping[str,Any]],bool]|None=None) -> list[dict]:
    """Full denominator and deterministic QUARANTINED/UNVERIFIED/MISSING/RECORDED.

    The proof verifier is a host-supplied independent PIT+commit+anchor verifier,
    not a record field. Without it, structurally valid records stay UNVERIFIED.
    """
    if not _is_hash(plan_sha): _fail("PLAN_SHA")
    rows=[];seen=set()
    for c2 in expected_c2:
        _fields(dict(c2),C2_FIELDS,"C2_SCHEDULE")
        if any(not _id(c2[k]) for k in C2_FIELDS-{"envelope_sha256"}) or not _is_hash(c2["envelope_sha256"]): _fail("SCHEDULE_IDENTITY")
        pair=digest({"experiment_plan_sha256":plan_sha,"c2_identity":dict(c2)})
        if pair in seen: _fail("DUPLICATE_SCHEDULED_C2")
        seen.add(pair)
        for arm in ARMS:
            entries=list(candidates.get((pair,arm),[]))
            row={"pair_id":pair,"arm":arm,"c2_identity":dict(c2),"capture_status":"MISSING_CAPTURE","f1_record_sha256":None,"reason_code":None}
            if entries:
                hashes=[];invalid=[]
                for item in entries:
                    try:
                        validate_f1(item,registry)
                        if item["pair_id"]!=pair or item["arm"]!=arm: _fail("SCHEDULE_ARM_BINDING")
                        hashes.append((item["f1_record_sha256"],item["producer_sequence"]))
                    except (CaptureError,KeyError,TypeError) as e: invalid.append(str(e))
                if invalid or len(set(hashes))!=1:
                    row.update(capture_status="QUARANTINED",reason_code=";".join(invalid) if invalid else "CONFLICTING_REPLAY")
                else:
                    original=entries[0]
                    row["f1_record_sha256"]=original["f1_record_sha256"]
                    if proof_verifier is None:
                        row.update(capture_status="UNVERIFIED",reason_code="INDEPENDENT_PIT_AND_COMMIT_PROOF_UNAVAILABLE")
                    else:
                        try: valid=proof_verifier(original) is True
                        except Exception: valid=False
                        row.update(capture_status="RECORDED" if valid else "UNVERIFIED",reason_code=None if valid else "INDEPENDENT_PROOF_UNCONFIRMED")
            rows.append(row)
    if set(candidates)-{(r["pair_id"],r["arm"]) for r in rows}: _fail("ORPHAN_CANDIDATE")
    return rows

def validate_commit_receipt(receipt: Mapping[str,Any],record: Mapping[str,Any]) -> None:
    keys={"schema_version","receipt_id","f1_record_sha256","producer_sequence","previous_event_sha256","frozen_arm_event_sha256","committed_at_ms","durable_store_ref","independent_anchor_ref","commit_receipt_sha256"}
    _fields(dict(receipt),keys,"COMMIT_RECEIPT")
    if (receipt["schema_version"]!="aql.f1-commit-receipt.v1" or receipt["f1_record_sha256"]!=record["f1_record_sha256"] or receipt["producer_sequence"]!=record["producer_sequence"] or receipt["previous_event_sha256"]!=record["previous_event_sha256"] or receipt["frozen_arm_event_sha256"]!=record["arm_event_sha256"]): _fail("COMMIT_BINDING")
    if not all(_id(receipt[k]) for k in ("receipt_id","durable_store_ref","independent_anchor_ref")) or not _int(receipt["committed_at_ms"]): _fail("COMMIT_FIELDS")
    if receipt["commit_receipt_sha256"]!=digest({k:v for k,v in receipt.items() if k!="commit_receipt_sha256"}): _fail("COMMIT_HASH")

def validate_ack(ack: Mapping[str,Any],record: Mapping[str,Any],receipt: Mapping[str,Any]) -> None:
    keys={"schema_version","ack_id","ack_for_f1_record_sha256","ack_for_commit_receipt_sha256","acknowledged_at_ms","ack_evidence_class","ack_sha256"}
    _fields(dict(ack),keys,"ACK")
    if ack["schema_version"]!="aql.f1-ack.v1" or ack["ack_for_f1_record_sha256"]!=record["f1_record_sha256"] or ack["ack_for_commit_receipt_sha256"]!=receipt["commit_receipt_sha256"]: _fail("ACK_BINDING")
    if not _id(ack["ack_id"]) or not _id(ack["ack_evidence_class"]) or not _int(ack["acknowledged_at_ms"]): _fail("ACK_FIELDS")
    if ack["ack_sha256"]!=digest({k:v for k,v in ack.items() if k!="ack_sha256"}): _fail("ACK_HASH")

def validate_excursion(outcome: Mapping[str,Any],original: Mapping[str,Any]|None,verified: bool) -> None:
    """Never upgrade complete MARKET_ONLY OHLC to signed directional MFE/MAE."""
    keys=("measurement_class","coverage_status","excursion_status","max_favorable","max_adverse","tp_sl_first_hit")
    if any(k not in outcome for k in keys): _fail("OUTCOME_FIELDS")
    if outcome["measurement_class"] not in ("MARKET_ONLY","COMMON_PAIRED","ARM_SPECIFIC_POLICY"): _fail("MEASUREMENT_CLASS")
    signed=outcome["measurement_class"]!="MARKET_ONLY"
    eligible=(signed and verified is True and original is not None and original.get("direction") in ("LONG","SHORT") and original.get("predecision_eligibility")=="YES" and original.get("reference",{}).get("price") is not None and outcome["coverage_status"]=="COMPLETE")
    if not eligible:
        if outcome["max_favorable"] is not None or outcome["max_adverse"] is not None or outcome["excursion_status"]=="EVALUABLE": _fail("SIGNED_MFE_MAE_FORBIDDEN")
    elif outcome["excursion_status"]=="EVALUABLE":
        if not _decimal_valid(outcome["max_favorable"]) or not _decimal_valid(outcome["max_adverse"]): _fail("SIGNED_EXCURSION_DECIMAL")
    if outcome["tp_sl_first_hit"] not in ("TP_FIRST","SL_FIRST","NEITHER","UNKNOWN","NOT_ESTABLISHED"): _fail("HIT_ORDER")

def duplicate_keys_reject(pairs: list[tuple[str,Any]]) -> dict:
    obj={}
    for key,value in pairs:
        if key in obj: _fail("JSON_DUPLICATE_KEY")
        obj[key]=value
    return obj

def write_original_candidate(path: Path,record: Mapping[str,Any],registry: Mapping[str,str]) -> str:
    """Append+fsync/read back only validated original *candidate*, not an external anchor."""
    validate_f1(dict(record),registry)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=jcs_bytes(dict(record))+b"\n"
    fd=os.open(path,os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
    try:
        os.write(fd,data);os.fsync(fd)
    finally:
        os.close(fd)
    with path.open("rb") as handle:
        if data not in handle.read().splitlines(keepends=True): _fail("DURABLE_READBACK_FAILURE")
    return record["f1_record_sha256"]
