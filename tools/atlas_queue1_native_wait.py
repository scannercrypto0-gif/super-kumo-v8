"""Run the checked-in Queue 1 synthetic Core/Scanner/Secretary WAIT proof."""

import argparse
from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "aql.integration.queue1.native-wait.v1"
EXPECTED_REJECTIONS = {
    "local_query": "CORE_D_PARENT_SEAL_query_sha256",
    "scanner_c_approval": "FROZEN_DIGEST_DRIFT",
    "secretary_enqueue": "CORE_C_D_GATE_ENQUEUE_POLICY_OR_EXPIRY",
}


def digest(body):
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_simulation_wait(gate, journal):
    from aql.paper_sim.engine import PaperSimulator

    body = {key: value for key, value in gate.items() if key != "gate_sha256"}
    require(digest(body) == gate["gate_sha256"],
            "WAIT_GATE_SEAL_MISMATCH")
    require(gate["decision"] == "WAIT"
            and gate["strategy_secretary_state"] == "NOT_ENQUEUED"
            and gate["factory_consumer_ack_sha256"] is None
            and gate["trading_authority"] == "NONE"
            and gate["orders_created"] == 0, "WAIT_GATE_AUTHORITY_DRIFT")
    before = PaperSimulator(journal).states
    reopened = PaperSimulator(journal)
    require(before == reopened.states == {} and not reopened.journal.ledger.events,
            "WAIT_CHANGED_SIMULATION_STATE")
    return before, reopened.states


def prove_wait(root):
    from research_wp_r0.aql_core_d_canonical_secretary_v1 import enqueue_scanner_d_strategy
    from research_wp_r0.aql_core_d_same_source_route_v1 import (
        verify_scanner_d_for_core_route,
    )
    from tools.scanner_strategy_d.permitted_test_cohort import (
        create_permitted_core_test_cohort,
    )
    from tools.strategy_service_offline.common import Frozen
    FIXTURES = ROOT / "tools/strategy_service_offline/fixtures"

    specs = json.loads((FIXTURES / "strategies.json").read_text(encoding="utf-8"))
    actions = {
        (item["payload"]["strategy_id"], item["payload"]["strategy_version"]): {
            "action": "DENY_TEST_ONLY",
            "approver_id": "INDEPENDENT_TEST_POLICY_FIXTURE",
            "governance_policy_id": "QUEUE_1_TEST_ONLY",
            "approval_nonce": item["payload"]["strategy_id"],
        }
        for item in specs
    }
    core = root / "core"
    vault = root / "vault"
    journal = root / "isolated-simulation.jsonl"
    root.mkdir()
    cohort = create_permitted_core_test_cohort(core, vault, specs, actions)
    handoff = Frozen.restore(cohort["scanner_d_handoff"])
    service = Frozen.restore(handoff.data["scanner_c_canonical_service_receipt"]).data
    routes = service["strategy_route_requests"]
    selected = next(item for item in routes if item["payload"]["scanner_nomination_status"] == "SELECTED")
    request = Frozen.restore(selected).data
    index = next(i for i, spec in enumerate(specs)
                 if spec["payload"]["strategy_id"] == request["strategy_id"])
    run = service["scanner_run"]
    nomination = next(n for n in run["payload"]["nominations"]
                      if n["sha256"] == request["scanner_nomination_sha256"])
    inputs = dict(
        warehouse=cohort["warehouse"],
        native_price_query=cohort["native_price_query"],
        local_query=cohort["local_query"],
        identity_map=cohort["identity_map"],
        core_d_witness=cohort["core_d_issued_witness"],
        scanner_d_handoff=cohort["scanner_d_handoff"],
        scanner_c_request=selected,
        scanner_c_approval=service["strategy_approvals"][index],
        scanner_run=run,
        scanner_nomination=nomination,
        work_spec=specs[index],
        native_policy=service["native15m_policies"][index],
    )
    gate = verify_scanner_d_for_core_route(core, **inputs)
    require(gate["decision"] == "WAIT", "SELECTED_STRATEGY_MUST_WAIT")
    require(gate["strategy_secretary_state"] == "NOT_ENQUEUED"
            and gate["source_ack_sha256"] is None
            and gate["factory_consumer_ack_sha256"] is None
            and gate["scanner_c_governance_action"] == "DENY_TEST_ONLY"
            and gate["trading_authority"] == "NONE"
            and gate["orders_created"] == 0
            and gate["paper_positions"] == 0, "WAIT_AUTHORITY_DRIFT")

    failures = {}
    wrong_source = deepcopy(inputs["local_query"])
    wrong_source["query_sha256"] = "0" * 64
    false_approval = deepcopy(inputs["scanner_c_approval"])
    false_approval["payload"]["governance_action"] = "APPROVE_TEST_ONLY"
    for key, replacement in (("local_query", wrong_source), ("scanner_c_approval", false_approval)):
        try:
            verify_scanner_d_for_core_route(core, **{**inputs, key: replacement})
        except ValueError as error:
            failures[key] = str(error)
        else:
            raise ValueError(f"Accepted invalid {key}")

    try:
        enqueue_scanner_d_strategy(
            core, gate=gate, source_ack=None, source_nomination_sha256=None,
            route_id="queue1-denied", now_ms=gate["cutoff_ms"],
            expires_at_ms=gate["cutoff_ms"] + 60_000,
        )
    except ValueError as error:
        failures["secretary_enqueue"] = str(error)
    else:
        raise ValueError("SECRETARY_ACCEPTED_DENIED_WAIT")

    require(failures == EXPECTED_REJECTIONS, "WAIT_REJECTION_REASON_DRIFT")
    # A denied route must never materialize either canonical outbox table.
    with closing(sqlite3.connect((core / "warehouse.sqlite").as_uri() + "?mode=ro", uri=True)) as con:
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE name IN (?, ?)",
            ("d_canonical_strategy_routes", "d_canonical_strategy_events"),
        ).fetchall()
    require(not tables, "WAIT_CREATED_SECRETARY_OUTBOX")

    before, after = verify_simulation_wait(gate, journal)
    return {
        "gate": gate, "rejected_inputs": failures, "simulation_before": before,
        "simulation_after_reopen": after, "simulation_events": 0,
        "factory_execution": "WITHHELD_PENDING_AUTHORITY", "dispatches": 0,
    }


def run(output):
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        def forbid_network(event, args):
            if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
                raise RuntimeError("QUEUE_1_NETWORK_FORBIDDEN")

        sys.addaudithook(forbid_network)
        first = prove_wait(root / "first")
        second = prove_wait(root / "second")
        require(first == second, "WAIT_REPLAY_DRIFT")
        receipt = {
            "schema": SCHEMA,
            "evidence": "SYNTHETIC_TEST_ONLY",
            "revision": git("rev-parse", "HEAD").decode().strip(),
            "deterministic_replay": True, **first,
        }
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump({**receipt, "receipt_sha256": digest(receipt)}, handle, indent=2, sort_keys=True)
            handle.write("\n")


if __name__ == "__main__":
    sys.path[:0] = [str(ROOT), str(ROOT / "src")]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()
    if args.readback:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        seal = receipt.pop("receipt_sha256")
        require(digest(receipt) == seal and receipt["schema"] == SCHEMA
                and receipt["evidence"] == "SYNTHETIC_TEST_ONLY"
                and receipt["rejected_inputs"] == EXPECTED_REJECTIONS,
                "WAIT_RECEIPT_SEAL_OR_SCOPE_DRIFT")
        require(receipt["revision"] == git("rev-parse", "HEAD").decode().strip(),
                "WAIT_RECEIPT_REVISION_DRIFT")
        require(receipt["deterministic_replay"] is True
                and receipt["simulation_events"] == receipt["dispatches"] == 0,
                "WAIT_RECEIPT_REPLAY_DRIFT")
        with TemporaryDirectory() as scratch:
            before, after = verify_simulation_wait(receipt["gate"], Path(scratch) / "sim.jsonl")
        require(before == receipt["simulation_before"]
                and after == receipt["simulation_after_reopen"], "WAIT_READBACK_DRIFT")
    else:
        run(args.receipt)
