"""One-command actual-component offline integration and process-death proof.

No network/real observer paths. All data, time, capacities and fills below are
declared synthetic assumptions. Every upstream import comes from immutable
Git blobs in a fresh disposable overlay, not a mock replacement component.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid
from unittest.mock import patch

from atlas_pkg03_stage import digest, stage, verify


def save(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def hashes(root):
    # Read-only WAL readers can update volatile SHM lock/cache metadata.
    # Bind durable DB bytes and nonempty WAL, not ephemeral shared-memory locks.
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).glob("*.sqlite*"))
            if p.name.endswith(".sqlite") or (p.name.endswith("-wal") and p.stat().st_size > 0)}


def deny_network(*args, **kwargs):
    raise RuntimeError("PKG03_NETWORK_FORBIDDEN")


def source(root, overlay, *, readonly):
    from aql.journal.durable_journal import DurableJournal
    from aql.storage.operational_store import OperationalStore
    from aql.observation.prospective import ProspectiveObserver

    fixture = json.loads((overlay / "tools/strategy_service_offline/fixtures/strategies.json").read_text(encoding="utf-8"))[0]
    with patch("aql.journal.durable_journal.uuid.uuid4", return_value=uuid.UUID("03" * 16)):
        journal = DurableJournal(str(root / "g1.sqlite"))
    store = OperationalStore(str(root / "store.sqlite"))
    observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture,
                                   synthetic=True, read_only=readonly)
    return journal, store, observer


def prepare(root, overlay):
    from aql.foundation.readiness import assess, FeatureRequirement
    from aql.models.bar import MarketBar
    from aql.observation.forward_evidence import read_forward_evidence
    from aql.observation.prospective import STEP
    from aql.paper_sim.adapter import signals_from_prospective
    from aql.paper_sim.contracts import Policy
    from aql.paper_sim.engine import PaperSimulator

    root.mkdir()
    journal, store, observer = source(root, overlay, readonly=False)
    # 24 finalized 15m bars. Synthetic UTC and journal identity are injected
    # only for reproducibility; never claim external clock/PIT provenance.
    bars = []
    for i in range(24):
        opening = i * STEP
        close = opening + STEP - 1
        bar = MarketBar("BTCUSDT", "15m", opening, close, 101., 102., 100., 101.,
                        10., True, "binance_ws", close + 1).with_checksum()
        with patch("time.time", return_value=(close + 3) / 1000):
            journal.commit(bar)
            store.upsert(bar)
            journal.mark_persisted(bar.stable_key())
        now = close + 4
        readiness = assess(journal, store, symbol="BTCUSDT", interval="15m", opens=[opening],
                           requirements=[FeatureRequirement("close", "v1", 1)],
                           available_versions={"close": "v1"}, decision_ms=now,
                           clock_verified=True, interval_ms=STEP)
        assert readiness["ready"], readiness
        with patch("aql.observation.prospective.time_ns", return_value=now * 1_000_000):
            observer.tick()
        bars.append(bar)
    # Writer is closed conceptually. Current-head #289 must accept only a
    # read-only G2 consumer for the actual finalized-horizon report.
    journal, store, reader = source(root, overlay, readonly=True)
    before = hashes(root)
    forward = read_forward_evidence(reader, as_of_ms=now)
    read = reader.verified_read(as_of_ms=now)
    earlier = reader.verified_read(as_of_ms=4 * STEP + 3)
    assert len(earlier["rows"]) == 4 and all(r["decision"]["cutoff_ms"] <= 4 * STEP + 3 for r in earlier["rows"])
    projected = signals_from_prospective(read, expected_sha=read["sha256"],
                                        expected_run=reader.identity, as_of_ms=now)
    assert hashes(root) == before, "READ_ONLY_SOURCE_MUTATED"
    assert len(read["rows"]) == 24 and sum(projected["census"].values()) == 24
    assert projected["signals"] and projected["horizon_values_used"] is False
    assert any(w["state"] == "mature" for r in forward["rows"] for w in r["windows"])
    assert all(w["state"] == "pending" for r in forward["rows"] for w in r["windows"] if w["horizon_ms"] == 259200000)
    signal = projected["signals"][0]
    first = (signal["decision_ms"] // STEP + 1) * STEP
    following = [b for b in bars if b.bar_open >= first][:2]
    assert len(following) == 2
    commands = []
    watch = dict(op="watch", at_ms=signal["decision_ms"], signal=signal,
                 policy=asdict(Policy()), instance="pkg03-synthetic-integration")
    sid = PaperSimulator.identity(watch)
    commands.append(["watch", watch])
    commands.append(["arm", dict(op="arm", at_ms=signal["decision_ms"] + 1, mode="taker",
                                qty="1", limit="101", stop="95", target="102",
                                expiry_ms=first + 2 * STEP - 1, queue_ahead="0")])
    # Same G1 finalized bars, with explicit synthetic liquidity assumptions;
    # no venue fills and no use of G2 horizon extrema as decision inputs.
    for i, b in enumerate(following):
        candle = dict(symbol=b.symbol, open_ms=b.bar_open, close_ms=b.bar_close,
                      received_ms=b.ingested_at, open=str(b.open), high=str(b.high),
                      low=str(b.low), close=str(b.close), final=b.is_final,
                      clock_verified=True, synthetic=True, taker_qty="10", maker_volume="10")
        commands.append(["bar" + str(i), dict(op="bar", at_ms=b.ingested_at, bar=candle)])
    # The first bar reaches the frozen target and produces two assumed fills.
    # Crash immediately after its durable commit, before in-memory ACK.
    commands = commands[:3]
    save(root / "commands.json", {"sid": sid, "commands": commands})
    save(root / "g2-read.json", read)
    save(root / "g2-forward.json", forward)
    save(root / "projection.json", projected)
    save(root / "source-hashes.json", before)
    save(root / "readiness.json", readiness)


def crash(root):
    from aql.paper_sim.engine import PaperSimulator

    plan = json.loads((root / "commands.json").read_text(encoding="utf-8"))
    sim = PaperSimulator(root / "simulation.jsonl")
    for command_id, command in plan["commands"][:-1]:
        sim.apply(plan["sid"], command_id, command)
    sim = PaperSimulator(root / "simulation.jsonl", post_commit=lambda: os._exit(73))
    command_id, command = plan["commands"][-1]
    sim.apply(plan["sid"], command_id, command)
    raise AssertionError("CRASH_HOOK_NOT_EXECUTED")


def replay(root, overlay):
    from aql.observation.forward_evidence import read_forward_evidence
    from aql.paper_sim.adapter import signals_from_prospective
    from aql.paper_sim.engine import PaperSimulator
    from aql.paper_sim.contracts import digest as sim_digest
    from aql.observation.contracts import digest as g2_digest

    plan = json.loads((root / "commands.json").read_text(encoding="utf-8"))
    read = json.loads((root / "g2-read.json").read_text(encoding="utf-8"))
    expected_hashes = json.loads((root / "source-hashes.json").read_text(encoding="utf-8"))
    sim = PaperSimulator(root / "simulation.jsonl")
    before = (root / "simulation.jsonl").read_bytes()
    recovered = sim.states
    for command_id, command in plan["commands"]:
        sim.apply(plan["sid"], command_id, command)
    assert (root / "simulation.jsonl").read_bytes() == before and sim.states == recovered
    state = sim.states[plan["sid"]]
    assert state["phase"] == "CLOSED" and len(state["fills"]) == 2
    assert state["trading_authority"] == "NONE"
    assert len(sim.journal.ledger.events) == len(plan["commands"]) == 3
    _, _, observer = source(root, overlay, readonly=True)
    forward = read_forward_evidence(observer, as_of_ms=read["as_of_ms"])
    assert forward == json.loads((root / "g2-forward.json").read_text(encoding="utf-8"))
    assert observer.verified_read(as_of_ms=read["as_of_ms"]) == read
    assert hashes(root) == expected_hashes
    rejected = []

    def reject(name, fn):
        old = (root / "simulation.jsonl").read_bytes()
        try:
            fn()
        except (ValueError, RuntimeError) as exc:
            rejected.append({"case": name, "reason": str(exc)})
        else:
            raise AssertionError("NEGATIVE_ACCEPTED:" + name)
        assert (root / "simulation.jsonl").read_bytes() == old

    for name, mutate in (
        ("receipt_tamper", lambda x: x.update(visible_sha256="0" * 64)),
        ("source_revision", lambda x: x["rows"][0].update(source_valid=False)),
        ("future_cutoff", lambda x: x["rows"][0]["decision"].update(cutoff_ms=x["as_of_ms"] + 1)),
        ("forged_live_scope", lambda x: x["run"].update(evidence_mode="PUBLIC_WS_OBSERVATION")),
    ):
        changed = json.loads(json.dumps(read))
        mutate(changed)
        if name != "receipt_tamper":
            for row in changed["rows"]:
                row["decision_sha256"] = g2_digest(row["decision"])
            changed["visible_sha256"] = g2_digest(changed["rows"])
            changed["sha256"] = g2_digest({k: v for k, v in changed.items() if k != "sha256"})
        reject(name, lambda d=changed: signals_from_prospective(
            d, expected_sha=d["sha256"], expected_run=d["run"], as_of_ms=d["as_of_ms"]))
    # Negative bars need a fresh ARMED simulation; do not rely on a terminal
    # state to reject malformed/future/provisional/gapped inputs.
    badsim = PaperSimulator(root / "negative.jsonl")
    for cid, cmd in plan["commands"][:2]:
        badsim.apply(plan["sid"], cid, cmd)
    bad_before = (root / "negative.jsonl").read_bytes()
    for name, changes in (("provisional_bar", {"final": False}),
                          ("future_bar", {"received_ms": 999999999}),
                          ("unverified_clock", {"clock_verified": False}),
                          ("foreign_source_symbol", {"symbol": "ETHUSDT"})):
        command = json.loads(json.dumps(plan["commands"][-1][1]))
        command["bar"].update(changes)
        reject(name, lambda c=command, n=name: badsim.apply(plan["sid"], n, c))
        assert (root / "negative.jsonl").read_bytes() == bad_before
    skipped = json.loads(json.dumps(plan["commands"][-1][1]))
    skipped["at_ms"] += 900000
    for field in ("open_ms", "close_ms", "received_ms"):
        skipped["bar"][field] += 900000
    reject("skipped_first_eligible_bar", lambda: badsim.apply(plan["sid"], "gap", skipped))
    assert (root / "negative.jsonl").read_bytes() == bad_before
    changed = dict(plan["commands"][0][1], instance="conflicting")
    reject("duplicate_command_conflict", lambda: sim.apply(plan["sid"], "watch", changed))
    # A whole process died after durable commit; neither journal was edited,
    # reset, truncated or repaired to make recovery pass.
    windows = Counter(w["state"] for r in forward["rows"] for w in r["windows"])
    result = {"schema": "aql.integration.pkg03.offline-result.v1",
              "status": "PASS_ENGINEERING_INTEGRATED_OFFLINE", "source_read_sha256": read["sha256"],
              "forward_sha256": forward["sha256"], "g1_source_unchanged": hashes(root) == expected_hashes,
              "decision_census": json.loads((root / "projection.json").read_text())["census"],
              "simulation_population": {"signals_projected": len(json.loads((root / "projection.json").read_text())["signals"]),
                                        "simulations_run": 1, "selection": "FIRST_CAUSAL_ENTRY_BOUNDED_SMOKE_NOT_PERFORMANCE_SELECTION"},
              "synthetic_horizon_census": dict(windows), "real_4_24_72_horizons": "NOT_OBSERVED_BY_THIS_RUN",
              "process_death_exit": 73, "replayed_events": len(sim.journal.ledger.events),
              "duplicate_retries": len(plan["commands"]), "assumed_fills": len(state["fills"]),
              "duplicate_fills": 0, "skipped_commands": 0, "simulation_state_sha256": sim_digest(state),
              "simulation_journal_sha256": hashlib.sha256(before).hexdigest(),
              "negatives": rejected, "negative_count": len(rejected),
              "model": "SYNTHETIC_TIME_UUID_DEPTH_AND_ASSUMED_EXECUTION",
              "component_calls": {"g1_finalized_commit_and_store": 24, "g1_assess": 24,
                                  "actual_prospective_observer_ticks": 24,
                                  "g2_readonly_forward_consumer": 2,
                                  "g3_durable_commands": 3, "earlier_asof_rows": 4},
              "historical_pit": "NOT_ATTESTED", "independent_custody": "NOT_ATTESTED",
              "stage_signoff": "NOT_GRANTED", "trading_authority": "NONE"}
    save(root / "result.json", {**result, "sha256": digest(result)})


def worker(mode, root, overlay, expected_sha):
    # Source hashes are checked before imports; imports are required to come
    # from this isolated overlay, never a globally installed editable checkout.
    verify(overlay, expected_sha=expected_sha)
    sys.path[:0] = [str(overlay / "src"), str(overlay)]
    with patch.object(socket.socket, "connect", deny_network), patch.object(socket, "create_connection", deny_network):
        {"prepare": lambda: prepare(root, overlay), "crash": lambda: crash(root),
         "replay": lambda: replay(root, overlay)}[mode]()
    provenance = {}
    modules = ("aql.journal.durable_journal", "aql.foundation.readiness", "tools.scanner_strategy_f.research_strategy_plugin",
               "aql.observation.prospective", "aql.observation.forward_evidence", "aql.paper_sim.engine")
    for name in modules:
        module = sys.modules.get(name)
        if module is not None:
            assert overlay.resolve() in Path(module.__file__).resolve().parents, "IMPORT_ESCAPED_OVERLAY"
            relative = Path(module.__file__).resolve().relative_to(overlay.resolve()).as_posix()
            provenance[name] = {"path": relative, "sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}
    save(root / (mode + "-component-provenance.json"), provenance)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--worker", choices=("prepare", "crash", "replay"))
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--manifest-sha")
    args = parser.parse_args()
    if args.worker:
        if args.manifest_sha is None:
            raise ValueError("PKG03_EXPECTED_MANIFEST_REQUIRED")
        worker(args.worker, args.output.resolve(), args.overlay.resolve(), args.manifest_sha)
        return
    root = args.output.resolve()
    if root.exists():
        raise ValueError("PKG03_OUTPUT_MUST_BE_NEW")
    root.mkdir(parents=True)
    overlay, run = root / "overlay", root / "run"
    manifest = stage(args.repo, overlay, fetch=args.fetch)
    events = []
    for mode, expected in (("prepare", 0), ("crash", 73), ("replay", 0)):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        process = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                  "--worker", mode, "--output", str(run), "--overlay", str(overlay),
                                  "--manifest-sha", manifest["sha256"]],
                                 cwd=overlay, env=env, capture_output=True, text=True)
        events.append({"mode": mode, "returncode": process.returncode})
        if process.returncode != expected:
            save(root / "failure.json", {"phase": mode, "stdout": process.stdout, "stderr": process.stderr})
            raise RuntimeError("PKG03_WORKER_FAILED:" + mode + "\n" + process.stderr)
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((run / "prepare-component-provenance.json").read_text(encoding="utf-8"))
    for row in provenance.values():
        expected = manifest["files"][row["path"]]
        assert row["sha256"] == expected["sha256"], "COMPONENT_PROVENANCE_DRIFT"
        row.update(role=expected["role"], commit=expected["commit"])
    body = {"schema": "aql.integration.pkg03.delivery.v1", "pins": manifest["pins"],
            "combined_overlay_sha256": manifest["combined_tree_sha256"], "processes": events,
            "actual_component_provenance": provenance,
            "result": result, "external_probe_repeated": False,
            "accepted_g1_external_receipt_reference": "https://github.com/scannercrypto0-gif/super-kumo-v8/issues/205#issuecomment-6760701161",
            "observer_readback_reference": "https://github.com/scannercrypto0-gif/super-kumo-v8/pull/271#issuecomment-6764652288",
            "owner_host_readback": "NOT_ACCESSED_NO_LATER_REAL_MATURITY_ASSERTED"}
    save(root / "delivery.json", {**body, "sha256": digest(body)})
    print(json.dumps({"status": result["status"], "combined_overlay_sha256": manifest["combined_tree_sha256"],
                      "result_sha256": result["sha256"], "output": str(root / "delivery.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
