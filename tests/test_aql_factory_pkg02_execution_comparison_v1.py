"""Adversarial synthetic execution and exit-policy delta tests; no source I/O."""
from __future__ import annotations

import copy
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, digest, migrate_store_v2,
)
from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_execution_exit_comparison
from research_wp_r0.aql_factory_h_execution_comparison_v1 import run_factory_h_execution_comparison
from tools.atlas_factory_pkg02_execution_smoke import fixture_packet, negative_receipt, seal


def report(packet=None):
    return evaluate_execution_exit_comparison(packet or fixture_packet())


def row(result, *, entry="candidate-0", policy="B", scenario="TAKER"):
    return next(r for r in result["outcomes"] if r["entry_id"] == entry and
                r["policy"] == policy and r["scenario"] == scenario)


def test_uses_all_frozen_entries_and_attempt_variant_denominators():
    result = report()
    assert result["denominators"] == {
        "total_attempted": 3, "generated": 2, "failed": 1, "failed_to_generate": 0,
        "attempt_state_counts": {"SELECTED": 1, "FAILED": 1, "UNSCANNED": 1},
        "candidate_entries": 5, "null_entries": 3,
        "variants_per_cohort": 9, "total_variant_rows": 72,
    }
    assert len(result["comparisons"]) == 18
    assert {r["policy"] for r in result["outcomes"]} == {"A", "B", "C"}
    assert result["winner"] is None
    assert result["orders_created"] == 0
    assert result["actual_fills"] is None
    assert result["holdout"] == "SEALED_UNOPENED"
    assert result["trading_authority"] == "NONE"


def test_staged_fee_spread_slippage_counted_once_and_gross_separate():
    result = report()
    for policy in ("A", "B", "C"):
        outcome = row(result, policy=policy)
        assert outcome["status"] == "MODEL_ONLY"
        assert Decimal(outcome["total_cost_bps"]) == 14
        assert Decimal(outcome["gross_return"]) - Decimal(outcome["net_return"]) == Decimal("0.0014")
        assert sum(Decimal(x["fraction_of_initial_notional"]) for x in outcome["legs"]) == 1
        fees = sum(Decimal(x["cost_components_bps"]["fee_entry_bps"])
                   for x in outcome["legs"])
        assert fees == 4  # three exits must not triple-charge the entry fee
    assert Decimal(row(result, policy="A")["gross_return"]) == Decimal("0.03")
    assert Decimal(row(result, policy="B")["gross_return"]) == Decimal("0.0225")


def test_maker_touch_does_not_become_fill_and_nonfill_is_not_dropped():
    result = report()
    unknown = row(result, entry="candidate-1", scenario="PASSIVE_ENTRY_MARKET_EXIT")
    assert unknown["status"] == "UNKNOWN_FILL"
    assert unknown["net_return"] is None and unknown["legs"] == []
    missed = row(result, entry="candidate-2", scenario="PASSIVE_ENTRY_MARKET_EXIT")
    assert missed["status"] == "NONFILL"
    assert missed["net_return"] == "0" and missed["total_cost_bps"] == "0"
    partial = row(result, entry="candidate-3", scenario="PASSIVE_ENTRY_MARKET_EXIT")
    assert partial["status"] == "MODEL_ONLY"
    assert partial["filled_fraction"] == "0.25"
    assert partial["unfilled_fraction"] == "0.75"
    assert Decimal(partial["total_cost_bps"]) == Decimal("2")
    assert Decimal(partial["gross_return"]) == Decimal("0.0225") / 4
    summary = result["comparisons"]["CANDIDATE:PASSIVE_ENTRY_MARKET_EXIT:B"]
    assert summary["attempted_entry_count"] == 5
    assert summary["nonfill_count"] == 1 and summary["partial_entry_count"] == 1
    assert summary["net_return_sum"] is None  # unknown subset cannot be promoted


def test_same_bar_stop_target_is_unknown_all_policies_no_optimistic_order():
    result = report()
    for policy in ("A", "B", "C"):
        outcome = row(result, entry="candidate-4", policy=policy)
        assert outcome["status"] == "UNKNOWN_INTRABAR_STOP_TARGET"
        assert outcome["gross_return"] is None and outcome["net_return"] is None
        assert outcome["legs"] == []


def test_c_stop_advance_only_next_bar_a_b_c_are_not_assumed_equivalent():
    packet = fixture_packet()
    entry = packet["entries"][0]
    # First target bar dips below breakeven but never the initial stop. The
    # predeclared C rule must not apply its stop retrospectively to that bar.
    entry["bars"][1].update(low="99.5")
    entry["bars"][2].update(open="100.5", high="100.8", low="99.5", close="100.1")
    result = report(seal(packet))
    c = row(result, policy="C")
    b = row(result, policy="B")
    assert c["status"] == "MODEL_ONLY"
    assert [x["reason"] for x in c["legs"]] == ["TARGET_1_MARKET_MODEL", "STOP_MARKET_MODEL"]
    assert Decimal(c["gross_return"]) == Decimal("0.0025")
    assert b["status"] == "MODEL_ONLY"
    # B crosses target 2 at the next bar's 102.5 opening gap.
    assert Decimal(b["gross_return"]) == Decimal("0.02375")
    assert Decimal(row(result, policy="A")["gross_return"]) == Decimal("0.03")


def test_stop_limit_fill_unknown_and_stop_market_gap_uses_worse_open():
    packet = fixture_packet()
    entry = packet["entries"][0]
    entry["bars"][1].update(open="98", high="98.5", low="97", close="98")
    result = report(seal(packet))
    stop = row(result)
    assert stop["status"] == "MODEL_ONLY"
    assert stop["legs"][0]["price"] == "98"
    packet["stop_order"] = "STOP_LIMIT"
    result = report(seal(packet))
    assert row(result)["status"] == "UNKNOWN_STOP_LIMIT_FILL"
    assert row(result)["net_return"] is None


def test_incomplete_exit_does_not_promote_realized_partial_subset():
    packet = fixture_packet()
    packet["entries"][0]["bars"] = packet["entries"][0]["bars"][:2]
    outcome = row(report(seal(packet)))
    assert outcome["status"] == "UNKNOWN_END_OF_DATA"
    assert len(outcome["legs"]) == 1
    assert outcome["gross_return"] is None and outcome["total_cost_bps"] is None


def test_stress_same_entries_and_gross_but_costs_only_worse():
    result = report()
    for policy in ("A", "B", "C"):
        taker = row(result, policy=policy)
        stress = row(result, policy=policy, scenario="STRESS_TAKER")
        assert taker["gross_return"] == stress["gross_return"]
        assert Decimal(stress["net_return"]) < Decimal(taker["net_return"])
        assert Decimal(stress["total_cost_bps"]) == 28


def test_independent_null_has_own_entry_population_and_unknowns():
    packet = fixture_packet()
    assert {e["entry_id"] for e in packet["entries"]}.isdisjoint(
        e["entry_id"] for e in packet["null_entries"])
    result = report(packet)
    placebo = [r for r in result["outcomes"] if r["cohort"] == "NULL_PLACEBO"]
    assert len(placebo) == 27
    assert len({r["entry_id"] for r in placebo}) == 3
    assert "NOT_SCIENTIFIC_INDEPENDENCE_PROOF" in result["coverage"]["null"]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(source_class="ORIGINAL"),
    lambda p: p.update(holdout="OPENED"),
    lambda p: p.update(selection="BEST_NET_RETURN"),
    lambda p: p.update(direction="SHORT"),
    lambda p: p.update(trading_authority="PAPER"),
    lambda p: p.update(embargo_ms=1),
    lambda p: p.update(frozen_at_ms=p["evaluation_start_ms"]),
    lambda p: p.update(cost_convention="SLIPPAGE_INCLUDES_SPREAD"),
    lambda p: p["costs"]["TAKER"].pop("fee_entry_bps"),
    lambda p: p["costs"]["TAKER"].update(funding_bps_per_bar="1"),
    lambda p: p["costs"]["STRESS_TAKER"].update(fee_entry_bps="0"),
    lambda p: p["costs"]["TAKER"].update(fee_entry_bps="NaN"),
    lambda p: p["entries"][1].update(maker_fill_fraction="1"),
    lambda p: p["entries"][3].update(maker_fill_fraction="1"),
    lambda p: p["entries"][0].update(entry_ms=p["entries"][0]["signal_ms"]),
    lambda p: p["entries"][0]["bars"][1].update(open_ms=0),
    lambda p: p["entries"][0]["bars"][1].update(high="1"),
    lambda p: p["entries"].reverse(),
    lambda p: p["entries"][1].update(entry_id=p["entries"][0]["entry_id"]),
    lambda p: p["null_entries"][0].update(entry_id=p["entries"][0]["entry_id"]),
    lambda p: p.update(allocations=["0.5", "0.5", "0.5"]),
    lambda p: p.update(target_r_multiples=["3", "2", "1"]),
    lambda p: p["attempts"].pop(0),
    lambda p: p["generation_states"].pop("failed-attempt"),
])
def test_adversarial_resealed_inputs_rejected(mutation):
    packet = fixture_packet()
    mutation(packet)
    with pytest.raises(ValueError):
        report(seal(packet))


def test_unsealed_packet_rejected():
    packet = fixture_packet()
    packet["costs"]["TAKER"]["fee_entry_bps"] = "5"
    with pytest.raises(ResultsStoreError, match="PACKET_SEAL"):
        report(packet)


def test_failed_generation_not_silently_counted_as_generated():
    packet = fixture_packet()
    packet["generation_states"]["failed-attempt"] = "FAILED_TO_GENERATE"
    result = report(seal(packet))
    assert result["denominators"]["generated"] == 1
    assert result["denominators"]["failed"] == 1
    assert result["denominators"]["failed_to_generate"] == 1
    assert result["denominators"]["total_attempted"] == 3


def test_existing_factory_store_restart_replay_and_conflict(tmp_path):
    path = tmp_path / "comparison.sqlite"
    migrate_store_v2(path)
    packet = fixture_packet()
    first = run_factory_h_execution_comparison(packet, path)
    # New process, no Python object cache: exact package hash must survive.
    code = (
        "import json,sys; from tools.atlas_factory_pkg02_execution_smoke import fixture_packet; "
        "from research_wp_r0.aql_factory_h_execution_comparison_v1 import run_factory_h_execution_comparison; "
        "print(json.dumps(run_factory_h_execution_comparison(fixture_packet(),sys.argv[1])))"
    )
    replay = json.loads(subprocess.check_output([sys.executable, "-B", "-c", code, str(path)],
                       cwd=Path(__file__).resolve().parents[1], text=True))
    assert replay["store_status"] == "REPLAY_IDENTICAL"
    assert first["package_sha256"] == replay["package_sha256"]
    assert first["report_sha256"] == replay["report_sha256"]
    assert first["receipt_sha256"] != replay["receipt_sha256"]
    packet["costs"]["TAKER"]["fee_entry_bps"] = "5"
    with pytest.raises(ResultsStoreError, match="IMMUTABLE_PACKAGE_CONFLICT"):
        run_factory_h_execution_comparison(seal(packet), path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM factory_h_research_results_v1").fetchone()[0] == 1


def test_invalid_input_never_creates_store_and_tamper_rejected(tmp_path):
    path = tmp_path / "never-created.sqlite"
    packet = fixture_packet()
    packet["source_class"] = "ORIGINAL"
    with pytest.raises(ValueError):
        run_factory_h_execution_comparison(seal(packet), path)
    assert not path.exists()
    path = tmp_path / "tamper.sqlite"
    migrate_store_v2(path)
    packet = fixture_packet()
    run_factory_h_execution_comparison(packet, path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE factory_h_research_results_v1 SET document='{}'")
    with pytest.raises(ResultsStoreError, match="IMMUTABLE_PACKAGE_CONFLICT"):
        run_factory_h_execution_comparison(packet, path)


def test_deterministic_report_seals_and_negative_receipt():
    packet = fixture_packet()
    one, two = report(packet), report(copy.deepcopy(packet))
    assert one == two
    assert one["sha256"] == digest({k: v for k, v in one.items() if k != "sha256"})
    negative = negative_receipt(packet)
    assert negative["rejected_count"] == 9
    assert negative["unexpected_acceptances"] == 0
    assert set(one["implementation_sources"]) == {
        "aql_factory_h_execution_comparison_v1.py", "aql_factory_h_scientific_lab_v1.py",
        "aql_factory_historical_rule_projection.py", "aql_factory_e_research_results_store_v1.py",
        "aql_factory_h_research_package_v1.py"}


def test_committed_artifacts_match_current_material_delta():
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "docs" / "evidence" / "codex-pkg02"
    assert json.loads((artifacts / "report.json").read_text(encoding="utf-8")) == report()
    assert json.loads((artifacts / "negative-rejections.json").read_text(encoding="utf-8")) == negative_receipt(fixture_packet())


def test_one_command_cli_emits_replay_and_no_real_authority(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = json.loads(subprocess.check_output([
        sys.executable, "-B", "tools/atlas_factory_pkg02_execution_smoke.py",
        "--output-dir", str(tmp_path / "smoke")], cwd=root, text=True))
    assert output["status"] == "PASS_SYNTHETIC_ENGINEERING_ONLY"
    assert output["replay"] == "REPLAY_IDENTICAL"
    assert output["negative_rejected"] == 9
    assert output["denominators"]["total_variant_rows"] == 72
    assert output["trading_authority"] == "NONE"
