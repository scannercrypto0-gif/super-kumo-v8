"""ATLAS Factory F: independently versioned 24-attempt F2 Recovery research lane.

Only Core read-only recovery receipts, frozen Work235 strategy definitions and
an owner-authorized explicit cost/window policy may enter this lane. It never
adapts to the old 53-trial projection, does not manufacture inventory receipts,
and cannot create F5 approvals or trading authority. Fixtures are structural
only: a SHA-verified object supplied by a caller is not independently sourced.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    digest, _sha, ResultsStoreError, build_experiment, register_experiment,
    read_experiment, audit_store_layout,
)
from research_wp_r0.aql_factory_f_f2_recovery_diagnostic_v1 import (
    MONTHS, RECOVERY_SHA, RECOVERY_RAW_BYTES_SHA, verified_core_receipts,
)
from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
    _month_boundaries, need,
)
from research_wp_r0.aql_factory_historical_rule_projection import (
    _validate_bars, _vectors, _expression, _modeled_trade, _costs, COST_KEYS,
)
from research_wp_r0.aql_factory_authentic_research_admission import seal
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

SCHEMA = "aql.factory.f.f2-recovery-research-input.v2"
REPORT = "aql.factory.f.f2-recovery-research-report.v2"
ATTEMPT_STATES = {"DIAGNOSTIC_EVALUATED_NOT_SELECTED", "UNKNOWN"}
SCOPE = "RECOVERY_RESEARCH_ONLY_NOT_F5"
INVENTORY = ("2024-02", "2024-08")
ALL_MONTHS = set(MONTHS) | set(INVENTORY)
STRATEGY_IDS = ("test_momentum@v1", "test_reversion@v1")
ROOT_FIELDS = {
    "schema", "sha256", "experiment_id", "purpose", "local_source_mode",
    "recovery_evidence_file_sha256", "recovery_raw_bytes_sha256",
    "original_f2_report_sha256", "recovery_core_receipts",
    "scanner_receipt_sha256", "strategy_definitions", "attempts",
    "source_manifest_sha256", "core_245_query_sha256",
    "core_253_query_sha256", "warehouse_graph_sha256",
    "dual_map_graph_sha256", "config_sha256", "code_sha256",
    "environment_sha256", "trial_packet", "operator_policy",
    "source_coverage", "historical_pit", "holdout", "trading_authority",
}
FOCUS_FIELDS = {"schema", "diagnostic_month", "strategy_id", "strategy",
                "source_bytes_sha256", "source_manifest_sha256",
                "dataset_id", "dataset_version", "availability", "market",
                "width_ms", "bars"}
POLICY_FIELDS = {"schema", "owner_operator_authorized", "costs",
                 "research_window", "direction", "ambiguity_policy"}
WINDOW_FIELDS = {"train_end_exclusive_ms", "embargo_ms",
                 "holdout_start_ms", "holdout_end_exclusive_ms"}
COVERAGE_FIELDS = {"new_admitted_months", "new_admitted_bars",
                   "retained_inventory_months", "retained_inventory_status",
                   "historical_pit", "source_rights_assurance"}


def _missing_policy(policy):
    """Field-only waiting reason; no owner paths, pricing or private bars."""
    missing = []
    if type(policy) is not dict:
        return ["operator_policy"]
    for key in sorted(POLICY_FIELDS):
        if key not in policy:
            missing.append("operator_policy." + key)
    if type(policy.get("costs")) is not dict:
        missing.append("operator_policy.costs")
    else:
        for key in COST_KEYS:
            if key not in policy["costs"]:
                missing.append("operator_policy.costs." + key)
    if type(policy.get("research_window")) is not dict:
        missing.append("operator_policy.research_window")
    else:
        for key in sorted(WINDOW_FIELDS):
            if key not in policy["research_window"]:
                missing.append("operator_policy.research_window." + key)
    return sorted(set(missing))


def _policy(policy):
    missing = _missing_policy(policy)
    if missing:
        raise ResultsStoreError("PRIVATE_WAIT_MISSING_FIELDS:" +
                                ",".join(missing))
    need(type(policy) is dict and set(policy) == POLICY_FIELDS and
         policy["schema"] ==
         "aql.factory.f.owner-authorized-recovery-policy.v2" and
         policy["owner_operator_authorized"] is True and
         policy["ambiguity_policy"] == "UNKNOWN_ON_INTRABAR_TOUCH" and
         policy["direction"] == "LONG" and
         type(policy["costs"]) is dict and
         set(policy["costs"]) == set(COST_KEYS) and
         all(type(v) is str for v in policy["costs"].values()),
         "V2_POLICY_SCOPE")
    window = policy["research_window"]
    need(type(window) is dict and set(window) == WINDOW_FIELDS and
         all(type(x) is int and x >= 0 for x in window.values())
         and window["embargo_ms"] >= 259_200_000
         and window["train_end_exclusive_ms"] + window["embargo_ms"]
         <= window["holdout_start_ms"] < window["holdout_end_exclusive_ms"],
         "V2_POLICY_WINDOW")
    # Reuse the existing bounded Decimal fee/spread/slippage validation.
    costs = _costs({"costs":policy["costs"],"market":"SPOT"})
    need(costs["funding_bps_per_bar"] == Decimal(0),
         "V2_SPOT_FUNDING")
    return costs


def _definitions(raw):
    need(type(raw) is dict and set(raw) == set(STRATEGY_IDS),
         "V2_EXACT_TWO_FROZEN_STRATEGIES")
    definitions = {}
    for identity in STRATEGY_IDS:
        # Value is the original frozen Work235 StrategyDefinition envelope,
        # never a rewritten AST or a synthesized candidate identifier.
        definition = StrategyDefinition.from_dict(
            raw[identity], registry=IndicatorRegistryV2())
        spec = definition.spec
        need(identity == spec["strategy_id"] + "@" + spec["strategy_version"]
             and spec["scope"] == "RESEARCH_ONLY"
             and spec["timing"] == {
                 "decision":"CONFIRMED_CLOSE",
                 "entry_execution":"NEXT_ELIGIBLE_OPEN",
                 "ambiguity":"REJECT",
             }, "V2_FROZEN_STRATEGY_IDENTITY")
        definitions[identity] = definition
    return definitions


def validate_recovery_research_input(packet):
    """Strict 10-Core-month + 20 evaluated + four NULL inventory proofs."""
    need(type(packet) is dict and set(packet) == ROOT_FIELDS
         and packet.get("schema") == SCHEMA
         and _sha(packet.get("sha256")) and
         digest({k:v for k,v in packet.items() if k != "sha256"})
         == packet["sha256"], "V2_INPUT_SEAL_OR_FIELDS")
    need(type(packet["experiment_id"]) is str and
         packet["experiment_id"].startswith("DIAG-F4-RECOVERY-V2-")
         and len(packet["experiment_id"]) <= 160 and
         packet["purpose"] == SCOPE and
         packet["local_source_mode"] == "OWNER_PRIVATE_READ_ONLY" and
         packet["recovery_evidence_file_sha256"] == RECOVERY_SHA and
         packet["recovery_raw_bytes_sha256"] == RECOVERY_RAW_BYTES_SHA and
         packet["original_f2_report_sha256"] is None and
         packet["historical_pit"] == "NOT_ATTESTED" and
         packet["holdout"] == "SEALED_UNOPENED" and
         packet["trading_authority"] == "NONE",
         "V2_NO_F2_F5_OR_EXECUTION_AUTHORITY")
    for name in ("scanner_receipt_sha256","source_manifest_sha256",
                 "core_245_query_sha256","core_253_query_sha256",
                 "warehouse_graph_sha256","dual_map_graph_sha256",
                 "config_sha256","code_sha256","environment_sha256"):
        need(_sha(packet[name]), "V2_PARENT_" + name.upper())
    need(packet["core_245_query_sha256"] != packet["core_253_query_sha256"],
         "V2_DUAL_QUERY_ALIAS")
    definitions = _definitions(packet["strategy_definitions"])
    parents = verified_core_receipts({
        "schema":"F2_RECOVERY_EVIDENCE.v1",
        "original_f2_report_sha256":None,
        "recovery_evidence_file_sha256":RECOVERY_SHA,
        "source_rights":"OWNER_LOCAL_NOT_INDEPENDENT",
        "readback_receipts":packet["recovery_core_receipts"],
    })
    digests = {
        "source_manifest_sha256":"manifest_sha256",
        "core_245_query_sha256":"native_sha256",
        "core_253_query_sha256":"local_sha256",
        "warehouse_graph_sha256":"warehouse_receipt_sha256",
        "dual_map_graph_sha256":"dual_map_sha256",
    }
    for target, source in digests.items():
        expected = digest([[m,parents[m][source]] for m in MONTHS])
        need(packet[target] == expected, "V2_CORE_PARENT_GRAPH_" + target)
    coverage = packet["source_coverage"]
    need(type(coverage) is dict and set(coverage) == COVERAGE_FIELDS
         and coverage["new_admitted_months"] == 10
         and coverage["new_admitted_bars"] == 29376
         and coverage["retained_inventory_months"] == list(INVENTORY)
         and coverage["retained_inventory_status"] ==
         "INVENTORY_ONLY_NOT_READBACK"
         and coverage["historical_pit"] == "NOT_ATTESTED"
         and coverage["source_rights_assurance"] ==
         "LOCAL_OPERATOR_DECLARED_NOT_INDEPENDENT",
         "V2_SOURCE_CENSUS")
    attempts = packet["attempts"]
    need(type(attempts) is list and len(attempts) == 24,
         "V2_EXACT_24_ATTEMPTS")
    ids = set()
    cells = set()
    accounting = Counter()
    for row in attempts:
        need(type(row) is dict and set(row) == {
             "attempt_id","candidate_id","month","state",
             "source_receipt_sha256"}, "V2_ATTEMPT_SHAPE")
        need(type(row["attempt_id"]) is str and
             0 < len(row["attempt_id"]) <= 160 and
             row["attempt_id"] not in ids and
             type(row["candidate_id"]) is str and
             row["candidate_id"] in STRATEGY_IDS and
             row["month"] in ALL_MONTHS,
             "V2_ATTEMPT_ID_OR_MONTH")
        ids.add(row["attempt_id"])
        cell=(row["month"],row["candidate_id"])
        need(cell not in cells, "V2_DUPLICATE_STRATEGY_MONTH")
        cells.add(cell)
        if row["month"] in INVENTORY:
            need(row["state"] == "UNKNOWN" and
                 row["source_receipt_sha256"] is None,
                 "V2_INVENTORY_MUST_HAVE_NULL_SOURCE")
            accounting["unknown"] += 1
        else:
            need(row["state"] == "DIAGNOSTIC_EVALUATED_NOT_SELECTED" and
                 row["source_receipt_sha256"] ==
                     parents[row["month"]]["source_sha256"],
                 "V2_SOURCE_ATTEMPT_ANCESTRY")
            accounting["evaluated"] += 1
    need(cells == {(m,s) for m in ALL_MONTHS for s in STRATEGY_IDS}
         and accounting == {"evaluated":20,"unknown":4},
         "V2_COMPLETE_20_PLUS_4_CENSUS")
    trial = packet["trial_packet"]
    need(type(trial) is dict and set(trial) == FOCUS_FIELDS
         and trial["schema"] == "aql.factory.f.recovery-focus.v2"
         and trial["diagnostic_month"] in MONTHS
         and trial["strategy_id"] in STRATEGY_IDS
         and trial["market"] == "SPOT" and
         trial["availability"] == "RETROSPECTIVE_NON_PIT" and
         trial["width_ms"] == 900000 and
         trial["dataset_version"] == 1,
         "V2_FOCUS_SCOPE")
    month=trial["diagnostic_month"]
    need(trial["dataset_id"] == "BINANCE-SPOT-BTCUSDT-15M-"+month+"-F-v1"
         and trial["source_bytes_sha256"] == parents[month]["source_sha256"]
         and trial["source_manifest_sha256"] == parents[month]["manifest_sha256"]
         and trial["strategy"] == packet["strategy_definitions"][
             trial["strategy_id"]], "V2_FOCUS_SOURCE_DEFINITION")
    bars=trial["bars"]
    window=packet["operator_policy"]
    # Must stop before any mutable store creation if policy is unavailable.
    _policy(window)
    # Existing per-bar seal/grid/closed-candle/future-window protections,
    # without calling the legacy 53-trial population validator.
    old={"bars":bars,"width_ms":900000,
         "research_window":window["research_window"],"opportunities":[]}
    _validate_bars(old)
    first,end=_month_boundaries(month)
    need(all(first <= b["open_ms"] and b["close_ms"] < end and
             b["known_at_ms"] is None for b in bars),
         "V2_ORIGINAL_MONTH_CLOSED_BARS_NOT_PIT")
    # Never invent Lab results: one original-month focus is required.
    need(len(bars) >= 2 and bars[-1]["close_ms"] <
         window["research_window"]["train_end_exclusive_ms"],
         "V2_FOCUS_NO_FUTURE_BARS")
    return definitions, parents


def _causal_focus(trial, definition, policy):
    """Reuse original Indicator/AST/Decimal cost kernels; NEVER run 53 trials."""
    bars = trial["bars"]
    costs = _policy(policy)
    risk = definition.spec["risk"]
    vectors = _vectors(definition, bars)
    modeled, decisions = [], []
    unknown = 0
    active = None
    blocked = False
    for i in range(len(bars)-1):
        if blocked:
            state="UNKNOWN_PATH_AFTER_BARRIER"
        elif active is None:
            flag=_expression(definition.spec["entry"],i,vectors)
            state="WARMUP_UNKNOWN" if flag is None else (
                "NO_SIGNAL" if flag is False else "ENTRY_TRIGGERED")
            if flag is True:
                active={"entry":i+1}
        else:
            entry=active["entry"]
            p=bars[entry]["open"]
            stop=p*(1-risk["stop_fraction"])
            target=p*(1+risk["target_fraction"])
            current=bars[i]
            if current["low"] <= stop or current["high"] >= target:
                unknown += 1
                modeled.append({"status":"UNKNOWN_INTRABAR_STOP_TARGET",
                                "entry_open_ms":bars[entry]["open_ms"],
                                "exit_open_ms":None})
                state="UNKNOWN_INTRABAR_STOP_TARGET"
                blocked=True
                active=None
            else:
                flag=_expression(definition.spec["exit"],i,vectors)
                if flag is None:
                    unknown+=1
                    modeled.append({"status":"UNKNOWN_EXIT_RULE",
                                    "entry_open_ms":bars[entry]["open_ms"],
                                    "exit_open_ms":None})
                    state="UNKNOWN_EXIT_RULE"
                    active=None
                    blocked=True
                elif flag or i+1-entry>=risk["holding_bars"]:
                    result=_modeled_trade(bars,entry,i+1,"LONG",costs,"SPOT")
                    modeled.append({**result,"status":"MODEL_ONLY"})
                    state="EXIT_TRIGGERED"
                    active=None
                else:
                    state="IN_POSITION"
        decisions.append({"bar_open_ms":bars[i]["open_ms"],"state":state})
    if active is not None:
        unknown+=1
        modeled.append({"status":"UNKNOWN_END_OF_DATA",
                        "entry_open_ms":bars[active["entry"]]["open_ms"],
                        "exit_open_ms":None})
    body={
        "schema":"aql.factory.f.recovery-causal-focus.v2",
        "strategy_digest":definition.digest,
        "source_bytes_sha256":trial["source_bytes_sha256"],
        "bar_count":len(bars),"decision_count":len(decisions),
        "decision_trace_sha256":digest(decisions),
        "outcome_trace_sha256":digest(modeled),
        "modeled_count":sum(x["status"]=="MODEL_ONLY" for x in modeled),
        "unknown_count":unknown,
        "costs":policy["costs"],
        "fill_policy":"UNKNOWN_ON_INTRABAR_TOUCH",
        "execution_status":"NOT_OBSERVED",
        "trading_authority":"NONE",
    }
    return {**body,"lab_sha256":digest(body)}


def _record_attempts(attempts, parents):
    """Store v2 currently accepts nonnull attempt parents; preserve NULL
    inventory semantics in the separately sealed v2 packet and map ONLY the
    private store index's ancestry to the signed v2 input digest. This is a
    storage-metadata surrogate, explicitly NOT a February/Aug source SHA.
    """
    raise ResultsStoreError("FACTORY_V2_STORAGE_NULL_ATTEMPTS_NOT_IMPLEMENTED")


def run_recovery_research_v2(packet, store_path):
    """Return immutable recovery-only diagnostic report (NOT legacy/F5)."""
    definitions, parents=validate_recovery_research_input(packet)
    store=Path(store_path)
    need(store.suffix == ".sqlite" and store.is_file(),
         "V2_EXISTING_ISOLATED_SQLITE_V2_REQUIRED")
    from research_wp_r0.aql_factory_e_research_results_store_v1 import (
        migrate_store_v2,
    )
    mig=migrate_store_v2(store)
    need(mig["status"] == "ALREADY_V2","V2_LAYOUT_REQUIRED")
    trial=packet["trial_packet"]
    lab=_causal_focus(trial,definitions[trial["strategy_id"]],
                      packet["operator_policy"])
    evaluation={
        "schema":"aql.factory.f.recovery-evaluation.v2",
        "input_sha256":packet["sha256"],
        "lab_sha256":lab["lab_sha256"],
        "source_graph_sha256":digest(parents),
        "research_class":"RETROSPECTIVE_NON_PIT",
        "not_authority":"NOT_F5_OR_CONSUMER_ACK",
        "modeled_count":lab["modeled_count"],
        "unknown_count":lab["unknown_count"],
        "costs":lab["costs"],
        "trading_authority":"NONE",
    }
    result_sha=digest(evaluation)
    attempts=_record_attempts(packet["attempts"],parents)
    record=build_experiment(
        experiment_id=packet["experiment_id"],lane="SCANNER",
        source_status="RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT",
        source_sha256=trial["source_bytes_sha256"],
        source_query_245_sha256=packet["core_245_query_sha256"],
        source_query_253_sha256=packet["core_253_query_sha256"],
        strategy_definition_sha256=definitions[trial["strategy_id"]].digest,
        config_sha256=packet["config_sha256"],
        code_sha256=packet["code_sha256"],
        environment_sha256=packet["environment_sha256"],
        parent_receipt_sha256=packet["sha256"],
        attempts=attempts,
        lab_receipt_sha256=lab["lab_sha256"],
        result_sha256=result_sha,
        evidence_class="RETROSPECTIVE_NON_PIT",
    )
    save=register_experiment(store,record)
    need(read_experiment(store,packet["experiment_id"])==record,
         "V2_IMMUTABLE_READBACK")
    layout=audit_store_layout(store)
    need(layout["layout_version"]==2, "V2_STORE_LAYOUT")
    body={
        "schema":REPORT,"status":"RECOVERY_RESEARCH_ONLY_NOT_F5",
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "recovery_evidence_file_sha256":RECOVERY_SHA,
        "recovery_raw_bytes_sha256":RECOVERY_RAW_BYTES_SHA,
        "original_f2_report_sha256":None,
        "core_receipt_graph_sha256":digest(parents),
        "scanner_receipt_sha256":packet["scanner_receipt_sha256"],
        "lab_sha256":lab["lab_sha256"],
        "experiment_sha256":record["sha256"],
        "result_sha256":result_sha,
        "attempt_count":24,"diagnostic_evaluated":20,
        "feb_aug_inventory_unknown":4,
        "modeled_count":lab["modeled_count"],
        "unknown_count":lab["unknown_count"],
        "costs":lab["costs"],
        "store_status":save["status"],
        "source_ack_sha256":None,"strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "historical_pit":"NOT_ATTESTED",
        "independent_attestation":"NOT_ATTESTED",
        "holdout":"SEALED_UNOPENED",
        "trading_authority":"NONE","paper":"NOT_ACTIVATED",
        "orders_created":0,"positions":0,"selected":False,
    }
    return {**body,"receipt_sha256":digest(body)}
