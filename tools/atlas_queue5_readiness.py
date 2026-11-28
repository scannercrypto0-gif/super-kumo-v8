"""Native synthetic prefreeze, capture and science-readiness drill."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "tests")]

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from aql.journal.durable_journal import DurableJournal
from research_wp_r0.aql_core_prospective_readiness_v1 import seal_readiness, admit_sample
from research_wp_r0.aql_f1_decision_capture_v1 import hash_f1, digest as capture_digest, write_original_candidate
from research_wp_r0.aql_queue5_readiness_v1 import validate_capture_chain, inspect_host_claim, require
from research_wp_r0.frozen_research_plan import commit_research_plan
from tools.core_prospective_readiness_smoke import fixture, mock_bar, commit_mock, sample_args
from tools.atlas_queue4_methods import produce as produce_methods, verify as verify_methods
from tools.pit_oos_readiness.promotion import review
# This CLI is a synthetic evidence generator. The original F1 test fixture
# supplies the complete versioned contract, never an original market event.
from test_aql_f1_decision_capture_v1 import fixture as capture_fixture


def capture_lane(directory, methods):
    directory.mkdir()
    config = fixture(directory)
    config["source"].update(provider="MOCK_QUEUE5", symbol="AAA",
                             source_label="MOCK:QUEUE5", source_version=methods["sha256"])
    config["bindings"].update(
        evaluator_sha256=digest(methods["evaluation"]),
        search_space_sha256=methods["family_sha256"],
        all_attempt_inventory_sha256=digest(methods["trial_report"]),
        risk_exit_sha256=digest("NO_ORDERS_OR_PROMOTION"),
    )
    raw, pin = commit_research_plan(
        "queue5-synthetic", [("fixture-only", methods["family_sha256"])],
        protocol_digest=digest(config["bindings"]), dataset_digest=digest(config["source"]),
        split_digest=digest(config["times"]), metrics=["NO_PROMOTION"],
        selection_rule={"rule": "NO_SELECTION"}, cost_model={"scope": "SYNTHETIC_ONLY"},
        baseline_digest=digest("NO_EXECUTED_OUTCOMES"),
    )
    config.update(plan_raw=raw, plan_sha256=pin)
    (directory / "plan.json").write_bytes(raw)
    seal = directory / "freeze.json"
    freeze = seal_readiness(seal, **config)
    records, admissions = [], []
    previous = None
    for index, opened in enumerate((900_000, 1_800_000)):
        bar = mock_bar(opened, symbol="AAA", source="MOCK:QUEUE5")
        require(commit_mock(config["journal"], bar), "QUEUE5_COMMIT_MISSING")
        admission = admit_sample(seal, **sample_args(config, freeze, bar))
        record, registry = capture_fixture()
        cutoff = admission["commit_return_observed_at_ms"]
        record.update(
            opportunity_id="mock-" + str(index), producer_event_id="mock-event-" + str(index),
            producer_sequence=index, previous_event_sha256=previous,
            experiment_plan_sha256=pin, source_id="MOCK_QUEUE5",
            source_version=methods["sha256"], source_bytes_sha256=admission["content_sha256"],
            source_available_at_ms=admission["available_at_ms"], source_asof_ms=bar.bar_close,
            source_availability_evidence_ref=admission["receipt_sha256"],
            decision_cutoff_ms=cutoff, decision_ms=cutoff, capture_ms=cutoff + 1,
            prefix_start_ms=opened, prefix_end_exclusive_ms=bar.bar_close + 1,
        )
        record["c2_identity"].update(
            opportunity_id=record["opportunity_id"], producer_event_id=record["producer_event_id"])
        record["pair_id"] = capture_digest({
            "experiment_plan_sha256": pin, "c2_identity": record["c2_identity"]})
        record["f1_record_sha256"] = hash_f1(record)
        write_original_candidate(directory / "captures.jsonl", record, registry)
        records.append(record)
        admissions.append(admission)
        previous = record["f1_record_sha256"]
    receipt = validate_capture_chain(records, registry, admissions, methods_receipt=methods)
    return {"records": records, "registry": registry, "admissions": admissions, "receipt": receipt}


def verify(directory):
    verify_methods(directory / "methods")
    methods = json.loads((directory / "methods/methods.json").read_text())
    evidence = json.loads((directory / "readiness.json").read_text())
    check = validate_capture_chain(evidence["records"], evidence["registry"], evidence["admissions"],
                                   methods_receipt=methods)
    require(check == evidence["receipt"], "QUEUE5_REPLAY_DRIFT")
    lane = directory / "first"
    journal = DurableJournal(str(lane / "journal.sqlite"))
    for admission in evidence["admissions"]:
        replayed = admit_sample(
            lane / "freeze.json", expected_freeze_sha256=admission["freeze_sha256"],
            plan_raw=(lane / "plan.json").read_bytes(), journal=journal,
            stable_key=admission["stable_key"], observed_at_ms=admission["observed_at_ms"],
            available_at_ms=admission["available_at_ms"],
            decision_cutoff_ms=admission["commit_return_observed_at_ms"],
        )
        require(replayed == admission, "QUEUE5_COMMITTED_SOURCE_READBACK")
    raw_records = [json.loads(line) for line in (directory / "first/captures.jsonl").read_bytes().splitlines()]
    require(raw_records == evidence["records"], "QUEUE5_CAPTURE_DISK_DRIFT")
    host = inspect_host_claim(json.loads((ROOT / "docs/evidence/queue5-owner-reported-host.json").read_text()))
    require(host == evidence["host"], "QUEUE5_HOST_CLAIM_DRIFT")
    return {"status": "PASS_SYNTHETIC_READINESS_ONLY", "sha256": check["sha256"],
            "real_pit_oos": "AUTHORITY_BLOCKED", "trading_authority": "NONE"}


def produce(directory):
    directory.mkdir(parents=True, exist_ok=False)
    produce_methods(directory / "methods")
    methods = json.loads((directory / "methods/methods.json").read_text())
    evidence = capture_lane(directory / "first", methods)
    repeat = capture_lane(directory / "repeat", methods)
    require(evidence == repeat, "QUEUE5_DETERMINISTIC_CAPTURE")
    rejected = {}

    def reject(name, operation):
        try:
            operation()
        except ValueError as error:
            rejected[name] = str(error)
        else:
            raise ValueError("QUEUE5_ACCEPTED_" + name)

    for name in ("sequence", "source", "lookahead", "custody"):
        records = deepcopy(evidence["records"])
        if name == "sequence":
            records[1]["producer_sequence"] = 3
        elif name == "source":
            records[1]["source_version"] = "foreign-source"
        elif name == "lookahead":
            records[1]["source_available_at_ms"] = records[1]["decision_cutoff_ms"] + 1
        else:
            records[1]["source_bytes_sha256"] = "0" * 64
        records[1]["f1_record_sha256"] = hash_f1(records[1])
        reject(name, lambda records=records: validate_capture_chain(
            records, evidence["registry"], evidence["admissions"], methods_receipt=methods))
    reject("out_of_order", lambda: validate_capture_chain(
        evidence["records"][::-1], evidence["registry"], evidence["admissions"][::-1],
        methods_receipt=methods))
    reject("holdout_peek", lambda: review({}, holdout_requested=True))
    reject("forged_science_grade", lambda: review({}, evidence_grade="INDEPENDENTLY_VERIFIED"))
    evidence["host"] = inspect_host_claim(json.loads(
        (ROOT / "docs/evidence/queue5-owner-reported-host.json").read_text()))
    evidence["rejected"] = rejected
    (directory / "readiness.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return verify(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()

    def forbid_network(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("QUEUE5_NETWORK_FORBIDDEN")

    sys.addaudithook(forbid_network)
    print(json.dumps(verify(args.directory) if args.readback else produce(args.directory), sort_keys=True))
