"""Focused synthetic producer and independent consumer-contract tests."""
from copy import deepcopy
from contextlib import closing
from decimal import Decimal, localcontext
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, _seal, digest, migrate_store_v2,
)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
from research_wp_r0.aql_factory_historical_rule_projection import COST_KEYS
from research_wp_r0.aql_factory_lab_shadow_v1 import (
    DOSSIER, PROTOCOL, classify, read_handoff, run, verify_handoff,
)
from research_wp_r0.aql_factory_shadow_exits_v1 import COST_CASES, FAMILIES


def reseal(body, **changes):
    return _seal({**{k: v for k, v in body.items() if k != "sha256"}, **changes})


def policy(targets, allocation, trail=None):
    return {"applicable": True, "reason": None, "risk": ".1", "targets": targets,
            "allocations": allocation, "trail": trail, "stop": "STOP_MARKET"}


def fixture():
    attachments = {}
    def attach(body):
        pin = digest(body)
        attachments[pin] = body
        return pin

    def strategy(name):
        return {"id": name, "version": 1, "code_sha256": attach({"code": name}),
                "parameters_sha256": attach({"period": 12})}

    market = ["BINANCE", "SPOT", "BTCUSDT", "BTC", "USDT"]
    step = 900_000
    start = 20 * step
    costs = {case: {k: ("0" if k == "funding_bps_per_bar" else
                        "2" if case == "STRESS_TAKER" else "1") for k in COST_KEYS}
             for case in COST_CASES}
    protocol = _seal({
        "schema": PROTOCOL, "category": "SWING", "market": market,
        "evaluator": "independent-evaluator", "protocol_custodian": "independent-custodian",
        "frozen_at": 16 * step, "train": [0, 4 * step], "validation": [8 * step, 12 * step],
        "evaluation": [start, 64 * step], "holdout": [68 * step, 80 * step],
        "embargo_ms": 4 * step, "step_ms": step, "holding_horizon_ms": 4 * step,
        "min_pairs": 6, "min_net_delta": "0.001", "alpha": ".05", "family_tests": 4,
        "primary_family": "SINGLE_TRAILING",
        "baseline_exit": {"family": "SINGLE_FIXED", "policy": policy(["3"], ["1"])},
        "exit_families": dict(zip(FAMILIES, (
            policy(["2"], ["1"]), policy(["3"], ["1"], ".05"),
            policy(["1", "2"], [".5", ".5"]), policy(["1", "3"], [".5", ".5"], ".05"),
        ), strict=True)),
        "costs": costs,
    })
    dossier = _seal({
        "schema": DOSSIER, "experiment_id": "btc-shadow-fixture", "origin": "LAB",
        "baseline": strategy("btc-original"), "shadow": strategy("btc-shadow"),
        "category": "SWING", "proposer": "lab-author", "market": market,
        "hypothesis": "Next-bar ratchet protects favorable excursions.",
        "falsification": "Paired net return does not exceed the preregistered margin.",
        "counterexamples_sha256": attach(["Whipsaw"]), "candle_ms": step,
        "holding_horizon_ms": 4 * step, "protocol_sha256": protocol["sha256"],
        "decision_sha256": attach({"mode": "DECISION", "rule": "Frozen entry"}),
        "monitor_sha256": attach({"mode": "MONITOR_ONLY", "rule": "ATR"}),
        "dependencies_sha256": attach({"python": "3.12"}),
        "previous_admission_sha256": None,
    })
    entries, attempts = [], []
    source = digest({"fixture": "BTC matched entries"})
    for index in range(10):
        key = "opportunity-" + str(index)
        entry = start + (4 * index + 1) * step
        attempts.append({"attempt_id": "attempt-" + str(index), "candidate_id": key,
                         "source_receipt_sha256": source, "state": "SELECTED"})
        entries.append({
            "id": key, "attempt_id": attempts[-1]["attempt_id"], "signal_at": entry - step,
            "entry_at": entry, "price": "100", "maker_fraction": ("0", ".5", None, "1")[index % 4],
            "bars": [
                {"at": entry, "open": "100", "high": "120", "low": "99", "close": "115"},
                {"at": entry + step, "open": "112", "high": "113", "low": "95", "close": "96"},
                {"at": entry + 2 * step, "open": "96", "high": "97", "low": "88", "close": "90"},
            ],
        })
    for key, state in (("rejected", "REJECTED"), ("unknown", "UNKNOWN")):
        attempts.append({"attempt_id": key, "candidate_id": key, "state": state,
                         "source_receipt_sha256": source})
    cohort = _seal({
        "schema": "aql.factory.shadow-cohort.v1", "market": market, "source_sha256": source,
        "grade": "TEST_ONLY", "universe": [e["id"] for e in entries] + ["rejected", "unknown"],
        "entries": entries, "attempts": attempts, "known_at_attested": False,
        "holdout": "SEALED_UNOPENED", "native_factory_receipt_sha256": None,
    })
    return dossier, protocol, cohort, attachments


def check_package_2(raw, pin):
    # Executed against the actual pinned #288 source staged outside this checkout.
    from aql.promotion import assess_factory, seal

    receipt = read_handoff(raw, pin)
    shadow = receipt["shadow"]
    families = receipt["exit_families"]
    policy = seal({
        "schema": "aql.promotion.protocol.v1", "strategy_id": shadow["id"],
        "strategy_version": str(shadow["version"]), "shadow_id": receipt["experiment_id"],
        "category": receipt["category"], "code_sha256": shadow["code_sha256"],
        "config_sha256": shadow["parameters_sha256"], "protocol_sha256": receipt["protocol_sha256"],
        "costs_sha256": receipt["costs_sha256"], "shadow_until_ms": 120000,
        "source_max_age_ms": 1000,
        "applicability": {key: row["applicable"] for key, row in families.items()},
        "exclusions": {key: row["reason"] for key, row in families.items() if not row["applicable"]},
    })
    options = dict(factory_pin=pin, policy=policy, policy_pin=policy["sha256"],
                   evidence={}, evidence_pins={}, at_ms=60000)
    state = assess_factory(receipt, **options)
    assert state["factory_sha256"] == pin
    assert (state["promotion"], state["paper"], state["shadow"], state["authority"]) == (
        "PROMOTION_BLOCKED", "PAPER_BLOCKED", "OBSERVATION_ONLY", "NONE")
    assert all(item["status"] == "UNKNOWN" for item in state["scenarios"].values())
    try:
        assess_factory(receipt | {"category": "SCALP"}, **options)
    except ValueError as exc:
        assert "PROMOTION_PIN" in str(exc)
    else:
        raise AssertionError("Package 2 accepted tampered receipt")
    return state


class ShadowTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.store = Path(root.name) / "existing-factory.sqlite"
        migrate_store_v2(self.store)
        self.dossier, self.protocol, self.cohort, self.attachments = fixture()

    def execute(self, **changes):
        options = {"dossier": self.dossier, "protocol": self.protocol, "cohort": self.cohort,
                   "store": self.store, "expected_protocol": self.protocol["sha256"],
                   "expected_dossier": self.dossier["sha256"], "expected_cohort": self.cohort["sha256"],
                   "attachments": self.attachments}
        return run(**(options | changes))

    def test_admission_to_existing_store_replay_and_handoff(self):
        first = self.execute()
        self.assertEqual(first["admission"]["state"], "ADMITTED")
        self.assertEqual(first["store_status"], "STORED_IMMUTABLE")
        self.assertEqual(first["evaluation"]["factory_verdict"], "BLOCKED")
        self.assertEqual(first["evaluation"]["engineering_classifier_only"]["verdict"], "SCIENTIFIC_PASS")
        again = self.execute()
        self.assertEqual(again, first | {"store_status": "REPLAY_IDENTICAL"})
        handoff = first["handoff"]
        self.assertEqual(read_handoff(json.dumps(handoff).encode(), handoff["sha256"]), handoff)
        self.assertEqual(handoff["eligibility"]["paper"], "PAPER_BLOCKED")
        with closing(sqlite3.connect(self.store)) as conn, conn:
            self.assertEqual(conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0], 2)
            conn.execute(f"UPDATE {TABLE} SET document='{{}}' WHERE experiment_id LIKE 'LAB-SHADOW-RESULT-%'")
        with self.assertRaisesRegex(ResultsStoreError, "IMMUTABLE_PACKAGE_CONFLICT"):
            self.execute()

    def test_frozen_protocol_and_attachment_rejections(self):
        wrong = self.execute(expected_dossier="a" * 64)
        self.assertEqual(wrong["admission"]["reasons"], ["SHADOW_DOSSIER_PIN"])
        wrong = self.execute(expected_protocol="a" * 64)
        self.assertEqual(wrong["admission"]["reasons"], ["SHADOW_PROTOCOL_PIN"])
        attachments = dict(self.attachments)
        attachments[self.dossier["shadow"]["code_sha256"]] = {"code": "wrong"}
        wrong = self.execute(attachments=attachments)
        self.assertEqual(wrong["admission"]["reasons"], ["SHADOW_ATTACHMENT_PIN"])
        for key, value, reason in (
            ("category", "SCALP", "CATEGORY_OR_MARKET"),
            ("evaluator", "lab-author", "SELF_APPROVAL"),
            ("embargo_ms", 1, "FROZEN_CHRONOLOGY"),
        ):
            with self.subTest(key=key):
                protocol = reseal(self.protocol, **{key: value})
                dossier = reseal(self.dossier, protocol_sha256=protocol["sha256"])
                denied = self.execute(dossier=dossier, protocol=protocol,
                                      expected_dossier=dossier["sha256"],
                                      expected_protocol=protocol["sha256"])
                self.assertEqual(denied["admission"]["reasons"], ["SHADOW_" + reason])
                self.assertIsNone(denied["handoff"])

    def test_return_to_lab_and_new_version(self):
        blocked = self.execute(attachments={})["admission"]
        self.assertEqual(blocked["state"], "RETURN_TO_LAB")
        dossier = reseal(self.dossier, shadow=self.dossier["shadow"] | {"version": 2},
                         previous_admission_sha256=blocked["sha256"])
        fixed = self.execute(dossier=dossier, expected_dossier=dossier["sha256"], previous=blocked)
        self.assertEqual(fixed["admission"]["state"], "ADMITTED")
        self.assertNotEqual(fixed["admission"]["attempt_id"], blocked["attempt_id"])
        self.assertEqual(fixed["handoff"]["shadow"]["version"], 2)
        with closing(sqlite3.connect(self.store)) as conn:
            self.assertEqual(conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0], 3)

    def test_frozen_families_costs_partial_and_full_census(self):
        result = self.execute()["evaluation"]
        self.assertEqual(result["denominators"], {"attempts": 12, "opportunities": 12, "matched_entries": 10})
        for family, scenarios in result["families"].items():
            self.assertEqual(set(scenarios), set(COST_CASES))
            for item in scenarios.values():
                self.assertEqual([row["opportunity_id"] for row in item["rows"]], self.cohort["universe"])
                self.assertIsNone(item["rows"][-1]["net"])
            passive = scenarios["PASSIVE_ENTRY_MARKET_EXIT"]["rows"]
            self.assertEqual([row["status"] for row in passive[:3]], ["NONFILL", "MODEL_ONLY", "UNKNOWN_FILL"])
            self.assertEqual(Decimal(passive[1]["cost_bps"]), Decimal(3))
        fixed = result["families"]["MULTI_FIXED"]["TAKER"]["rows"][0]
        self.assertEqual(len(fixed["legs"]), 2)
        self.assertEqual(Decimal(fixed["cost_bps"]), Decimal(6))
        self.assertEqual(Decimal(fixed["gross"]) - Decimal(fixed["net"]), Decimal(".0006"))
        stress = result["families"]["MULTI_FIXED"]["STRESS_TAKER"]["rows"][0]
        self.assertEqual(fixed["gross"], stress["gross"])
        self.assertGreater(Decimal(fixed["net"]), Decimal(stress["net"]))
        self.assertEqual(len(result["trials"]), 15)
        trailing = result["families"]["SINGLE_TRAILING"]["TAKER"]["rows"][0]
        self.assertEqual(trailing["legs"][0]["price"], "112")
        self.assertEqual(trailing["legs"][0]["reason"], "STOP_MARKET")

    def test_exclusion_and_unknown_execution(self):
        families = deepcopy(self.protocol["exit_families"])
        families["MULTI_TRAILING"] = {"applicable": False, "reason": "PREDECLARED_UNSUPPORTED",
                                     "risk": None, "targets": None, "allocations": None,
                                     "trail": None, "stop": None}
        protocol = reseal(self.protocol, exit_families=families)
        dossier = reseal(self.dossier, protocol_sha256=protocol["sha256"])
        entries = deepcopy(self.cohort["entries"])
        entries[0]["bars"].pop(1)
        entries[1]["bars"][0]["low"] = "89"
        entries[1]["bars"][0]["high"] = "131"
        cohort = reseal(self.cohort, entries=entries)
        result = self.execute(dossier=dossier, protocol=protocol, cohort=cohort,
                              expected_dossier=dossier["sha256"], expected_protocol=protocol["sha256"],
                              expected_cohort=cohort["sha256"])
        rows = result["evaluation"]["families"]["SINGLE_TRAILING"]["TAKER"]["rows"]
        self.assertEqual([row["status"] for row in rows[:2]], ["UNKNOWN_GAP", "UNKNOWN_INTRABAR"])
        self.assertNotIn("MULTI_TRAILING", result["evaluation"]["families"])
        self.assertEqual(sum(row["status"] == "EXCLUDED" for row in result["evaluation"]["trials"]), 3)
        self.assertEqual(result["handoff"]["exit_families"]["MULTI_TRAILING"]["reason"],
                         "PREDECLARED_UNSUPPORTED")
        self.assertEqual(result["evaluation"]["engineering_classifier_only"]["verdict"], "INCONCLUSIVE")

    def test_classifier_and_adversarial_consumer(self):
        with localcontext() as ctx:
            ctx.prec = 50
            self.assertEqual(classify([Decimal(".01")] * 10, self.protocol)["verdict"], "SCIENTIFIC_PASS")
            self.assertEqual(classify([Decimal("-.01")] * 10, self.protocol)["verdict"], "SCIENTIFIC_FAIL")
            self.assertEqual(classify([None] * 10, self.protocol)["verdict"], "INCONCLUSIVE")
        handoff = self.execute()["handoff"]
        with self.assertRaisesRegex(ResultsStoreError, "HANDOFF_DUPLICATE_KEY"):
            read_handoff(b'{"schema":1,"schema":2}', handoff["sha256"])
        for changes in (
            {"evidence_grade": "PIT_ATTESTED"},
            {"factory_verdict": "SCIENTIFIC_PASS"},
            {"eligibility": handoff["eligibility"] | {"selected_live_exit": "SINGLE_TRAILING"}},
        ):
            forged = reseal(handoff, **changes)
            with self.assertRaisesRegex(ResultsStoreError, "HANDOFF_PIN"):
                verify_handoff(forged, handoff["sha256"])
            with self.assertRaisesRegex(ResultsStoreError, "HANDOFF_AUTHORITY"):
                verify_handoff(forged, forged["sha256"])
        forged = reseal(self.cohort, grade="PIT_ATTESTED")
        result = self.execute(cohort=forged, expected_cohort=forged["sha256"])
        self.assertEqual(result["admission"]["reasons"], ["SHADOW_COHORT_AUTHORITY"])


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--receipt":
        path = Path(sys.argv[2])
        if not path.exists():
            migrate_store_v2(path)
        dossier, protocol, cohort, attachments = fixture()
        receipt = run(dossier, protocol, cohort, path, expected_protocol=protocol["sha256"],
                      expected_dossier=dossier["sha256"], expected_cohort=cohort["sha256"],
                      attachments=attachments)
        assert receipt["handoff"] is not None
        print(json.dumps(receipt["handoff"], sort_keys=True, separators=(",", ":")))
    elif len(sys.argv) == 4 and sys.argv[1] == "--consumer":
        assessment = check_package_2(Path(sys.argv[2]).read_bytes(), sys.argv[3])
        print(json.dumps(assessment, sort_keys=True, separators=(",", ":")))
    else:
        unittest.main()
