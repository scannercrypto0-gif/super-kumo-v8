"""One joined synthetic acceptance; all component test suites remain external evidence."""
from contextlib import closing
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def save(path, value):
    path.write_bytes(canonical(value))


def read(path):
    return json.loads(path.read_bytes())


def rejects(call, reason):
    try:
        call()
    except ValueError as exc:
        assert reason in str(exc), str(exc)
    else:
        raise AssertionError("Missing rejection: " + reason)


def scanner(root):
    from tools.atlas_scanner_p0_receivers import ResearchReceivers
    from tools.scanner_strategy_f import p0_slice as p
    from tools.scanner_strategy_f.p0_delivery import Store
    from tools.scanner_strategy_f.test_p0_slice import ORIGIN, STEP, custody, plugin, request, schedule
    from research_wp_r0.aql_core_backbone_local_v1 import query_local

    core = root / "core"
    source, strategy = custody(core), plugin()
    plan = schedule(source, [strategy])
    now = ORIGIN + STEP
    outbox = Store(root / "outbox", plan, plan["sha256"])
    receiver = ResearchReceivers(root / "receivers", outbox, plan["sha256"])
    decision = outbox.poll(now, [strategy], {"BTCUSDT": (source, core)},
                          {"BTCUSDT": [request(strategy)]})["rows"][0]
    assert decision["state"] == "ENTRY_SIGNAL" and decision["known_at"] is None

    def lost_ack():
        raise OSError("ACK lost after COMMIT")

    assert outbox.deliver(now, lambda doc: receiver.receive(doc, now), fault=lost_ack) == "PENDING"
    outbox = Store(root / "outbox", plan, plan["sha256"])
    receiver = ResearchReceivers(root / "receivers", outbox, plan["sha256"])
    retry = now + 1000
    for _ in range(2):
        assert outbox.deliver(retry, lambda doc: receiver.receive(doc, retry)) == "ACKED_FIXTURE"
    assert outbox.deliver(retry, lambda _: None) == "IDLE"
    unknown = outbox.poll(now + STEP, [strategy], {"BTCUSDT": (None, None)}, {})["rows"][0]
    assert unknown["state"] == "UNKNOWN"
    census = receiver.record_census()
    assert census == receiver.record_census()

    proof = {}
    for route, expected in (("secretary", 3), ("lab", 1)):
        with closing(sqlite3.connect(receiver.root / (route + ".sqlite"))) as db:
            records = [(json.loads(body), json.loads(receipt)) for body, receipt in
                       db.execute("SELECT body,receipt FROM effects ORDER BY id")]
        assert len(records) == expected
        proof[route] = records
    with outbox.tx() as db:
        acks = [json.loads(raw) for raw, in db.execute("SELECT ack FROM outbox ORDER BY id")]
        (raw,) = db.execute("SELECT raw FROM batches").fetchone()
    batch = json.loads(raw)
    native = p.native.verify_factory_signal_batch(batch).data
    assert native["trading_authority"] == "NONE" and not native["cost_or_pnl_computed"]
    assert decision["native_batch_sha256"] == batch["sha256"]
    for ack in acks:
        assert any(receipt["effect_sha256"] == ack["effect_sha256"]
                   for _, receipt in proof[ack["route"].lower()])

    # A later immutable query supplies outcome marks from the same synthetic Core source.
    end = now + 5 * STEP
    query = query_local(core, source["dataset_id"], source["version"], now, end, end,
                        required_source_sha256=source["source_bytes_sha256"], sqlite_immutable=True)
    assert query["source_bytes_sha256"] == source["source_bytes_sha256"]
    assert query["manifest_integrity_sha256"] == source["manifest_sha256"]
    bars = [dict(at=row["bar_open_ms"], **{k: str(row[k]) for k in ("open", "high", "low", "close")})
            for row in query["bars"]]
    assert [bar["at"] for bar in bars] == list(range(now, end, STEP))
    save(root / "scanner.json", dict(source=source, decision=decision, unknown=unknown,
                                    native_batch_sha256=batch["sha256"], proof=proof, acks=acks,
                                    outcome_query_sha256=query["query_sha256"], bars=bars))


def factory(root):
    from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
    from research_wp_r0.aql_factory_lab_shadow_v1 import TABLE, digest as native_digest, run

    inputs = read(root / "scanner.json")
    decision, unknown, bars = (inputs[key] for key in ("decision", "unknown", "bars"))
    monitor, lab_receipt = inputs["proof"]["lab"][0]
    source = inputs["source"]
    secretary_receipt = next(receipt for body, receipt in inputs["proof"]["secretary"]
                             if body == decision and receipt["disposition"] == "RESEARCH_ONLY")
    assert monitor["decision_sha256"] == decision["sha256"]
    assert monitor["source_query_sha256"] == decision["source_query_sha256"]
    assert decision["source_sha256"] == source["sha256"] and unknown["source_sha256"] == source["sha256"]
    for body, receipt in [(monitor, lab_receipt), (decision, secretary_receipt)]:
        assert digest({k: v for k, v in body.items() if k != "sha256"}) == receipt["body_sha256"]
        assert digest({k: v for k, v in receipt.items() if k != "sha256"}) == receipt["sha256"]
    fixture = runpy.run_path("tests/test_aql_factory_lab_shadow_v1.py")
    dossier, protocol, cohort, attachments = fixture["fixture"]()
    reseal = fixture["reseal"]
    step, at = protocol["step_ms"], decision["cutoff"]
    baseline = protocol["baseline_exit"]
    baseline["policy"] |= {"risk": ".01", "targets": ["1"]}
    protocol = reseal(protocol, train=[at-21*step, at-17*step], validation=[at-13*step, at-9*step],
                      frozen_at=at-8*step, evaluation=[at-step, at+5*step], holdout=[at+9*step, at+13*step])

    def attach(body):
        key = native_digest(body)
        attachments[key] = body
        return key

    lineage = dict(core=source, decision=decision, secretary=secretary_receipt,
                   lab=lab_receipt, outcome_query_sha256=inputs["outcome_query_sha256"])
    dossier = reseal(dossier, protocol_sha256=protocol["sha256"],
                     decision_sha256=attach(dict(mode="DECISION", receipt=decision, ack=secretary_receipt)),
                     monitor_sha256=attach(dict(mode="MONITOR_ONLY", receipt=monitor, ack=lab_receipt)),
                     dependencies_sha256=attach(lineage))
    selected, missing = decision["id"], unknown["id"]
    source_pin = native_digest(lineage)
    cohort = reseal(cohort, source_sha256=source_pin, universe=[selected, missing],
                    attempts=[dict(attempt_id=key, candidate_id=key, source_receipt_sha256=source_pin,
                                   state=state) for key, state in ((selected, "SELECTED"), (missing, "UNKNOWN"))],
                    entries=[dict(id=selected, attempt_id=selected, signal_at=at, entry_at=at+step,
                                  price=bars[1]["open"], maker_fraction=None, bars=bars[1:])])
    store = root / "factory.sqlite"
    migrate_store_v2(store)
    args = dict(expected_protocol=protocol["sha256"], expected_dossier=dossier["sha256"],
                expected_cohort=cohort["sha256"], attachments=attachments)
    result = run(dossier, protocol, cohort, store, **args)
    assert result["admission"]["state"] == "ADMITTED", result["admission"]
    repeated = run(dossier, protocol, cohort, store, **args)
    assert all(result[k] == repeated[k] for k in ("admission", "evaluation", "handoff"))
    with closing(sqlite3.connect(store)) as db:
        assert db.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0] == 2
    assert result["evaluation"]["source_sha256"] == source_pin
    assert result["handoff"]["receipts"]["dossier_sha256"] == dossier["sha256"]
    assert any(row["status"] == "UNKNOWN_DECISION" and row["net"] is None
               for row in result["evaluation"]["baseline"]["TAKER"]["rows"])
    taker = next(row for row in result["evaluation"]["baseline"]["TAKER"]["rows"]
                 if row["opportunity_id"] == selected)
    assert taker["net"] is not None
    assert Decimal(taker["gross"]) - Decimal(taker["cost_bps"]) / 10000 == Decimal(taker["net"])
    tampered = reseal(cohort, source_sha256="f" * 64)
    source_denied = run(dossier, protocol, tampered, store, **(args | {"expected_cohort": tampered["sha256"]}))
    assert any("ATTEMPT_SOURCE" in reason for reason in source_denied["admission"]["reasons"]) and source_denied["handoff"] is None
    wrong = attachments | {dossier["monitor_sha256"]: dict(mode="DECISION")}
    denied = run(dossier, protocol, cohort, store, **(args | {"attachments": wrong}))
    assert denied["admission"]["state"] == "RETURN_TO_LAB" and denied["handoff"] is None
    assert any("ATTACHMENT_PIN" in reason for reason in denied["admission"]["reasons"])
    save(root / "factory.json", dict(result=result["handoff"], evaluation_sha256=result["evaluation"]["sha256"],
                                    source_sha256=source_pin, lineage=lineage, rejected=denied["admission"],
                                    source_rejected=source_denied["admission"]))


def paper(root):
    from aql.paper_sim.engine import PaperSimulator
    from aql.promotion import Lifecycle, assess_factory, dashboard, read_factory_receipt, seal

    f = read(root / "factory.json")
    receipt = read_factory_receipt(canonical(f["result"]))
    pin = receipt["sha256"]
    shadow, exits = receipt["shadow"], receipt["exit_families"]
    at = f["lineage"]["decision"]["cutoff"] + 5 * 900_000
    policy = seal(dict(schema="aql.promotion.protocol.v1", strategy_id=shadow["id"],
                       strategy_version=str(shadow["version"]), shadow_id=receipt["experiment_id"],
                       category=receipt["category"], code_sha256=shadow["code_sha256"],
                       config_sha256=shadow["parameters_sha256"], protocol_sha256=receipt["protocol_sha256"],
                       costs_sha256=receipt["costs_sha256"], shadow_until_ms=at+60000, source_max_age_ms=1000,
                       applicability={k: v["applicable"] for k, v in exits.items()},
                       exclusions={k: v["reason"] for k, v in exits.items() if not v["applicable"]}))
    args = dict(factory_pin=pin, policy=policy, policy_pin=policy["sha256"], evidence={}, evidence_pins={}, at_ms=at)
    assessment = assess_factory(receipt, **args)
    rejects(lambda: assess_factory(receipt | {"evidence_grade": "ORIGINAL_PIT_OOS"}, **args), "PROMOTION_PIN")
    assert assessment["factory_sha256"] == pin and assessment["paper"] == "PAPER_BLOCKED"
    assert all(row["status"] == "UNKNOWN" for row in assessment["scenarios"].values())
    path, sim_path = root / "lifecycle", root / "simulator"
    manager = Lifecycle(path, assessment, assessment_pin=assessment["sha256"])
    simulator = PaperSimulator(sim_path)
    rejects(lambda: manager.apply("activate", dict(op="simulate_activation", at_ms=at,
                                                  proof="DISPOSABLE_TEST_ONLY")), "ACTIVATION_DENIED")
    rejects(lambda: manager.apply_simulated(simulator, "none", "stale", {"at_ms": at+2000},
                                           source_at_ms=at, source_valid=False), "SIMULATION_INACTIVE")
    rejects(lambda: manager.apply("retire", dict(op="retire", at_ms=at+2000, proof=None)),
            "OWNER_APPROVAL_REQUIRED")
    view = dashboard(manager, simulator, as_of_ms=at+2000)
    assert view["status"] == "PAPER_BLOCKED" and view["assessment_sha256"] == assessment["sha256"]
    assert view["closed_trades"] == 0 and view["freshness"] == "UNKNOWN"
    assert view["actual_execution"] == "NONE" and view["realized_net"] is None
    assert not sim_path.exists()
    restored = Lifecycle(path, assessment, assessment_pin=assessment["sha256"])
    assert dashboard(restored, PaperSimulator(sim_path), as_of_ms=at+2000) == view
    save(root / "dashboard.json", dict(assessment=assessment, dashboard=view,
                                      safety="PRE_ACTIVATION_DENIAL", retirement="UNAUTHORIZED_DENIED"))


def main():
    if len(sys.argv) == 3:
        globals()[sys.argv[1]](Path(sys.argv[2]))
        return
    output, scanner_root, factory_root, paper_root = map(lambda x: Path(x).resolve(), sys.argv[1:])
    output.mkdir()
    receipts = []
    for label in ("first", "second"):
        root = output / label
        root.mkdir()
        for role, cwd, paths in (("scanner", scanner_root, [scanner_root / "src", scanner_root]),
                                  ("factory", factory_root, [factory_root]),
                                  ("paper", paper_root, [paper_root / "src", paper_root])):
            env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, paths)))
            if role == "scanner":
                env["PYTHONPATH"] += os.pathsep + os.environ.get("ATLAS_PYTEST_PATH", "")
            subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), role, str(root)],
                           cwd=cwd, env=env, check=True, timeout=120)
        receipts.append({role: digest(read(root / (role + ".json"))) for role in ("scanner", "factory", "dashboard")})
    assert receipts[0] == receipts[1]
    summary = dict(replays=receipts, input="TEST_ONLY", active_paper=False, provider_calls=0,
                   result="BLOCKED_EXACT_TEST_ONLY_HANDOFF_CANNOT_ACTIVATE_PAPER")
    save(output / "summary.json", summary)
    print(json.dumps(summary, sort_keys=True))
    print("JOIN_PROOF_SHA256=" + digest(summary))


if __name__ == "__main__":
    main()
