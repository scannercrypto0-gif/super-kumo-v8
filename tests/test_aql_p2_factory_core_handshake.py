"""Factory/Core exact-head, cross-PR TEST_ONLY contract handshake.

Requires checked-out Core PR #221 at exact commit in an isolated directory.
No Core code vendored, no source download, no real-data claim.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from research_wp_r0.aql_p2_factory_lab import (
    LabContractError, build_lab, digest, validate_schedule,
)

CORE_PR = 221
CORE_PIN = "0842fc0a753ec6a3327c00c24e74908e8f6ca39c"
START = 1704067200000  # TEST_ONLY synthetic aligned UTC clock
BAR_MS = 900000


def load_pinned_core():
    raw = os.environ.get("AQL_P2_CORE_FILE")
    if not raw:
        raise RuntimeError("MISSING_ISOLATED_CORE_PATH (set AQL_P2_CORE_FILE)")
    module_path = Path(raw).resolve(strict=True)
    root = module_path.parent.parent
    actual_sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_sha != CORE_PIN:
        raise RuntimeError("CORE_SHA_PIN_MISMATCH: " + actual_sha)
    spec = importlib.util.spec_from_file_location("aql_p2_core_exact_head", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CORE_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(core, *, unicode_id=False):
    H, J, K, L = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
    src = core.HistoricalSourceV1(
        "TEST_ONLY_SOURCE", "BINANCE", "SPOT", "BTCUSDT",
        H, J, K, "TEST_ONLY_GENERATION",
    )
    bars = tuple(core.HistoricalBarV1(
        START + i * BAR_MS, START + (i + 1) * BAR_MS - 1, H
    ) for i in range(5))
    trial = core.FrozenTrialV1.seal(
        trial_id="TEST_ONLY_TRIAL",
        hypothesis_sha256=H, base_definition_sha256=J,
        shadow_definition_sha256=K, preregistration_sha256=L,
        train_end_exclusive_ms=START + 6 * BAR_MS,
        holdout_start_ms=START + 6 * BAR_MS + core.EMBARGO_MIN_MS,
        holdout_end_exclusive_ms=START + 7 * BAR_MS + core.EMBARGO_MIN_MS,
    )
    items = [
        core.P2HistoricalOpportunityV1(
            trial_id=trial.trial_id,
            opportunity_id=("TEST_ONLY_فرصة" if unicode_id else "TEST_ONLY_OPP_1"),
            producer_event_id="TEST_ONLY_EVENT_1", source_id=src.source_id,
            source_package_sha256=src.source_package_sha256,
            feature_prefix_sha256=H, policy_sha256=J,
            decision_cutoff_ms=START + 2 * BAR_MS,
            decision_ms=START + 2 * BAR_MS + 2000,
            disposition="NO_SIGNAL",
            direction=None, direction_evidence_ref=None,
            regime=None, regime_source_sha256=None,
        ),
        core.P2HistoricalOpportunityV1(
            trial_id=trial.trial_id,
            opportunity_id="TEST_ONLY_OPP_2",
            producer_event_id="TEST_ONLY_EVENT_2", source_id=src.source_id,
            source_package_sha256=src.source_package_sha256,
            feature_prefix_sha256=H, policy_sha256=J,
            decision_cutoff_ms=START + 3 * BAR_MS,
            decision_ms=START + 3 * BAR_MS + 2000,
            disposition="REJECTED",
            direction=None, direction_evidence_ref=None,
            regime=None, regime_source_sha256=None,
        ),
    ]
    schedule = core.schedule_pair(
        trial, src, bars, items, test_only=True, permit_holdout=False
    )
    rows = []
    for pair in schedule["pairs"]:
        for arm in ("BASE", "SHADOW"):
            for hours in (4, 24, 72):
                status, reason, metrics = {
                    4: ("COMPLETE", None, {
                        "reference_price": 100.0, "observed_high": 101.0,
                        "observed_low": 99.0}),
                    24: ("CENSORED", "ARCHIVE_END_CENSORED", None),
                    72: ("UNKNOWN", "TEST_ONLY_MISSING_SOURCE", None),
                }[hours]
                rows.append({
                    "pair_id": pair["pair_id"], "arm": arm,
                    "horizon_hours": hours, "availability": status,
                    "availability_reason": reason,
                    "market_metrics": metrics,
                    "directional_metrics": None,
                    "execution_status": "NOT_OBSERVED",
                })
    return schedule, rows


def repin(schedule):
    schedule["artifact_sha256"] = digest({
        k: v for k, v in schedule.items() if k != "artifact_sha256"
    })


def run_handshake(core):
    schedule, rows = fixture(core)
    before = copy.deepcopy(schedule)
    input_sha = schedule["artifact_sha256"]
    pairs = validate_schedule(schedule)
    result = build_lab(schedule, rows)
    if schedule != before or schedule["artifact_sha256"] != input_sha:
        raise AssertionError("PRODUCER_ARTIFACT_MUTATED")
    if result["source_schedule_sha256"] != input_sha:
        raise AssertionError("CONSUMER_LOST_SOURCE_PIN")
    if (len(pairs) != len(schedule["pairs"]) or
            len(pairs) != result["scheduled_opportunities"]):
        raise AssertionError("PAIR_CARDINALITY_MISMATCH")
    if any(len(p["arms"]) != 2 or
           {a["arm"] for a in p["arms"]} != {"BASE", "SHADOW"}
           for p in pairs.values()):
        raise AssertionError("ARM_IDENTITY_MISMATCH")
    receipt = {
        "schema": "aql.p2.factory.core-test-only-handshake.v1",
        "test_only": True,
        "evidence_class": "TEST_ONLY_NOT_MARKET_EVIDENCE",
        "core_pr": CORE_PR,
        "core_head_sha": CORE_PIN,
        "factory_pr": 222,
        "factory_head_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_schedule_sha256": input_sha,
        "source_schedule_preserved": True,
        "paired_opportunities": len(pairs),
        "arm_slots": sum(len(p["arms"]) for p in pairs.values()),
        "horizon_observation_slots": result["observation_slots"],
        "disposition_counts": result["disposition_counts"],
        "market_coverage_by_horizon": result["market_coverage_by_horizon"],
        "factory_artifact_sha256": result["artifact_sha256"],
        "comparative_alpha": "NOT_EVALUABLE",
        "holdout_status": "SEALED_UNOPENED",
        "real_data_execution": "NOT_PERFORMED",
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


class FactoryCoreExactHeadHandshakeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_pinned_core()

    def test_actual_core_to_factory_artifact_no_mutation(self):
        receipt = run_handshake(self.core)
        self.assertTrue(receipt["source_schedule_preserved"])
        self.assertEqual(receipt["paired_opportunities"], 2)
        self.assertEqual(receipt["arm_slots"], 4)
        self.assertEqual(receipt["horizon_observation_slots"], 12)
        self.assertEqual(receipt["disposition_counts"],
                         {"NO_SIGNAL": 1, "REJECTED": 1})
        self.assertEqual(receipt["market_coverage_by_horizon"]["72"]["UNKNOWN"], 2)
        self.assertEqual(receipt["comparative_alpha"], "NOT_EVALUABLE")

    def test_core_canonical_unicode_id_accepted(self):
        schedule, rows = fixture(self.core, unicode_id=True)
        self.assertEqual(len(validate_schedule(schedule)), 2)
        self.assertEqual(build_lab(schedule, rows)["observation_slots"], 12)

    def test_root_digest_tamper_rejected(self):
        schedule, _ = fixture(self.core)
        schedule["scheduled_total"] += 1
        with self.assertRaisesRegex(LabContractError, "SCHEDULE_DIGEST_MISMATCH"):
            validate_schedule(schedule)

    def test_duplicate_pair_rejected_even_with_rehashed_root(self):
        schedule, _ = fixture(self.core)
        schedule["pairs"].append(copy.deepcopy(schedule["pairs"][0]))
        schedule["scheduled_total"] += 1
        repin(schedule)
        with self.assertRaisesRegex(LabContractError, "DUPLICATE_OR_BAD_PAIR_ID"):
            validate_schedule(schedule)

    def test_missing_pair_rejected_even_with_rehashed_root(self):
        schedule, _ = fixture(self.core)
        schedule["pairs"].pop()
        repin(schedule)
        with self.assertRaisesRegex(LabContractError, "DENOMINATOR_MISMATCH"):
            validate_schedule(schedule)

    def test_null_direction_remains_missing(self):
        schedule, _ = fixture(self.core)
        self.assertTrue(all(
            p["opportunity"]["direction"] is None and
            p["opportunity"]["direction_evidence_ref"] is None
            for p in schedule["pairs"]
        ))
        schedule["pairs"][0]["opportunity"]["direction"] = "LONG"
        repin(schedule)
        with self.assertRaisesRegex(LabContractError, "DIRECTION_WITHOUT_EVIDENCE"):
            validate_schedule(schedule)

    def test_embargo_mutation_rejected(self):
        schedule, _ = fixture(self.core)
        schedule["protocol"]["embargo_ms"] = 259199999
        repin(schedule)
        with self.assertRaisesRegex(LabContractError, "EMBARGO_TOO_SHORT"):
            validate_schedule(schedule)

    def test_holdout_open_rejected(self):
        schedule, _ = fixture(self.core)
        schedule["holdout_status"] = "OPEN"
        repin(schedule)
        with self.assertRaisesRegex(LabContractError, "HOLDOUT_OPEN"):
            validate_schedule(schedule)

    def test_missing_observation_slot_rejected(self):
        schedule, rows = fixture(self.core)
        rows.pop()
        with self.assertRaisesRegex(LabContractError, "INCOMPLETE_DENOMINATOR"):
            build_lab(schedule, rows)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--emit-receipt":
        path = Path(sys.argv[2])
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt = run_handshake(load_pinned_core())
        path.write_text(json.dumps(receipt, sort_keys=True, indent=2,
                                   ensure_ascii=True, allow_nan=False) + "\n",
                        encoding="utf-8")
        print("FACTORY_P2_TEST_ONLY_RECEIPT_OK", path, receipt["receipt_sha256"])
    else:
        unittest.main()
