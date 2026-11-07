#!/usr/bin/env python3
"""ATLAS owner-only F2 recovery entry-shape probe (stdlib, read-only).

Never prints field values, identifiers, SHA digests, source paths, exception
messages, OHLCV, or source bytes. The owner report itself is NOT modified.
This is only a diagnostics probe, never a trading or F5 approval gate.
"""
from __future__ import annotations
import argparse
import calendar
import hashlib
import json
from pathlib import Path

EXPECTED_RAW_SHA = "52b47d7d93f5966fffe41ae16cb21486fb14a0753a2821dccc35f4f09e4903d2"
EXPECTED_INTERNAL_SHA = "0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220"
MONTHS = ("2024-01","2024-03","2024-04","2024-05","2024-06",
          "2024-07","2024-09","2024-10","2024-11","2024-12")
FIELDS = frozenset(("bars","core245_native_query_sha256",
                   "core253_local_query_sha256","dataset_id","manifest_sha256",
                   "month","source_sha256","state"))
DIGEST_KEYS = ("source_sha256","manifest_sha256",
               "core245_native_query_sha256","core253_local_query_sha256")
ERROR = "OWNER_REPORT_MONTH_CENSUS_OR_IDENTITY_DRIFT"


def _is_sha(value):
    return type(value) is str and len(value)==64 and all(
        char in "0123456789abcdef" for char in value)


def categories(report):
    issues={}
    expected=set(MONTHS)
    def mark(code, month=None):
        found=issues.setdefault(code,set())
        if type(month) is str and month in expected:
            found.add(month)
    if type(report) is not dict or type(report.get("entries")) is not list:
        mark("ENTRY_COUNT")
    else:
        rows=report["entries"]
        if len(rows)!=10:
            mark("ENTRY_COUNT")
        seen=[]
        total=0
        valid_numbers=True
        for row in rows[:24]:
            if type(row) is not dict:
                mark("ENTRY_FIELDS")
                valid_numbers=False
                continue
            month=row.get("month")
            known=month if type(month) is str and month in expected else None
            if set(row)!=FIELDS:
                mark("ENTRY_FIELDS",known)
            if known is None:
                mark("MONTH_SET")
            else:
                seen.append(known)
                y,m=map(int,known.split("-"))
                expected_bars=calendar.monthrange(y,m)[1]*96
                if type(row.get("bars")) is not int or row["bars"]!=expected_bars:
                    mark("MONTH_BAR_CENSUS",known)
                if row.get("dataset_id")!=(
                    "BINANCE-SPOT-BTCUSDT-15M-"+known+"-F-v1"):
                    mark("DATASET_ID_PATTERN",known)
            if row.get("state")!="RAW_AND_DUAL_QUERY_READBACK":
                mark("STATE_LITERAL",known)
            if any(not _is_sha(row.get(k)) for k in DIGEST_KEYS):
                mark("DIGEST_FORMAT",known)
            if type(row.get("bars")) is int:
                total+=row["bars"]
            else:
                valid_numbers=False
        if len(rows)>24:
            mark("ENTRY_COUNT")
        if len(seen)!=10 or set(seen)!=expected:
            mark("MONTH_SET")
            for m in expected.difference(seen):
                mark("MONTH_SET",m)
            for m in set(seen):
                if seen.count(m)>1:
                    mark("MONTH_SET",m)
        if not valid_numbers or total!=29376 or len(rows)>24:
            mark("TOTAL_BARS")
    return [{"category":category,"months":sorted(labels)[:10]}
            for category,labels in sorted(issues.items())][:8]


def _no_duplicate_keys(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise ValueError("duplicate json key")
        out[key]=value
    return out


def _reject_constant(_):
    raise ValueError("nonfinite json")


# Evidence-grounded candidates represent distinct historical source
# stages; only the literal selected after inspecting the original producer
# can be promoted into the Core research receipt contract. Never accept
# any of these candidates automatically as source authority.
STATE_CANDIDATES = (
    "RAW_AND_DUAL_QUERY_READBACK",          # F2 original admission
    "OWNER_LOCAL_DUAL_READBACK_PASS",       # observed report disposition
    "REVERIFIED_PRIVATE_BYTES",             # F2 local byte recheck
    "OFFLINE_LOCAL_WAREHOUSE_COMMITTED",    # indexed warehouse receipt
    "ORIGINAL_PIN_MATCHED_PROVENANCE_PENDING",  # sealed #226 admission
)


def state_equality_classes(report):
    """Boolean-only candidate matches; no raw producer state string output."""
    if type(report) is not dict or type(report.get("entries")) is not list:
        return {"uniform": False, "matches": [], "all_ten_matched": False}
    rows=report["entries"]
    if len(rows)!=10 or any(type(row) is not dict for row in rows):
        return {"uniform": False, "matches": [], "all_ten_matched": False}
    vals=[row.get("state") for row in rows]
    uniform=all(type(v) is str and v==vals[0] for v in vals)
    matches=[{"candidate":name,"all_ten_equal":all(v==name for v in vals)}
             for name in STATE_CANDIDATES]
    return {"uniform":uniform,"matches":matches,
            "all_ten_matched":any(x["all_ten_equal"] for x in matches)}


def probe(path):
    """Only static safe output. Never trusts caller SHA or user-provided mapping."""
    try:
        p=Path(path).absolute()
        if any(x.is_symlink() for x in (p,*p.parents)) or not p.is_file():
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_READ_DENIED",
                    "mismatches":[]}
        if p.stat().st_size==0 or p.stat().st_size>5_000_000:
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_READ_DENIED",
                    "mismatches":[]}
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=EXPECTED_RAW_SHA:
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_FILE_PIN_MISMATCH",
                    "mismatches":[]}
        obj=json.loads(raw,object_pairs_hook=_no_duplicate_keys,
                       parse_constant=_reject_constant)
        if type(obj) is not dict or obj.get("schema")!=(
            "aql.owner-local.f2-recovery-evidence.v1") or obj.get(
            "recovery_sha256")!=EXPECTED_INTERNAL_SHA or obj.get(
            "disposition")!="OWNER_LOCAL_DUAL_READBACK_PASS" or type(
            obj.get("verified_months")) is not int or obj["verified_months"]!=10 or type(
            obj.get("verified_bars")) is not int or obj["verified_bars"]!=29376:
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_ROOT_PIN_FAILED",
                    "mismatches":[]}
        mismatches=categories(obj)
        if mismatches:
            result={"status":"PRIVATE_WAIT","code":ERROR,
                    "mismatches":mismatches}
            if len(mismatches)==1 and mismatches[0]["category"]=="STATE_LITERAL":
                result["state_equality"]=state_equality_classes(obj)
            return result
        # Keep all separate F5 authority predicates even though this probe is
        # diagnostic-only and does not sign or confer any authority.
        if obj.get("historical_pit")!="NOT_ATTESTED" or obj.get(
            "trading_authority")!="NONE" or obj.get(
            "signed_f5_approval") not in (None,False) or obj.get(
            "original_f2_report_restored") is not False:
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_AUTHORITY_DENIED",
                    "mismatches":[]}
        return {"status":"ENTRY_PREDICATES_PASS","code":"NONE","mismatches":[]}
    except (OSError,ValueError,TypeError,UnicodeError,OverflowError):
        return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_READ_OR_PARSE_DENIED",
                "mismatches":[]}


def main():
    parser=argparse.ArgumentParser(description="Read-only, SHA-pinned owner report entry diagnosis")
    parser.add_argument("--recovery-file",required=True)
    args=parser.parse_args()
    print(json.dumps(probe(args.recovery_file),
                     sort_keys=True,separators=(",",":")))


if __name__=="__main__":
    main()
