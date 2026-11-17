from copy import deepcopy
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from aql.archive.contracts import digest
from aql.archive.source_view import as_of_view
from aql.recovery.rest_budget import RestBudget
from aql.recovery.gap_recovery import _fetch_klines, recover_gap


class SourceViewTests(unittest.TestCase):
    def setUp(self):
        self.market = ["BINANCE", "SPOT", "BTCUSDT", "BTC", "USDT"]
        self.rights = {
            "source": "fixture", "state": "VERIFIED", "uses": ["MONITOR_ONLY", "DECISION"],
            "valid_from": 0, "expires_at": 1000,
        }

    def record(self, **changes):
        return {
            "key": "news", "version": 1, "prior": None, "source": "fixture",
            "market": self.market.copy(), "use": "MONITOR_ONLY", "grade": "TEST_ONLY",
            "value": "original", "final": True, "event_at": 10, "published_at": 20,
            "received_at": 30, "committed_at": 31, "known_at": None, "witness": None,
            "rights": digest(self.rights), **changes,
        }

    def view(self, records, **changes):
        options = {
            "expected_keys": ["news"], "source": "fixture", "market": self.market,
            "cutoff": 80, "use": "MONITOR_ONLY", "max_age_ms": 50,
            "rights_by_digest": {digest(self.rights): self.rights},
            "pins": {(r["key"], r["version"]): digest(r) for r in records},
        }
        return as_of_view(records, **(options | changes))

    def test_revision_as_of_and_replay(self):
        original = self.record()
        revised = self.record(version=2, prior=digest(original), value="corrected",
                              published_at=90, received_at=91, committed_at=92)
        before = self.view([revised, original])
        self.assertEqual(before, self.view([original, revised]))
        self.assertEqual(before["slots"][0]["record"]["value"], "original")
        after = self.view([original, revised], cutoff=93)
        self.assertEqual(after["slots"][0]["record"]["value"], "corrected")
        before["slots"][0]["record"]["value"] = "caller mutation"
        self.assertEqual(original["value"], "original")

    def test_coverage_missing_stale_future_and_rolling(self):
        row = self.record()
        self.assertEqual(self.view([row], expected_keys=["news", "absent"])["coverage"], "PARTIAL")
        self.assertEqual(self.view([row], cutoff=81)["slots"][0]["reason"], "STALE")
        self.assertEqual(self.view([row], cutoff=30)["coverage"], "UNKNOWN")
        self.assertEqual(self.view([self.record(final=False)])["slots"][0]["reason"], "NOT_FINAL")

    def test_wrong_identity_and_tampering(self):
        row = self.record()
        with self.assertRaisesRegex(ValueError, "SOURCE_IDENTITY"):
            self.view([row], market=["OTHER"])
        tampered = deepcopy(row)
        tampered["value"] = "tampered"
        with self.assertRaisesRegex(ValueError, "SOURCE_DIGEST"):
            self.view([tampered], pins={("news", 1): digest(row)})
        with self.assertRaisesRegex(ValueError, "DUPLICATE_REVISION"):
            self.view([row, row])
        with self.assertRaisesRegex(ValueError, "MISSING_PINNED_REVISION"):
            self.view([], pins={("news", 1): digest(row)})
        with self.assertRaisesRegex(ValueError, "REVISION_LINEAGE"):
            self.view([row, self.record(version=2, prior="a" * 64)])

    def test_rights_and_pit_boundaries(self):
        row = self.record()
        with self.assertRaisesRegex(ValueError, "RIGHTS_PIN_UNAVAILABLE"):
            self.view([row], rights_by_digest={})
        self.rights["state"] = "UNKNOWN"
        self.assertEqual(self.view([self.record()])["slots"][0]["reason"], "RIGHTS_UNAVAILABLE")
        self.rights["state"] = "VERIFIED"
        with self.assertRaisesRegex(ValueError, "PIT_UNATTESTED"):
            self.view([self.record(grade="PIT_ATTESTED")])
        with self.assertRaisesRegex(ValueError, "PIT_OVERCLAIM"):
            self.view([self.record(known_at=35)])
        with self.assertRaisesRegex(ValueError, "CONSUMER_MODE"):
            self.view([self.record()], use="DECISION")
        denied = self.view([self.record(use="DECISION")], use="DECISION")
        self.assertEqual(denied["slots"][0]["reason"], "PIT_UNATTESTED")

    def test_denied_revision_does_not_restore_old_context(self):
        original = self.record()
        first_rights = self.rights.copy()
        self.rights["state"] = "DENIED"
        revised = self.record(version=2, prior=digest(original), committed_at=40)
        result = self.view([original, revised], rights_by_digest={
            digest(first_rights): first_rights, digest(self.rights): self.rights,
        })
        self.assertEqual(result["coverage"], "UNKNOWN")
        self.assertEqual(result["slots"][0]["reason"], "RIGHTS_UNAVAILABLE")

    def test_injected_shared_budget_cooldown_and_core_reserve(self):
        now = [0]
        budget = RestBudget(limit=10, reserve=2, clock=lambda: now[0])
        budget.acquire(8)
        with self.assertRaisesRegex(RuntimeError, "admission denied"):
            budget.acquire(1)
        budget.acquire(2, core=True)
        budget.cooldown(65)
        now[0] = 60
        with self.assertRaisesRegex(RuntimeError, "admission denied"):
            budget.acquire(1, core=True)
        now[0] = 65
        budget.acquire(1, core=True)
        self.assertEqual(budget.used, 1)

    def test_http_429_cooldown_blocks_other_recovery_calls(self):
        for header, delay in (("75", 75), ("NaN", 60), ("-1", 60)):
            with self.subTest(header=header):
                now = [0]
                budget = RestBudget(clock=lambda: now[0])
                error = HTTPError("https://example.invalid", 429, "limited",
                                  {"Retry-After": header}, None)
                with (patch("aql.recovery.gap_recovery.SHARED_REST_BUDGET", budget),
                      patch("urllib.request.urlopen", side_effect=error) as transport):
                    with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                        _fetch_klines("BTCUSDT", "15m", 0, 900000)
                    now[0] = delay - 1
                    with self.assertRaisesRegex(RuntimeError, "admission denied"):
                        _fetch_klines("BTCUSDT", "15m", 0, 900000)
                    self.assertEqual(transport.call_count, 1)
                    now[0] = delay
                    budget.acquire(2, core=True)

    def test_gap_metrics_and_idempotent_resume(self):
        width = 900_000
        row = [0, "10", "11", "9", "10", "1", width - 1, "10", 1, "1", "10", "0"]
        missing_row = [width, *row[1:6], 2 * width - 1, *row[7:]]
        with patch("aql.recovery.gap_recovery._fetch_klines",
                   side_effect=[([row], 5), ([row, missing_row], 7)]):
            bars, partial = recover_gap("BTCUSDT", "15m", 0, 2 * width, set())
            self.assertEqual(partial.missing_opens, [width])
            self.assertEqual(partial.last_seen_window_weight, 5)
            recovered, complete = recover_gap("BTCUSDT", "15m", 0, 2 * width,
                                              {bar.bar_open for bar in bars})
        self.assertEqual([bar.bar_open for bar in recovered], [width])
        self.assertEqual(complete.status, "FULL")
        self.assertEqual(complete.already_stored, 1)
        self.assertEqual(complete.last_seen_window_weight, 7)
