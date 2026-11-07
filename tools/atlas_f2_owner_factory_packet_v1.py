"""Build source-backed Factory recovery v2 packet; never fabricate trials or inventory."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import platform

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest
from research_wp_r0.aql_factory_authentic_research_admission import seal
from research_wp_r0.aql_factory_f_f2_recovery_research_v2 import (
    SCHEMA, validate_recovery_research_input,
)
from research_wp_r0.aql_factory_f_f2_recovery_diagnostic_v1 import (
    MONTHS, RECOVERY_SHA, RECOVERY_RAW_BYTES_SHA,
)
from tools.strategy_service_offline.common import Frozen

POLICY_SCHEMA = "aql.factory.f.owner-authorized-recovery-policy.v2"


def policy_missing(policy, ledger=None, inventory=None):
    """No legacy 53-trial ledger or inventory hashes are needed in v2."""
    missing=[]
    if not isinstance(policy,dict) or policy.get("schema")!=POLICY_SCHEMA:
        missing.append("operator_policy.schema")
    for key in ("owner_operator_authorized","costs","research_window",
                "direction","ambiguity_policy","focus_month","focus_strategy_id"):
        if not isinstance(policy,dict) or key not in policy:
            missing.append("operator_policy."+key)
    for key in ("fee_entry_bps","fee_exit_bps","spread_entry_bps",
                "spread_exit_bps","slippage_entry_bps","slippage_exit_bps",
                "funding_bps_per_bar"):
        if not isinstance(policy,dict) or not isinstance(policy.get("costs"),dict) or key not in policy["costs"]:
            missing.append("operator_policy.costs."+key)
    for key in ("train_end_exclusive_ms","embargo_ms","holdout_start_ms",
                "holdout_end_exclusive_ms"):
        if not isinstance(policy,dict) or not isinstance(policy.get("research_window"),dict) or key not in policy["research_window"]:
            missing.append("operator_policy.research_window."+key)
    return sorted(set(missing))


def _bar_from_original(bar):
    body={
        "open_ms":bar["bar_open_ms"],"close_ms":bar["bar_close_ms"],
        "open":bar["open"],"high":bar["high"],"low":bar["low"],
        "close":bar["close"],"volume":bar["volume"],
        "known_at_ms":None,"quality":"FINAL",
    }
    return {**body,"bar_sha256":seal(body)["artifact_sha256"]}


def build_factory_packet(*,original,scanner_receipt,work_specs,policy,
                         ledger=None,inventory=None):
    missing=policy_missing(policy)
    if missing:
        raise ValueError("PRIVATE_WAIT_MISSING_FIELDS:"+",".join(missing))
    if type(original) is not dict or set(original)!=set(MONTHS):
        raise ValueError("F2_OWNER_FACTORY_ORIGINAL_COHORT")
    frozen=[Frozen.restore(spec).data for spec in work_specs]
    definitions={v["strategy_id"]+"@"+v["strategy_version"]:v["definition"]
                 for v in frozen}
    if len(definitions)!=2:
        raise ValueError("F2_OWNER_FACTORY_EXACT_FROZEN_PAIR")
    scan=scanner_receipt["payload"]
    if not (scan["attempts"]==24 and scan["diagnostic_evaluated"]==20
            and scan["feb_aug_unknown"]==4 and scan["selected"]==0
            and scan["trading_authority"]=="NONE"
            and set(scan["frozen_strategy_ids"])==set(definitions)):
        raise ValueError("F2_OWNER_FACTORY_SCANNER_SCOPE")
    receipts=[original[m]["receipt"] for m in MONTHS]
    if not all(x["opaque_recovery_file_pin_verified"] is True
               and x["original_f2_report_sha256"] is None
               and x["trading_authority"]=="NONE" for x in receipts):
        raise ValueError("F2_OWNER_FACTORY_SOURCE_RECEIPT")
    bymonth={r["month"]:r for r in receipts}
    month=policy["focus_month"]
    identity=policy["focus_strategy_id"]
    if month not in original or identity not in definitions:
        raise ValueError("F2_OWNER_FACTORY_FOCUS")
    def graph(field):
        return digest([[m,bymonth[m][field]] for m in MONTHS])
    attempts=[]
    for m in list(MONTHS)+["2024-02","2024-08"]:
        for name in sorted(definitions):
            real=m in bymonth
            attempts.append({
                "attempt_id":"F2RV2-"+m+"-"+name,
                "candidate_id":name,"month":m,
                "state":"DIAGNOSTIC_EVALUATED_NOT_SELECTED" if real else "UNKNOWN",
                "source_receipt_sha256":bymonth[m]["source_zip_sha256"] if real else None,
            })
    bars=original[month]["local_bars"]
    if type(bars) is not list or len(bars)<2:
        raise ValueError("F2_OWNER_FACTORY_FOCUS_BARS")
    modules=(
        "research_wp_r0/aql_factory_f_f2_recovery_research_v2.py",
        "research_wp_r0/aql_factory_historical_rule_projection.py",
        "tools/scanner_strategy_f/research_e2e_diagnostic.py",
    )
    root=Path(__file__).resolve().parents[1]
    if not all((root/p).is_file() and not (root/p).is_symlink() for p in modules):
        raise ValueError("F2_OWNER_FACTORY_PINNED_MODULES")
    code_sha=sha256(b"\n--pinned-modules--\n".join(
        (root/p).read_bytes() for p in modules)).hexdigest()
    focus={
        "schema":"aql.factory.f.recovery-focus.v2",
        "diagnostic_month":month,"strategy_id":identity,
        "strategy":definitions[identity],
        "source_bytes_sha256":bymonth[month]["source_zip_sha256"],
        "source_manifest_sha256":bymonth[month]["manifest_integrity_sha256"],
        "dataset_id":bymonth[month]["dataset_id"],
        "dataset_version":1,"availability":"RETROSPECTIVE_NON_PIT",
        "market":"SPOT","width_ms":900000,
        "bars":[_bar_from_original(x) for x in bars],
    }
    body={
        "schema":SCHEMA,
        "experiment_id":"DIAG-F4-RECOVERY-V2-"+month+"-"+identity,
        "purpose":"RECOVERY_RESEARCH_ONLY_NOT_F5",
        "local_source_mode":"OWNER_PRIVATE_READ_ONLY",
        "recovery_evidence_file_sha256":RECOVERY_SHA,
        "recovery_raw_bytes_sha256":RECOVERY_RAW_BYTES_SHA,
        "original_f2_report_sha256":None,
        "recovery_core_receipts":receipts,
        "scanner_receipt_sha256":scanner_receipt["sha256"],
        "strategy_definitions":definitions,
        "attempts":attempts,
        "source_manifest_sha256":graph("manifest_integrity_sha256"),
        "core_245_query_sha256":graph("core245_native_query_sha256"),
        "core_253_query_sha256":graph("core253_local_query_sha256"),
        "warehouse_graph_sha256":graph("warehouse_receipt_sha256"),
        "dual_map_graph_sha256":graph("dual_map_sha256"),
        "config_sha256":digest(policy),"code_sha256":code_sha,
        "environment_sha256":digest({
            "python":platform.python_version(),
            "implementation":platform.python_implementation(),
        }),
        "trial_packet":focus,"operator_policy":policy,
        "source_coverage":{
            "new_admitted_months":10,"new_admitted_bars":29376,
            "retained_inventory_months":["2024-02","2024-08"],
            "retained_inventory_status":"INVENTORY_ONLY_NOT_READBACK",
            "historical_pit":"NOT_ATTESTED",
            "source_rights_assurance":"LOCAL_OPERATOR_DECLARED_NOT_INDEPENDENT",
        },
        "historical_pit":"NOT_ATTESTED","holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE",
    }
    packet={**body,"sha256":digest(body)}
    validate_recovery_research_input(packet)
    return packet
