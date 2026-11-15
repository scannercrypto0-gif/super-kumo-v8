"""Manual, socket-free recurring research windows and immutable completion ledger."""
import argparse
from contextlib import closing
import ctypes
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import sqlite3
import time
from unittest.mock import patch

from aql.observation.contracts import digest
from aql.observation.durable_bridge_v1 import DurableG2Bridge, require, sha
from tools.atlas_bounded_research_cycle import execute, FIXTURE, STEP
from tools.atlas_prospective_observe import dedicated_root

MARKER = "atlas-recurring-research-v1"
BARS = 4
DAY = 86_400_000
ARCHIVE_MARKER = "atlas-authorized-periodic-v1"


def local_archive_source(value):
    path = Path(value)
    require(path.is_absolute(), "LOCAL_ARCHIVE_SOURCE_REQUIRED")
    if os.name == "nt":
        require(ctypes.windll.kernel32.GetDriveTypeW(path.anchor) == 3,
                "LOCAL_FIXED_ARCHIVE_DRIVE_REQUIRED")
    return path


def archive_queue(root, jobs, pin, mode, *, now=None, runner=None, reader=None):
    require(isinstance(jobs, list) and 1 <= len(jobs) <= 8 and sha(pin)
            and digest(jobs) == pin, "ARCHIVE_QUEUE_PIN")
    now = time.time_ns() // 1_000_000 if now is None else now
    seen = set()
    for job in jobs:
        opening, end, cutoff = (job.get(key) for key in ("start_ms", "end_ms", "cutoff_ms"))
        require(all(type(value) is int for value in (opening, end, cutoff)) and
                1715040000000 <= opening < end <= cutoff <= now and opening % DAY == 0
                and end == opening + DAY and opening not in seen, "ARCHIVE_WINDOW")
        seen.add(opening)
        day = datetime.fromtimestamp(opening // 1000, timezone.utc).strftime("%Y-%m-%d")
        require(job.get("archive") == f"BTCUSDT-1m-{day}.zip" and
                job.get("experiment") == f"ATLAS-RETROSPECTIVE-BTCUSDT-{day.replace('-', '')}"
                and all(sha(job.get(key)) for key in ("archive_sha256", "checksum_sha256"))
                and type(job.get("original_reads")) is int and job["original_reads"] == 1
                and job.get("host") == os.environ.get("COMPUTERNAME")
                and bool(job.get("host"))
                and all(isinstance(job.get(key), str) and job[key].strip()
                        for key in ("source", "rights_ref", "authorization_ref", "retention_scope")),
                "EXACT_ARCHIVE_AUTHORIZATION_REQUIRED")
    require(jobs == sorted(jobs, key=lambda job: job["start_ms"]), "ARCHIVE_QUEUE_ORDER")
    if runner is None:
        from tools.atlas_authorized_archive_research import run as runner, verify as reader
    root = dedicated_root(root, ARCHIVE_MARKER)
    stop = root / "stop.request"
    if mode == "stop":
        try:
            with stop.open("x"):
                pass
        except FileExistsError:
            pass

    def collect():
        rows = []
        for job in jobs:
            key = str(job["start_ms"])
            target = root / key
            claim = root / f"{key}.claim"
            if not claim.exists():
                rows.append({"start_ms": job["start_ms"], "status": "BLOCKED" if stop.exists() else "READY"})
                continue
            require(claim.read_text(encoding="ascii") == digest(job), "ARCHIVE_CLAIM_DRIFT")
            if not (target / "result.json").is_file():
                rows.append({"start_ms": job["start_ms"], "status": "BLOCKED",
                             "reason": "ORIGINAL_ALREADY_CLAIMED_INCOMPLETE"})
                continue
            result = reader(target, job["experiment"])
            require(result["archive_sha256"] == job["archive_sha256"]
                    and result["checksum_sha256"] == job["checksum_sha256"]
                    and result["current_entry"] == "NO_CURRENT_ENTRY"
                    and result["orders"] == 0, "ARCHIVE_RESULT_PARENT")
            rows.append({"start_ms": job["start_ms"], "status": "COMPLETE", "receipt": result})
        return rows

    if mode in ("start", "recover", "rearm"):
        with closing(sqlite3.connect(root / "writer.sqlite", timeout=0)) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            if mode == "rearm":
                stop.unlink(missing_ok=True)
            elif not stop.exists():
                rows = collect()
                if any(row["status"] == "BLOCKED" for row in rows):
                    return {"status": "BLOCKED", "windows": rows}
                for job, row in zip(jobs, rows, strict=True):
                    if row["status"] != "READY":
                        continue
                    source = local_archive_source(job["source"])
                    if not all((source / filename).is_file()
                               for filename in (job["archive"], job["archive"] + ".CHECKSUM")):
                        return {"status": "BLOCKED", "reason": "AUTHORIZED_ARCHIVE_NOT_PRESENT", "windows": rows}
                    require(not (root / str(job["start_ms"])).exists(), "UNCLAIMED_ARCHIVE_STATE")
                    with (root / f'{job["start_ms"]}.claim').open("x", encoding="ascii") as stream:
                        stream.write(digest(job))
                        stream.flush()
                        os.fsync(stream.fileno())
                    runner(root / str(job["start_ms"]), source, job)
                    break
    rows = collect()
    return {"status": "COMPLETE" if all(row["status"] == "COMPLETE" for row in rows) else
            "BLOCKED" if any(row["status"] == "BLOCKED" for row in rows) else "READY",
            "windows": rows}


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
    p.add_argument("--authorized-plan", type=Path)
    p.add_argument("--authorized-plan-sha256")
    p.add_argument("--fixture-interrupt", choices=("before-ack", "after-ack", "before-append", "after-append"))
    args = p.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        fixture = json.loads(FIXTURE.read_text())[0]
        code_pin = digest([sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                           for name in ("atlas_recurring_research.py", "atlas_bounded_research_cycle.py")])
        plan = schedule(args.start_ms, args.count, fixture, code_pin)
        if args.authorized_plan:
            require(args.mode != "plan", "AUTHORIZED_PLAN_MUST_BE_OPERATOR_PINNED")
            with args.authorized_plan.open("rb") as stream:
                raw = stream.read(65537)
            require(len(raw) <= 65536, "ARCHIVE_QUEUE_SIZE")
            result = archive_queue(args.state, json.loads(raw), args.authorized_plan_sha256, args.mode)
        elif args.mode == "plan":
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
