"""Read a pinned #296 saved experiment as a model-only Lab view."""
import argparse
from collections import Counter
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .aql_factory_e_research_results_store_v1 import ResultsStoreError, digest


def require(condition, code):
    if not condition:
        raise ResultsStoreError(code)


def seal_matches(document, expected):
    return document.get("sha256") == expected == digest({
        key: value for key, value in document.items() if key != "sha256"
    })


def read_saved_lab(run, *, result_file_sha256, plan_sha256, store_file_sha256):
    """Verify owner-pinned files and query a detached, checkpointed SQLite snapshot."""
    root = Path(run).resolve()
    store = root / "factory.sqlite"
    require(all(not Path(str(store) + suffix).exists() for suffix in ("-wal", "-journal", "-shm")),
            "DETACHED_SNAPSHOT_REQUIRED")
    raw = (root / "result.json").read_bytes()
    require(sha256(raw).hexdigest() == result_file_sha256, "RESULT_FILE_PIN")
    result = json.loads(raw)
    plan = json.loads((root / "market-plan.json").read_bytes())
    require(seal_matches(result, result.get("sha256")) and
            result["schema"] == "aql.first-cycle.actual-market-result.v1", "RESULT_SEAL_OR_SCHEMA")
    require(digest(plan) == plan_sha256 == result["plan_sha256"], "PLAN_PIN")
    require(sha256(store.read_bytes()).hexdigest() == store_file_sha256, "STORE_FILE_PIN")

    start, train, validation, holdout, end = (plan[key] for key in (
        "first_open_ms", "train_end_ms", "validation_end_ms", "holdout_start_ms", "end_exclusive_ms"
    ))
    require(start < train < validation and holdout - validation >= 259200000 and holdout < end and
            (end - start) == 900000 * plan["expected_bars"] and
            plan["holdout"] == result["holdout"] == "SEALED_UNOPENED", "SPLIT_OR_HOLDOUT")
    require(result["source_class"] == plan["source_class"] ==
            "RETAINED_ACTUAL_MARKET_RETROSPECTIVE_NON_PIT", "SOURCE_CLASS")
    require([(r["name"], r["sha256"], r["rows"]) for r in result["source"]] ==
            [(r["name"], r["sha256"], r["rows"]) for r in plan["archives"]], "SOURCE_PINS")

    with closing(sqlite3.connect(store.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
        entries = conn.execute("SELECT experiment_id, sha, document, immutable FROM experiments LIMIT 2").fetchall()
        packages = conn.execute(
            "SELECT experiment_id, canonical_sha256, document, immutable FROM factory_h_research_results_v1 LIMIT 2"
        ).fetchall()
    require(len(entries) == len(packages) == 1, "STORE_POPULATION")
    eid, exp_sha, exp_raw, exp_lock = entries[0]
    pid, package_sha, package_raw, package_lock = packages[0]
    experiment, package = json.loads(exp_raw), json.loads(package_raw)
    require(exp_lock == package_lock == 1 and eid == pid == experiment["experiment_id"] ==
            package["experiment_id"] and seal_matches(experiment, exp_sha) and
            exp_sha == result["factory_experiment_sha256"] == package["factory_experiment_sha256"]
            and seal_matches(package, package_sha) and package_sha == result["result_store_sha256"],
            "EXPERIMENT_PACKAGE_LINK")
    require(digest(result["source"]) == experiment["source_sha256"] == package["source_sha256"] and
            package["source_class"] == result["source_class"] and
            plan["strategy"]["digest"] == experiment["strategy_definition_sha256"] and
            digest(plan["strategy"]) == experiment["config_sha256"] and
            package["candidate_package_sha256"] == result["candidate_package_sha256"] ==
            experiment["parent_receipt_sha256"] and package["decision_census_sha256"] ==
            result["decision_census_sha256"] and package["native_plan_sha256"] ==
            result["native_plan_sha256"], "PARENT_IDENTITY")
    require(experiment["evidence_class"] == "RETROSPECTIVE_NON_PIT" and
            experiment["historical_pit"] == "NOT_ATTESTED" and
            experiment["holdout"] == "SEALED_UNOPENED" and
            experiment["orders_created"] == experiment["paper_positions"] == 0 and
            experiment["strategy_performance_accepted"] is False and
            all(d["trading_authority"] == "NONE" and d["actual_fills"] is None
                for d in (experiment, package, result)), "RESEARCH_AUTHORITY")

    rows = package["outcomes"]
    counts = Counter(row["status"] for row in rows)
    keys = {(r["cohort"], r["entry_id"], r["scenario"], r["policy"]) for r in rows}
    census = result["populations"]["scanner_census"]
    require(sum(census.values()) == result["populations"]["source_bars"] == plan["expected_bars"]
            and census["EMBARGO"] == (holdout - validation) // 900000
            and census["SEALED_HOLDOUT"] == (end - holdout) // 900000
            and len(keys) == len(rows) == result["populations"]["cost_rows"]
            and dict(counts) == result["outcome_status_counts"], "CENSUS_DRIFT")
    require(all(r["partition"] in {"TRAIN", "VALIDATION"} and
                all(leg["accounting_asof_ms"] <= validation for leg in r["legs"]) for r in rows),
            "HOLDOUT_LOOKAHEAD")
    body = dict(schema="aql.factory.lab-saved-read.v1", experiment_id=eid,
                experiment_sha256=exp_sha, package_sha256=package_sha, result_sha256=result["sha256"],
                plan_sha256=plan_sha256, source=result["source"], source_bars=plan["expected_bars"],
                strategy_sha256=experiment["strategy_definition_sha256"], null_sha256=digest(plan["null"]),
                costs_sha256=digest(plan["costs"]), split_ms=[start, train, validation, holdout, end],
                holdout="SEALED_UNOPENED", populations=result["populations"], outcome_counts=dict(counts),
                evidence_class="RETROSPECTIVE_NON_PIT", execution="MODEL_ONLY",
                scientific_status="REAL_PIT_OOS_BLOCKED", trading_authority="NONE", actual_fills=None,
                status="SAVED_LAB_READBACK_PASS")
    return {**body, "sha256": digest(body)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--result-sha256", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--store-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(read_saved_lab(args.run, result_file_sha256=args.result_sha256,
                                   plan_sha256=args.plan_sha256, store_file_sha256=args.store_sha256),
                     sort_keys=True))
