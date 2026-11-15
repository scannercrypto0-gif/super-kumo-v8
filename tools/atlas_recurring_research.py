"""Manual, socket-free recurring research windows and immutable completion ledger."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import sqlite3
from unittest.mock import patch

from aql.observation.contracts import digest
from aql.observation.durable_bridge_v1 import DurableG2Bridge, require
from tools.atlas_bounded_research_cycle import execute, FIXTURE, STEP
from tools.atlas_prospective_observe import dedicated_root

MARKER = "atlas-recurring-research-v1"
BARS = 4


class Cycles(DurableG2Bridge):
    def _replay(self, con, *, prospective=None):
        cycles = {}

        def apply(kind, key, result):
            require(kind == "completed_cycle" and key == str(result["plan"]["first_open_ms"])
                    and key not in cycles and result["grade"] == "TEST_ONLY"
                    and result["sha256"] == digest({k: v for k, v in result.items() if k != "sha256"})
                    and result["current_entry"] == "NO_CURRENT_ENTRY", "CYCLE_RECEIPT_DRIFT")
            cycles[key] = result

        _, _, tail = super()._replay(con, prospective=apply)
        return cycles, {}, tail

    def read(self):
        with closing(self._connect_readonly()) as con:
            cycles, _, _ = self._replay(con)
        return cycles

    def complete(self, result):
        key = str(result["plan"]["first_open_ms"])
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            cycles, _, tail = self._replay(con)
            if key in cycles:
                require(cycles[key] == result, "CYCLE_ALREADY_SEALED")
            else:
                self._append(con, "completed_cycle", key, result, tail)


def schedule(start, count, fixture, code_pin):
    require(start >= 0 and start % STEP == 0 and 2 <= count <= 8, "CYCLE_SCOPE")
    return {"grade": "TEST_ONLY", "windows": [
        [start + i * BARS * STEP, start + (i + 1) * BARS * STEP] for i in range(count)
    ], "retention": "LOCAL_SYNTHETIC_ONLY", "clock": "SIMULATED_UTC",
        "code_pin": code_pin, "strategy_fixture_sha256": fixture["sha256"],
        "config_sha256": fixture["payload"]["config_digest"]}


def start_run(root, plan, pin, fixture, fault):
    require(digest(plan) == pin, "SCHEDULE_PIN")
    root = dedicated_root(root, MARKER)
    with closing(sqlite3.connect(root / "writer.sqlite", timeout=0)) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        ledger = Cycles(root / "cycles.sqlite")
        with closing(sqlite3.connect(root / "schedule.sqlite")) as con, con:
            con.execute("CREATE TABLE IF NOT EXISTS schedule (id INTEGER PRIMARY KEY, plan TEXT)")
            con.execute("INSERT OR IGNORE INTO schedule VALUES (1,?)", (json.dumps(plan, sort_keys=True),))
            actual = json.loads(con.execute("SELECT plan FROM schedule WHERE id=1").fetchone()[0])
            require(actual == plan, "STATE_SCHEDULE_DRIFT")
        for opening, end in plan["windows"]:
            if (root / "stop.request").exists():
                break
            if str(opening) in ledger.read():
                continue
            if fault == "before-ack":
                os._exit(73)
            result = execute(root / str(opening), fixture=fixture, start=opening,
                             interrupt=fault == "after-ack")
            if fault == "after-ack":
                os._exit(73)
            require(result["as_of_ms"] == end + 3 and result["factory"]["orders_enabled"] is False
                    and result["factory"]["secretary_enqueued"] is False, "CYCLE_OUTPUT_SCOPE")
            body = {k: v for k, v in result.items() if k != "sha256"}
            body.update(current_entry="NO_CURRENT_ENTRY", mode="RESEARCH_DELAYED",
                        schedule_sha256=pin, end_exclusive_ms=end, lab="NOT_ELIGIBLE")
            result = {**body, "sha256": digest(body)}
            if fault == "before-append":
                os._exit(73)
            ledger.complete(result)
            if fault == "after-append":
                os._exit(73)
    return status(root)


def status(root):
    require((root / MARKER).is_file(), "STATE_REQUIRED")
    with closing(sqlite3.connect((root / "schedule.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as con:
        plan = json.loads(con.execute("SELECT plan FROM schedule WHERE id=1").fetchone()[0])
    # Read the event DB without migrations or writer PRAGMAs.
    reader = Cycles.__new__(Cycles)
    reader.db = root / "cycles.sqlite"
    cycles = reader.read()
    pin = digest(plan)
    expected = {str(opening): end for opening, end in plan["windows"]}
    require(all(key in expected and row["end_exclusive_ms"] == expected[key]
                and row["schedule_sha256"] == pin for key, row in cycles.items()),
            "SCHEDULE_RECEIPT_DRIFT")
    stopped = (root / "stop.request").exists()
    running = False
    with closing(sqlite3.connect((root / "writer.sqlite").resolve().as_uri() + "?mode=ro&cache=private",
                                 uri=True, timeout=0)) as con:
        try:
            con.execute("SELECT name FROM sqlite_master").fetchall()
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                raise
            running = True
    pending = "RUNNING" if running else "BLOCKED" if stopped else "READY"
    windows = [{"start_ms": opening, "end_exclusive_ms": end, "grade": plan["grade"],
                "status": "COMPLETE" if str(opening) in cycles else pending,
                "receipt": cycles.get(str(opening))} for opening, end in plan["windows"]]
    return {"schedule_sha256": pin, "windows": windows,
            "status": "COMPLETE" if all(w["status"] == "COMPLETE" for w in windows)
            else pending,
            "next_action": "NONE" if len(cycles) == len(windows) else
            "WAIT" if running else "REARM" if stopped else "RECOVER"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("plan", "start", "status", "stop", "rearm", "recover"))
    p.add_argument("--state", type=Path)
    p.add_argument("--start-ms", type=int, default=1735689600000)
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--pin")
    p.add_argument("--fixture-interrupt", choices=("before-ack", "after-ack", "before-append", "after-append"))
    args = p.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        fixture = json.loads(FIXTURE.read_text())[0]
        code_pin = digest([sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                           for name in ("atlas_recurring_research.py", "atlas_bounded_research_cycle.py")])
        plan = schedule(args.start_ms, args.count, fixture, code_pin)
        if args.mode == "plan":
            result = {"plan": plan, "sha256": digest(plan)}
        elif args.mode in ("start", "recover"):
            result = start_run(args.state, plan, args.pin, fixture, args.fixture_interrupt)
        elif args.mode == "status":
            result = status(args.state)
        else:
            require((args.state / MARKER).is_file(), "STATE_REQUIRED")
            root = dedicated_root(args.state, MARKER)
            stop = root / "stop.request"
            if args.mode == "stop":
                stop.touch(exist_ok=True)
            else:
                with closing(sqlite3.connect(root / "writer.sqlite", timeout=0)) as lock:
                    lock.execute("BEGIN EXCLUSIVE")
                    stop.unlink(missing_ok=True)
            result = status(root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
