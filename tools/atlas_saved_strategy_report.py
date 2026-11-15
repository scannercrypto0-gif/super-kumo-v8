"""Read one pinned retrospective modeled strategy experiment and seal its report."""
import argparse
from collections import Counter
from contextlib import closing
from decimal import Decimal, localcontext
import json
from pathlib import Path
import shutil
import socket
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aql.observation.contracts import digest
from research_wp_r0.aql_factory_lab_saved_read_v1 import read_saved_lab
from tools.atlas_saved_research_disposition import publish, read, require
from tools.first_research_cycle.verify_run import verify


def validate_plan(plan, strategy_pin):
    require(plan["strategy"]["digest"] == strategy_pin, "STRATEGY_PIN")
    start, train, validation, holdout, end = (plan[key] for key in (
        "first_open_ms", "train_end_ms", "validation_end_ms", "holdout_start_ms", "end_exclusive_ms"))
    require(start < train < validation and validation + 259_200_000 <= holdout < end and
            all(value % 900_000 == 0 for value in (start, train, validation, holdout, end)),
            "SPLIT_OR_HOLDOUT")
    require(plan["holdout"] == "SEALED_UNOPENED" and plan["candidate_budget"] == 1 and
            plan["winner"] is None and plan["trading_authority"] == "NONE"
            and plan["real_pit"] == "NOT_ATTESTED", "TRIAL_OR_HOLDOUT_AUTHORITY")
    for costs in plan["costs"].values():
        require(all(Decimal(value).is_finite() and 0 <= Decimal(value) < 10_000
                    for value in costs.values()), "COST_SCOPE")


def verify_saved_accounting(root, result):
    # SQLite can create sidecars even in read-only WAL mode.
    filenames = ["result.json", "market-plan.json", "factory.sqlite"]
    ordered = "scanner_receipt_sha256" in result
    if ordered:
        for filename in ("scanner-census.json", "candidate.json", "native-plan.json", "discoverer-ledger.json"):
            source = root / filename
            require(source.is_file() and not source.is_symlink() and source.stat().st_size <= 5_000_000,
                    f"SCANNER_PARENT_MISSING_OR_INVALID: {filename}")
            filenames.append(filename)
    with TemporaryDirectory() as scratch:
        staging = Path(scratch)
        for filename in filenames:
            shutil.copyfile(root / filename, staging / filename)
        validated = verify(staging)
    require(validated["result_sha256"] == result["sha256"], "SAVED_MODEL_PARENT")
    if ordered:
        require(validated.get("scanner_membership", {}).get("receipt_sha256")
                == result["scanner_receipt_sha256"], "SCANNER_VERIFIER_REQUIRED")
    return validated


def build(root, *, plan_pin, result_file_pin, store_file_pin, strategy_pin, saved_only):
    require(saved_only, "SAVED_READ_AUTHORITY_REQUIRED")
    plan = read(root / "market-plan.json")
    require(digest(plan) == plan_pin, "PLAN_PIN")
    validate_plan(plan, strategy_pin)
    lab = read_saved_lab(root, result_file_sha256=result_file_pin,
                         plan_sha256=plan_pin, store_file_sha256=store_file_pin)
    result = read(root / "result.json")
    validated = verify_saved_accounting(root, result)
    require(lab["result_sha256"] == result["sha256"] and
            validated["verified_cost_rows"] == lab["populations"]["cost_rows"]
            and validated["scientific_status"] == lab["scientific_status"] == "REAL_PIT_OOS_BLOCKED",
            "SAVED_MODEL_PARENT")
    db_path = root / "factory.sqlite"
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        package = json.loads(db.execute("SELECT document FROM factory_h_research_results_v1").fetchone()[0])
    require(package["sha256"] == lab["package_sha256"] and digest(
        {key: value for key, value in package.items() if key != "sha256"}) == package["sha256"],
        "MODELED_ROWS_PARENT")
    cells = {}
    with localcontext() as context:
        context.prec = 40
        for row in package["outcomes"]:
            key = "/".join(row[field] for field in ("partition", "cohort", "scenario", "policy"))
            counts, totals = cells.setdefault(key, (Counter(), [Decimal(0)] * 3))
            counts[row["status"]] += 1
            if row["status"] == "MODEL_ONLY":
                gross, net, cost = map(Decimal, (row["gross_return"], row["net_return"], row["total_cost_bps"]))
                require(gross - net == cost / 10000, "MODELED_COST_CONSERVATION")
                for index, value in enumerate((gross, net, cost / 10000)):
                    totals[index] += value
    require(sum(sum(counts.values()) for counts, _ in cells.values()) == validated["verified_cost_rows"],
            "MODELED_DENOMINATOR")
    summaries = {key: {"statuses": dict(counts), "expected": sum(counts.values()),
                       "known_subset_gross": str(totals[0]) if counts["MODEL_ONLY"] else None,
                       "known_subset_net": str(totals[1]) if counts["MODEL_ONLY"] else None,
                       "known_subset_cost": str(totals[2]) if counts["MODEL_ONLY"] else None}
                 for key, (counts, totals) in cells.items()}
    body = dict(grade="EXPLORATORY_STRATEGY_SLICE_PASS", evidence="OWNER_LOCAL_RETAINED_MODEL",
                strategy=plan["strategy"], strategy_sha256=strategy_pin, plan_sha256=plan_pin,
                result_sha256=result["sha256"], result_file_sha256=result_file_pin,
                factory_store_file_sha256=store_file_pin, experiment_sha256=lab["experiment_sha256"],
                modeled_package_sha256=lab["package_sha256"], lab_readback_sha256=lab["sha256"],
                accounting_verification_sha256=validated["sha256"], source=lab["source"],
                utc_split_ms=lab["split_ms"], holdout="SEALED_UNOPENED",
                trial_budget=plan["candidate_budget"], freeze_purpose=plan["freeze_purpose"],
                cost_assumptions=plan["costs"], populations=lab["populations"],
                outcome_counts=lab["outcome_counts"], cells=summaries, current_entry="NO_CURRENT_ENTRY",
                lab="NOT_ELIGIBLE_FOR_SCIENTIFIC_PIT_OOS", secretary="WAIT", orders=0, actual_fills=None,
                limitations=["Known subset sums exclude unresolved rows and are not portfolio returns.",
                             "One source population; no survivorship or out-of-sample performance claim.",
                             "Workload selection for this report does not constitute a new freeze or trial."])
    if "scanner_membership" in validated:
        body["scanner_membership"] = validated["scanner_membership"]
    else:
        body["limitations"].insert(2, "Standalone ordered Scanner receipt is unavailable in the legacy saved schema.")
    return {**body, "sha256": digest(body)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--saved", required=True, type=Path)
    p.add_argument("--plan-sha256", required=True)
    p.add_argument("--result-file-sha256", required=True)
    p.add_argument("--store-file-sha256", required=True)
    p.add_argument("--strategy-sha256", required=True)
    p.add_argument("--saved-only", action="store_true")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        result = build(args.saved, plan_pin=args.plan_sha256, result_file_pin=args.result_file_sha256,
                       store_file_pin=args.store_file_sha256, strategy_pin=args.strategy_sha256,
                       saved_only=args.saved_only)
        publish(args.output, result)
    print(result["sha256"])


if __name__ == "__main__":
    main()
