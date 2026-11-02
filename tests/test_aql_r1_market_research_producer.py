"""R1 changed-seam tests: no forward bars, source/version, complete 2N ledger."""
from __future__ import annotations

import copy
import io
import zipfile
import unittest
from datetime import datetime, timezone

from research_wp_r0.aql_r1_market_research_producer import (
    BAR_MS, B1_ARTIFACT_SHA256, B1_REPORT_SHA256, REGIME_VERSION,
    INDICATOR_VERSION, PROOF_STATUS, R1Rejected, SOURCE_STATUS,
    build_handoff, canonical, compute_features, load_pinned_originals,
    make_opportunity, parse_pinned_month, validate_clock,
)


def source_and_market():
    source = {
        "symbol": "BTCUSDT", "market": "SPOT", "interval": "15m",
        "mode": SOURCE_STATUS, "external_evidence": PROOF_STATUS,
        "source_version": "2024-retrospective-original-archive-snapshot",
        "archive_artifact_sha256": B1_ARTIFACT_SHA256,
        "accepted_market_report_sha256": B1_REPORT_SHA256,
        "market_lock_sha256": "267964c81772b1a118cd740c8d8a6bc6a757e615a98d80769a68e5a12df34679",
        "source_available_at_ms": None,
        "correction_published_at_ms": None,
        "correction_generation": "UNKNOWN_UNATTESTED",
        "months": [
            {"name": f"BTCUSDT-15m-2024-{m:02}.zip",
             "member_sha256": str(m)*64} for m in (2,7)
        ],
    }
    market = {}
    for month in (2,7):
        first = int(datetime(2024, month, 1, tzinfo=timezone.utc).timestamp()*1000)
        rows = []
        for i in range(1600):
            t = first + i * BAR_MS
            price = 40000 + i/10 + month*7
            rows.append({
                "open_ms": t, "close_exclusive_ms": t + BAR_MS,
                "open": f"{price:.2f}", "high": f"{price + 5:.2f}",
                "low": f"{price - 5:.2f}", "close": f"{price:.2f}",
                "volume": "2.00000000",
            })
        market[month] = rows
    return source, market


class R1CoreResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.market = source_and_market()

    def test_deterministic_2024_sample_and_full_arms(self):
        first = build_handoff(self.market, self.source)
        second = build_handoff(self.market, self.source)
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(first["counts"]["n_opportunities"], 32)
        self.assertEqual(first["counts"]["arm_slots_2n"], 64)
        self.assertEqual(first["counts"]["expected_outcome_rows_6n"], 192)
        self.assertEqual(first["counts"]["features_ready"], 32)
        self.assertEqual(len({r["opportunity_id"] for r in first["opportunities"]}), 32)
        self.assertEqual({r["regime"]["state"] for r in first["opportunities"]},
                         {"UP_TREND"})
        self.assertTrue(all(len(r["arms"])==2
            and all(a["capture_status"]=="MISSING_CAPTURE" and
                    a["direction"] is None for a in r["arms"])
            and r["decision_status"]=="UNKNOWN_ORIGINAL_DECISION"
            and r["source_available_at_ms"] is None
            and r["pit_status"]=="BLOCKED_EXTERNAL_EVIDENCE"
            for r in first["opportunities"]))
        self.assertEqual(first["feature_version"], INDICATOR_VERSION)
        self.assertEqual(first["regime_version"], REGIME_VERSION)

    def test_no_lookahead_mutating_later_bar_does_not_change_snapshot(self):
        row = self.market[2]
        i = 1350
        first = make_opportunity(row[:i+1],self.source,
                 month_member_sha256="2"*64)
        new = copy.deepcopy(row)
        new[i+1]["close"] = "99999999"
        again = make_opportunity(new[:i+1],self.source,
                 month_member_sha256="2"*64)
        self.assertEqual(canonical(first), canonical(again))

    def test_future_bar_rejected_at_earlier_cutoff(self):
        prefix = self.market[2][:1400]
        earlier = prefix[-2]["close_exclusive_ms"]
        with self.assertRaisesRegex(R1Rejected, "FUTURE_BAR_LOOKAHEAD"):
            compute_features(prefix, earlier)

    def test_gap_and_duplicate_bars_fail_closed(self):
        bars = self.market[2][:260]
        with self.assertRaisesRegex(R1Rejected, "PREFIX_MISSING_OR_DUPLICATE_BAR"):
            compute_features(bars[:50]+bars[51:],bars[-1]["close_exclusive_ms"])
        with self.assertRaisesRegex(R1Rejected, "PREFIX_MISSING_OR_DUPLICATE_BAR"):
            compute_features(bars[:15]+bars[14:],bars[-1]["close_exclusive_ms"])

    def test_insufficient_warmup_is_unknown_not_dropped(self):
        early = self.market[2][:30]
        result = make_opportunity(early,self.source,
                  month_member_sha256="2"*64)
        self.assertEqual(result["features"]["readiness"],"INSUFFICIENT_WARMUP")
        self.assertEqual(result["regime"]["state"],"UNKNOWN")
        self.assertEqual(len(result["arms"]), 2)

    def test_source_version_drift_refused(self):
        source = copy.deepcopy(self.source)
        source["source_version"] = "arbitrary-new-vintage"
        with self.assertRaisesRegex(R1Rejected, "SOURCE_SCOPE_OR_PROVENANCE_DRIFT"):
            build_handoff(self.market,source)

    def test_rehashed_but_changed_accepted_archive_sha_refused(self):
        source = copy.deepcopy(self.source)
        source["archive_artifact_sha256"] = "f"*64
        with self.assertRaisesRegex(R1Rejected, "SOURCE_SCOPE_OR_PROVENANCE_DRIFT"):
            build_handoff(self.market,source)

    def test_correction_or_source_arrival_after_cutoff_refused(self):
        b = self.market[2][200]
        cutoff = b["close_exclusive_ms"]
        with self.assertRaisesRegex(R1Rejected,"CORRECTION_AFTER_CUTOFF"):
            validate_clock(b,cutoff,correction_published_at_ms=cutoff+1)
        with self.assertRaisesRegex(R1Rejected,"SOURCE_AFTER_CUTOFF"):
            validate_clock(b,cutoff,source_available_at_ms=cutoff+1)

    def test_original_historical_strategy_decision_not_inferred(self):
        result=build_handoff(self.market,self.source)
        self.assertEqual(result["counts"]["verified_original_strategy_decisions"],0)
        self.assertTrue(all(x["strategy_version"]=="NOT_CONNECTED" and
                           x["strategy_signal"] is None and
                           not x["trade_or_alpha_evidence"]
                           for x in result["opportunities"]))

    def test_pinned_market_zip_digest_rejects_fake_source(self):
        with self.assertRaisesRegex(R1Rejected,"B1_ARTIFACT_SHA_MISMATCH"):
            load_pinned_originals(b"this-is-not-the-original-2024-archive")

    def test_member_archive_checksum_mismatch_refused(self):
        name="BTCUSDT-15m-2024-02.zip"
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,"w") as z:
            z.writestr(name[:-4]+".csv","bad")
        outer=io.BytesIO()
        with zipfile.ZipFile(outer,"w") as z:
            z.writestr("b1-originals/"+name,archive.getvalue())
            z.writestr("b1-originals/"+name+".CHECKSUM","bad")
        with zipfile.ZipFile(io.BytesIO(outer.getvalue())) as z:
            with self.assertRaisesRegex(R1Rejected,"ARCHIVE_PIN_DRIFT"):
                parse_pinned_month(z,{"name":name,"archive_bytes":len(archive.getvalue()),
                    "archive_sha256":"a"*64,"checksum_sha256":"b"*64,
                    "member_sha256":"c"*64,"first_open_ms":0,"bars":1})

    def test_missing_month_sample_refused(self):
        with self.assertRaisesRegex(R1Rejected,"MISSING_SOURCE_MONTH"):
            build_handoff({2:self.market[2]},self.source)

    def test_correction_history_never_retroactively_certified(self):
        result=build_handoff(self.market,self.source)
        self.assertIsNone(result["source"]["source_available_at_ms"])
        self.assertEqual(result["source"]["correction_generation"],"UNKNOWN_UNATTESTED")
        self.assertEqual(result["external_issuer_correction_clock_and_freeze"],
                         PROOF_STATUS)


if __name__ == "__main__":
    unittest.main()
