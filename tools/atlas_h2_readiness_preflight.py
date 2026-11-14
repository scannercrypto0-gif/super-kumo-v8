"""ATLAS H2 original-history readiness ONLY: zero IO to private source.

An authorization preflight, never an owner-source operator or a waiver of
independent custody, economic, PIT, source-rights or trading approvals.
No imports from Warehouse, SQLite, scanners or engine implementations.
"""
from __future__ import annotations
import argparse
import json
import re
from decimal import Decimal, InvalidOperation

SCHEMA="aql.integration.h2.readiness-request.v1"
RESULT_SCHEMA="aql.integration.h2.readiness-result.v1"
SHA=re.compile(r"^[0-9a-f]{40}$")
HEX=re.compile(r"^[0-9a-f]{64}$")
KEYS=("fee_entry_bps","fee_exit_bps","spread_entry_bps","spread_exit_bps",
      "slippage_entry_bps","slippage_exit_bps","funding_bps_per_bar")
REQUIRED=("integration","core","scanner","factory","work235")
EXPECTED={
    "core":"99c27ea2c1a4d41aaae361141301a8a9ea3b33c3",
    "scanner":"3c82448702c9ae35783716e4e2c3b640010db97c",
    "factory":"a4b887fe7067b89febc339e466652a5fcb1c2bee",
    "work235":"6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
}
REQUEST_FIELDS={"schema","exact_heads","bounded_request","owner_permission",
                "owner_cost_policy","source_provenance"}
BOUNDED_FIELDS={"dataset_id","month","start_ms","end_exclusive_ms",
                "decision_cutoff_ms","strategy_definition_sha256"}
PERMISSION_FIELDS={"granted","scope","authorization_reference"}
COST_FIELDS={"owner_authorized","authorization_reference","market",
             "direction","scenario_class","costs"}
PROVENANCE_FIELDS={"source_rights_attested","publisher_pit_attested",
                   "source_receipt_sha256","manifest_integrity_sha256",
                   "core245_native_query_sha256","core253_local_query_sha256"}


def result(status,reason):
    return {"schema":RESULT_SCHEMA,"status":status,"reason":reason,
            "operation":"READINESS_ONLY_NO_SOURCE_IO",
            "owner_private_data_accessed":False,
            "warehouse_written":False,
            "trading_authority":"NONE","f5":"BLOCKED_EXTERNAL_INPUT",
            "holdout":"SEALED_UNOPENED"}


def _hash(v,n=64):
    return type(v) is str and (HEX if n==64 else SHA).fullmatch(v) is not None


def _cost_good(cost):
    if type(cost) is not dict or set(cost)!=COST_FIELDS:
        return False
    if (cost.get("owner_authorized") is not True
        or type(cost.get("authorization_reference")) is not str
        or not cost["authorization_reference"].strip()
        or cost.get("market")!="SPOT" or cost.get("direction")!="LONG"
        or cost.get("scenario_class")!="OWNER_DECLARED_RESEARCH_SCENARIO"
        or type(cost.get("costs")) is not dict
        or set(cost["costs"])!=set(KEYS)):
        return False
    nums={}
    try:
        for k,v in cost["costs"].items():
            if type(v) is not str or not v or v.strip()!=v:
                return False
            d=Decimal(v)
            if not d.is_finite() or d<0:
                return False
            nums[k]=d
    except InvalidOperation:
        return False
    return nums["funding_bps_per_bar"]==0 and any(
        nums[k]>0 for k in KEYS if k!="funding_bps_per_bar")


def assess(request):
    """Pure and fail-closed; no filesystem calls and no source-handle imports."""
    if type(request) is not dict or set(request)!=REQUEST_FIELDS or request.get("schema")!=SCHEMA:
        return result("BLOCKED_CONTRACT","H2_REQUEST_SCHEMA")
    heads=request["exact_heads"]
    if (type(heads) is not dict or set(REQUIRED)-set(heads)
        or any(not _hash(v,40) for v in heads.values())
        or any(heads.get(k)!=v for k,v in EXPECTED.items())):
        return result("BLOCKED_CONTRACT","EXACT_OWNER_HEAD_MISMATCH")
    bounded=request["bounded_request"]
    if (type(bounded) is not dict or set(bounded)!=BOUNDED_FIELDS
        or type(bounded["dataset_id"]) is not str
        or not bounded["dataset_id"].startswith("BINANCE-SPOT-BTCUSDT-15M-")
        or type(bounded["month"]) is not str
        or not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])",bounded["month"])
        or not _hash(bounded["strategy_definition_sha256"])
        or any(type(bounded[k]) is not int for k in (
            "start_ms","end_exclusive_ms","decision_cutoff_ms"))
        or bounded["start_ms"]<0
        or bounded["end_exclusive_ms"]<=bounded["start_ms"]
        or bounded["end_exclusive_ms"]-bounded["start_ms"]>4096*900000
        or any(bounded[k]%900000 for k in ("start_ms","end_exclusive_ms"))
        or bounded["decision_cutoff_ms"]<bounded["start_ms"]
        or bounded["decision_cutoff_ms"]>bounded["end_exclusive_ms"]):
        return result("BLOCKED_CONTRACT","BOUNDED_CUTOFF_OR_STRATEGY")
    permission=request["owner_permission"]
    if (type(permission) is not dict or set(permission)!=PERMISSION_FIELDS
        or permission.get("granted") is not True
        or permission.get("scope")!="BOUNDED_ORIGINAL_HISTORY_READONLY"
        or type(permission.get("authorization_reference")) is not str
        or not permission["authorization_reference"].strip()):
        return result("WAIT_SOURCE_PERMISSION","EXPLICIT_OWNER_SOURCE_AUTHORIZATION_REQUIRED")
    if not _cost_good(request["owner_cost_policy"]):
        return result("WAIT_COST_POLICY","INDEPENDENT_OWNER_COST_POLICY_REQUIRED")
    provenance=request["source_provenance"]
    if (type(provenance) is not dict or set(provenance)!=PROVENANCE_FIELDS
        or provenance.get("source_rights_attested") is not True
        or provenance.get("publisher_pit_attested") is not True
        or any(not _hash(provenance.get(k)) for k in (
            "source_receipt_sha256","manifest_integrity_sha256",
            "core245_native_query_sha256","core253_local_query_sha256"))
        or provenance["core245_native_query_sha256"]==
           provenance["core253_local_query_sha256"]):
        return result("WAIT_PROVENANCE","INDEPENDENT_SOURCE_RIGHTS_PIT_AND_DUAL_QUERY_REQUIRED")
    # A declarative manifest is NOT permission to open any original private file,
    # regardless of caller claims in the JSON. Only owner may authorize a future
    # separate operator; self-reported booleans are not independent evidence.
    return result("READY_FOR_OWNER_AUTHORIZATION",
                  "SELF_DECLARED_INPUTS_REQUIRE_INDEPENDENT_REVIEW_NO_EXECUTION")


def main(argv=None):
    p=argparse.ArgumentParser(description="H2 permission gate: no original file IO")
    p.add_argument("--request-json",required=True,
                   help="PUBLIC synthetic readiness request, never owner paths/bytes")
    a=p.parse_args(argv)
    try:
        doc=json.loads(a.request_json)
    except (ValueError,TypeError):
        doc=None
    print(json.dumps(assess(doc),sort_keys=True,separators=(",",":")))
    return 0 if assess(doc)["status"]=="READY_FOR_OWNER_AUTHORIZATION" else 2


if __name__=="__main__":
    raise SystemExit(main())
