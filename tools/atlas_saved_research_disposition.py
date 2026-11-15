"""Read the authorized saved research chain and publish its downstream WAIT."""
import argparse
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
from unittest.mock import patch

from aql.observation.contracts import digest

STEP = 900_000


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def without_seal(doc):
    return digest({key: value for key, value in doc.items() if key != "sha256"})


def disposition(root, *, expected_result, plan, expected_plan, as_of_ms, saved_only,
                decision_open_ms=None):
    require(saved_only, "SAVED_READ_AUTHORITY_REQUIRED")
    from research_wp_r0.aql_core_backbone_local_v1 import query_local
    from research_wp_r0.aql_factory_authentic_research_admission import assess_research_admission, seal
    from research_wp_r0.aql_factory_e_research_results_store_v1 import read_experiment
    from tools.atlas_prospective_observe import FIXTURE

    require(digest(plan) == expected_plan, "APPROVED_PLAN_PIN")
    result, source, scanner, ack = (read(root / name) for name in
                                    ("result.json", "source.json", "scanner.json", "factory-ack.json"))
    require(without_seal(result) == result["sha256"] == expected_result, "RESULT_PIN")
    require(result["current_entry"] == scanner["current_entry"] == "NO_CURRENT_ENTRY",
            "HISTORICAL_CURRENT_ENTRY_DENIED")
    require(digest(source) == result["source_manifest_sha256"] == scanner["source_manifest_sha256"]
            and digest(scanner) == result["scanner_sha256"]
            and without_seal(ack) == ack["sha256"] and ack == result["factory_ack"], "SAVED_PARENT_PIN")
    opening, end = source["start_ms"], source["end_exclusive_ms"]
    cutoff = scanner["decision_cutoff_ms"]
    require(type(as_of_ms) is int and end <= cutoff <= as_of_ms, "AS_OF_SCOPE")
    candidates = [job for job in plan if job["start_ms"] == opening]
    require(len(candidates) == 1, "SOURCE_PLAN_MEMBERSHIP")
    job = candidates[0]
    require(job["end_ms"] == end and job["cutoff_ms"] == cutoff and job["original_reads"] == 1
            and job["authorization_ref"] == source["owner_authorization_ref"]
            and source["rights_status"] == "VERIFIED_FOR_EXACT_USE"
            and source["publisher_first_available_at_ms"] is None
            and source["pit"] == "NOT_ATTESTED"
            and source["source_version"] == source["archive_sha256"]
            and job["archive_sha256"] == source["archive_sha256"] == result["archive_sha256"]
            and job["checksum_sha256"] == source["checksum_sha256"] == result["checksum_sha256"],
            "SOURCE_SCOPE_DRIFT")
    rows = scanner["decisions"]
    require([row["open_ms"] for row in rows] == list(range(opening, end, STEP))
            and all(row["historical_bar_end_ms"] == row["open_ms"] + STEP
                    and row["historical_known_at_ms"] is None
                    and isinstance(row["derived_sha256"], str)
                    and len(row["derived_sha256"]) == 64
                    and all(c in "0123456789abcdef" for c in row["derived_sha256"]) for row in rows)
            and len(rows) == result["derived_rows"]
            and dict(Counter(row["state"] for row in rows)) == result["census"], "SCANNER_CENSUS_OR_TIME")
    store = root / "factory.sqlite"
    wal = Path(str(store) + "-wal")
    require(not wal.exists() or wal.stat().st_size == 0, "DETACHED_FACTORY_REQUIRED")
    factory = read_experiment(store, job["experiment"], detached_snapshot=True)
    with closing(sqlite3.connect(store.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        require(db.execute("SELECT count(*) FROM experiments").fetchone()[0] == 1,
                "FACTORY_PARENT_COUNT")
    require(factory["sha256"] == result["factory_sha256"] == ack["experiment_sha256"]
            and factory["source_sha256"] == digest(source)
            and factory["parent_receipt_sha256"] == digest(scanner)
            and factory["core_245_price_query_sha256"] == scanner["core245"] == result["core245"]
            and factory["core_253_query_local_sha256"] == scanner["core253"] == result["core253"]
            and factory["strategy_definition_sha256"] == scanner["strategy_sha256"]
            and factory["config_sha256"] == scanner["config_sha256"]
            and factory["historical_pit"] == "NOT_ATTESTED"
            and factory["evidence_class"] == result["evidence_class"] == "RETROSPECTIVE_NON_PIT"
            and factory["orders_created"] == factory["paper_positions"] == result["orders"] == 0
            and factory["actual_fills"] is result["actual_fills"] is None
            and factory["trading_authority"] == "NONE", "FACTORY_PARENT_DRIFT")
    core = query_local(root / "core", job["experiment"], 1, opening, end, cutoff,
                       required_source_sha256=source["archive_sha256"],
                       require_complete=True, sqlite_immutable=True,
                       expected_saved_query_sha256=scanner["core253"])
    require(core["query_sha256"] == scanner["core253"] and core["coverage"] == "COMPLETE"
            and len(core["bars"]) == result["native_rows"], "CORE_SAVED_QUERY_DRIFT")
    fixture = read(FIXTURE)[0]["payload"]
    require(fixture["definition"]["digest"] == scanner["strategy_sha256"]
            and fixture["config_digest"] == scanner["config_sha256"], "STRATEGY_PARENT_DRIFT")
    attempts = [{"attempt_id": attempt["attempt_id"], "strategy_id": fixture["strategy_id"],
                 "strategy_version": fixture["strategy_version"], "plan_digest": expected_plan,
                 "decision_cutoff_ms": cutoff, "feature_available_ms": None, "state": "NOT_EVALUATED",
                 "duplicate_of": None, "result": None, "holdout_access": False}
                for attempt in factory["attempts"]]
    gate = assess_research_admission(seal(dict(
        schema="aql.factory.authentic-research-admission.v1", execution_authority="NONE",
        paper_live=False, holdout="SEALED_UNOPENED", source_kind="ORIGINAL_UNVERIFIED",
        source_bytes_sha256=source["archive_sha256"], source_manifest_sha256=digest(source),
        dataset_version_sha256=digest(source), plan_digest=expected_plan,
        dataset_id=job["experiment"], strategy_id=fixture["strategy_id"],
        strategy_version=fixture["strategy_version"], strategy_definition_digest=scanner["strategy_sha256"],
        decision_cutoff_ms=cutoff, availability="RETROSPECTIVE_NON_PIT",
        expected_attempts=len(attempts), attempts=attempts)))
    require(gate["admission"] == "AUTHENTIC_SOURCE_NOT_CONNECTED" and
            gate["scientific_result"] == "INSUFFICIENT_EVIDENCE" and gate["pit_verified"] is False,
            "SCIENTIFIC_GATE_FAIL_OPEN")
    require(end - opening < 259_200_000 and result["lab"] == "NOT_ELIGIBLE_SPLIT_LOOKAHEAD"
            and factory["lab_receipt_sha256"] is None and factory["paper_receipt_sha256"] is None,
            "LAB_PARENT_OR_SCOPE")
    report = dict(grade="RESEARCH_DISPOSITION_SLICE_PASS", evidence="OWNER_LOCAL_SAVED_ORIGINAL_DERIVED",
                  as_of_ms=as_of_ms, start_ms=opening, end_ms=end, decision_cutoff_ms=cutoff,
                  trace_id=factory["experiment_id"], plan_sha256=expected_plan, result_sha256=expected_result,
                  source_manifest_sha256=digest(source), core245=scanner["core245"], core253=scanner["core253"],
                  scanner_sha256=digest(scanner), factory_sha256=factory["sha256"], factory_ack_sha256=ack["sha256"],
                  census=result["census"], eligibility=gate, lab=result["lab"],
                  secretary={"disposition": "WAIT_AUTHENTICATED_PARENTS", "dispatch": None},
                  current_entry="NO_CURRENT_ENTRY", orders=0, original_reads=0)
    if decision_open_ms is not None:
        require(type(decision_open_ms) is int and opening <= decision_open_ms < end
                and (decision_open_ms - opening) % STEP == 0, "ORDERED_DECISION_SCOPE")
        position = (decision_open_ms - opening) // STEP
        report["scanner_membership"] = {
            "position": position, "decision": rows[position], "decision_sha256": digest(rows[position]),
            "ordered_census_sha256": digest(rows), "scanner_receipt_sha256": report["scanner_sha256"],
            "source_version": source["source_version"], "core253_query_sha256": core["query_sha256"],
            "discoverer": "NOT_APPLICABLE_SCANNER_LANE", "known_at": "KNOWN_AT_UNATTESTED",
        }
    return {**report, "sha256": digest(report)}


def publish(path, report):
    path = path.absolute()
    raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            require(path.read_bytes() == raw, "DISPOSITION_ALREADY_SEALED")
    finally:
        temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--result-sha256", required=True)
    parser.add_argument("--as-of-ms", required=True, type=int)
    parser.add_argument("--saved-only", action="store_true")
    parser.add_argument("--decision-open-ms", type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        report = disposition(args.saved, expected_result=args.result_sha256,
                             plan=read(args.plan), expected_plan=args.plan_sha256,
                             as_of_ms=args.as_of_ms, saved_only=args.saved_only,
                             decision_open_ms=args.decision_open_ms)
        publish(args.output, report)
    print(report["sha256"])


if __name__ == "__main__":
    main()
