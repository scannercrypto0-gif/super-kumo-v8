"""Current-head G4 composition of the existing Discoverer and Factory seams."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
from unittest.mock import patch

import run_wp03 as wp
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment, read_experiment, register_experiment, ResultsStoreError,
)
from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1, NominationEvidenceV1, _digest,
)
from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint
from tools.strategy_discoverer_offline.g4_candidate_preregistration import (
    build_g4_synthetic_candidate_proposal, verify_g4_synthetic_candidate_proposal,
)
from tools.strategy_discoverer_offline.g4_factory_acceptance_seam import (
    build_g4_factory_research_attempt_join,
)
from tools.strategy_discoverer_offline.tests import test_g4_candidate_preregistration as fixture

DISCOVERER = "c568e3b281795f9eef2165c0e6f571b87157a23c"
base_query = wp.query
base_register = wp.register
source_raw = wp.digest({p: base_query(p)["bars"] for p in wp.PHASES})
manifest = wp.digest({"fixture": "TEST-ONLY-G4-CURRENT-HEAD", "raw": source_raw,
                      "missing_control": {"partition": "validation", "bar_index": 7}})
wp.SOURCE_PINS["discoverer"] = DISCOVERER


def query(phase, missing=False):
    q = base_query(phase, missing)
    q.update(dataset_id="TEST-ONLY-G4-CURRENT-HEAD", source_bytes_sha256=source_raw,
             manifest_integrity_sha256=manifest)
    q["query_sha256"] = wp.digest({k: v for k, v in q.items() if k != "query_sha256"})
    return q


wp.query = query
original_case = fixture.case


def source_bound_case():
    candidate, nomination = original_case()
    nomination.update(source_dataset_id="TEST-ONLY-G4-CURRENT-HEAD",
                      source_raw_sha256=source_raw, source_manifest_sha256=manifest,
                      timeframe="15m", cutoff_ms=query("train")["decision_cutoff_ms"])
    nomination["omission_reason_codes"] = tuple(nomination["omission_reason_codes"])
    nomination = NominationEvidenceV1.build(
        **{k: v for k, v in nomination.items() if k != "nomination_digest"}).to_dict()
    candidate.update(nomination_evidence_digest=nomination["nomination_digest"],
                     source_manifest_sha256=manifest)
    fields = {k: v for k, v in candidate.items() if k not in (
        "package_digest", "evaluation_status", "scientific_acceptance", "execution_status",
        "publishable", "delivery_authorized", "holdout_status", "factory_routing")}
    return DiscoveryCandidatePackageV1.build(**fields).to_dict(), nomination


def read_frozen(root):
    o = json.loads((root / "originals.json").read_text())
    return {**o, "durable_checkpoint": DurableDiscovererCheckpoint(root / "g4-discoverer.sqlite")}


def register(o, proposal):
    base = base_register(o["candidate_package"], o["synthetic_nomination"])
    assert base["plugin"] == o["scanner_plugin"] and base["binding"] == o["scanner_binding"]
    return wp.seal({**{k: v for k, v in base.items() if k != "sha256"},
                    "current_head_proposal": proposal["proposal_sha256"],
                    "closeout_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "fixture_source_manifest_sha256": manifest})


def freeze(root):
    root.mkdir()
    with patch.object(fixture, "case", source_bound_case):
        o = fixture.setup(root)
    o["frozen_trial_budget"] = len(wp.PLAN)
    proposal = build_g4_synthetic_candidate_proposal(**o)
    wp.save(root / "originals.json", {k: v for k, v in o.items() if k != "durable_checkpoint"})
    assert verify_g4_synthetic_candidate_proposal(proposal=proposal, **read_frozen(root))
    wp.save(root / "proposal.json", proposal)
    wp.save(root / "registration.json", register(o, proposal))
    wp.save(root / "checkpoint.json", o["durable_checkpoint"].read_latest_ledger())


def reject(operation, exc):
    try:
        operation()
    except exc:
        return
    raise AssertionError("negative control accepted")


def run(frozen, output):
    output.mkdir()
    o = read_frozen(frozen)
    proposal = json.loads((frozen / "proposal.json").read_text())
    reg = json.loads((frozen / "registration.json").read_text())
    assert verify_g4_synthetic_candidate_proposal(proposal=proposal, **o)
    assert reg == register(o, proposal)
    assert proposal["frozen_trial_budget"] == len(wp.PLAN)
    assert proposal["source_manifest_sha256"] == manifest
    assert all(q["source_bytes_sha256"] == source_raw for q in reg["query_pins"].values())
    store = output / "factory-generation.sqlite"
    inputs = dict(proposal=proposal, originals=o, factory_store_path=store,
                  experiment_id="G4-GENERATION-" + reg["sha256"],
                  config_sha256=o["scanner_plugin"]["payload"]["config_digest"],
                  source_query_245_sha256=wp.digest(["SYNTHETIC_245_FIXTURE_ONLY", manifest]),
                  source_query_253_sha256=query("train")["query_sha256"],
                  code_sha256=reg["closeout_code_sha256"],
                  environment_sha256=wp.digest([platform.system(), sys.version.split()[0]]))
    join = build_g4_factory_research_attempt_join(**inputs)
    gen = read_experiment(store, inputs["experiment_id"])
    assert gen["attempt_count"] == 3 and {x["state"] for x in gen["attempts"]} == {
        "FAILED", "REJECTED", "SELECTED"}
    assert build_g4_factory_research_attempt_join(**inputs)["factory_write_status"] == "REPLAY_IDENTICAL"
    for field in ("candidate_package_sha256", "source_manifest_sha256", "scanner_plugin_sha256"):
        bad = deepcopy(proposal)
        bad[field] = "0" * 64
        bad["proposal_sha256"] = _digest({k:v for k,v in bad.items() if k!="proposal_sha256"})
        reject(lambda: build_g4_factory_research_attempt_join(**{**inputs,"proposal":bad}), ValueError)
    bad = deepcopy(proposal)
    bad["attempt_census"]["FAILED"] = 0
    bad["proposal_sha256"] = _digest({k:v for k,v in bad.items() if k!="proposal_sha256"})
    reject(lambda: build_g4_factory_research_attempt_join(**{**inputs,"proposal":bad}), ValueError)

    # The prior execution driver uses the verified registration seal as each
    # Factory experiment ID parent. Keep the original driver, registry and Lab.
    with patch.object(wp, "register", lambda *args: register(o, proposal)):
        trial = wp.run(reg, output)
    attempts = [
        {"attempt_id": v["attempt"], "candidate_id": o["candidate_package"]["candidate_id"],
         "state": "UNKNOWN" if k.endswith("MISSING_CONTROL") else "SELECTED",
         "source_receipt_sha256": v["hashes"]["package_sha256"]}
        for k, v in sorted(trial["records"].items())
    ]
    assert len(attempts) == len({row["attempt_id"] for row in attempts}) == proposal["frozen_trial_budget"]
    checkpoint = json.loads((output / "registry.json").read_text())
    ledger = wp.DiscovererLedger.from_dict_list(checkpoint)
    assert {e.attempt_id for e in ledger.entries()} == {v["attempt_id"] for v in attempts}
    linked = build_experiment(
        experiment_id="G4-VARIANTS-" + reg["sha256"], lane="SCANNER",
        source_status="SYNTHETIC_ENGINEERING_PASS", source_sha256=manifest,
        source_query_245_sha256=inputs["source_query_245_sha256"],
        source_query_253_sha256=inputs["source_query_253_sha256"],
        strategy_definition_sha256=proposal["strategy_definition_sha256"],
        config_sha256=inputs["config_sha256"], code_sha256=inputs["code_sha256"],
        environment_sha256=inputs["environment_sha256"],
        parent_receipt_sha256=join["receipt_sha256"], attempts=attempts,
        result_sha256=trial["sha256"])
    register_experiment(store, linked)
    assert read_experiment(store, linked["experiment_id"]) == linked
    assert register_experiment(store, linked)["status"] == "REPLAY_IDENTICAL"
    altered = {**linked, "attempts": linked["attempts"][:-1]}
    altered = wp.seal({k:v for k,v in altered.items() if k!="sha256"})
    reject(lambda: register_experiment(store, altered), ResultsStoreError)
    report = wp.seal({"proposal_sha256": proposal["proposal_sha256"], "registration_sha256": reg["sha256"],
                      "generation": join, "variant_registry": linked, "trial": trial,
                      "negative_checks": ["swapped_candidate", "swapped_source", "swapped_scanner_sha",
                                          "hidden_generation_failure", "hidden_variant", "duplicate_replay"],
                      "source": "GENERATED_TEST_ONLY_245_ID_IS_FIXTURE_TAG_NOT_REAL_RECEIPT",
                      "trading_authority": "NONE", "historical_pit": "NOT_ATTESTED"})
    wp.save(output / "result.json", trial)
    wp.save(output / "closeout.json", report)
    print(report["sha256"])


if __name__ == "__main__":
    mode, root, *out = sys.argv[1:]
    if mode == "freeze" and not out:
        freeze(Path(root))
    elif mode == "run" and len(out) == 1:
        run(Path(root), Path(out[0]))
    else:
        raise SystemExit("Use freeze ROOT or run ROOT OUTPUT")
