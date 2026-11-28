"""Read independently pinned retrospective Scanner/Factory evidence without dispatch."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest, read_experiment

STEP = 900_000
MAX_BYTES = 5_000_000
HASH = re.compile(r"[0-9a-f]{64}")
STATES = {"ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL", "REJECTED", "UNKNOWN",
          "UNSCANNED", "INELIGIBLE", "SEALED_HOLDOUT", "EMBARGO"}


def require(ok, code):
    if not ok:
        raise ValueError(code)


def unique_fields(pairs):
    obj = dict(pairs)
    require(len(obj) == len(pairs), "CENSUS_DUPLICATE_FIELD")
    return obj


def read_saved_census(path, experiment_path, *, receipt_pin, experiment_pin):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES and raw.endswith(b"\n")
            and sha256(raw[:-1]).hexdigest() == receipt_pin, "CENSUS_PIN")
    receipt = json.loads(raw, object_pairs_hook=unique_fields)
    require(type(receipt) is dict and digest(receipt) == receipt_pin
            and receipt.get("schema") == "aql.first-cycle.scanner-census-receipt.v1"
            and receipt.get("availability") == "RETROSPECTIVE_NON_PIT"
            and receipt.get("known_at_status") == "UNKNOWN"
            and receipt.get("core_link_status") == "SOURCE_BLOCKED"
            and "core_receipt_id" in receipt and receipt["core_receipt_id"] is None
            and receipt.get("source_class") in {"SIMULATED_ADAPTER_TEST",
                                               "RETAINED_ACTUAL_MARKET_RETROSPECTIVE_NON_PIT"},
            "CENSUS_SCOPE")
    experiment = read_experiment(experiment_path, receipt["factory_experiment_id"], detached_snapshot=True)
    require(experiment["sha256"] == experiment_pin == receipt.get("factory_experiment_sha256")
            and experiment["lane"] == "SCANNER"
            and experiment["evidence_class"] == "RETROSPECTIVE_NON_PIT"
            and experiment["source_status"] == "RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT"
            and experiment["trading_authority"] == "NONE"
            and experiment["historical_pit"] == "NOT_ATTESTED"
            and experiment["holdout"] == "SEALED_UNOPENED"
            and experiment["orders_created"] == experiment["paper_positions"] == 0
            and experiment["actual_fills"] is None
            and experiment["strategy_performance_accepted"] is False, "CENSUS_FACTORY_SCOPE")
    for field, parent in (("source_sha256", "source_sha256"), ("strategy_sha256", "strategy_definition_sha256"),
                          ("config_sha256", "config_sha256"), ("candidate_package_sha256", "parent_receipt_sha256")):
        require(type(receipt.get(field)) is str and HASH.fullmatch(receipt[field])
                and receipt[field] == experiment[parent], "CENSUS_FACTORY_PARENT")
    attempts = experiment["attempts"]
    require(type(attempts) is list and len(attempts) == experiment["attempt_count"] == 1, "CENSUS_ATTEMPT_COUNT")
    attempt = attempts[0]
    require(attempt["attempt_id"] == receipt["attempt_id"] and attempt["candidate_id"] == receipt["candidate_id"]
            and attempt["source_receipt_sha256"] == receipt["candidate_package_sha256"], "CENSUS_ATTEMPT_PARENT")
    rows = receipt.get("decisions")
    require(type(rows) is list and 0 < len(rows) <= 8192
            and digest(rows) == receipt.get("decision_census_sha256"), "CENSUS_ROWS")
    counts = Counter()
    previous = None
    for row in rows:
        require(type(row) is dict, "CENSUS_ROW_SHAPE")
        opened = row.get("open_ms")
        state = row.get("state")
        require(type(opened) is int and opened >= 0 and opened % STEP == 0
                and (previous is None or opened == previous + STEP)
                and row.get("decision_cutoff_ms") == opened + STEP
                and row.get("availability") == "RETROSPECTIVE_NON_PIT"
                and "known_at_ms" in row and row["known_at_ms"] is None
                and row.get("strategy_sha256") == receipt["strategy_sha256"]
                and type(row.get("source_row_sha256")) is str and HASH.fullmatch(row["source_row_sha256"])
                and type(state) is str and state in STATES, "CENSUS_ORDER_OR_AUTHORITY")
        previous = opened
        counts[state] += 1
    return dict(schema="atlas.saved-retrospective-census.v1", receipt_sha256=receipt_pin,
                experiment_sha256=experiment_pin, experiment_id=experiment["experiment_id"],
                attempt_id=attempt["attempt_id"], counts=dict(sorted(counts.items())), row_count=len(rows),
                source_class=receipt["source_class"], known_at="UNKNOWN",
                core="SOURCE_BLOCKED", historical_pit="NOT_ATTESTED",
                trading_authority="NONE", secretary="WAIT", orders=0, dispatch=None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--receipt-pin", required=True)
    parser.add_argument("--experiment-pin", required=True)
    args = parser.parse_args()
    print(json.dumps(read_saved_census(args.receipt, args.experiment,
                                      receipt_pin=args.receipt_pin, experiment_pin=args.experiment_pin),
                     sort_keys=True))
