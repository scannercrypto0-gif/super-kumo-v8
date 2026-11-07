"""One private, read-only F2->Scanner->Factory research diagnostic.

NOT the signed F5 lane. No Source/Strategy/Consumer ACK, SELECTED, PIT,
Paper, trading, or external provenance is generated here.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

SCHEMA = "aql.integration.f.research-e2e-diagnostic-operator.v1"
RECEIPT = "aql.research-e2e.diagnostic.v1"
MONTHS = ("2024-01","2024-03","2024-04","2024-05","2024-06",
          "2024-07","2024-09","2024-10","2024-11","2024-12")
# Git blob identities pinned from the exact owner branches (NOT test trust roots).
MODULE_BLOBS = {
    "research_wp_r0/aql_core_f_research_diagnostic_query_v1.py":
        "ee129da558867d195258fc6507fba93be2fd6066",
    "tools/scanner_strategy_f/research_e2e_diagnostic.py":
        "1878666e92b641c49a93330fc21afd084668e1e8",
    "research_wp_r0/aql_factory_f_research_e2e_diagnostic_v1.py":
        "65b74ef25bc9fc223e490fdc81d0c2fe93767c1d",
}
FIELDS = frozenset((
    "schema","owner_operator_authorized","warehouse_root","vault_root",
    "core_f2_report_path","scanner_policy_draft_path","scanner_proposal_path",
    "scanner_approval_request_path","frozen_work_specs_path",
    "factory_diagnostic_input_path","diagnostic_store_path",
    "sanitized_output_path"
))


def demand(condition, code):
    if not condition:
        raise ValueError("AQL_DIAG_" + code)


def read_json(path):
    path = Path(path)
    demand(path.is_file() and not path.is_symlink()
           and 0 < path.stat().st_size <= 50_000_000, "INPUT_FILE_REQUIRED")
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",",":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def require_scope(m):
    demand(type(m) is dict and set(m) == FIELDS and m["schema"] == SCHEMA
           and m["owner_operator_authorized"] is True,
           "PRIVATE_OWNER_AUTHORIZATION_AND_MANIFEST_REQUIRED")
    vault = Path(m["vault_root"]).resolve(strict=True)
    warehouse = Path(m["warehouse_root"]).resolve(strict=True)
    demand(vault != warehouse and vault.is_dir() and warehouse.is_dir(),
           "DISTINCT_EXISTING_ORIGINAL_ROOTS")
    store = Path(m["diagnostic_store_path"]).absolute()
    out = Path(m["sanitized_output_path"]).absolute()
    demand(store != out and not store.is_symlink() and not out.is_symlink()
           and store.parent.is_dir() and out.parent.is_dir(),
           "DISPOSABLE_OUTPUT_PATHS_REQUIRED")
    for dest in (store, out):
        d = dest.resolve(strict=False)
        demand(vault not in d.parents and warehouse not in d.parents
               and d != vault and d != warehouse,
               "NO_WRITES_UNDER_ORIGINAL_SOURCE")
    # One new bounded experiment; no previous database is quietly reused.
    demand(not store.exists() and not out.exists(), "FRESH_RUN_OUTPUT_REQUIRED")
    return vault, warehouse, store, out


def verify_pinned_modules():
    base = Path(__file__).resolve().parents[1]
    verified = {}
    for rel, expected in MODULE_BLOBS.items():
        p = base / rel
        demand(p.is_file() and not p.is_symlink(), "ASSEMBLED_OWNER_MODULE_MISSING")
        actual = subprocess.check_output(
            ["git","-C",str(base),"hash-object",str(p)], text=True
        ).strip()
        demand(actual == expected, "ASSEMBLED_OWNER_MODULE_BLOB_MISMATCH")
        verified[rel] = {"git_blob":actual,
                         "working_bytes_sha256":sha256(p.read_bytes()).hexdigest()}
    return verified


def compare_trial_with_original(factory, original_month, scanner):
    from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
        validate_diagnostic_input,
    )
    validate_diagnostic_input(factory)
    trial = factory["trial_packet"]
    month = trial["diagnostic_month"]
    demand(month in MONTHS, "FACTORY_MONTH_NOT_ADMITTED")
    receipt = original_month[month]["receipt"]
    demand(factory["core_f2_report_sha256"] ==
           "daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40"
           and factory["source_manifest_sha256"] ==
           receipt["manifest_integrity_sha256"]
           and factory["core_245_query_sha256"] ==
           receipt["core245_native_query_sha256"]
           and factory["core_253_query_sha256"] ==
           receipt["core253_local_query_sha256"]
           and factory["operator_local_source_readback_sha256"] ==
           receipt["source_zip_sha256"],
           "FACTORY_VS_CORE_ORIGINAL_MONTH_SHA_DRIFT")
    scan = scanner["payload"]
    demand(scan["total_attempts"] == 24 and
           scan["diagnostic_evaluated_attempts"] == 20 and
           scan["unknown_feb_aug_attempts"] == 4 and
           scan["native15m_month_bars"] == 29376 and
           scan["selected"] == 0 and
           scan["trading_authority"] == "NONE" and
           scan["source_query_shas"][month] ==
           receipt["core253_local_query_sha256"],
           "SCANNER_CENSUS_OR_MONTH_SOURCE_DRIFT")
    true_ids = {(x["payload"]["month"], x["payload"]["strategy_id"])
                for x in scan["attempts"]}
    factory_ids = {(x["month"],x["candidate_id"]) for x in factory["attempts"]}
    demand(true_ids == factory_ids, "FACTORY_SCANNER_STRATEGY_MONTH_ID_DRIFT")
    focus = trial["selected_attempt_id"]  # computational focus, never selection
    frow = next((x for x in factory["attempts"] if x["attempt_id"] == focus), None)
    demand(frow is not None and frow["month"] == month and
           frow["state"] == "UNKNOWN",
           "FOCUS_MUST_BE_UNSELECTED_ORIGINAL_MONTH")
    srow = next((x["payload"] for x in scan["attempts"]
                 if x["payload"]["month"] == month and
                 x["payload"]["strategy_id"] == frow["candidate_id"]), None)
    demand(srow is not None and srow["definition_digest"] ==
           factory["strategy_definition_sha256"],
           "FROZEN_STRATEGY_DEFINITION_MISMATCH")
    by_open = {b["bar_open_ms"]:b for b in original_month[month]["local_bars"]}
    bars = trial["bars"]
    demand(type(bars) is list and 2 <= len(bars) <= len(by_open),
           "ORIGINAL_TRIAL_BAR_POPULATION")
    last = None
    for b in bars:
        start = b.get("open_ms")
        demand(type(start) is int and start in by_open and
               b.get("close_ms") == by_open[start]["bar_close_ms"] and
               (last is None or start == last + 900000) and
               b.get("known_at_ms") is None,
               "TRIAL_MUST_BE_CONTIGUOUS_ORIGINAL_CLOSED_BARS")
        reference = by_open[start]
        try:
            equal = all(Decimal(str(b[key])) == Decimal(str(reference[key]))
                        for key in ("open","high","low","close","volume"))
        except (KeyError, InvalidOperation, TypeError):
            equal = False
        demand(equal, "TRIAL_OHLCV_DIFFERS_FROM_CORE_READBACK")
        last = start
    return month, focus, len(bars)


def check_fail_closed_negatives(factory):
    from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
        validate_diagnostic_input,
    )
    # No adversarial mutation touches the original owner store, just memory.
    import copy
    attacks = []
    def reject(mutated, name):
        try:
            validate_diagnostic_input(mutated)
        except (ValueError, TypeError, KeyError):
            attacks.append(name)
            return
        raise ValueError("AQL_DIAG_NEGATIVE_NOT_REJECTED_" + name)
    tampered = copy.deepcopy(factory)
    tampered["source_manifest_sha256"] = "0" * 64
    reject(tampered, "UNSEALED_SOURCE_MUTATION")
    promoted = copy.deepcopy(factory)
    promoted["strategy_approval_sha256"] = "f" * 64
    promoted["sha256"] = digest({k:v for k,v in promoted.items() if k!="sha256"})
    reject(promoted, "RESEALED_AUTHORITY_PROMOTION")
    future = copy.deepcopy(factory)
    future["trial_packet"]["bars"][-1]["close_ms"] += 900000
    future["sha256"] = digest({k:v for k,v in future.items() if k!="sha256"})
    reject(future, "RESEALED_UNCLOSED_BAR")
    return attacks


def run(m):
    vault, warehouse, store, out = require_scope(m)
    modules = verify_pinned_modules()
    from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
        read_original_diagnostic,
    )
    from research_wp_r0.aql_core_backbone_local_v1 import query_local
    from tools.scanner_strategy_f.research_e2e_diagnostic import (
        diagnostic_original_cohort,
    )
    from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
        run_diagnostic,
    )
    original_report = read_json(m["core_f2_report_path"])
    original = {}
    queries = {}
    for month in MONTHS:
        readback = read_original_diagnostic(
            warehouse,vault,original_report,month=month)
        receipt = readback["receipt"]
        query = query_local(
            warehouse,receipt["dataset_id"],receipt["version"],
            receipt["start_ms"],receipt["end_exclusive_ms"],
            receipt["decision_cutoff_ms"],
            required_source_sha256=receipt["source_zip_sha256"],
            require_complete=True)
        demand(query["query_sha256"] == receipt["core253_local_query_sha256"]
               and query["bars"] == readback["local_bars"],
               "ORIGINAL_CORE253_SECOND_READBACK_DRIFT")
        original[month] = readback
        queries[month] = query
    scanner = diagnostic_original_cohort(
        warehouse_root=warehouse,month_queries=queries,
        policy_draft=read_json(m["scanner_policy_draft_path"]),
        proposal=read_json(m["scanner_proposal_path"]),
        approval_request=read_json(m["scanner_approval_request_path"]),
        work_specs=read_json(m["frozen_work_specs_path"]))
    factory = read_json(m["factory_diagnostic_input_path"])
    month,focus,focus_bars = compare_trial_with_original(factory, original, scanner)
    negative_cases = check_fail_closed_negatives(factory)
    first = run_diagnostic(factory, store)
    second = run_diagnostic(factory, store)
    demand(first["store_status"] == "STORED_IMMUTABLE"
           and second["store_status"] == "REPLAY_IDENTICAL"
           and all(first[key] == second[key] for key in
                   ("experiment_sha256","lab_sha256","result_sha256",
                    "input_sha256","receipt_sha256"))
           and first["attempt_count"] == 24
           and first["feb_aug_inventory_unknown"] == 4
           and first["historical_pit"] == "NOT_ATTESTED"
           and first["trading_authority"] == "NONE"
           and all(first[x] is None for x in
                   ("source_ack_sha256","strategy_approval_sha256",
                    "factory_consumer_ack_sha256")),
           "IMMUTABLE_REPLAY_OR_AUTHORITY_BOUNDARY_FAILED")
    packet = {
        "schema":RECEIPT,"kind":"RESEARCH_E2E_DIAGNOSTIC",
        "disposition":"RESEARCH_E2E_DIAGNOSTIC_PASS",
        "trust_class":"OWNER_LOCAL_DECLARED_NOT_INDEPENDENT",
        "owner_operator_authorized":True,
        "retrospective_scope":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED","independent_attestation":"NOT_ATTESTED",
        "operational_authority":"NONE","signed_f5_approval":"NOT_GRANTED",
        "selected":False,"source_ack_sha256":None,
        "strategy_approval_sha256":None,"factory_consumer_ack_sha256":None,
        "trading_authority":"NONE","paper":"NOT_ACTIVATED",
        "holdout":"SEALED_UNOPENED","orders_created":0,
        "actual_fills":None,
        "f2_report_sha256":factory["core_f2_report_sha256"],
        "source_manifest_sha256":factory["source_manifest_sha256"],
        "modules":modules,
        "source_query_months":{month:{
            "source_zip_sha256":original[month]["receipt"]["source_zip_sha256"],
            "native_245_sha256":original[month]["receipt"]["core245_native_query_sha256"],
            "local_253_sha256":original[month]["receipt"]["core253_local_query_sha256"],
            "readback_count":original[month]["receipt"]["readback_bar_count"]}
            for month in MONTHS},
        "admitted_months":10,"original_bar_count":29376,
        "total_strategy_month_attempts":24,
        "scanner_evaluated_attempts":20,"feb_aug_inventory_only_unknown":4,
        "factory_lab_focused_month":month,
        "factory_lab_focused_attempt_id":focus,
        "factory_lab_focused_bar_count":focus_bars,
        "scanner_receipt_sha256":scanner["sha256"],
        "factory_input_sha256":factory["sha256"],
        "factory_experiment_sha256":first["experiment_sha256"],
        "factory_lab_sha256":first["lab_sha256"],
        "factory_result_sha256":first["result_sha256"],
        "factory_receipt_sha256":first["receipt_sha256"],
        "factory_modeled_outcomes":first["modeled_count"],
        "factory_unknown_outcomes":first["unknown_count"],
        "cost_assumptions":first["costs"],
        "result_store_layout_version":first["layout_version"],
        "restart_replay":"REPLAY_IDENTICAL",
        "fail_closed_negatives":negative_cases,
        "f5_acceptance":"NOT_EVALUATED"
    }
    envelope = {**packet,"sha256":digest(packet)}
    out.write_text(json.dumps(envelope,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return envelope


def main():
    parser = argparse.ArgumentParser(description="Local original F2 diagnostic ONLY; no signed F5 authority")
    parser.add_argument("--operator-manifest",required=True)
    parser.add_argument("--owner-private-authorized",action="store_true")
    args = parser.parse_args()
    try:
        demand(args.owner_private_authorized,"EXPLICIT_OWNER_PRIVATE_AUTHORIZATION_REQUIRED")
        value = run(read_json(args.operator_manifest))
        print(json.dumps({"disposition":value["disposition"],"sha256":value["sha256"],
                          "original_bar_count":value["original_bar_count"],
                          "total_attempts":value["total_strategy_month_attempts"],
                          "f5_acceptance":value["f5_acceptance"]},sort_keys=True))
    except Exception as exc:
        # Never emit private paths, hashes of unseen inputs, or OHLCV in errors.
        safe = str(exc)
        if not safe.startswith("AQL_DIAG_"):
            safe = "AQL_DIAG_PRIVATE_INPUT_OR_ENGINEERING_GATE_FAILED"
        print("PRIVATE_WAIT "+safe,file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
