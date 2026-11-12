"""Only the changed Discoverer review seam. Inputs use the accepted Core fixture."""
from copy import deepcopy
from contextlib import closing
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import aql
from aql.archive.discoverer_view import DiscovererView
from tools.strategy_discoverer_offline import continuous_research as discoverer
from tools.strategy_discoverer_offline.contracts import _canonical, _digest
from aql.archive.contracts import digest as core_digest
from tools.strategy_discoverer_offline.review_vertical import (
    csv_export, dashboard_section, import_csv, read_review, run_review, weekly_report,
)


ROOT = Path(os.environ["DISCOVERER_REVIEW_STAGE"]).resolve()
SLOTS = [200, 300, 400, 500]


def load(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core_fixture = load("core_fixture", ROOT / "core/tests/test_core_discoverer_followup.py")
factory = load("factory_native", ROOT / "factory/research_wp_r0/aql_factory_e_research_results_store_v1.py")
aql.__path__.append(str(ROOT / "paper/src/aql"))
from aql.paper_sim.engine import PaperSimulator
from aql.promotion import IDENTITY, Lifecycle, dashboard, seal as paper_seal


def reseal(value, **changes):
    return discoverer.seal({**{k: v for k, v in value.items() if k != "sha256"}, **changes})


def args(inventory=None):
    inventory = core_fixture.inventory() if inventory is None else inventory
    plan = discoverer.policy(origin=200, step=100, members=core_fixture.MEMBERS, query_limit=4)
    code = Path(__file__).resolve().parents[1] / "review_vertical.py"
    return dict(inventory=inventory, inventory_pin=inventory["sha256"], plan=plan,
                plan_pin=plan["sha256"], access_ms=1000, slots=SLOTS, missed_slots=(400,),
                factory=factory, code_pin=_digest(code.read_text(encoding="utf-8")),
                environment_pin=_digest({"fixture": "pinned-core-factory-paper-v1"}))


def existing_dashboard(root):
    # Independent TEST_ONLY host assessment. It does not interpret hypotheses
    # as Paper strategies or register any simulated orders.
    assessment = paper_seal({
        "schema": "aql.promotion.assessment.v1",
        **dict(zip(IDENTITY, ("fixture", "1", "SWING", "fixture", "1"*64, "2"*64, "3"*64), strict=True)),
        "factory_sha256": "4"*64, "policy_sha256": "5"*64, "scientific": "BLOCKED",
        "promotion": "PROMOTION_BLOCKED", "paper": "PAPER_BLOCKED", "shadow": "OBSERVATION_ONLY",
        "blockers": ["TEST_ONLY"], "scenarios": {}, "assessed_at_ms": 1000, "source_max_age_ms": 10,
        "costs_sha256": "6"*64, "risk_sha256": None, "authority": "NONE",
    })
    lifecycle = Lifecycle(root / "paper-lifecycle.jsonl", assessment, assessment_pin=assessment["sha256"])
    engine = PaperSimulator(root / "paper-simulator.jsonl")
    return dashboard(lifecycle, engine, as_of_ms=1000)


def execute(root):
    result = run_review(root, **args())
    dashboard_doc = dashboard_section(existing_dashboard(root), root / "weekly-review.json",
                                      result["sha256"], as_of_ms=1000, max_age_ms=10)
    csv = csv_export(result)
    assert import_csv(csv, result["sha256"]) == result
    for name, raw in (
        ("discoverer-dashboard.json", _canonical(dashboard_doc)),
        ("weekly-review.csv", csv.encode()),
        ("weekly-review.md", weekly_report(result).encode()),
    ):
        target = root / name
        if target.exists():
            assert target.read_bytes() == raw
        else:
            target.write_bytes(raw)
    return result, dashboard_doc


def test_exact_vertical_reopen_and_exports(tmp_path):
    root = tmp_path / "vertical"
    result, displayed = execute(root)
    assert read_review(root / "weekly-review.json", result["sha256"]) == result
    assert result["counts"] == {
        "observations": 12, "watch_states": {"UP": 2, "DOWN": 2, "UNKNOWN": 1,
                                              "NO_EVENT": 4, "MISSED": 3},
        "search_states": {"COMPLETE": 8, "UNAVAILABLE": 4},
        "candidate_generation_attempts": 2, "nominated": 2,
        "rejected_candidates": 0, "evaluation_pending": 2, "factory_trials": 0,
    }
    assert {row["direction"] for row in displayed["discoverer"]["candidates"]} == {"UP", "DOWN"}
    assert displayed["status"] == "PAPER_BLOCKED"
    assert displayed["trades"] == [] and displayed["actual_execution"] == "NONE"
    assert not (root / "paper-simulator.jsonl").exists()
    assert all(item["candidate"]["comparison"]["counts"]["CONTROL_TRIGGER"] >= 1
               for item in result["candidates"])
    assert all(not item["sent"] for item in result["alerts"])
    assert len({item["sha256"] for item in result["alerts"]}) == len(result["alerts"]) == 4
    for row in result["candidates"]:
        ack = row["factory"]
        native = factory.read_experiment(root / "factory.sqlite", ack["experiment_id"])
        assert native["sha256"] == ack["factory_experiment_sha256"]
        assert native["attempt_count"] == 2 and native["historical_pit"] == "NOT_ATTESTED"
        assert native["result_sha256"] is None and native["actual_fills"] is None
    found = dashboard_section(existing_dashboard(root), root / "weekly-review.json", result["sha256"],
                              search="PRECURSOR-UP", direction="UP", status="EVALUATION_PENDING",
                              as_of_ms=1020, max_age_ms=10)
    assert found["discoverer"]["freshness"] == "STALE"
    assert [c["direction"] for c in found["discoverer"]["candidates"]] == ["UP"]
    assert all(proof["cutoff_exclusive_ms"] == proof["request"]["cutoff_exclusive_ms"]
               for proof in found["discoverer"]["candidates"][0]["source_context"].values())
    absent = dashboard_section(existing_dashboard(root), root / "weekly-review.json", result["sha256"],
                               search="absent", as_of_ms=1000, max_age_ms=10)
    assert absent["discoverer"]["candidates"] == []
    assert "generation attempts 2" in weekly_report(result)
    assert execute(root) == (result, displayed)


def test_core_temporal_and_rights_negatives(tmp_path):
    parameters = args()
    original, plan = parameters["inventory"], parameters["plan"]
    core = DiscovererView(original, original["sha256"], access_ms=1000)
    request = discoverer.context_query(plan, {"symbol": "ALT", "onset": 100})
    fixture, proof = core.context(request, request["sha256"])
    assert proof["unavailable"]["news"] == "NOT_AVAILABLE_BY_CUTOFF"
    assert [row["original"]["version"] for row in proof["records"] if row["feature"] == "liquidity"] == [1]
    assert all(row["original"]["known_at"] is None for row in proof["records"])
    with pytest.raises(ValueError, match="QUERY_BINDING"):
        foreign = reseal(fixture, schema="foreign.v2")
        discoverer.precursor(request, foreign, foreign["sha256"])
    with pytest.raises(ValueError, match="MANIFEST_PIN"):
        run_review(tmp_path / "forged", **(parameters | {"inventory_pin": "a"*64}))
    bad = deepcopy(original)
    series = next(row for row in bad["series"] if row["symbol"] == "ALT" and row["feature"] == "liquidity")
    series["status"] = "BLOCKED_SOURCE"
    bad = reseal(bad)
    denied = DiscovererView(bad, bad["sha256"], access_ms=1000)
    _, rejected = denied.context(request, request["sha256"])
    assert rejected["unavailable"]["liquidity"] == "BLOCKED_SOURCE"
    assert not any(row["feature"] == "liquidity" for row in rejected["records"])
    denied_inventory = deepcopy(original)
    series = next(row for row in denied_inventory["series"]
                  if row["symbol"] == "ALT" and row["feature"] == "liquidity")
    rights = {**next(iter(series["rights"].values())), "state": "DENIED"}
    rights_pin = core_digest(rights)
    series["rights"][rights_pin] = rights
    first = next(row for row in series["records"]
                 if row["key"] == "context:100" and row["version"] == 1)
    first["rights"] = rights_pin
    series["pins"]["context:100"]["1"] = core_digest(first)
    second = next(row for row in series["records"]
                  if row["key"] == "context:100" and row["version"] == 2)
    second["prior"] = core_digest(first)
    series["pins"]["context:100"]["2"] = core_digest(second)
    denied_inventory = reseal(denied_inventory)
    denied = DiscovererView(denied_inventory, denied_inventory["sha256"], access_ms=1000)
    _, proof = denied.context(request, request["sha256"])
    assert proof["unavailable"]["liquidity"] == "RIGHTS_UNAVAILABLE"


def test_factory_loss_before_ack_and_restart(tmp_path):
    root = tmp_path / "restart"
    child = subprocess.run([sys.executable, "-B", __file__, str(root), "--crash"],
                           capture_output=True, text=True)
    assert child.returncode == 73, child.stderr
    assert not (root / "weekly-review.json").exists()
    with closing(sqlite3.connect(root / "factory.sqlite")) as conn:
        assert conn.execute("SELECT count(*) FROM experiments").fetchone()[0] == 1
    result, _ = execute(root)
    assert execute(root)[0]["sha256"] == result["sha256"]
    with closing(sqlite3.connect(root / "factory.sqlite")) as conn:
        assert conn.execute("SELECT count(*) FROM experiments").fetchone()[0] == 2
    changed = args()
    changed["environment_pin"] = "a"*64
    with pytest.raises(factory.ResultsStoreError, match="IMMUTABLE_IDEMPOTENCY_CONFLICT"):
        run_review(root, **changed)


def test_swaps_exports_and_authority_denied(tmp_path):
    root = tmp_path / "invalid"
    result, dashboard_doc = execute(root)
    path = root / "weekly-review.json"
    items = deepcopy(result["candidates"])
    items[0]["factory"], items[1]["factory"] = items[1]["factory"], items[0]["factory"]
    bad = reseal(result, candidates=items)
    other = root / "bad.json"
    other.write_bytes(_canonical(bad))
    with pytest.raises(ValueError, match="REVIEW_FACTORY_BINDING"):
        read_review(other, bad["sha256"])
    with pytest.raises(ValueError, match="CSV_CANONICAL"):
        import_csv(csv_export(result).replace("NOT_SENT", "SENT", 1), result["sha256"])
    with pytest.raises(ValueError, match="DASHBOARD_HOST_SCHEMA"):
        dashboard_section(dashboard_doc, path, result["sha256"], as_of_ms=1000, max_age_ms=10)
    with pytest.raises(ValueError, match="DASHBOARD_QUERY"):
        dashboard_section(existing_dashboard(root), path, result["sha256"], status="PAPER_ACTIVE",
                          as_of_ms=1000, max_age_ms=10)
    assert not any((root / name).exists() for name in ("paper-lifecycle.jsonl", "paper-simulator.jsonl"))
    bad = reseal(result, authority="LIVE")
    other.write_bytes(_canonical(bad))
    with pytest.raises(ValueError, match="REVIEW_AUTHORITY"):
        read_review(other, bad["sha256"])


if __name__ == "__main__":
    target = Path(sys.argv[1])
    if len(sys.argv) == 3 and sys.argv[2] == "--crash":
        try:
            run_review(target, **args(), crash_before_ack=True)
        except InterruptedError:
            os._exit(73)
        raise AssertionError("Expected injected commit-before-ACK crash")
    summary, _ = execute(target)
    print("JOIN_SHA256=" + summary["sha256"])
