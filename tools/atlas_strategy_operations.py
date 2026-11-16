"""Read-only strategy operations over a pinned, saved Factory/Lab report."""
import argparse
from collections import Counter
from dataclasses import asdict
from decimal import Decimal, localcontext
import os
from pathlib import Path
import re
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aql.observation.contracts import digest
from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
from tools.atlas_saved_research_disposition import publish, read, require, without_seal
from tools.research_capacity_scale.runtime import catalog, safe, store


def isolated_paper_view(handoff, scanner, states, journal_events, policy):
    """Project verified, detached TEST_ONLY simulation evidence for operators."""
    require(handoff["evidence"] == "GENERATED_TEST_ONLY", "PAPER_REPORT_EVIDENCE")
    phases = Counter(state["phase"] for state in states.values())
    decisions = Counter(row["decision"]["state"] for row in scanner["rows"])
    fills = [fill for state in states.values() for fill in state["fills"]]
    net_pnl = [Decimal(state["net_pnl"]) for state in states.values()
               if state["net_pnl"] is not None]
    fees = sum(Decimal(state["fees"]) for state in states.values())
    spread_slippage_rate = (Decimal(policy.half_spread_bps) + Decimal(policy.slippage_bps)) / 10000
    require(all(fill["liquidity"] == "ASSUMED_TAKER" for fill in fills), "PAPER_REPORT_FILL_SCOPE")
    spread_slippage = sum(Decimal(fill["qty"]) * Decimal(fill["price"]) * spread_slippage_rate
                          / (1 + spread_slippage_rate if fill["side"] == "buy" else 1 - spread_slippage_rate)
                          for fill in fills)
    report = dict(schema="atlas.strategy-operations.paper-acceptance.v1",
                  evidence=handoff["evidence"], run_id=handoff["run_id"],
                  strategy_sha256=handoff["strategy_sha256"], acceptance_sha256=handoff["sha256"],
                  scanner_sha256=scanner["sha256"], journal_sha256=handoff["journal_sha256"],
                  replay_state_sha256=handoff["replay_state_sha256"], decision_states=dict(decisions),
                  decision_total=sum(decisions.values()), terminal_states=dict(phases),
                  journal_events=journal_events, virtual_entry_orders=len(states),
                  virtual_exit_executions=sum(fill["side"] == "sell" for fill in fills),
                  virtual_fills=len(fills), virtual_closed_positions=phases["CLOSED"],
                  assumed_fees_quote=str(fees), assumed_spread_slippage_quote=str(spread_slippage),
                  assumed_total_cost_quote=str(fees + spread_slippage),
                  modeled_closed_net_pnl_quote=str(sum(net_pnl)), policy=asdict(policy),
                  errors=handoff["errors"], duplicate=handoff["duplicate"],
                  current_entry="NO_CURRENT_ENTRY", secretary="WAIT", dispatch=None, orders=0,
                  telegram="NOT_SENT", trading_authority="NONE",
                  scientific_status="REAL_PIT_OOS_BLOCKED", continuous_paper="NOT_ACTIVATED")
    return {**report, "sha256": digest(report)}


def project(report, expected):
    require(report.get("sha256") == expected == without_seal(report), "REPORT_PIN")
    require(report["grade"] == "EXPLORATORY_STRATEGY_SLICE_PASS"
            and report["evidence"] == "OWNER_LOCAL_RETAINED_MODEL"
            and report["holdout"] == "SEALED_UNOPENED"
            and report["lab"] == "NOT_ELIGIBLE_FOR_SCIENTIFIC_PIT_OOS"
            and report["secretary"] == "WAIT" and report["current_entry"] == "NO_CURRENT_ENTRY"
            and type(report["orders"]) is int and report["orders"] == 0
            and report["actual_fills"] is None, "RESEARCH_AUTHORITY")
    strategy = report["strategy"]["definition"]
    identity = [strategy["strategy_id"], strategy["strategy_version"]]
    require(digest(strategy) == report["strategy"]["digest"] == report["strategy_sha256"],
            "STRATEGY_PIN")
    start, train_end, validation_end, holdout_start, end = report["utc_split_ms"]
    require(start < train_end < validation_end < holdout_start < end, "SPLIT_ORDER")
    outcomes = {}
    for cell in report["cells"].values():
        require(all(type(count) is int and count >= 0 for count in cell["statuses"].values())
                and sum(cell["statuses"].values()) == cell["expected"], "CELL_POPULATION")
        for status, count in cell["statuses"].items():
            outcomes[status] = outcomes.get(status, 0) + count
        totals = [cell["known_subset_" + key] for key in ("gross", "net", "cost")]
        if cell["statuses"].get("MODEL_ONLY", 0):
            with localcontext() as ctx:
                ctx.prec = 40
                gross, net, cost = map(Decimal, totals)
                require(all(x.is_finite() for x in (gross, net, cost)) and cost >= 0
                        and gross - net == cost, "COST_CONSERVATION")
        else:
            require(all(value is None for value in totals), "UNKNOWN_RETURN")
    require(outcomes == report["outcome_counts"]
            and sum(outcomes.values()) == report["populations"]["cost_rows"], "REPORT_POPULATION")
    return dict(
        identity=identity, strategy_sha256=report["strategy_sha256"], classification=strategy["scope"],
        modes={"Research": "MODEL_ONLY", "Shadow": "NOT_AVAILABLE",
               "Paper": "NOT_AVAILABLE", "Live": "NOT_AVAILABLE"},
        source=report["source"], source_report_sha256=expected, plan_sha256=report["plan_sha256"],
        factory_experiment_sha256=report["experiment_sha256"],
        factory_package_sha256=report["modeled_package_sha256"], evidence=report["evidence"],
        status="SAVED_SNAPSHOT", coverage_utc_ms=report["utc_split_ms"],
        train_days=(train_end - start) / 86_400_000,
        validation_days=(validation_end - train_end) / 86_400_000,
        operational_duration="NOT_AVAILABLE", trades="NOT_AVAILABLE",
        mean_daily_trades="NOT_AVAILABLE", fees_realized="NOT_AVAILABLE",
        slippage_realized="NOT_AVAILABLE", drawdown="NOT_AVAILABLE",
        evidence_counts=outcomes, opportunities=report["populations"], accounting_cells=report["cells"],
        cost_assumptions=report["cost_assumptions"], declared_risk=strategy["risk"],
        current_entry="NO_CURRENT_ENTRY", orders=0, scientific_status=report["lab"],
    )


def initialize(path):
    if not path.exists():
        with TemporaryDirectory(dir=path.parent) as scratch:
            stage = Path(scratch) / "operations.sqlite"
            migrate_store_v2(stage)
            store(stage, dict(experiment_id="OPERATIONS-SCOPE", schema="aql.strategy-operations.store.v1"))
            try:
                os.link(stage, path)
            except FileExistsError:
                pass
    require(path.is_file() and path.stat().st_size <= 32_000_000, "OPERATIONS_STORE_BOUND")
    require(catalog(path).get("OPERATIONS-SCOPE", {}).get("schema")
            == "aql.strategy-operations.store.v1", "OPERATIONS_STORE_SCOPE")


def register(checkpoint, row):
    identity = digest(row["identity"])
    store(checkpoint, dict(schema="aql.strategy-operations.identity.v1",
                           experiment_id="IDENTITY-" + identity,
                           identity=row["identity"], strategy_sha256=row["strategy_sha256"]))
    store(checkpoint, dict(schema="aql.strategy-operations.performance.v1",
                           experiment_id="PERFORMANCE-" + row["source_report_sha256"], strategy=row))


def strategies_view(records):
    grouped = {}
    for key, record in records.items():
        if key.startswith("PERFORMANCE-"):
            row = record["strategy"]
            identity = digest(row["identity"])
            anchor = records.get("IDENTITY-" + identity, {})
            require(anchor.get("strategy_sha256") == row["strategy_sha256"], "STRATEGY_IDENTITY_PARENT")
            grouped.setdefault(identity, []).append(row)
    strategies = []
    for identity in sorted(grouped):
        history = sorted(grouped[identity], key=lambda row: (row["coverage_utc_ms"][2],
                                                            row["source_report_sha256"]))
        strategies.append({**history[-1], "report_history": [dict(source_report_sha256=row["source_report_sha256"],
                                                                coverage_utc_ms=row["coverage_utc_ms"])
                                                            for row in history]})
    return strategies


def request(checkpoint, row, request_id, action):
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id) is not None, "INVALID_REQUEST_ID")
    decisions = {
        "REPORT": "REPORT_ALLOWED",
        "REMOVE_PAPER": "OWNER_APPROVAL_REQUIRED",
        "ADD_PAPER": "QUALIFICATION_AND_AUTHORITY_REQUIRED",
        "PROMOTE_LIVE": "QUALIFICATION_AND_AUTHORITY_REQUIRED",
    }
    require(action in decisions, "INVALID_ACTION")
    body = dict(schema="aql.strategy-operations.audit.v1", experiment_id="REQUEST-" + request_id,
                strategy_sha256=row["strategy_sha256"], role="OPERATION_MANAGER",
                action=action, decision=decisions[action], state_changed=False)
    event, _ = store(checkpoint, body)
    return event


def preview(checkpoint, row):
    body = dict(schema="aql.strategy-operations.notification-preview.v1",
                experiment_id="PREVIEW-" + row["source_report_sha256"], channel="TELEGRAM",
                delivery="OFFLINE_PREVIEW_ONLY", message="A saved strategy research report is available.")
    receipt, _ = store(checkpoint, body)
    return receipt


def run(report_path, expected, checkpoint, output, *, action="REPORT", request_id=None):
    report_path, checkpoint = map(safe, (report_path, checkpoint))
    output = safe(output) if output is not None else None
    require(len({report_path, checkpoint, output}) == 3 and report_path.is_file()
            and report_path.stat().st_size <= 5_000_000, "OPERATIONS_PATH_SCOPE")
    require(action == "REPORT" or request_id is not None, "CHANGE_REQUEST_ID_REQUIRED")
    row = project(read(report_path), expected)
    initialize(checkpoint)
    register(checkpoint, row)
    event = request(checkpoint, row, request_id, action) if request_id is not None else None
    if event is not None and event["decision"] != "REPORT_ALLOWED":
        return None, event
    preview(checkpoint, row)
    records = catalog(checkpoint)
    body = dict(schema="aql.strategy-operations.read-view.v1", strategies=strategies_view(records),
                execution_authority="NONE",
                notifications=[records[key] for key in sorted(records) if key.startswith("PREVIEW-")])
    view = {**body, "sha256": digest(body)}
    if output is not None:
        publish(output, view)
    return view, event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("report", "checkpoint", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--action", default="REPORT", choices=("REPORT", "REMOVE_PAPER", "ADD_PAPER", "PROMOTE_LIVE"))
    parser.add_argument("--request-id")
    args = parser.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        view, event = run(args.report, args.report_sha256, args.checkpoint, args.output,
                          action=args.action, request_id=args.request_id)
    print(event["decision"] if view is None else view["sha256"])
    return 2 if view is None else 0


if __name__ == "__main__":
    raise SystemExit(main())
