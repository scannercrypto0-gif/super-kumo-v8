import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_w1_opportunity_outcomes import (
    BAR_MS, HORIZONS, AppendOnlyOutcomeJournal, EvidenceError,
    RetrospectiveSnapshot, market_outcome, reconcile,
)


def snap(t=1704067200000, direction="LONG"):
    return RetrospectiveSnapshot("trial", "manifest", "opp", "producer", "sha", t,
                                 t + 2000, "REJECTED", "reason", direction,
                                 "NOT_ESTABLISHED", None, "context")


def bars(t, count, *, both=False):
    rows = []
    for i in range(count):
        rows.append(dict(open_ms=t + i * BAR_MS, open=100, high=110 if both else 102,
                         low=90 if both else 98, close=100, finalized=True))
    return rows


class W1OutcomesTest(unittest.TestCase):
    def test_4_24_72_exact_windows(self):
        s = snap()
        for h, n in zip(HORIZONS, (16, 96, 288)):
            result = market_outcome(s, h, bars(s.decision_cutoff_ms, n),
                                    source_version="source1",
                                    source_end_exclusive_ms=s.decision_cutoff_ms + h)
            self.assertEqual(result["status"], "EVALUATED")
            self.assertEqual(result["bar_count"], n)
            self.assertEqual(result["reference_kind"], "OPEN_AT_CUTOFF_NON_EXECUTABLE")

    def test_archive_end_and_missing(self):
        s = snap()
        t = s.decision_cutoff_ms
        self.assertEqual(market_outcome(s, HORIZONS[0], [], source_version="s",
                         source_end_exclusive_ms=t, archive_finalized=True)["status"], "MISSING_DATA")
        self.assertEqual(market_outcome(s, HORIZONS[0], [], source_version="s",
                         source_end_exclusive_ms=t, archive_finalized=False)["status"], "PENDING")
        self.assertEqual(market_outcome(s, HORIZONS[0], bars(t, 15), source_version="s",
                         source_end_exclusive_ms=t + HORIZONS[0])["reason"], "GAPPED_WINDOW")

    def test_complete_excursion_does_not_prove_order(self):
        s = snap()
        r = market_outcome(s, HORIZONS[0], bars(s.decision_cutoff_ms, 16, both=True),
                           source_version="s", source_end_exclusive_ms=s.decision_cutoff_ms + HORIZONS[0])
        self.assertEqual(r["status"], "EVALUATED")
        self.assertEqual(r["execution_status"], "NOT_OBSERVED")
        self.assertEqual(r["order_resolution"], "NOT_APPLICABLE")
        self.assertAlmostEqual(r["mfe"], .1)
        self.assertAlmostEqual(r["mae"], .1)

    def test_no_fabricated_pit_and_unknown_direction(self):
        with self.assertRaises(EvidenceError):
            RetrospectiveSnapshot("t", "m", "o", "p", "e", 1704067200000,
                                  1704067202000, "REJECTED", None, "LONG",
                                  "YES", None, "ctx")
        s = snap(direction=None)
        self.assertEqual(market_outcome(s, HORIZONS[0], bars(s.decision_cutoff_ms, 16),
                         source_version="s",
                         source_end_exclusive_ms=s.decision_cutoff_ms + HORIZONS[0])["status"], "UNKNOWN")

    def test_exact_join_conflict(self):
        s = snap()
        e = dict(trial_id="trial", opportunity_id="opp", producer_event_id="producer",
                 run_manifest_sha256="manifest", envelope_sha256="sha",
                 decision_cutoff_ms=s.decision_cutoff_ms, decision_ms=s.decision_ms,
                 signal_state="REJECTED", reason_code="reason",
                 prefix_start_ms=1, prefix_end_exclusive_ms=s.decision_cutoff_ms,
                 prefix_bar_checksums_sha256="prefix", input_disposition="ACCEPTED",
                 strategy_id="strategy", dataset_version=1,
                 feature_policy_version="v1", gap_inventory_sha256="gap",
                 correction_lineage_sha256="lineage")
        selection = dict(trial_id="trial", opportunity_id="opp", producer_event_id="producer",
                         decision_cutoff_ms=s.decision_cutoff_ms, signal_state="REJECTED",
                         reason_code="reason", context_digest="ctx",
                         decision_ms=s.decision_ms, prefix_start_ms=1,
                         prefix_end_exclusive_ms=s.decision_cutoff_ms,
                         prefix_bar_checksums_sha256="prefix", input_disposition="ACCEPTED",
                         strategy_id="strategy", dataset_version=1)
        self.assertEqual(len(reconcile([e], [selection])), 1)
        self.assertEqual(reconcile([e], [selection])[0].eligibility, "NOT_ESTABLISHED")
        with self.assertRaises(EvidenceError):
            reconcile([e], [{**selection, "prefix_bar_checksums_sha256": "tampered"}])
        with self.assertRaises(EvidenceError):
            reconcile([e, e], [selection, selection])

    def test_no_negative_excursions_on_monotone_move(self):
        s = snap()
        t = s.decision_cutoff_ms
        rising = [dict(open_ms=t + i * BAR_MS, open=100 + i,
                       high=101 + i, low=100 + i, close=101 + i,
                       finalized=True) for i in range(16)]
        r = market_outcome(s, HORIZONS[0], rising, source_version="s",
                           source_end_exclusive_ms=t + HORIZONS[0])
        self.assertEqual(r["status"], "EVALUATED")
        self.assertEqual(r["mae"], 0.0)
        self.assertEqual(r["window_quality"], "COMPLETE_FINALIZED")

    def test_append_replay_conflict_corruption(self):
        s = snap()
        t = s.decision_cutoff_ms
        p = market_outcome(s, HORIZONS[0], bars(t, 16), source_version="s",
                           source_end_exclusive_ms=t + HORIZONS[0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "outcomes.jsonl"
            journal = AppendOnlyOutcomeJournal(path)
            self.assertTrue(journal.append(p))
            self.assertFalse(journal.append(p))
            self.assertFalse(AppendOnlyOutcomeJournal(path).append(p))
            with self.assertRaises(EvidenceError):
                journal.append({**p, "mfe": 999})
            with path.open("ab") as f:
                f.write(b"corrupted tail")
            with self.assertRaises(EvidenceError):
                AppendOnlyOutcomeJournal(path)


if __name__ == "__main__":
    unittest.main()
