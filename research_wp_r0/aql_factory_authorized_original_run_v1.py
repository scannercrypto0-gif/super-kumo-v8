"""Private owner-authorized #254 source smoke. NEVER download or publish bytes.

Only SHA-pinned February/August BTCUSDT Spot 15m Work #247 originals can
enter this path. No fixtures accepted as genuine. The result is SOURCE/RAW
custody only, NOT Scanner→strategy→Paper E2E or source historical PIT.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile,BadZipFile

from research_wp_r0.aql_factory_unified_backbone_v1 import (
    consume_core_warehouse_query,freeze,
)

CORE_SHA="5d7c869d97ad99219a5ef27f9c841c70f0fcd505"
RAW_SHA="7d97b09c0c6ee2650a61d523acb8d8c771a99c46"
PINS={
 "2024-02":("55066890cd3a76c97c05e94213311b17a4146d697f6abe8762b3edae8495b20e",
            "7621f87a8fa1d2588fdaebacdd30333d2feaa05b453118c7c697f17aa27f4720",
            "57d0671d08ef213d12bdc145624665ed8b62cdc6b71190f57557cefa76ff4eec",
            2784,"BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1"),
 "2024-08":("44e084e916a4c661b2177741d71438916388c0d34554f63cb147973aac13b094",
            "54fecf17078a8fb0d1a6ec16be6a64003947bf411e2697ced2815162cb69a7b0",
            "3fe8d6caf60fa6e7b7bc22e482fc04710aaedbd281dc725fba8a36e913e33118",
            2976,"BINANCE-SPOT-BTCUSDT-15M-2024-08-DEV-v1"),
}
class OriginalAccessError(ValueError): pass

def need(ok,why):
    if not ok: raise OriginalAccessError("FACTORY_254_ORIGINAL_"+why)

def digest(b): return sha256(b).hexdigest()

def preflight(raw,checksum,month,expected):
    """Pure checker, testable with independently generated TEST_ONLY pins."""
    need(type(raw) is bytes and 0<len(raw)<=8_000_000,"SOURCE_SIZE")
    need(type(checksum) is bytes and 0<len(checksum)<=4096,"CHECKSUM_SIZE")
    zhash,mhash,chash,n,ds=expected
    need(digest(raw)==zhash,"SOURCE_SHA_MISMATCH")
    need(digest(checksum)==chash,"CHECKSUM_FILE_SHA_MISMATCH")
    name=f"BTCUSDT-15m-{month}.zip"
    member=f"BTCUSDT-15m-{month}.csv"
    try:
        with ZipFile(BytesIO(raw)) as archive:
            need(archive.namelist()==[member],"MEMBER_IDENTITY")
            need(archive.getinfo(member).file_size<=4_000_000,"MEMBER_SIZE")
            need(archive.testzip() is None,"CRC_FAIL")
            need(digest(archive.read(member))==mhash,"MEMBER_SHA_MISMATCH")
    except (BadZipFile,OSError,KeyError) as exc:
        raise OriginalAccessError("FACTORY_254_ORIGINAL_ZIP_INVALID") from exc
    try: parts=checksum.decode("ascii").strip().split()
    except UnicodeError as exc:
        raise OriginalAccessError("FACTORY_254_ORIGINAL_CHECKSUM_ENCODING") from exc
    need(len(parts)==2 and parts[0].lower()==zhash
         and parts[1].lstrip("*")==name,"CHECKSUM_CONTENT")
    return {"dataset_id":ds,"source_sha256":zhash,"member_sha256":mhash,
            "checksum_sha256":chash,"bar_count":n,
            "archive_name":name,"member_name":member}

def verify_original(raw,checksum,month):
    """Production binding: untrusted caller cannot override trusted pins."""
    need(month in PINS,"UNRECOGNIZED_MONTH")
    return preflight(raw,checksum,month,PINS[month])

def pinned_dir(path,sha):
    d=Path(path).resolve(strict=True)
    need(d.is_dir(),"CHECKOUT_MISSING")
    try:
        p=subprocess.run(["git","-C",str(d),"rev-parse","HEAD"],
                         capture_output=True,text=True,check=True,timeout=15)
    except (OSError,subprocess.SubprocessError) as exc:
        raise OriginalAccessError("FACTORY_254_ORIGINAL_CODE_SHA_UNAVAILABLE") from exc
    need(p.stdout.strip()==sha,"PINNED_CODE_CHANGED")
    return d

def month_spec(month,cutoff,pin):
    y,m=map(int,month.split("-"))
    start=int(datetime(y,m,1,tzinfo=timezone.utc).timestamp()*1000)
    end=int(datetime(y+1,1,1,tzinfo=timezone.utc).timestamp()*1000) if m==12 else int(
        datetime(y,m+1,1,tzinfo=timezone.utc).timestamp()*1000)
    need(type(cutoff) is int and cutoff>=
         int(datetime(2026,11,1,tzinfo=timezone.utc).timestamp()*1000),
         "OBSERVATION_CUTOFF_NOT_RETROSPECTIVE")
    return dict(dataset_id=pin["dataset_id"],version=1,symbol="BTCUSDT",
                interval="15m",exchange="BINANCE",market="SPOT",
                source_label="owner-authorized-existing-work247-original",
                start_ms=start,end_exclusive_ms=end,as_of_ms=cutoff,
                parent_source_sha256=None,correction_reason=None,
                test_only=False)

def run_source_only(raw,checksum,month,cutoff,core_checkout,raw_checkout,
                    core_root,vault_root):
    """SHA-pin and commit one original archive; DO NOT fake a Scanner receipt."""
    p=verify_original(raw,checksum,month)
    spec=month_spec(month,cutoff,p)
    core=pinned_dir(core_checkout,CORE_SHA)
    vault=pinned_dir(raw_checkout,RAW_SHA)
    sys.path.insert(0,str(core));sys.path.insert(0,str(vault))
    import research_wp_r0
    research_wp_r0.__path__.insert(0,str(core/"research_wp_r0"))
    import tools
    tools.__path__.insert(0,str(vault/"tools"))
    from tools.raw_vault_offline.vault import RawVault
    from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original,query_local
    from research_wp_r0.aql_authenticated_historical_admission_v1 import admit_original_bytes
    from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
    from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
    from research_wp_r0.aql_core_chronology_universe_evidence_v1 import assess_chronology_universe
    from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
    from research_wp_r0.historical_library import HistoricalLibrary
    core_root=Path(core_root).resolve();vault_root=Path(vault_root).resolve()
    need(core_root!=vault_root and core_root not in vault_root.parents
         and vault_root not in core_root.parents,"RAW_STORE_MUST_BE_SEPARATE")
    pin=dict(schema="aql.core.external-original-byte-pin.v1",
             source_kind="BINANCE_KLINES_ZIP",
             original_object_id=f"BTCUSDT-15m-{month}",
             original_sha256=p["source_sha256"],
             provenance_reference="WORK247_AUDIT248_EXISTING_RETAINED_BYTES",
             captured_at_ms=None,claimed_available_at_ms=None,
             expected_inventory_sha256=None,vault_object_metadata=None,
             universe_manifest_sha256=None,universe_member_count=None,
             test_only=False,archive_name=p["archive_name"],
             csv_member_name=p["member_name"],csv_member_sha256=p["member_sha256"],
             checksum_file_sha256=p["checksum_sha256"])
    raw_vault=RawVault(vault_root)
    warehouse=admit_local_original(core_root,raw,checksum,pin,spec,
                                  decision_cutoff_ms=cutoff,vault=raw_vault)
    need(warehouse["status"]=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
         and raw_vault.read(p["source_sha256"])==raw
         and raw_vault.recovery_scan()["status"]=="CLEAN",
         "RAW_COMMIT_READBACK")
    query=query_local(core_root,p["dataset_id"],1,spec["start_ms"],
                      spec["end_exclusive_ms"],cutoff,
                      required_source_sha256=p["source_sha256"])
    need(query["coverage"]=="COMPLETE"
         and query["available_bar_count"]==p["bar_count"],"BAR_CENSUS")
    lib=HistoricalLibrary()
    admission=admit_original_bytes(raw,pin,spec,
               stager=OfflineBridgeStager(core_root/"factory254-verify"),
               library=lib,decision_cutoff_ms=cutoff,checksum_file_bytes=checksum)
    price=query_price_custody(lib,dict(schema=REQUEST_SCHEMA,
             dataset_id=p["dataset_id"],version=1,
             start_ms=spec["start_ms"],end_exclusive_ms=spec["end_exclusive_ms"],
             decision_cutoff_ms=cutoff,require_complete=False,
             confirmed_only=False),
             expected_source_sha256=p["source_sha256"],
             expected_manifest_integrity_sha256=admission["manifest_integrity_sha256"])
    chronology=assess_chronology_universe(
        admission,price,chronology_evidence=None,universe_evidence=None)
    source=consume_core_warehouse_query(admission,price,chronology,warehouse,query)
    need(source["raw_warehouse_query"]=="CONNECTED_PINNED_CORE_253_RAW_WAREHOUSE"
         and not source["source_eligible_for_historical_pit"],"FACTORY_RAW_LINK")
    return freeze({
        "schema":"aql.factory.authentic-original-source-only-smoke.v1",
        "cohort":month,"source_archive_sha256":p["source_sha256"],
        "source_member_sha256":p["member_sha256"],
        "checksum_file_sha256":p["checksum_sha256"],
        "source_receipt_sha256":source["artifact_sha256"],
        "raw_211_sha":RAW_SHA,"core_253_sha":CORE_SHA,
        "warehouse_receipt_sha256":warehouse["receipt_sha256"],
        "query_sha256":query["query_sha256"],
        "retained_original_bar_count":query["available_bar_count"],
        "coverage":query["coverage"],
        "raw_vault":"EXISTING_PINNED_RAW_VAULT",
        "independent_publisher_issuance":"NOT_ATTESTED",
        "historical_known_at":None,
        "scanner_secretary":"NOT_CONNECTED_SOURCE_LOCKED_SCANNER_EVIDENCE",
        "independent_work_policy":"NOT_CONNECTED_SOURCE_MATCH_MISSING",
        "authentic_source_to_paper_e2e":"NOT_COMPLETE",
        "holdout":"SEALED_UNOPENED",
        "orders_created":0,"trading_authority":"NONE",
        "scientific_result":"INSUFFICIENT_EVIDENCE",
    })

def main(argv=None):
    ap=argparse.ArgumentParser(description="Private SHA-pinned original source smoke")
    for name in ("month","original-zip","checksum-file","core-checkout",
                 "raw-checkout","core-root","raw-root","receipt-out","cutoff-ms"):
        ap.add_argument("--"+name,required=True,
                        type=int if name=="cutoff-ms" else str)
    args=vars(ap.parse_args(argv))
    try:
        need(os.environ.get("AQL_AUTHORIZED_ORIGINAL_CORE_FACTORY_RUNNER")==
             "OWNER_APPROVED_PRIVATE_ONLY","RUNNER_AUTHORIZATION_MISSING")
        month=args["month"]
        need(month in PINS,"MONTH_UNKNOWN")
        zp=Path(args["original-zip"]).resolve(strict=True)
        cs=Path(args["checksum-file"]).resolve(strict=True)
        out=Path(args["receipt-out"]).resolve()
        need(zp.name==f"BTCUSDT-15m-{month}.zip"
             and cs.name==zp.name+".CHECKSUM"
             and zp.is_file() and cs.is_file()
             and zp.stat().st_size<=8_000_000
             and cs.stat().st_size<=4096,"PRIVATE_INPUT_MISSING")
        need(not out.is_relative_to(Path.cwd().resolve()),
             "NO_OUTPUT_INSIDE_REPO")
        result=run_source_only(
            zp.read_bytes(),cs.read_bytes(),month,args["cutoff-ms"],
            args["core-checkout"],args["raw-checkout"],
            args["core-root"],args["raw-root"])
        need(out.parent.is_dir() and not out.exists(),"RECEIPT_CREATE_ONLY")
        with os.fdopen(os.open(str(out),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),
                       "w",encoding="utf-8") as f:
            json.dump(result,f,sort_keys=True,separators=(",",":"))
            f.write("\n");f.flush();os.fsync(f.fileno())
        print("OWNER_ORIGINAL_SOURCE_ONLY_COMPLETE; PAPER_E2E_NOT_COMPLETE")
        return 0
    except (OSError,ValueError,KeyError) as exc:
        msg=str(exc)
        print(msg if msg.startswith("FACTORY_254_ORIGINAL_") else
              "FACTORY_254_ORIGINAL_RUN_BLOCKED",file=sys.stderr)
        return 2
if __name__=="__main__": raise SystemExit(main())
