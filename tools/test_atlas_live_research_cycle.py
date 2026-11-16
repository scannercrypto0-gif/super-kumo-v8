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
from tools.atlas_single_receipt import persist_frame
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
    def test_bounded_pilot_is_opt_in_and_custody_scoped(self):
        clock.current = slot + 100
        pilot_plan = make_plan(slot, fixture, 4, bounded_pilot=True)
        pilot_pin = digest(pilot_plan)
        self.assertEqual((pilot_plan["wall_ms"], pilot_plan["max_connections"], pilot_plan["rest_requests"]),
                         (3_900_000, 2, 0))
        with self.assertRaisesRegex(ValueError, "^PILOT_REQUIRES_FOUR_BARS$"):
            make_plan(slot, fixture, 3, bounded_pilot=True)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")), \
             patch("time.time", side_effect=lambda: clock.now()/1000), \
             patch("aql.observation.prospective.time_ns", side_effect=lambda: clock.now()*1000000):
            root = Path(tmp) / "run"
            transport = Wire()
            qualification = dict(plan_sha256=pilot_pin, endpoint=pilot_plan["endpoint"],
                                 raw_retention_ms=86_400_000, source_rights_ref="fixture",
                                 region_ref="fixture", custody_ref="fixture", network_permission_ref="fixture",
                                 clock_checked_ms=clock.now(), clock_uncertainty_ms=10,
                                 state_path=str(root.resolve()))
            args = dict(clock=clock, transport=transport, wait=wait, synthetic=True, stop_after_first=True)
            with self.assertRaisesRegex(ValueError, "^LIVE_PLAN_PIN$"):
                run(root, pilot_plan, pilot_pin, fixture, verifier=None, **args)
            with self.assertRaisesRegex(ValueError, "^PILOT_QUALIFICATION_SCOPE$"):
                run(root, pilot_plan, pilot_pin, fixture, verifier=None, **args,
                    pilot_qualification={**qualification, "state_path": "wrong"})
            with self.assertRaisesRegex(ValueError, "^CONTROLLED_EGRESS_AUTHORITY_UNAVAILABLE$"):
                run(root, plan, pin, fixture, verifier=None, **args)
            self.assertFalse(root.exists())
            self.assertEqual(transport.attempts, 0)
            result = run(root, pilot_plan, pilot_pin, fixture, verifier=None,
                         pilot_qualification=qualification, **args)
            self.assertEqual(transport.attempts, 1)
            self.assertEqual(len(result["bars"]), 1)
            self.assertEqual(result["egress_budget"], "LOCAL_PILOT_ONLY")
            self.assertEqual(result["shared_headroom"], "UNVERIFIED")
            self.assertEqual(result["admission"], "WAIT_AUTHENTICATED_PARENTS")
            self.assertFalse(result["factory"]["orders_enabled"])

    def test_recovery_rejects_foreign_session_before_ack(self):
        clock.current = slot + STEP + 499
        close = slot + STEP - 1
        raw = json.dumps({"E": close + 10, "k": dict(s="BTCUSDT", i="15m",
            t=slot, T=close, o="100", h="102", l="99", c="101", v="3", x=True)}).encode()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")), \
             patch("time.time", side_effect=lambda: clock.now()/1000), \
             patch("aql.observation.prospective.time_ns", side_effect=lambda: clock.now()*1000000):
            root = Path(tmp)
            path = root / str(slot)
            path.mkdir()
            foreign_pin = digest(make_plan(slot, fixture, count=3))
            persist_frame(path, raw, slot=slot, received=clock.now(), uncertainty=10,
                          monotonic_ns=clock.monotonic_ns(), session=foreign_pin[:24])
            journal = DurableJournal(str(root / "journal.sqlite"))
            store = OperationalStore(str(root / "market.sqlite"))
            observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture, synthetic=True)
            with self.assertRaisesRegex(ValueError, "^LIVE_RECEIPT_SESSION$"):
                recover(root, journal, store, observer, slot, clock.now, wait, plan_pin=pin)
            self.assertEqual(journal.replay("BTCUSDT", "15m", limit=3), [])

    def test_delayed_renewal_cannot_revive_expired_lease(self):
        clock.current = slot

        def late_renewal(lease_id, **scope):
            clock.current += 11_000
            return lease_record(**scope)

        with patch.object(authority, "renew_research_lease", side_effect=late_renewal):
            with Lease(authority, {"connections": 2}, now=clock.now) as lease:
                clock.current += 50_000
                with self.assertRaisesRegex(ValueError, "LEASE_RENEWAL_AFTER_EXPIRY"):
                    lease.check()

    def test_authority_loss_does_not_reconnect_market_transport(self):
        clock.current = slot + 100
        transport = Wire()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            authority, "renew_research_lease", side_effect=TimeoutError("authority offline")
        ), patch.object(authority, "release_research_lease") as release, patch.object(
            socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")
        ):
            with self.assertRaisesRegex(ValueError, "LEASE_AUTHORITY_LOST"):
                run(Path(tmp), plan, pin, fixture, verifier=authority, clock=clock,
                    transport=transport, wait=wait, synthetic=True)
            self.assertEqual(transport.attempts, 1)
            release.assert_called_once()

    def test_conflicting_external_reservation_does_not_connect(self):
        clock.current = slot + 100
        transport = Wire()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            authority, "acquire_research_lease", side_effect=ValueError("LEASE_CONFLICT")
        ):
            with self.assertRaisesRegex(ValueError, "LEASE_CONFLICT"):
                run(Path(tmp), plan, pin, fixture, verifier=authority, clock=clock,
                    transport=transport, wait=wait, synthetic=True)
            self.assertEqual(transport.attempts, 0)

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
                self.assertEqual(recover(root, journal, store, observer, slot, clock.now, wait,
                                         plan_pin=pin), result['bars'])
                print("TEST_ONLY reconnect=1 durable_bars=2 duplicate_ignored=1 negative_missing_authority=PASS")
