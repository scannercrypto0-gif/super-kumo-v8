"""Collect only authorized, newly published Binance Vision daily Spot archives."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import stat
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_authorized_archive_research import put, verify
from tools.atlas_recurring_research import DAY, archive_queue, local_archive_source

BASE = "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/"
TERMS = "https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md"
HOUR = DAY // 24
RETENTION = 30 * DAY


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(name, limit):
    try:
        with build_opener(NoRedirect()).open(BASE + name, timeout=25) as response:
            data = response.read(limit + 1)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise ValueError(f"VISION_HTTP_{exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("VISION_TRANSPORT_FAILED") from None
    if not 0 < len(data) <= limit:
        raise ValueError("VISION_DOWNLOAD_BOUND")
    return data


def file_bytes(folder, name, limit, downloader):
    path = folder / name
    if path.exists():
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if not 0 < len(data) <= limit:
            raise ValueError("VISION_DOWNLOAD_BOUND")
        return data
    data = downloader(name, limit)
    if data is None:
        return None
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return data


def validate(policy, pin):
    if (set(policy) != {"schema", "first_open_ms", "host", "authorization_ref"}
            or policy["schema"] != "atlas.vision.daily-research.v1" or digest(policy) != pin
            or type(policy["first_open_ms"]) is not int or policy["first_open_ms"] % DAY
            or policy["first_open_ms"] <= 0 or not policy["host"]
            or policy["host"] != os.environ.get("COMPUTERNAME")
            or not isinstance(policy["authorization_ref"], str) or not policy["authorization_ref"].strip()):
        raise ValueError("VISION_SCOPE_PIN")


def purge(daily, state, now):
    for date_folder in daily.glob("day-*"):
        stamp = date_folder / "created.json"
        if not stamp.is_file() or now - json.loads(stamp.read_bytes()) < RETENTION:
            continue
        key = date_folder.name.removeprefix("day-")
        if not key.isdecimal():
            raise ValueError("VISION_RETENTION_SCOPE")
        expired = state / key
        for path, parent in ((expired, state), (date_folder, daily)):
            if path.exists():
                reparse = getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                if path.resolve().parent != parent.resolve() or path.is_symlink() or reparse:
                    raise ValueError("VISION_RETENTION_SCOPE")
                shutil.rmtree(path)


def tick(policy, state, daily, now, *, downloader=fetch, queue=archive_queue, reader=verify):
    purge(daily, state, now)
    if (state / "stop.request").exists():
        return {"status": "BLOCKED", "reason": "OPERATOR_STOP_REQUESTED"}
    today = now - now % DAY
    opening = policy["first_open_ms"]
    while (daily / f"{opening}.done.json").is_file():
        opening += DAY
    result = state / str(opening) / "result.json"
    claim = state / f"{opening}.claim"
    folder = daily / f"day-{opening}"
    job_path = folder / "job.json"

    def completed(job):
        with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
            receipt = reader(result.parent, job["experiment"])
        if (receipt["archive_sha256"] != job["archive_sha256"]
                or receipt["checksum_sha256"] != job["checksum_sha256"]
                or claim.read_text(encoding="ascii") != digest(job)):
            raise ValueError("VISION_RESULT_PARENT")
        put(daily / f"{opening}.done.json", {"receipt_sha256": receipt["sha256"], "start_ms": opening})
        return {"status": "COMPLETE", "source_day_ms": opening, "windows": [{"receipt": receipt}]}

    if claim.exists():
        if not result.is_file() or not job_path.is_file():
            raise ValueError("ORIGINAL_ALREADY_CLAIMED_INCOMPLETE")
        return completed(json.loads(job_path.read_bytes()))
    eligible = opening + DAY
    slot = 12 if now - today >= 12 * HOUR else 6
    next_check = max(eligible, today) + 6 * HOUR
    if opening >= today or now - today < 6 * HOUR:
        return {"status": "WAIT_FOR_SOURCE", "source_day_ms": opening, "next_check_ms": next_check}
    if opening < today - RETENTION:
        raise ValueError("VISION_SOURCE_OUTSIDE_RETENTION_WINDOW")
    date = datetime.fromtimestamp(opening / 1_000, timezone.utc).date().isoformat()
    archive = f"BTCUSDT-1m-{date}.zip"
    experiment = "ATLAS-RETROSPECTIVE-BTCUSDT-" + date.replace("-", "")
    folder.mkdir(exist_ok=True)
    if not (folder / "created.json").exists():
        put(folder / "created.json", now)
    if job_path.exists():
        job = json.loads(job_path.read_bytes())
        if (job["start_ms"] != opening or job["end_ms"] != eligible or job["source"] != str(folder)
                or job["archive"] != archive or job["experiment"] != experiment
                or job["authorization_ref"] != policy["authorization_ref"]):
            raise ValueError("VISION_JOB_SCOPE")
        for name, field in ((archive, "archive_sha256"), (archive + ".CHECKSUM", "checksum_sha256")):
            with (folder / name).open("rb") as stream:
                if sha256(stream.read(4 * 1024**2 + 1)).hexdigest() != job[field]:
                    raise ValueError("VISION_JOB_INPUT_PIN")
    else:
        attempt = folder / f"{today}-{slot}.attempt.json"
        next_check = today + (12 * HOUR if slot == 6 else DAY + 6 * HOUR)
        wait = {"status": "WAIT_FOR_SOURCE", "source_day_ms": opening, "next_check_ms": next_check}
        if attempt.exists():
            return wait
        put(attempt, now)
        checksum = file_bytes(folder, archive + ".CHECKSUM", 512, downloader)
        if checksum is None:
            return wait
        match = re.fullmatch(rb"([0-9a-f]{64})\s+\*?" + re.escape(archive.encode()), checksum.strip())
        if not match:
            raise ValueError("PUBLISHER_CHECKSUM_FORMAT")
        raw = file_bytes(folder, archive, 4 * 1024**2, downloader)
        if raw is None:
            return wait
        archive_pin = sha256(raw).hexdigest()
        if archive_pin != match[1].decode():
            raise ValueError("PUBLISHER_CHECKSUM_MISMATCH")
        job = dict(start_ms=opening, end_ms=eligible, cutoff_ms=now, archive=archive,
                   experiment=experiment,
                   archive_sha256=archive_pin, checksum_sha256=sha256(checksum).hexdigest(),
                   original_reads=1, source=str(folder), host=policy["host"],
                   rights_ref=TERMS + " sections 3,4,7; private non-commercial research",
                   authorization_ref=policy["authorization_ref"],
                   retention_scope="Private local Windows NTFS; 30 days")
        put(job_path, job)
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        outcome = queue(state, [job], digest([job]), "recover", now=now)
    if outcome["status"] != "COMPLETE":
        return outcome
    return completed(job)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "tick", "stop", "rearm", "status"))
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_bytes())
    validate(policy, args.pin)
    state = local_archive_source(str(args.state))
    daily = local_archive_source(str(args.policy.parent / "daily"))
    if not (state / "atlas-authorized-periodic-v1").is_file():
        raise ValueError("DURABLE_ORIGINAL_LEDGER_REQUIRED")
    if args.mode == "preflight":
        result = {"status": "SOURCE_POLICY_PIN_VERIFIED"}
    elif args.mode == "status":
        result = {"status": "STOPPED" if (state / "stop.request").exists() else "AVAILABLE",
                  "completed_days": len(list(daily.glob("*.done.json")))}
    elif args.mode == "stop":
        (state / "stop.request").touch()
        result = {"status": "STOPPED"}
    else:
        daily.mkdir(exist_ok=True)
        with closing(sqlite3.connect(daily / "writer.sqlite", timeout=0)) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            if args.mode == "rearm":
                (state / "stop.request").unlink(missing_ok=True)
                result = {"status": "AVAILABLE"}
            else:
                result = tick(policy, state, daily, int(datetime.now(timezone.utc).timestamp() * 1_000))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        reason = str(exc)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", reason):
            reason = "VISION_INPUT_INVALID"
        print(json.dumps({"status": "FAILED", "reason": reason}))
        raise SystemExit(1) from None
