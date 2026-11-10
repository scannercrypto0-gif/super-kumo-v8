"""G4 integration evidence only. Generated input, no market or broker access."""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from unittest.mock import patch

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest, migrate_store_v2
from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import (
    COST_SCHEMA, SCHEMA, run_factory_h_generic_research,
)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
from tools.scanner_strategy_f import research_strategy_plugin as scanner
from tools.scanner_strategy_f.test_research_strategy_plugin import START, synthetic_query
from tools.strategy_discoverer_offline.ledger import AttemptState, DiscovererLedger
from tools.strategy_discoverer_offline.synthetic_scanner_candidate_bridge import (
    project_test_only_candidate, verify_test_only_candidate_binding,
)
from tools.strategy_discoverer_offline.tests.test_d_scan_1_candidate_bridge import case

STEP = 900000
EMBARGO = 72 * 3600000
SOURCE_PINS = {
    "main": "90af9794880cbeb00e7e974bfa906ff5e9666183",
    "factory": "04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf",
    "scanner": "ccf57ad3db7e71290a8321840e800136567e3af4",
    "discoverer": "711fd97a65e3bcc37695ec3f33ce3a97772ee8fd",
    "core_fixture_interface": "59510d302e7bb97a63e3d9603b9fb9f81f8f378a",
    "scanner_b": "30c37ae56851488b882998c7fa0085ec51dbfc92",
    "work235": "6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
}
PHASES = {"train": 0, "validation": 65 * STEP, "synthetic_oos": 130 * STEP + EMBARGO}
ARMS = {"BASE": 1, "SHADOW": 3, "PLACEBO": 1}
PLAN = [(p, a) for p in PHASES for a in ARMS] + [("validation", "MISSING_CONTROL")]


def seal(body):
    return {**body, "sha256": digest(body)}


def save(path, data):
    with path.open("x", encoding="utf-8") as out:
        json.dump(data, out, indent=2, sort_keys=True)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())


def query(phase, missing=False):
    q = synthetic_query(n=64, missing_index=7 if missing else None)
    offset = PHASES[phase]
    for k in ("start_ms", "end_exclusive_ms", "decision_cutoff_ms"):
        q[k] += offset
    q["missing_bar_opens"] = [t + offset for t in q["missing_bar_opens"]]
    for b in q["bars"]:
        i = (b["bar_open_ms"] - START) // STEP
        px = round(101 + i / 100, 2)
        for k in ("bar_open_ms", "bar_close_ms", "observation_lower_bound_ms"):
            b[k] += offset
        b.update(open=px, close=px, high=round(px + .05, 2), low=round(px - .05, 2))
        b["bar_checksum"] = digest({k: v for k, v in b.items() if k != "bar_checksum"})
    q["dataset_id"] = "TEST-ONLY-G4-" + phase + ("-MISSING" if missing else "")
    q["source_bytes_sha256"] = digest(q["bars"])
    q["manifest_integrity_sha256"] = digest([q["dataset_id"], q["source_bytes_sha256"]])
    q["query_sha256"] = digest({k: v for k, v in q.items() if k != "query_sha256"})
    return q


def cost(bps):
    fields = {f"{name}_{leg}_bps": str(bps)
              for name in ("fee", "spread", "slippage") for leg in ("entry", "exit")}
    return seal(dict(schema=COST_SCHEMA, costs={**fields, "funding_bps_per_bar": "0"},
                     market="SPOT", direction="LONG", scenario_class="SYNTHETIC_TEST_EXPLICIT",
                     owner_operator_authorized=False,
                     fill_semantics="NEXT_ELIGIBLE_OPEN_UNKNOWN_ON_INTRABAR_TOUCH",
                     holdout="SEALED_UNOPENED", trading_authority="NONE"))


def register():
    candidate, nomination = case()
    plugin, binding = project_test_only_candidate(candidate_package=candidate,
                                                 synthetic_nomination=nomination)
    query_pins = {}
    for phase, arm in PLAN:
        q = query(phase, arm == "MISSING_CONTROL")
        query_pins[f"{phase}/{arm}"] = {k: q[k] for k in
            ("query_sha256", "source_bytes_sha256", "start_ms", "end_exclusive_ms", "decision_cutoff_ms")}
    return seal(dict(schema="aql.g4.synthetic.wp03.registration.v1",
                     code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     dependency_heads=SOURCE_PINS, candidate=candidate, nomination=nomination,
                     binding=binding, plugin=plugin, query_pins=query_pins, embargo_ms=EMBARGO,
                     arms={a: cost(b) for a, b in {**ARMS, "MISSING_CONTROL": 1}.items()},
                     hypothesis="Same gross paths; SHADOW subtracts 12 additional bps; PLACEBO null.",
                     selection="FIXED_BEFORE_EVALUATION_NO_TUNING", holdout="SYNTHETIC_HASH_SEALED",
                     uncertainty="INFERENCE_NOT_ESTIMABLE_FROM_SINGLE_GENERATED_PATH_PER_PARTITION",
                     historical_pit="NOT_ATTESTED", trading_authority="NONE"))


def validate_schedule(reg):
    p = reg["query_pins"]
    train, validation, holdout = (p[f"{phase}/BASE"] for phase in PHASES)
    if not (train["decision_cutoff_ms"] < validation["start_ms"]
            and validation["decision_cutoff_ms"] + reg["embargo_ms"] <= holdout["start_ms"]):
        raise ValueError("EMBARGO_OR_OVERLAP")


def inputs(reg, phase, arm, *, unlocked):
    if phase == "synthetic_oos" and not unlocked:
        raise ValueError("SYNTHETIC_OOS_STILL_SEALED")
    q = query(phase, arm == "MISSING_CONTROL")
    if any(q[key] != value for key, value in reg["query_pins"][f"{phase}/{arm}"].items()):
        raise ValueError("SOURCE_PIN_MISMATCH")
    return q


def packet(reg, q, arm, attempt):
    plugin = reg["plugin"]
    meta = plugin["payload"]
    policy = scanner.research_signal_policy(source_class="TEST_ONLY")
    with patch.object(scanner, "query_local", return_value=q) as local:
        batch = scanner.evaluate_strategy_plugin(plugin, q, warehouse_root="/synthetic-no-warehouse",
                                                policy=policy)
    if local.call_count != 1 or not local.call_args.kwargs["sqlite_immutable"]:
        raise ValueError("SCANNER_IMMUTABLE_READ_MISSING")
    scanner.verify_factory_signal_batch(batch)
    adapter = Path("research_wp_r0/aql_factory_h_generic_signal_adapter_v1.py")
    return seal(dict(schema=SCHEMA, experiment_id=attempt, scanner_signal_batch=batch,
                     strategy_plugin=plugin, scanner_signal_policy=policy, core_query=q,
                     operator_cost_policy=reg["arms"][arm],
                     factory_code_sha256=hashlib.sha256(adapter.read_bytes()).hexdigest(),
                     source_query_sha256=q["query_sha256"], source_bytes_sha256=q["source_bytes_sha256"],
                     manifest_integrity_sha256=q["manifest_integrity_sha256"],
                     strategy_definition_sha256=meta["definition_digest"],
                     strategy_plugin_sha256=plugin["sha256"], config_sha256=meta["config_digest"],
                     scanner_policy_sha256=policy["sha256"],
                     scanner_evaluator_code_sha256=meta["evaluator_code_sha256"],
                     decision_cutoff_ms=q["decision_cutoff_ms"], holdout="SEALED_UNOPENED",
                     historical_pit="NOT_ATTESTED", trading_authority="NONE", source_ack_sha256=None,
                     strategy_approval_sha256=None, factory_consumer_ack_sha256=None))


def compare(group):
    base, shadow, placebo = (group[a] for a in ARMS)
    assert base["events"] == shadow["events"] == placebo["events"]
    assert base["outcomes"] == placebo["outcomes"]
    assert len(base["outcomes"]) == len(shadow["outcomes"])
    paired = 0
    for left, right in zip(base["outcomes"], shadow["outcomes"]):
        if left["status"] != "MODEL_ONLY":
            assert left == right
            continue
        assert all(left[k] == right[k] for k in
                   ("entry_open_ms", "exit_open_ms", "modeled_gross_return"))
        assert Decimal(left["total_cost_bps"]) == 6 and Decimal(right["total_cost_bps"]) == 18
        assert abs(Decimal(left["modeled_net_return"]) - Decimal(right["modeled_net_return"])
                   - Decimal(".0012")) < Decimal("1e-25")
        paired += 1
    assert paired > 0
    return {"paired_modeled_outcomes": paired, "shadow_delta_bps": -12, "placebo_delta_bps": 0,
            "unknown_outcomes": len(base["outcomes"]) - paired}


def run(reg, root):
    assert reg == register()
    validate_schedule(reg)
    db = root / "factory.sqlite"
    migrate_store_v2(db)
    registry = DiscovererLedger()
    attempts = {f"{p}/{a}": digest([reg["sha256"], p, a]) for p, a in PLAN}
    for key, attempt in attempts.items():
        registry.register(attempt, reg["candidate"]["candidate_id"], "G4-WP03",
                          reg["plugin"]["payload"]["definition_digest"], reg["sha256"],
                          reg["candidate"]["nomination_evidence_digest"], key)
    save(root / "registered.json", registry.to_dict_list())
    registry = DiscovererLedger.from_dict_list(json.loads((root / "registered.json").read_text()))
    verify_test_only_candidate_binding(candidate_package=reg["candidate"],
                                       synthetic_nomination=reg["nomination"],
                                       plugin=reg["plugin"], binding=reg["binding"])
    records, outputs, comparisons = {}, {}, {}
    unlocked = False
    for phase in ("train", "validation", "synthetic_oos"):
        outputs[phase] = {}
        for p, arm in (x for x in PLAN if x[0] == phase):
            key = f"{p}/{arm}"
            attempt = attempts[key]
            registry.transition(attempt, AttemptState.PENDING)
            save(root / f"pending-{attempt}.json", registry.entries()[-1].to_dict())
            try:
                q = inputs(reg, phase, arm, unlocked=unlocked)
                request = packet(reg, q, arm, attempt)
                first = run_factory_h_generic_research(request, db)
                replay = run_factory_h_generic_research(request, db)
                assert replay["store_status"] == "REPLAY_IDENTICAL"
                hashes = {k: first[k] for k in ("package_sha256", "trade_ledger_sha256",
                                                "scientific_lab_sha256", "result_sha256")}
                assert all(replay[k] == v for k, v in hashes.items())
                from contextlib import closing
                with closing(sqlite3.connect(db.resolve().as_uri()+"?mode=ro", uri=True)) as con:
                    raw = con.execute(f"SELECT document FROM {TABLE} WHERE experiment_id=?",
                                      (attempt,)).fetchone()[0]
                result = json.loads(raw)["trade_event_ledger"]
                assert result["trading_authority"] == "NONE"
                assert result["cohort"]["decision_slots"] == 64
                if arm == "MISSING_CONTROL":
                    assert result["cohort"]["signal_unknown"] == 64 and not result["outcomes"]
                outputs[phase][arm] = result
                records[key] = {"attempt": attempt, "hashes": hashes, "cohort": result["cohort"]}
                registry.transition(attempt, AttemptState.COMPLETE)
            except Exception:
                registry.transition(attempt, AttemptState.FAILED)
                raise
            finally:
                save(root / f"terminal-{attempt}.json", registry.entries()[-1].to_dict())
        comparisons[phase] = compare(outputs[phase])
        if phase == "validation":
            assert len(records) == 7
            save(root / "selection-lock.json", seal({"registration": reg["sha256"],
                 "fixed_selection": reg["selection"], "completed_non_oos": sorted(records)}))
            unlocked = True
    summary = registry.summary()
    assert registry.verify_chain() and summary["total_attempts"] == len(attempts)
    assert not summary["incomplete_attempts"] and len(records) == len(attempts)
    save(root / "registry.json", registry.to_dict_list())
    return seal({"trial_id": reg["sha256"], "records": records, "paired": comparisons,
                 "registry": summary, "trading_authority": "NONE", "historical_pit": "NOT_ATTESTED",
                 "uncertainty": reg["uncertainty"], "scope": "SYNTHETIC_ONLY"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["register", "run"])
    parser.add_argument("registration", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.mode == "register":
        save(args.registration, register())
        return
    args.output.mkdir()
    result = run(json.loads(args.registration.read_text()), args.output)
    save(args.output / "result.json", result)
    print(result["sha256"])


if __name__ == "__main__":
    main()
