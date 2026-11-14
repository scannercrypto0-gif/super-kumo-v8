import contextlib
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_live_research_cycle import FIXTURE, STEP, make_plan, run, report, recover, DurableJournal, OperationalStore, ProspectiveObserver

fixture = json.loads(FIXTURE.read_text())[0]
slot = 1794654000000
plan = make_plan(slot, fixture)
pin = digest(plan)

class Clock:
    current = slot + 100
    def now(self):
        return self.current
    def monotonic_ns(self):
        return (self.current - slot) * 1000000

class Wire:
    attempts = 0
    calls = 0
    @contextlib.contextmanager
    def stream(self, endpoint, timeout):
        self.attempts += 1
        yield self
    def getstatus(self):
        return 101
    def frame(self, connection, timeout):
        self.calls += 1
        if self.calls == 2:
            raise TimeoutError("fixture outage")
        candle_slot = slot + (STEP if self.calls == 4 else 0)
        close = candle_slot + STEP - 1
        if self.calls != 3:
            clock.current = close + 500
        return "text", json.dumps({"E": close + 10, "k": dict(s="BTCUSDT", i="15m",
            t=candle_slot, T=close, o="100", h="102", l="99", c="101", v="3", x=True)}).encode()

clock = Clock()
wire = Wire()
authority = SimpleNamespace(
    read_verified_reservation=lambda **_: dict(plan_pin=pin, endpoint=plan["endpoint"],
        authority_ref="fixture", egress_identity="fixture", reservation_ref="fixture",
        observed_ms=clock.now(), expires_ms=clock.now()+plan["wall_ms"], reserved_and_used=2, limit=4),
    read_verified_host=lambda **_: dict(clock_checked_ms=clock.now(), clock_uncertainty_ms=10,
        source_rights_ref="fixture", region_ref="fixture", custody_ref="fixture"),
    verify_observation_reservation=lambda **_: True)
def wait(seconds):
    clock.current += round(seconds * 1000)
class LiveResearchTests(unittest.TestCase):
    def test_reconnect_duplicate_and_authority_stop(self):
        clock.current = slot + 100
        wire.attempts = wire.calls = 0
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            # Only the test's injected wire and clock are available.
            with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")), \
                 patch("time.time", side_effect=lambda: clock.now()/1000), \
                 patch("aql.observation.prospective.time_ns", side_effect=lambda: clock.now()*1000000):
                try:
                    run(root, plan, pin, fixture, verifier=None, clock=clock, transport=wire, wait=wait, synthetic=True)
                except ValueError as exc:
                    assert str(exc) == "CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE"
                else:
                    raise AssertionError("missing authority accepted")
                assert wire.attempts == 0 and not root.exists()
                result = run(root, plan, pin, fixture, verifier=authority, clock=clock, transport=wire, wait=wait, synthetic=True)
                assert wire.attempts == 2 and len(result["bars"]) == 2
                assert result["factory"] == report(root, fixture, clock.now(), synthetic=True)["factory"]
                assert result["factory"]["decision_counts"] == {"UNKNOWN": 2}
                journal = DurableJournal(str(root / 'journal.sqlite'))
                store = OperationalStore(str(root / 'market.sqlite'))
                observer = ProspectiveObserver(root / 'g2.sqlite', journal, store, fixture, synthetic=True)
                self.assertEqual(recover(root, journal, store, observer, slot, clock.now, wait), result['bars'])
                print("TEST_ONLY reconnect=1 durable_bars=2 duplicate_ignored=1 negative_missing_authority=PASS")
