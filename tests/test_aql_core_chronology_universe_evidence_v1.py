"""Issue #249: source-locked chronology/universe evidence boundary TEST_ONLY.

There is no independent vendor issuance/2024 known-at or real full-market
catalog here. These tests DO NOT promote self-authored sidecars to PIT.
"""
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    OfflineBridgeStager, digest,
)
from research_wp_r0.aql_authenticated_historical_admission_v1 import (
    admit_original_bytes,
)
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.aql_core_chronology_universe_evidence_v1 import (
    CHRONOLOGY_SCHEMA, UNIVERSE_SCHEMA, SCHEMA, EvidenceBoundaryError,
    assess_chronology_universe,
)
from research_wp_r0.historical_library import HistoricalLibrary
from test_aql_archive_custody_bridge_v1 import START, WIDTH, N, spec
from test_aql_native_binance_zip_v1 import native_source, request

S = "a"*64


def sealed(doc, name="evidence_sha256"):
    return {**doc, name:digest(doc)}


class ChronologyUniverseBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stager = OfflineBridgeStager(self.tmp.name)
        self.lib = HistoricalLibrary()
        self.spec = spec(source_label="native-monthly-zip")
        raw, csv, checksum, pin = native_source()
        self.cutoff = START + N*WIDTH + 2000
        self.admission = admit_original_bytes(
            raw, pin, self.spec, stager=self.stager, library=self.lib,
            decision_cutoff_ms=self.cutoff, checksum_file_bytes=checksum,
        )
        self.price = query_price_custody(
            self.lib, request(self.spec, self.cutoff),
            expected_source_sha256=self.admission["source_bytes_sha256"],
            expected_manifest_integrity_sha256=
                self.admission["manifest_integrity_sha256"],
        )
        self.assertEqual(self.price["status"], "OK")

    def assess(self, chronology=None, universe=None):
        return assess_chronology_universe(
            self.admission, self.price,
            chronology_evidence=chronology, universe_evidence=universe,
        )

    def chronology(self):
        a = self.admission
        b = self.price["bars"]
        return sealed({
            "schema":CHRONOLOGY_SCHEMA,
            "dataset_id":a["dataset_id"], "version":a["version"],
            "original_zip_sha256":a["source_bytes_sha256"],
            "manifest_integrity_sha256":a["manifest_integrity_sha256"],
            "issuer_name":"BINANCE_CLAIM_TEST_ONLY",
            "evidence_reference":"UNVERIFIED_RETENTION_TEST",
            "evidence_bytes_sha256":S,
            "observed_capture_ms":START+N*WIDTH+10000,
            "claimed_publication_ms":None,
            "claimed_historical_known_at_ms":None,
            "correction_state":"UNKNOWN",
            "correction_parent_sha256":None,
            "bar_claims":[{
                "bar_open_ms": b[0]["bar_open_ms"],
                "bar_checksum": b[0]["checksum"],
                "claimed_known_at_ms": b[0]["bar_close_ms"]+1000,
                "evidence_record_sha256": S,
            }],
        })

    def universe(self):
        a = self.admission
        p = self.price
        return sealed({
            "schema":UNIVERSE_SCHEMA,
            "dataset_id":a["dataset_id"],"version":a["version"],
            "original_zip_sha256":a["source_bytes_sha256"],
            "manifest_integrity_sha256":a["manifest_integrity_sha256"],
            "market":"SPOT", "venue":"BINANCE","timeframe":"1m",
            "start_ms":START,"end_exclusive_ms":START+N*WIDTH,
            "source_manifest_sha256":S,
            "inventory_observed_at_ms":None,
            "completeness_claim":"DECLARED_COMPLETE_UNVERIFIED",
            "members":[{
                "symbol":"BTCUSDT", "market":"SPOT", "venue":"BINANCE",
                "timeframe":"1m", "status":"INCLUDED",
                "missing_bar_opens":[], "exclusion_reason":None,
            },{
                "symbol":"ETHUSDT", "market":"SPOT", "venue":"BINANCE",
                "timeframe":"1m", "status":"EXCLUDED",
                "missing_bar_opens":[], "exclusion_reason":"EXCLUDED_TEST",
            }],
            "opportunities":[{
                "opportunity_id":"OPP-TEST-01","symbol":"BTCUSDT",
                "bar_open_ms":p["bars"][0]["bar_open_ms"],
                "status":"ELIGIBLE", "reason":"TEST_ONLY",
                "source_bar_checksum":p["bars"][0]["checksum"],
            },{
                "opportunity_id":"OPP-TEST-02","symbol":"BTCUSDT",
                "bar_open_ms":p["bars"][1]["bar_open_ms"],
                "status":"UNKNOWN", "reason":"UNKNOWN_TEST",
                "source_bar_checksum":p["bars"][1]["checksum"],
            }],
        })

    def test_absence_is_explicit_unknown_not_fake_zero(self):
        result = self.assess()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["chronology"]["evidence_state"],
                         "CHRONOLOGY_EVIDENCE_NOT_AVAILABLE")
        self.assertEqual(result["universe"]["evidence_state"],
                         "UNIVERSE_EVIDENCE_NOT_AVAILABLE")
        self.assertIsNone(result["independent_opportunity_denominator"])
        self.assertIsNone(result["universe"]["reported_opportunity_count"])
        self.assertEqual(result["factory_scientific_input"],"BLOCKED")
        self.assertEqual(result["historical_pit"],"NOT_ATTESTED")
        self.assertEqual(result["assessment_sha256"],
                         digest({k:v for k,v in result.items()
                                 if k != "assessment_sha256"}))

    def test_supplied_unverified_evidence_is_deterministic_non_authoritative(self):
        c, u = self.chronology(), self.universe()
        first, second = self.assess(c,u), self.assess(c,u)
        self.assertEqual(first,second)
        self.assertEqual(first["chronology"]["bar_timestamps_claimed"],1)
        self.assertEqual(first["chronology"]["bar_timestamps_unknown"],N-1)
        self.assertEqual(first["universe"]["reported_member_count"],2)
        self.assertEqual(first["universe"]["reported_exclusions"],1)
        self.assertEqual(first["universe"]["reported_opportunity_count"],2)
        self.assertEqual(first["universe"]["reported_status_counts"]["UNKNOWN"],1)
        self.assertIsNone(first["independent_opportunity_denominator"])
        self.assertEqual(first["universe"]["independently_complete_universe"],
                         "NOT_ATTESTED")
        self.assertEqual(first["historical_pit"],"NOT_ATTESTED")

    def test_tampered_or_resealed_core_price_parent_rejected(self):
        wrong=deepcopy(self.price);wrong["source_bytes_sha256"]="0"*64
        wrong["price_query_sha256"]=digest({k:v for k,v in wrong.items()
                                             if k!="price_query_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"CORE_SOURCE_PRICE_DRIFT"):
            assess_chronology_universe(self.admission,wrong)
        bad=deepcopy(self.admission);bad["decision_cutoff_ms"]+=1
        with self.assertRaisesRegex(EvidenceBoundaryError,"EVIDENCE_SEAL_INVALID"):
            assess_chronology_universe(bad,self.price)

    def test_chronology_source_and_manifest_tampering(self):
        c=self.chronology();c["issuer_name"]="EVIL"
        with self.assertRaisesRegex(EvidenceBoundaryError,"EVIDENCE_SEAL_INVALID"):
            self.assess(c)
        c=self.chronology();c["original_zip_sha256"]="0"*64
        c["evidence_sha256"]=digest({k:v for k,v in c.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"CHRONOLOGY_SOURCE_DRIFT"):
            self.assess(c)

    def test_future_capture_and_correction_parent_conflict(self):
        c=self.chronology()
        c["observed_capture_ms"]=START
        c["evidence_sha256"]=digest({k:v for k,v in c.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"CHRONOLOGY_BAR_AFTER_CAPTURE"):
            self.assess(c)
        c=self.chronology();c["correction_state"]="CORRECTION_CLAIM"
        c["evidence_sha256"]=digest({k:v for k,v in c.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"CORRECTION_PARENT_DRIFT"):
            self.assess(c)

    def test_known_at_before_bar_closed_refused(self):
        c=self.chronology()
        c["bar_claims"][0]["claimed_known_at_ms"]=START
        c["evidence_sha256"]=digest({k:v for k,v in c.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"CHRONOLOGY_BAR_FUTURE_LEAK_OR_TIME"):
            self.assess(c)

    def test_duplicate_claimed_bar_and_forged_checksum(self):
        c=self.chronology();c["bar_claims"].append(dict(c["bar_claims"][0]))
        c["evidence_sha256"]=digest({k:v for k,v in c.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"CHRONOLOGY_BAR_PARENT"):
            self.assess(c)
        c=self.chronology();c["bar_claims"][0]["bar_checksum"]="f"*64
        c["evidence_sha256"]=digest({k:v for k,v in c.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"CHRONOLOGY_BAR_PARENT"):
            self.assess(c)

    def test_forged_universe_source_and_duplicate_opportunity(self):
        u=self.universe();u["original_zip_sha256"]="f"*64
        u["evidence_sha256"]=digest({k:v for k,v in u.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"UNIVERSE_SOURCE_DRIFT"):
            self.assess(universe=u)
        u=self.universe();u["opportunities"].append(dict(u["opportunities"][0]))
        u["evidence_sha256"]=digest({k:v for k,v in u.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"OPPORTUNITY_IDENTITY_OR_CLOCK"):
            self.assess(universe=u)

    def test_invalid_member_gaps_and_opportunity_status(self):
        u=self.universe();u["members"][0]["missing_bar_opens"]=[START+WIDTH]
        u["opportunities"][1]["status"]="ELIGIBLE"
        u["evidence_sha256"]=digest({k:v for k,v in u.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"MISSING_OPPORTUNITY_PROMOTED"):
            self.assess(universe=u)
        u=self.universe();u["opportunities"][0]["bar_open_ms"]=START+N*WIDTH
        u["evidence_sha256"]=digest({k:v for k,v in u.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"OPPORTUNITY_IDENTITY_OR_CLOCK"):
            self.assess(universe=u)

    def test_excluded_member_cannot_be_eligible(self):
        u=self.universe()
        u["opportunities"].append({
            "opportunity_id":"OPP-EXCLUDED-01","symbol":"ETHUSDT",
            "bar_open_ms":START, "status":"ELIGIBLE","reason":"BAD_TEST",
            "source_bar_checksum":None,
        })
        u["evidence_sha256"]=digest({k:v for k,v in u.items()
                                     if k!="evidence_sha256"})
        with self.assertRaisesRegex(EvidenceBoundaryError,"EXCLUDED_MEMBER_OPPORTUNITY"):
            self.assess(universe=u)


if __name__ == "__main__":
    unittest.main()
