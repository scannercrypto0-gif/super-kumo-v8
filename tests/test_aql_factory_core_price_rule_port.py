"""Factory #246 read-only actual Core #245 schema-shaped price-query port tests.

Only synthetic checksum-shaped fixtures are used here; Core #245 owns actual
original ZIP byte admission tests and Work #247 owns retained real source.
"""
from __future__ import annotations

import copy
import unittest

from research_wp_r0.aql_factory_authentic_research_admission import (
    ResearchAdmissionError, _digest, seal,
)
from research_wp_r0.aql_factory_core_price_rule_port import (
    from_core_original_price_query,
)
from test_aql_factory_historical_rule_projection import fixture


def core_fixture():
    p = fixture()
    cutoff = p["bars"][-1]["close_ms"] + 10_000_000
    plan = {
        "schema": "aql.factory.historical-rule-work-plan.v1",
        "dataset_id": p["dataset_id"],
        "dataset_version": p["dataset_version"],
        "source_bytes_sha256": p["source_bytes_sha256"],
        "manifest_integrity_sha256": p["source_manifest_sha256"],
        "correction_parent_source_sha256": None,
        "decision_cutoff_ms": cutoff,
        "holdout": p["holdout"],
        "execution_authority": p["execution_authority"],
        "market": "SPOT", "direction": "LONG",
        "trial_budget": p["trial_budget"], "trials": p["trials"],
        "selected_attempt_id": p["selected_attempt_id"],
        "strategy": p["strategy"], "plan_digest": p["plan_digest"],
        "universe": p["universe"],
        "opportunity_count": p["opportunity_count"],
        "opportunities": p["opportunities"],
        "research_window": p["research_window"],
        "width_ms": p["width_ms"], "costs": p["costs"],
    }
    native = []
    witnesses = []
    for i, b in enumerate(p["bars"]):
        checksum = _digest({"synthetic_mock_core_bar": i,
                            "normalized_bar_digest": b["bar_sha256"]})
        item = {
            "bar_open_ms": b["open_ms"], "bar_close_ms": b["close_ms"],
            "open": b["open"], "high": b["high"], "low": b["low"],
            "close": b["close"], "volume": b["volume"],
            "checksum": checksum,
            "observation_lower_bound_ms": b["close_ms"]+1,
            "historical_known_at_ms": None,
            "availability_kind": "RETROSPECTIVE",
        }
        native.append(item)
        witnesses.append({
            "bar_open": b["open_ms"], "bar_close": b["close_ms"],
            "checksum": checksum,
            "observation_cutoff_ms": b["close_ms"]+1,
            "availability_kind": "RETROSPECTIVE",
        })
    base = {
        "schema": "aql.bridge.custody-range.v1",
        "dataset_id": p["dataset_id"],
        "version": p["dataset_version"],
        "source_bytes_sha256": p["source_bytes_sha256"],
        "manifest_integrity_sha256": p["source_manifest_sha256"],
        "decision_cutoff_ms": cutoff,
        "status": "COMPLETE",
        "required_bar_count": len(witnesses),
        "available_bar_count": len(witnesses),
        "missing_bar_opens": [],
        "bars": witnesses,
    }
    admission = {
        "schema": "aql.core.historical-original-admission.v1",
        "status": "ORIGINAL_PIN_MATCHED_PROVENANCE_PENDING",
        "source_kind": "BINANCE_KLINES_ZIP",
        "dataset_id": p["dataset_id"],
        "version": p["dataset_version"],
        "source_bytes_sha256": p["source_bytes_sha256"],
        "manifest_integrity_sha256": p["source_manifest_sha256"],
        "native_csv_member_sha256": "c"*64,
        "native_checksum_file_sha256": "d"*64,
        "packet_sha256": "e"*64,
        "custody_receipt_sha256": "f"*64,
        "correction_parent_source_sha256": None,
        "correction_reason": None,
        "decision_cutoff_ms": cutoff,
        "coverage": "COMPLETE",
        "missing_bar_opens": [],
        "required_bar_count": len(witnesses),
        "available_bar_count": len(witnesses),
        "query": {"status": "OK", "result": base},
        "authenticated_source": "NOT_ATTESTED",
        "independent_provenance": "NOT_ATTESTED",
        "source_available_at_cutoff": "NOT_ATTESTED",
        "confirmed_pit": "NOT_ATTESTED",
        "complete_market_universe": "NOT_ATTESTED",
        "factory_scientific_input": "BLOCKED",
        "paper_live_trading": "DISABLED",
    }
    admission["manifest_record_sha256"] = _digest(admission)
    price = {
        "schema": "aql.core.historical-price-custody-query.v1",
        "status": "OK", "error": None,
        "dataset_id": p["dataset_id"], "version": p["dataset_version"],
        "source_bytes_sha256": p["source_bytes_sha256"],
        "manifest_integrity_sha256": p["source_manifest_sha256"],
        "decision_cutoff_ms": cutoff, "coverage": "COMPLETE",
        "required_bar_count": len(native),
        "available_bar_count": len(native),
        "missing_bar_opens": [], "bars": native,
        "numeric_projection": "HISTORICAL_LIBRARY_FLOAT_FROM_ORIGINAL_NATIVE_DECIMALS",
        "historical_known_at_ms": None,
        "source_availability": "RETROSPECTIVE_NON_PIT",
        "scientific_pit": "NOT_ATTESTED",
        "factory_scientific_input": "BLOCKED_PENDING_INDEPENDENT_EVIDENCE",
        "paper_live_trading": "DISABLED",
    }
    price["price_query_sha256"] = _digest(price)
    return admission, price, seal(plan)


def repin_admission(admission):
    admission["manifest_record_sha256"] = _digest({
        k: v for k, v in admission.items() if k != "manifest_record_sha256"
    })


def repin_price(price):
    price["price_query_sha256"] = _digest({
        k: v for k, v in price.items() if k != "price_query_sha256"
    })


class CorePriceRulePortTests(unittest.TestCase):
    def test_original_unverified_core_to_ten_kernel_port(self):
        args = core_fixture()
        before = copy.deepcopy(args)
        a = from_core_original_price_query(*args)
        b = from_core_original_price_query(*args)
        self.assertEqual(args, before)
        self.assertEqual(a, b)
        self.assertEqual(a["source_evidence"], "ORIGINAL_UNVERIFIED")
        self.assertEqual(a["authentic_source_attestation"], "NOT_ATTESTED")
        self.assertEqual(a["historical_pit"], "NOT_ATTESTED")
        self.assertEqual(a["scientific_result"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(a["factory_report"]["trial_budget"], 53)
        self.assertGreater(a["factory_report"]["decision_counts"].get(
            "ENTRY_TRIGGERED", 0), 0)
        self.assertEqual(a["factory_report"]["unverified_known_at_count"],
                         len(args[1]["bars"]))
        self.assertEqual(a["artifact_sha256"], _digest({
            k: v for k, v in a.items() if k != "artifact_sha256"}))

    def test_test_only_pin_never_source_upgrade(self):
        admission, price, plan = core_fixture()
        admission["status"] = "TEST_ONLY_INTEGRITY_VERIFIED"
        repin_admission(admission)
        out = from_core_original_price_query(admission, price, plan)
        self.assertEqual(out["source_evidence"], "TEST_ONLY")
        self.assertEqual(out["scientific_result"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(out["factory_report"]["source_original_bytes_verified"])

    def test_core_provenance_negative_matrix(self):
        cases = [
            ("core-sha", lambda a,p,s: a.update(source_bytes_sha256="9"*64)),
            ("source-sha", lambda a,p,s: p.update(source_bytes_sha256="9"*64)),
            ("manifest", lambda a,p,s: p.update(manifest_integrity_sha256="8"*64)),
            ("partial", lambda a,p,s: p.update(coverage="PARTIAL")),
            ("gap", lambda a,p,s: p["bars"].pop()),
            ("renamed", lambda a,p,s: p.update(schema="v2")),
            ("future-known", lambda a,p,s: p["bars"][5].update(historical_known_at_ms=p["bars"][5]["bar_close_ms"]+1)),
            ("checksum", lambda a,p,s: p["bars"][5].update(checksum="4"*64)),
            ("fake-pit", lambda a,p,s: p.update(scientific_pit="ATTESTED")),
            ("fake-core-auth", lambda a,p,s: a.update(authenticated_source="ATTESTED")),
            ("future-query", lambda a,p,s: s.update(decision_cutoff_ms=1)),
            ("cost-model", lambda a,p,s: s["costs"].update(fee_entry_bps="-10")),
            ("strategy", lambda a,p,s: s["strategy"]["definition"]["risk"].update(holding_bars=1)),
            ("missing-trials", lambda a,p,s: s["trials"].pop()),
            ("unknown-market", lambda a,p,s: s.update(market="PERP")),
            ("empty-original", lambda a,p,s: a.update(native_csv_member_sha256=None)),
            ("correction", lambda a,p,s: a.update(correction_parent_source_sha256="5"*64)),
            ("holdout", lambda a,p,s: s.update(holdout="OPEN")),
            ("missing-arm", lambda a,p,s: s.update(opportunity_count=1)),
            ("untrusted-coverage", lambda a,p,s: s["universe"].update(source_coverage="ATTESTED")),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                a,p,s=core_fixture()
                s={k:v for k,v in s.items() if k != "artifact_sha256"}
                mutate(a,p,s)
                repin_admission(a)
                repin_price(p)
                with self.assertRaises((ResearchAdmissionError, ValueError)):
                    from_core_original_price_query(a,p,seal(s))

    def test_tampered_unrepinned_core_receipt_and_prices(self):
        a,p,s=core_fixture()
        a["coverage"] = "UNKNOWN"
        with self.assertRaises(ResearchAdmissionError):
            from_core_original_price_query(a,p,s)
        a,p,s=core_fixture()
        p["bars"][0]["close"] = 9999
        with self.assertRaises(ResearchAdmissionError):
            from_core_original_price_query(a,p,s)
        a,p,s=core_fixture()
        s["costs"]["fee_entry_bps"] = "999"
        with self.assertRaises(ResearchAdmissionError):
            from_core_original_price_query(a,p,s)


if __name__ == "__main__":
    unittest.main()
