"""Changed-seam end-to-end controlled RAW CSV -> bars -> F1 research outcomes.

All host callbacks are synthetic test doubles, not independent PIT authority.
"""
import copy
import hashlib
import unittest

from research_wp_r0.aql_w1_raw_research_demo import (
    derive_15m_bars_from_original_csv, run_controlled_raw_research_demo,
)
from research_wp_r0.aql_w1_market_window_adapter import BAR_MS
from research_wp_r0.aql_w1_opportunity_outcomes import EvidenceError
from research_wp_r0.aql_f1_parent_witness_v1 import make_parent_bound_provenance_verifier
from tests.test_aql_w1_raw_parent_bridge import fixture
from tests.test_aql_w1_core_parent_market_integration import core_evidence


class ControlledEndToEnd(unittest.TestCase):
    def build(self, *, missing_manifest=False, tamper=False,
              correction=False, source=False, anchor=False, market=False,
              gaps=False, asof_ms=None, extra_pair=False):
        plan, record, registry, parent, manifest, old_derived, old_lineage = fixture()
        cutoff = plan["decision_cutoff_ms"]
        # Construct an actual CSV fixture whose original bytes, 288 bars and
        # derived JSON bytes have three independent deterministic digest IDs.
        starts = [cutoff + i * BAR_MS for i in range(288)]
        if gaps:
            starts.remove(cutoff + 8 * BAR_MS)
        raw = ("open_ms,high,low\n" +
               "".join(f"{x},110,95\n" for x in starts)).encode()
        manifest["content_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["byte_length"] = len(raw)
        from datetime import datetime, timezone
        end = cutoff + 288 * BAR_MS
        manifest["coverage_start_utc"] = datetime.fromtimestamp(
            cutoff / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest["coverage_end_utc"] = datetime.fromtimestamp(
            end / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest["admitted_at_utc"] = datetime.fromtimestamp(
            (end + BAR_MS) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        evidence = core_evidence(record, raw, manifest)
        verifier = make_parent_bound_provenance_verifier(
            registry, lambda _: evidence,
            source_attestor=(lambda _: True) if source else None,
            freeze_attestor=lambda _: True,
            durable_anchor_verifier=(lambda _: True) if anchor else None,
            parent_witness=lambda _: True)
        callbacks = dict(
            parent_manifest=lambda meta, raw_bytes: True,
            derivation=lambda info, parent_raw, derived: True,
            market_receipt=(lambda info, meta: True) if market else None)
        if tamper:
            raw += b"CORRUPT"
        if correction:
            manifest["correction_generation"] = 2
        report = run_controlled_raw_research_demo(
            [plan], [record], parent_bytes_by_pair={plan["pair_id"]: raw},
            manifest_by_pair={} if missing_manifest else {plan["pair_id"]: manifest},
            indicator_registry=registry,
            normalization_policy="controlled_csv_15m.v1",
            source_witnesses={plan["pair_id"]: callbacks},
            proof_verifier=verifier, asof_ms=asof_ms)
        return report, plan, raw, manifest

    def test_end_to_end_288_bars_full_denominator_and_raw_trace(self):
        report, plan, raw, manifest = self.build(market=True)
        self.assertEqual(report["scheduled_total"], 1)
        self.assertEqual(report["arm_slots"], 2)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertEqual(sorted(x["horizon_ms"] for x in report["outcomes"]),
                         sorted([4*3600000,24*3600000,72*3600000]*2))
        self.assertTrue(all(x["coverage_status"] == "COMPLETE"
                            for x in report["outcomes"]))
        self.assertEqual(report["capture_status_counts"],
                         {"MISSING_CAPTURE": 1, "UNVERIFIED": 1})
        self.assertTrue(all(x["max_favorable"] is None and
                            x["max_adverse"] is None and
                            x["measurement_class"] == "MARKET_ONLY"
                            for x in report["outcomes"]))
        trace = report["source_derivation_trace"][0]
        self.assertEqual(trace["parent_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(trace["derived_sha256"], trace["parent_sha256"])
        self.assertNotEqual(trace["parent_sha256"], plan["source_bytes_sha256"])
        self.assertTrue(report["controlled_demo_only"])
        self.assertFalse(report["real_raw_issuer_or_pit_proven"])

    def test_no_market_receipt_no_directional_measurement(self):
        report, *_ = self.build()
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(x["coverage_status"] == "UNKNOWN"
                            for x in report["outcomes"]))
        self.assertTrue(all(x["max_favorable"] is None for x in report["outcomes"]))

    def test_synthetic_core_witness_does_not_turn_demo_operational(self):
        report, *_ = self.build(source=True, anchor=True, market=True)
        self.assertEqual(report["capture_status_counts"],
                         {"MISSING_CAPTURE": 1, "RECORDED": 1})
        self.assertFalse(report["operational_pit_and_custody_proven"])
        self.assertFalse(report["real_raw_issuer_or_pit_proven"])

    def test_missing_manifest_keeps_full_denominator(self):
        report, *_ = self.build(missing_manifest=True, market=True)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(row["max_adverse"] is None for row in report["outcomes"]))
        self.assertTrue(all(row["coverage_status"] == "UNKNOWN" for row in report["outcomes"]))

    def test_tampered_original_raw_denied(self):
        report, *_ = self.build(tamper=True, market=True)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(row["coverage_status"] == "UNKNOWN" for row in report["outcomes"]))

    def test_changed_correction_vintage_denied(self):
        report, *_ = self.build(correction=True, market=True)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(row["coverage_status"] == "UNKNOWN" for row in report["outcomes"]))

    def test_missing_bar_preserves_six_rows(self):
        report, *_ = self.build(gaps=True, market=True)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(row["max_favorable"] is None for row in report["outcomes"]))

    def test_censored_horizon_preserves_six_rows(self):
        plan, _, _, _, _, _, _ = fixture()
        report, *_ = self.build(
            market=True, asof_ms=plan["decision_cutoff_ms"] + 5 * 3600000)
        self.assertEqual(report["outcome_rows"], 6)
        self.assertTrue(all(row["max_favorable"] is None for row in report["outcomes"]))

    def test_original_parser_bad_high_low_rejected(self):
        with self.assertRaises(EvidenceError):
            derive_15m_bars_from_original_csv(
                b"open_ms,high,low\n0,1,2\n",
                finalized_at_ms=900000, published_at_ms=900001)

    def test_original_parser_duplicate_grid_rejected(self):
        with self.assertRaises(EvidenceError):
            derive_15m_bars_from_original_csv(
                b"open_ms,high,low\n0,2,1\n0,2,1\n",
                finalized_at_ms=900000, published_at_ms=900001)


if __name__ == "__main__":
    unittest.main()
