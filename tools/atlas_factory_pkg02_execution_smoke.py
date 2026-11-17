"""One-command disposable synthetic Factory H cost/exit comparison evidence."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_wp_r0.aql_factory_e_research_results_store_v1 import (  # noqa: E402
    ResultsStoreError, digest, migrate_store_v2,
)
from research_wp_r0.aql_factory_h_scientific_lab_v1 import (  # noqa: E402
    evaluate_execution_exit_comparison,
)
from research_wp_r0.aql_factory_h_execution_comparison_v1 import (  # noqa: E402
    COST_KEYS, MIN_EMBARGO_MS, SCHEMA, run_factory_h_execution_comparison,
)


def seal(packet):
    packet["sha256"] = digest({k: v for k, v in packet.items() if k != "sha256"})
    return packet


def fixture_packet():
    start = MIN_EMBARGO_MS + 1000
    entry = start + 900000

    def safe_bars(at):
        points = [("100", "100.5", "99.5", "100"),
                  ("100.5", "101.5", "100.1", "101"),
                  ("101.5", "102.5", "101.1", "102"),
                  ("102.5", "103.5", "102.1", "103")]
        return [{"open_ms": at + i * 900000,
                 "close_ms": at + (i + 1) * 900000 - 1,
                 **dict(zip(("open", "high", "low", "close"), values))}
                for i, values in enumerate(points)]

    entries = []
    for i, (state, fraction) in enumerate((
        ("FILLED", "1"), ("UNKNOWN", None), ("NONFILL", "0"),
        ("PARTIAL", "0.25"), ("FILLED", "1"))):
        at = entry + i * 10 * 900000
        row = {"entry_id": "candidate-%d" % i, "attempt_id": "candidate-attempt",
               "signal_ms": at - 1, "entry_ms": at, "entry_price": "100",
               "bars": safe_bars(at), "maker_state": state,
               "maker_fill_fraction": fraction}
        if i == 4:
            row["bars"] = [{"open_ms": at, "close_ms": at + 899999,
                            "open": "100", "high": "104", "low": "98",
                            "close": "101"}]
        entries.append(row)
    # Separate seeded placebo path: never copied, permuted or selected from the
    # candidate outcomes. A fixture is not scientific null-independence proof.
    rng = random.Random(2702)
    nulls = []
    for i in range(3):
        at = entry + (100 + i * 10) * 900000
        opening = rng.randint(90, 110)
        points = []
        for j in range(4):
            close = opening + rng.choice((-2, -1, 1, 2))
            points.append({"open_ms": at + j * 900000,
                           "close_ms": at + (j + 1) * 900000 - 1,
                           "open": str(opening), "high": str(max(opening, close)),
                           "low": str(min(opening, close)), "close": str(close)})
            opening = close
        nulls.append({"entry_id": "null-%d" % i, "attempt_id": "candidate-attempt",
                      "signal_ms": at - 1, "entry_ms": at,
                      "entry_price": points[0]["open"], "bars": points,
                      "maker_state": "UNKNOWN", "maker_fill_fraction": None})
    taker = dict(zip(COST_KEYS, ("4", "4", "1", "1", "2", "2", "0")))
    maker = {**taker, "fee_entry_bps": "1", "spread_entry_bps": "0",
             "slippage_entry_bps": "0"}
    stress = {k: str(int(v) * 2) for k, v in taker.items()}
    return seal({
        "schema": SCHEMA, "experiment_id": "RESEARCH-H-EXEC-CMP-PKG02-SYNTHETIC",
        "source_class": "SYNTHETIC_FIXTURE_ONLY", "market": "SPOT",
        "direction": "LONG", "trading_authority": "NONE",
        "holdout": "SEALED_UNOPENED", "historical_pit": "NOT_ATTESTED",
        "frozen_at_ms": 100, "train_end_ms": 0, "embargo_ms": MIN_EMBARGO_MS,
        "evaluation_start_ms": start,
        "strategy_sha256": digest({"synthetic_strategy": "frozen-entry-risk"}),
        "scanner_entry_batch_sha256": digest(entries),
        "baseline_sha256": digest({"cost_baseline": taker, "null_seed": 2702}),
        "null_method": "INDEPENDENT_PREDECLARED_SYNTHETIC_ENTRIES",
        "cost_convention": "HALF_SPREAD_PER_LEG_SLIPPAGE_EXCLUDES_SPREAD",
        "cost_provenance": "SYNTHETIC_ASSUMPTION_NOT_ATTESTED",
        "costs": {"TAKER": taker, "PASSIVE_ENTRY_MARKET_EXIT": maker,
                  "STRESS_TAKER": stress},
        "stop_order": "STOP_MARKET",
        "generation_states": {"candidate-attempt": "GENERATED",
                              "failed-attempt": "GENERATED",
                              "unscanned-attempt": "UNSCANNED"},
        "attempts": [{"attempt_id": "candidate-attempt", "candidate_id": "candidate",
                      "state": "SELECTED", "source_receipt_sha256": digest(entries)},
                     {"attempt_id": "failed-attempt", "candidate_id": "failed",
                      "state": "FAILED", "source_receipt_sha256": "f" * 64},
                     {"attempt_id": "unscanned-attempt", "candidate_id": "unscanned",
                      "state": "UNSCANNED", "source_receipt_sha256": "e" * 64}],
        "entries": entries, "null_entries": nulls,
        "initial_risk_fraction": "0.01", "target_r_multiples": ["1", "2", "3"],
        "allocations": ["0.25", "0.25", "0.5"],
        "selection": "PREDECLARED_ALL_VARIANTS_NO_WINNER",
    })


def negative_receipt(packet):
    def update(p, key, value):
        p[key] = value

    cases = {
        "real_data": lambda p: update(p, "source_class", "RETROSPECTIVE_NON_PIT"),
        "live_authority": lambda p: update(p, "trading_authority", "LIVE"),
        "opened_oos": lambda p: update(p, "holdout", "OPENED"),
        "no_embargo": lambda p: update(p, "embargo_ms", 0),
        "freeze_after_first_sample": lambda p: update(p, "frozen_at_ms", p["evaluation_start_ms"]),
        "spread_double_charge": lambda p: update(p, "cost_convention", "SLIPPAGE_INCLUDES_SPREAD"),
        "missing_fee": lambda p: p["costs"]["TAKER"].pop("fee_entry_bps"),
        "unknown_numeric_fill": lambda p: p["entries"][1].update(maker_fill_fraction="1"),
        "lost_attempt_denominator": lambda p: p["attempts"].pop(0),
    }
    rejected = []
    for name, mutate in cases.items():
        bad = copy.deepcopy(packet)
        mutate(bad)
        seal(bad)
        try:
            evaluate_execution_exit_comparison(bad)
        except ValueError as exc:
            rejected.append({"case": name, "result": "REJECTED", "reason": str(exc)})
        else:
            raise ResultsStoreError("NEGATIVE_CASE_ACCEPTED_" + name)
    body = {"schema": "aql.factory.h.execution-negative-receipt.v1",
            "input_sha256": packet["sha256"], "rejections": rejected,
            "rejected_count": len(rejected), "unexpected_acceptances": 0}
    return {**body, "sha256": digest(body)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    packet = fixture_packet()
    report = evaluate_execution_exit_comparison(packet)
    db = destination / "synthetic-comparison.sqlite"
    if not db.exists():
        migrate_store_v2(db)
    one = run_factory_h_execution_comparison(packet, db)
    replay = run_factory_h_execution_comparison(packet, db)
    if one["package_sha256"] != replay["package_sha256"]:
        raise ResultsStoreError("REPLAY_IDENTITY_DRIFT")
    documents = {"input.json": packet, "report.json": report,
                 "receipt.json": one, "replay-receipt.json": replay,
                 "negative-rejections.json": negative_receipt(packet)}
    for name, document in documents.items():
        (destination / name).write_text(json.dumps(document, sort_keys=True,
            indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS_SYNTHETIC_ENGINEERING_ONLY",
                      "report_sha256": report["sha256"],
                      "package_sha256": one["package_sha256"],
                      "denominators": report["denominators"],
                      "negative_rejected": len(documents["negative-rejections.json"]["rejections"]),
                      "replay": replay["store_status"], "trading_authority": "NONE"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
