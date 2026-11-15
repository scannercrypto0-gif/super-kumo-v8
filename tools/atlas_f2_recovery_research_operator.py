"""One owner-private F2_RECOVERY_EVIDENCE.v1 research-only integration runner.

No original-F2 impersonation, independent F5 authority, source writes or
fabricated strategy approval. Owner must provide genuine recovery/mapping,
frozen Work235 fixture and real Factory original-month diagnostic packet.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from tools.atlas_f2_recovery_evidence_v1 import (
    read_recovered_diagnostic, EXPECTED_RECOVERY_FILE_SHA256,
)
from tools.atlas_f_research_diagnostic_operator import (
    canonical, digest, demand, read_json, verify_pinned_modules,
)

SCHEMA="aql.integration.f2-recovery-research-operator.v1"
FIELDS={
    "schema","owner_operator_authorized","warehouse_root","vault_root",
    "recovery_file","recovery_mapping_file","frozen_work235_file",
    "factory_recovery_input_file","fresh_results_store","sanitized_output",
}


def run(manifest):
    demand(type(manifest) is dict and set(manifest)==FIELDS
           and manifest["schema"]==SCHEMA
           and manifest["owner_operator_authorized"] is True,
           "RECOVERY_PRIVATE_MANIFEST_AND_AUTHORIZATION_REQUIRED")
    vault=Path(manifest["vault_root"]).resolve(strict=True)
    warehouse=Path(manifest["warehouse_root"]).resolve(strict=True)
    demand(vault.is_dir() and warehouse.is_dir() and vault!=warehouse,
           "RECOVERY_DISTINCT_EXISTING_SOURCE_ROOTS")
    store=Path(manifest["fresh_results_store"]).absolute()
    out=Path(manifest["sanitized_output"]).absolute()
    demand(store!=out and not store.exists() and not out.exists()
           and store.parent.is_dir() and out.parent.is_dir()
           and not store.is_symlink() and not out.is_symlink(),
           "RECOVERY_FRESH_RESULTS_AND_RECEIPT_REQUIRED")
    for p in (store,out):
        rp=p.resolve(strict=False)
        demand(rp!=vault and rp!=warehouse and vault not in rp.parents
               and warehouse not in rp.parents,
               "RECOVERY_NO_WRITES_UNDER_SOURCE")
    # The three old F2 operator modules stay pinned; new recovery modules
    # are staged by the exact-head Integration workflow and tested separately.
    verify_pinned_modules()
    mapping=read_json(manifest["recovery_mapping_file"])
    original=read_recovered_diagnostic(
        warehouse,vault,manifest["recovery_file"],mapping)
    from tools.scanner_strategy_f.frozen_diagnostic_contracts import (
        load_frozen_work235_contracts,
    )
    from tools.scanner_strategy_f.recovery_diagnostic_adapter import (
        diagnostic_from_verified_recovery,
    )
    frozen=load_frozen_work235_contracts(manifest["frozen_work235_file"])
    scanner=diagnostic_from_verified_recovery(
        warehouse_root=warehouse,
        verified_recovery_readbacks=original,
        recovery_file_sha256=EXPECTED_RECOVERY_FILE_SHA256,
        work_specs=frozen["work_specs"])
    scanner_data=scanner["payload"]
    demand(scanner_data["attempts"]==24 and
           scanner_data["diagnostic_evaluated"]==20 and
           scanner_data["feb_aug_unknown"]==4 and
           scanner_data["selected"]==0 and
           scanner_data["original_f2_report_sha256"] is None and
           scanner_data["trading_authority"]=="NONE",
           "RECOVERY_SCANNER_SCOPE_OR_AUTHORITY_DRIFT")
    factory=read_json(manifest["factory_recovery_input_file"])
    from research_wp_r0.aql_factory_f_f2_recovery_research_v2 import (
        validate_recovery_research_input, run_recovery_research_v2,
    )
    from research_wp_r0.aql_factory_e_research_results_store_v1 import (
        migrate_store_v2, digest as factory_digest,
    )
    definitions, parents=validate_recovery_research_input(factory)
    month=factory["trial_packet"]["diagnostic_month"]
    demand(month in original,"RECOVERY_FACTORY_FOCUS_NOT_ORIGINAL")
    receipt=original[month]["receipt"]
    demand(factory["original_f2_report_sha256"] is None and
           factory["recovery_evidence_file_sha256"]==
           EXPECTED_RECOVERY_FILE_SHA256 and
           factory["trial_packet"]["source_bytes_sha256"]==
           receipt["source_zip_sha256"] and
           len(factory["recovery_core_receipts"])==10 and
           {x["receipt_sha256"] for x in factory["recovery_core_receipts"]}==
           {x["receipt"]["receipt_sha256"] for x in original.values()} and
           factory["scanner_receipt_sha256"]==scanner["sha256"],
           "RECOVERY_FACTORY_SOURCE_RECEIPT_GRAPH_DRIFT")
    original_bars={x["bar_open_ms"]:x for x in original[month]["local_bars"]}
    from decimal import Decimal
    trial=factory["trial_packet"]["bars"]
    demand(type(trial) is list and len(trial)>=2,
           "RECOVERY_FOCUS_BARS_REQUIRED")
    last=None
    for b in trial:
        start=b.get("open_ms")
        demand(type(start) is int and start in original_bars
               and (last is None or start==last+900000)
               and b.get("close_ms")==original_bars[start]["bar_close_ms"]
               and all(Decimal(str(b[k]))==Decimal(str(original_bars[start][k]))
                       for k in ("open","high","low","close","volume")),
               "RECOVERY_FACTORY_FOCUS_OHLCV_OR_TIME_DRIFT")
        last=start
    # No mutable store before the genuine source, frozen strategy and
    # owner-authorized policy pass validation.
    migrated=migrate_store_v2(store)
    demand(migrated["status"]=="UPGRADED_V2",
           "RECOVERY_FRESH_SQLITE_V2_REQUIRED")
    first=run_recovery_research_v2(factory,store)
    second=run_recovery_research_v2(factory,store)
    demand(first["store_status"]=="STORED_IMMUTABLE"
           and second["store_status"]=="REPLAY_IDENTICAL"
           and all(first[k]==second[k] for k in
                   ("lab_sha256","experiment_sha256","result_sha256"))
           and all(factory_digest({k:v for k,v in row.items()
                                  if k!="receipt_sha256"})==
                   row["receipt_sha256"] for row in (first,second))
           and first["receipt_sha256"]!=second["receipt_sha256"]
           and first["attempt_count"]==second["attempt_count"]==24
           and first["diagnostic_evaluated"]==second["diagnostic_evaluated"]==20
           and first["feb_aug_inventory_unknown"]==
               second["feb_aug_inventory_unknown"]==4
           and first["original_f2_report_sha256"] is None
           and second["original_f2_report_sha256"] is None
           and first["trading_authority"]==second["trading_authority"]=="NONE",
           "RECOVERY_FACTORY_REPLAY_OR_AUTHORITY_FAILED")
    packet={
        "schema":"aql.research-e2e.diagnostic.v1",
        "status":"RESEARCH_E2E_DIAGNOSTIC_PASS",
        "source_class":"F2_RECOVERY_EVIDENCE.v1_OWNER_LOCAL_NOT_INDEPENDENT",
        "recovery_file_sha256":EXPECTED_RECOVERY_FILE_SHA256,
        "original_f2_report_sha256":None,
        "admitted_months":10,"original_bars":29376,
        "attempts":24,"scanner_evaluated":20,"feb_aug_unknown":4,
        "scanner_sha256":scanner["sha256"],
        "factory_input_sha256":factory["sha256"],
        "factory_receipt_sha256":first["receipt_sha256"],
        "factory_lab_sha256":first["lab_sha256"],
        "factory_result_sha256":first["result_sha256"],
        "factory_experiment_sha256":first["experiment_sha256"],
        "focus_month":month,"focus_original_bars":len(trial),
        "source_receipts":{m:x["receipt"]["receipt_sha256"]
                           for m,x in original.items()},
        "work235_commit":frozen["work235_commit"],
        "strategy_ids":scanner_data["frozen_strategy_ids"],
        "costs":first["costs"],
        "immutable_replay":"REPLAY_IDENTICAL",
        "historical_pit":"NOT_ATTESTED",
        "independent_source_rights":"NOT_ATTESTED",
        "source_ack_sha256":None,"strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "selected":False,"paper":"NOT_ACTIVATED",
        "trading_authority":"NONE","f5":"BLOCKED_EXTERNAL_INPUT",
    }
    result={**packet,"sha256":digest(packet)}
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--operator-manifest",required=True)
    parser.add_argument("--owner-private-authorized",action="store_true")
    a=parser.parse_args()
    try:
        demand(a.owner_private_authorized,"RECOVERY_OWNER_AUTHORIZATION_REQUIRED")
        packet=run(read_json(a.operator_manifest))
        print(json.dumps({"status":packet["status"],"sha256":packet["sha256"],
                          "f5":packet["f5"]},sort_keys=True))
    except Exception as exc:
        message=str(exc)
        if not message.startswith("AQL_DIAG_"):
            message="AQL_DIAG_PRIVATE_INPUT_OR_RECOVERY_CONTRACT_FAILED"
        print("PRIVATE_WAIT "+message,file=sys.stderr)
        raise SystemExit(2)


if __name__=="__main__":
    main()
