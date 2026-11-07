"""Build Factory's genuine owner-private recovery focus only from source receipts.

Never invent a market source SHA, 53 trial ledger, fee schedule or sealed
holdout window. Scanner identity and frozen Work235 ASTs are verified inputs.
No original F2, F5, Paper or execution authority can be produced here.
"""
from __future__ import annotations
from hashlib import sha256
import platform
from pathlib import Path

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_factory_authentic_research_admission import seal
from research_wp_r0.aql_factory_f_f2_recovery_diagnostic_v1 import (
    validate_recovery_input, SCHEMA, MONTHS, RECOVERY_SHA,
)
from research_wp_r0.aql_factory_historical_rule_projection import COST_KEYS
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest as factory_digest,
)
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_f.frozen_diagnostic_contracts import (
    identify_frozen_work235_contracts,
)

POLICY_SCHEMA = "aql.integration.owner-local-factory-diagnostic-policy.v1"
LEDGER_SCHEMA = "aql.integration.owner-local-factory-53-trial-ledger.v1"
INVENTORY_SCHEMA = "aql.integration.owner-local-inventory-receipts.v1"


def need(ok, code):
    if not ok:
        raise ValueError("F2_OWNER_FACTORY_" + code)


def hexsha(x):
    return type(x) is str and len(x) == 64 and all(ch in
        "0123456789abcdef" for ch in x)


def policy_missing(policy, ledger, inventory):
    """Report missing root fields only; never include private data or paths."""
    missing=[]
    if type(policy) is not dict or policy.get("schema") != POLICY_SCHEMA:
        missing.append("policy.schema")
    for key in ("costs", "research_window", "direction", "focus_month",
                "focus_strategy_id"):
        if type(policy) is not dict or key not in policy:
            missing.append("policy."+key)
    if type(ledger) is not dict or ledger.get("schema") != LEDGER_SCHEMA:
        missing.append("trial_ledger.schema")
    for key in ("trials", "selected_attempt_id", "plan_digest"):
        if type(ledger) is not dict or key not in ledger:
            missing.append("trial_ledger."+key)
    if type(inventory) is not dict or inventory.get("schema") != INVENTORY_SCHEMA:
        missing.append("inventory.schema")
    for month in ("2024-02", "2024-08"):
        if type(inventory) is not dict or month not in inventory:
            missing.append("inventory."+month+".source_receipt_sha256")
    return sorted(set(missing))


def _bar_from_original(bar):
    body={
        "open_ms":bar["bar_open_ms"], "close_ms":bar["bar_close_ms"],
        "open":bar["open"], "high":bar["high"], "low":bar["low"],
        "close":bar["close"], "volume":bar["volume"],
        "known_at_ms":None,"quality":"FINAL",
    }
    sealed=seal(body)
    return {**body,"bar_sha256":sealed["artifact_sha256"]}


def build_factory_packet(*, original, scanner_receipt, work_specs,
                         policy, ledger, inventory):
    """No source replacement. Inputs are actually Core/Scanner read back."""
    missing=policy_missing(policy,ledger,inventory)
    need(not missing,"MISSING_EXPLICIT_POLICY_LEDGER_OR_INVENTORY")
    need(type(original) is dict and set(original)==set(MONTHS),
         "ORIGINAL_COHORT")
    ident=identify_frozen_work235_contracts(work_specs)
    specs={Frozen.restore(spec).data["strategy_id"]:Frozen.restore(spec).data
           for spec in work_specs}
    scanner=scanner_receipt["payload"]
    need(scanner["schema"] ==
         "aql.scanner-f.recovery-source-research-e2e-diagnostic.v1"
         and scanner["attempts"]==24 and scanner["diagnostic_evaluated"]==20
         and scanner["feb_aug_unknown"]==4
         and scanner["selected"]==0
         and scanner["trading_authority"]=="NONE"
         and sorted(scanner["frozen_strategy_ids"])==sorted(specs),
         "SCANNER_RESEARCH_SCOPE")
    need(type(policy) is dict and set(policy)=={
             "schema","costs","research_window","direction","focus_month",
             "focus_strategy_id"} and
         policy["schema"]==POLICY_SCHEMA and
         policy["direction"]=="LONG" and
         policy["focus_month"] in MONTHS and
         policy["focus_strategy_id"] in specs and
         type(policy["costs"]) is dict and
         set(policy["costs"])==set(COST_KEYS) and
         all(type(v) is str for v in policy["costs"].values()) and
         type(policy["research_window"]) is dict and
         set(policy["research_window"]) == {
             "train_end_exclusive_ms","embargo_ms",
             "holdout_start_ms","holdout_end_exclusive_ms"} and
         all(type(v) is int for v in policy["research_window"].values()),
         "EXPLICIT_COST_OR_WINDOW_POLICY")
    need(type(inventory) is dict and set(inventory)=={
             "schema","2024-02","2024-08"} and
         inventory["schema"]==INVENTORY_SCHEMA and
         all(hexsha(inventory[m]) for m in ("2024-02","2024-08")),
         "TRUE_INVENTORY_SHA_REQUIRED")
    month=policy["focus_month"]
    strategy=specs[policy["focus_strategy_id"]]
    definition=StrategyDefinition.from_dict(
        strategy["definition"],registry=IndicatorRegistryV2())
    need(definition.digest==ident["strategy_identities"][
         policy["focus_strategy_id"]]["definition_digest"],
         "FROZEN_WORK235_STRATEGY_DIGEST")
    need(type(ledger) is dict and set(ledger)=={
             "schema","trials","selected_attempt_id","plan_digest"} and
         ledger["schema"]==LEDGER_SCHEMA and
         type(ledger["trials"]) is list and
         len(ledger["trials"])==53 and
         hexsha(ledger["plan_digest"]) and
         type(ledger["selected_attempt_id"]) is str,
         "ORIGINAL_FROZEN_TRIAL_LEDGER_REQUIRED")
    selected=[x for x in ledger["trials"] if type(x) is dict and
              x.get("attempt_id")==ledger["selected_attempt_id"]]
    need(len(selected)==1 and
         selected[0].get("state")=="PROPOSED" and
         selected[0].get("candidate_digest")==definition.digest and
         all(type(x) is dict and
             x.get("plan_digest")==ledger["plan_digest"]
             for x in ledger["trials"]),
         "TRIAL_LEDGER_NOT_FOCUS_DEFINITION")
    focus_attempt = "RECOVERY-" + month + "-" + policy["focus_strategy_id"]
    need(ledger["selected_attempt_id"]==focus_attempt,
         "TRIAL_LEDGER_FOCUS_ATTEMPT_MISMATCH")

    receipts=[original[m]["receipt"] for m in MONTHS]
    need(all(v["opaque_recovery_file_pin_verified"] is True and
             v["original_f2_report_sha256"] is None and
             v["trading_authority"]=="NONE" for v in receipts),
         "LIVE_CORE_RECEIPTS_ONLY")
    sources={m:original[m]["receipt"]["source_zip_sha256"] for m in MONTHS}
    attempts=[]
    for m in list(MONTHS)+["2024-02","2024-08"]:
        for ident_name in sorted(specs):
            attempt_id="RECOVERY-"+m+"-"+ident_name
            attempts.append({
                "attempt_id":attempt_id,
                "candidate_id":ident_name,
                "month":m,
                # UNKNOWN means NOT selected/approved in the Factory diagnostic.
                # Scanner evaluates its own 20 original-source attempts.
                "state":"UNKNOWN",
                "source_receipt_sha256":sources[m] if m in sources else
                    inventory[m],
            })
    need(len(attempts)==24 and
         ledger["selected_attempt_id"] in {x["attempt_id"] for x in attempts},
         "FACTORY_24_ATTEMPTS")
    real=original[month]["local_bars"]
    need(type(real) is list and len(real)>2,"REAL_MONTH_BARS")
    trial={
        "schema":"aql.factory.historical-rule-projection.v1",
        "source_kind":"ORIGINAL_UNVERIFIED",
        "availability":"RETROSPECTIVE_NON_PIT",
        "holdout":"SEALED_UNOPENED","execution_authority":"NONE",
        "market":"SPOT","width_ms":900000,
        "dataset_id":original[month]["receipt"]["dataset_id"],
        "dataset_version":1,
        "source_bytes_sha256":sources[month],
        "source_manifest_sha256":factory_digest([
            [m, original[m]["receipt"]["manifest_integrity_sha256"]]
            for m in MONTHS]),
        "plan_digest":ledger["plan_digest"],
        "trial_budget":53,
        "trials":ledger["trials"],
        "selected_attempt_id":focus_attempt,
        "universe":{
            "full":2,"eligible":2,"ineligible":0,"unscanned":2,
            "rejected":0,"unknown":0,"nominated":0,
            "source_coverage":"NOT_INDEPENDENTLY_ATTESTED",
        },
        "opportunity_count":0,"opportunities":[],
        "bars":[_bar_from_original(b) for b in real],
        "research_window":policy["research_window"],
        "strategy":strategy["definition"],
        "direction":"LONG","costs":policy["costs"],
        "diagnostic_month":month,
    }
    code_path=Path(__file__).resolve().parents[1]
    files=(
        code_path/"research_wp_r0/aql_factory_historical_rule_projection.py",
        code_path/"research_wp_r0/aql_factory_f_f2_recovery_diagnostic_v1.py",
        code_path/"tools/scanner_strategy_f/research_e2e_diagnostic.py",
    )
    need(all(p.is_file() and not p.is_symlink() for p in files),
         "PINNED_CODE_MODULES_REQUIRED")
    code_sha=sha256(b"\n--pinned-modules--\n".join(
        p.read_bytes() for p in files)).hexdigest()
    body={
        "schema":SCHEMA,
        "experiment_id":"DIAG-F4-RECOVERY-"+month+"-"+policy["focus_strategy_id"],
        "local_source_mode":"OWNER_PRIVATE_READ_ONLY",
        "purpose":"RESEARCH_E2E_DIAGNOSTIC",
        "original_f2_report_sha256":None,
        "recovery_evidence_file_sha256":RECOVERY_SHA,
        "recovery_core_receipts":receipts,
        "source_manifest_sha256":trial["source_manifest_sha256"],
        "core_245_query_sha256":factory_digest([
            [m, original[m]["receipt"]["core245_native_query_sha256"]]
            for m in MONTHS]),
        "core_253_query_sha256":factory_digest([
            [m, original[m]["receipt"]["core253_local_query_sha256"]]
            for m in MONTHS]),
        "operator_local_source_readback_sha256":sources[month],
        "strategy_definition_sha256":definition.digest,
        "config_sha256":factory_digest(policy),
        "code_sha256":code_sha,
        "environment_sha256":factory_digest({
            "python":platform.python_version(),
            "implementation":platform.python_implementation(),
        }),
        "strategy":strategy["definition"],
        "admitted_months":list(MONTHS),
        "attempts":attempts,
        "trial_packet":trial,
        "source_coverage":{
            "new_admitted_months":10,
            "new_admitted_bars":29376,
            "retained_inventory_months":["2024-02","2024-08"],
            "retained_inventory_status":"INVENTORY_ONLY_NOT_READBACK",
            "historical_pit":"NOT_ATTESTED",
            "source_rights_assurance":
                "LOCAL_OPERATOR_DECLARED_NOT_INDEPENDENT",
        },
        "market":"BINANCE:SPOT:USDT",
        "symbol":"BTCUSDT","timeframe":"15m",
    }
    packet={**body,"sha256":factory_digest(body)}
    validate_recovery_input(packet)
    return packet
