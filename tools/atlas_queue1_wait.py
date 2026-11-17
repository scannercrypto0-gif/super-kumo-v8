"""Run the Queue 1 same-source WAIT scenario against pinned producer code."""

import argparse
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "7d97b09c0c6ee2650a61d523acb8d8c771a99c46": ("tools/raw_vault_offline/",),
    "6acbcc7fc243b132f58170df4c6469bbf7f4eff8": ("tools/strategy_service_offline/",),
    "b9c9ff8602e79c534402f44bce83c56ec2fa6bb9": ("tools/scanner_engine_offline/",),
    "30c37ae56851488b882998c7fa0085ec51dbfc92": ("tools/scanner_strategy_b/",),
    "1659713c80d1934f3c08af1af422b89cd5706360": ("tools/scanner_strategy_c/",),
    "a91e370ae7e5197e9af71f8300eeaff4a7aff022": ("tools/scanner_strategy_d/",),
    "40ad0b4cf3b4b75b8ba55f524e79af3928b0673f": ("research_wp_r0/aql_",),
    "a86a590a5e2c32c18e03522f52896dbcf50c60ff": ("research_wp_r0/aql_core_d_",),
}


def git(*args):
    return subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "-C", str(ROOT), *args]
    )


def stage(destination):
    # Keep the upstream components in a disposable overlay. Record exact Git
    # blobs, including any inherited Core files needed by the selected seam.
    files = {}
    for commit, prefixes in PINS.items():
        paths = {}
        for entry in git("ls-tree", "-rz", commit).split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            name = raw_name.decode()
            if name.startswith(prefixes) and name.endswith((".py", ".json")):
                mode, kind, blob = metadata.decode().split()
                if kind != "blob" or mode not in {"100644", "100755"}:
                    raise ValueError(f"Unsafe source entry: {name}")
                paths[name] = blob
        if not paths:
            raise ValueError(f"No source files at {commit}")
        data = git("archive", "--format=tar", commit, "--", *paths)
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for name, blob in paths.items():
                relative = Path(name)
                member = archive.getmember(name)
                if relative.is_absolute() or ".." in relative.parts or not member.isfile():
                    raise ValueError(f"Unsafe archive entry: {name}")
                content = archive.extractfile(member).read()
                git_bytes = f"blob {len(content)}\0".encode() + content
                if hashlib.sha1(git_bytes).hexdigest() != blob:
                    raise ValueError(f"Source bytes changed: {name}")
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                files[name] = {
                    "commit": commit, "blob": blob,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
    return files


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_simulation_wait(gate, journal):
    from aql.paper_sim.engine import PaperSimulator

    body = {key: value for key, value in gate.items() if key != "gate_sha256"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    require(hashlib.sha256(encoded).hexdigest() == gate["gate_sha256"],
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
    from research_wp_r0.aql_core_d_same_source_route_v1 import (
        verify_scanner_d_for_core_route,
    )
    from tools.scanner_strategy_d.permitted_test_cohort import (
        create_permitted_core_test_cohort,
    )
    from tools.strategy_service_offline.common import Frozen
    from tools.strategy_service_offline.run import FIXTURES

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

    before, after = verify_simulation_wait(gate, journal)
    return {
        "gate": gate, "rejected_inputs": failures, "simulation_before": before,
        "simulation_after_reopen": after, "simulation_events": 0,
        "factory_execution": "WITHHELD_PENDING_AUTHORITY", "dispatches": 0,
    }


def run(output):
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        overlay = root / "overlay"
        files = stage(overlay)
        sys.path[:0] = [str(overlay), str(ROOT), str(ROOT / "src")]
        import research_wp_r0
        import tools

        research_wp_r0.__path__.insert(0, str(overlay / "research_wp_r0"))
        tools.__path__ = [str(overlay / "tools"), *tools.__path__]

        def forbid_network(event, args):
            if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
                raise RuntimeError("QUEUE_1_NETWORK_FORBIDDEN")

        sys.addaudithook(forbid_network)
        first = prove_wait(root / "first")
        second = prove_wait(root / "second")
        require(first == second, "WAIT_REPLAY_DRIFT")
        receipt = {
            "schema": "aql.integration.queue1.wait.v1",
            "evidence": "SYNTHETIC_TEST_ONLY",
            "revision": git("rev-parse", "HEAD").decode().strip(),
            "files": files, "deterministic_replay": True, **first,
        }
        with output.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()
    if args.readback:
        sys.path.insert(0, str(ROOT / "src"))
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
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
