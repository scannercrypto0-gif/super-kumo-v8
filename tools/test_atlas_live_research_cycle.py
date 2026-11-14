import contextlib
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_research_lease import Lease
from tools.atlas_live_research_cycle import operational_guard, ingest
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
        if self.calls in (0, 3):
            target = slot + (STEP if self.calls == 0 else 2 * STEP) + 499
            if clock.current + 25_000 < target:
                clock.current += 25_000
                return "text", b'{"k":{"t":1794654000000,"s":"BTCUSDT","i":"15m","x":false}}'
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
def lease_record(**scope):
    return dict(lease_id="fixture", scope=scope, expires_ms=clock.now()+60_000,
                reserved_and_used=2, limit=4)

authority = SimpleNamespace(
    acquire_research_lease=lease_record,
    renew_research_lease=lambda lease_id, **scope: lease_record(**scope),
    read_verified_host=lambda **_: dict(clock_checked_ms=clock.now(), clock_uncertainty_ms=10,
        source_rights_ref="fixture", region_ref="fixture", custody_ref="fixture"),
    release_research_lease=lambda **_: None)
def wait(seconds):
    clock.current += round(seconds * 1000)
class LiveResearchTests(unittest.TestCase):
    def test_missed_final_and_second_writer_fail_closed(self):
        raw = json.dumps({"k": {"t": slot + STEP, "s": "BTCUSDT", "i": "15m", "x": True}}).encode()
        with self.assertRaisesRegex(ValueError, "FINALIZED_SOURCE_GAP"):
            ingest(None, raw, [], slot, 0, 0, 0, pin, None, None, None, None, None)
        clock.current = slot + 100
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from tools.atlas_prospective_observe import dedicated_root
            from tools.atlas_live_research_cycle import MARKER
            dedicated_root(root, MARKER)
            with contextlib.closing(sqlite3.connect(root / "lock.sqlite")) as lock:
                lock.execute("BEGIN EXCLUSIVE")
                with patch.object(authority, "acquire_research_lease") as acquire:
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        run(root, plan, pin, fixture, verifier=authority, clock=clock,
                            transport=Wire(), wait=wait, synthetic=True)
                    acquire.assert_not_called()

    def test_lease_expires_and_releases(self):
        clock.current = slot
        released = []
        with patch.object(authority, "release_research_lease", side_effect=lambda **kw: released.append(kw)):
            with Lease(authority, {"connections": 2}, now=clock.now) as lease:
                original = lease.record["expires_ms"]
                clock.current += 50_000
                lease.check()
                self.assertGreater(lease.record["expires_ms"], original)
                clock.current = lease.record["expires_ms"]
                with self.assertRaisesRegex(ValueError, "LEASE_EXPIRED"):
                    lease.check()
        self.assertEqual(len(released), 1)

    def test_stop_and_low_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("shutil.disk_usage", return_value=SimpleNamespace(free=1)):
                with self.assertRaisesRegex(ValueError, "DISK_RESERVE_LOW"):
                    operational_guard(root)
            (root / "stop.request").touch()
            with self.assertRaisesRegex(ValueError, "OPERATOR_STOP_REQUESTED"):
                operational_guard(root)

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
