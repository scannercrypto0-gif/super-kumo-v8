"""Synthetic Queue 2 storage plus zero-exposure journal snapshot/recovery drill."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from aql.paper_sim.contracts import Policy  # noqa: E402
from aql.paper_sim.engine import PaperSimulator  # noqa: E402
from research_wp_r0.aql_factory_e_research_results_store_v1 import _check_seal, digest  # noqa: E402
from research_wp_r0.aql_queue3_recovery_v1 import (  # noqa: E402
    create_snapshot, file_sha, require, restore_snapshot, verify_snapshot,
)
from tools.atlas_queue2_dev import produce as produce_queue2, revision  # noqa: E402


def implementation_sources():
    paths = ("research_wp_r0/aql_queue3_recovery_v1.py", "tools/atlas_queue3_recovery.py",
             "src/aql/observation/position_journal.py", "src/aql/observation/positions.py",
             "research_wp_r0/indicator_library.py",
             "src/aql/archive/backup.py", "tools/offline_custody_kit.py")
    return {p: hashlib.sha256((ROOT / p).read_text(encoding="utf-8").encode()).hexdigest()
            for p in paths}


def seed_journal(source, *, instance="queue3-offline-recovery-only"):
    package = json.loads((source / "evidence.json").read_text())["paired_package"]
    schedule = package["schedule"]
    cutoff = schedule["pairs"][0]["opportunity"]["decision_cutoff_ms"]
    signal = {"schema": "aql.paper-sim.signal.v1", "signal_id": digest({"fixture": instance}),
              "strategy_id": "recovery-fixture", "strategy_version": "v1",
              "definition_sha256": schedule["protocol"]["base_definition_sha256"],
              "config_sha256": package["plan_sha256"], "evaluator_sha256": package["code_sha256"],
              "source_sha256": package["cohort_receipt"]["source_zip_sha256"],
              "symbol": "AAA", "interval_ms": 900000, "decision_ms": cutoff,
              "source_close_ms": cutoff - 1, "available_ms": cutoff,
              "evidence_mode": "SYNTHETIC_TESTED", "trading_authority": "NONE"}
    command = {"op": "watch", "at_ms": cutoff, "signal": signal,
               "policy": asdict(Policy()), "instance": instance}
    simulation = PaperSimulator(source / "simulation.jsonl", max_events=2)
    identity = simulation.identity(command)
    simulation.apply(identity, "watch", command)
    simulation.apply(identity, "cancel", {"op": "cancel", "at_ms": cutoff + 1})
    return simulation.states


def negative_checks(snapshot, anchor, pin):
    rejected = {}
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        for name in ("corrupt_database", "truncated_journal", "self_resealed_manifest", "path_traversal"):
            bad = root / name
            shutil.copytree(snapshot, bad)
            external = anchor
            expected = pin
            if name == "corrupt_database":
                data = bytearray((bad / "results.sqlite").read_bytes())
                data[-1] ^= 1
                (bad / "results.sqlite").write_bytes(data)
            elif name == "truncated_journal":
                journal = bad / "simulation.jsonl"
                journal.write_bytes(journal.read_bytes()[:-1])
            else:
                manifest = json.loads((bad / "custody-manifest.json").read_bytes())
                manifest["files"][0]["path"] = "../escape" if name == "path_traversal" else "wrong-name"
                (bad / "custody-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                if name == "path_traversal":
                    expected = file_sha(bad / "custody-manifest.json")
                    external = root / "traversal-anchor.sha256"
                    external.write_text(expected, encoding="ascii")
            target = root / (name + "-restore")
            try:
                restore_snapshot(bad, external, target, expected_manifest_sha256=expected)
            except ValueError as error:
                rejected[name] = str(error)
            else:
                raise ValueError("QUEUE3_ACCEPTED_" + name)
            require(not target.exists(), "INVALID_RESTORE_PUBLISHED")
        for name, expected in (("missing_pin", None), ("wrong_pin", "0" * 64)):
            try:
                verify_snapshot(snapshot, anchor, expected_manifest_sha256=expected)
            except ValueError as error:
                rejected[name] = str(error)
            else:
                raise ValueError("QUEUE3_ACCEPTED_" + name)
    return rejected


def produce(root):
    root.mkdir(parents=True, exist_ok=False)
    source = root / "source"
    produce_queue2(source)
    original_states = seed_journal(source)
    evidence_pin = file_sha(source / "evidence.json")
    journal_pin = file_sha(source / "simulation.jsonl")
    snapshot = root / "snapshot"
    created = create_snapshot(source, snapshot, expected_evidence_sha256=evidence_pin,
                              expected_journal_sha256=journal_pin)
    pin = created["manifest_sha256"]
    anchor = root / "retained-manifest.sha256"
    anchor.write_text(pin + "\n", encoding="ascii")
    verified = verify_snapshot(snapshot, anchor, expected_manifest_sha256=pin)
    require(verified == verify_snapshot(snapshot, anchor, expected_manifest_sha256=pin),
            "VERIFICATION_REPLAY_DRIFT")
    # Explicit filesystem-append crash fixture. Native append crash/lock boundaries
    # are separately covered by the reused #93 subprocess regression suite.
    child = ("import os,sys; f=open(sys.argv[1],'ab'); "
             "f.write(b'{\\\"torn\\\":'); f.flush(); os.fsync(f.fileno()); os._exit(73)")
    crashed = subprocess.run([sys.executable, "-B", "-c", child, str(source / "simulation.jsonl")],
                             capture_output=True, timeout=10)
    require(crashed.returncode == 73, "CRASH_FIXTURE_EXIT")
    damaged_pin = file_sha(source / "simulation.jsonl")
    try:
        PaperSimulator(source / "simulation.jsonl")
    except ValueError:
        pass
    else:
        raise ValueError("QUEUE3_TORN_PRIMARY_ACCEPTED")
    recovered = restore_snapshot(snapshot, anchor, root / "restored", expected_manifest_sha256=pin)
    require(recovered == verified
            and PaperSimulator(root / "restored/simulation.jsonl").states == original_states
            and file_sha(source / "simulation.jsonl") == damaged_pin,
            "RESTORE_STATE_OR_PRIMARY_PRESERVATION")
    body = {"schema": "aql.queue3.recovery-evidence.v1", "revision": revision(),
            "implementation_sources": implementation_sources(), "created": created,
            "verified": verified, "restored": recovered, "manifest_sha256": pin,
            "source_evidence_file_sha256": evidence_pin, "source_journal_sha256": journal_pin,
            "damaged_primary_sha256": damaged_pin, "crash_exit_code": crashed.returncode,
            "negative_rejections": negative_checks(snapshot, anchor, pin),
            "source_class": "SYNTHETIC_FIXTURE_ONLY", "encrypted": False,
            "independent_custody_verified": False, "orders_created": 0,
            "paper_positions": 0, "dispatches": 0, "trading_authority": "NONE"}
    evidence = {**body, "sha256": digest(body)}
    (root / "recovery-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return verify(root)


def verify(root, *, restore_to=None):
    evidence = json.loads((root / "recovery-evidence.json").read_text(encoding="utf-8"))
    _check_seal(evidence)
    require(evidence["revision"] == revision()
            and evidence["implementation_sources"] == implementation_sources(), "EVIDENCE_REVISION")
    result = verify_snapshot(root / "snapshot", root / "retained-manifest.sha256",
                             expected_manifest_sha256=evidence["manifest_sha256"])
    require(result == evidence["verified"] == evidence["restored"]
            and evidence["crash_exit_code"] == 73
            and len(evidence["negative_rejections"]) == 6, "RECOVERY_EVIDENCE_DRIFT")
    if restore_to is not None:
        actual = restore_snapshot(root / "snapshot", root / "retained-manifest.sha256", restore_to,
                                  expected_manifest_sha256=evidence["manifest_sha256"])
        require(actual == result, "CROSS_OS_RESTORE_DRIFT")
    return {"status": "SYNTHETIC_LOCAL_RECOVERY_VERIFIED", "manifest_sha256": evidence["manifest_sha256"],
            "evidence_sha256": evidence["sha256"], "recovery_receipt_sha256": result["sha256"],
            "negative_rejected": 6, "encrypted": False, "independent_custody_verified": False,
            "orders_created": 0, "paper_positions": 0, "dispatches": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--restore-to", type=Path)
    args = parser.parse_args()

    def forbid_network(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("QUEUE3_NETWORK_FORBIDDEN")

    sys.addaudithook(forbid_network)
    result = verify(args.directory, restore_to=args.restore_to) if args.verify else produce(args.directory)
    print(json.dumps(result, sort_keys=True))
