"""Read a single completed Daily archive's bounded lineage metadata.

This diagnostic never opens market payloads, scans for alternate receipts, or
mutates the task's runtime state.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat
import os

from aql.observation.contracts import digest

DAY_MS = 86_400_000
MAX_BYTES = 64 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def plain_path(path, leaf_kind):
    """Return an absolute path after rejecting links/reparse points in every component."""
    path = Path(os.path.abspath(os.fspath(path)))
    try:
        chain = list(reversed((path, *path.parents)))
        for index, item in enumerate(chain):
            st = item.lstat()
            attrs = getattr(st, "st_file_attributes", 0)
            require(not item.is_symlink() and not (attrs & REPARSE_POINT),
                    "DAILY_EVIDENCE_PATH_LINK")
            is_leaf = index == len(chain) - 1
            if not is_leaf:
                require(stat.S_ISDIR(st.st_mode), "DAILY_EVIDENCE_PATH_SCOPE")
            elif leaf_kind == "file":
                require(stat.S_ISREG(st.st_mode), "DAILY_EVIDENCE_FILE_SCOPE")
            else:
                require(stat.S_ISDIR(st.st_mode), "DAILY_EVIDENCE_STATE_SCOPE")
        return path
    except OSError:
        raise ValueError("DAILY_EVIDENCE_UNAVAILABLE") from None


def read_json(path):
    path = plain_path(path, "file")
    try:
        st = path.lstat()
        require(st.st_nlink == 1 and 0 <= st.st_size <= MAX_BYTES,
                "DAILY_EVIDENCE_FILE_SCOPE")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "DAILY_EVIDENCE_FILE_SCOPE")
        def unique(pairs):
            out = {}
            for key, value in pairs:
                require(key not in out, "DAILY_EVIDENCE_DUPLICATE_KEY")
                out[key] = value
            return out
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
        require(type(value) is dict, "DAILY_EVIDENCE_JSON_SCOPE")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("DAILY_EVIDENCE_UNAVAILABLE") from None


def read_claim(path):
    path = plain_path(path, "file")
    try:
        st = path.lstat()
        require(st.st_nlink == 1 and 0 < st.st_size <= 256,
                "DAILY_EVIDENCE_CLAIM_SCOPE")
        raw = path.read_bytes()
        require(len(raw) <= 256, "DAILY_EVIDENCE_CLAIM_SCOPE")
        return raw.decode("ascii").strip()
    except (OSError, UnicodeError):
        raise ValueError("DAILY_EVIDENCE_UNAVAILABLE") from None


def verify_daily_success(state, policy_path, policy_pin, source_day_ms, receipt_sha256):
    require(type(source_day_ms) is int and source_day_ms > 0 and source_day_ms % DAY_MS == 0,
            "DAILY_EVIDENCE_DAY_INVALID")
    require(type(receipt_sha256) is str and HEX64.fullmatch(receipt_sha256),
            "DAILY_EVIDENCE_RECEIPT_INVALID")
    state = plain_path(state, "directory")
    policy_path = plain_path(policy_path, "file")
    policy = read_json(policy_path)
    require(set(policy) == {"schema", "first_open_ms", "host", "authorization_ref"}
            and policy.get("schema") == "atlas.vision.daily-research.v1"
            and digest(policy) == policy_pin
            and type(policy.get("first_open_ms")) is int
            and policy["first_open_ms"] > 0 and policy["first_open_ms"] % DAY_MS == 0
            and policy.get("host") == os.environ.get("COMPUTERNAME")
            and type(policy.get("authorization_ref")) is str
            and bool(policy["authorization_ref"].strip()), "DAILY_EVIDENCE_POLICY_PIN")
    marker = plain_path(state / "atlas-authorized-periodic-v1", "file")
    marker_stat = marker.lstat()
    require(marker_stat.st_nlink == 1 and marker_stat.st_size == 0,
            "DAILY_EVIDENCE_STATE_SCOPE")
    day = str(source_day_ms)
    daily = policy_path.parent / "daily"
    done = read_json(daily / f"{day}.done.json")
    job = read_json(daily / f"day-{day}" / "job.json")
    claim = read_claim(state / f"{day}.claim")
    archive_date = datetime.fromtimestamp(source_day_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    require(done.get("start_ms") == source_day_ms
            and done.get("receipt_sha256") == receipt_sha256
            and job.get("start_ms") == source_day_ms
            and digest(job) == claim
            and job.get("authorization_ref") == policy["authorization_ref"]
            and job.get("host") == policy["host"]
            and job.get("archive") == f"BTCUSDT-1m-{archive_date}.zip"
            and type(job.get("archive_sha256")) is str
            and HEX64.fullmatch(job["archive_sha256"])
            and type(job.get("checksum_sha256")) is str
            and HEX64.fullmatch(job["checksum_sha256"]), "DAILY_EVIDENCE_LINK_UNPROVEN")
    return {
        "status": "VERIFIED",
        "source_day_ms": source_day_ms,
        "receipt_sha256": receipt_sha256,
        "source_zip_sha256": job["archive_sha256"],
        "checksum_sha256": job["checksum_sha256"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--source-day-ms", type=int, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_daily_success(args.state, args.policy, args.pin,
                                          args.source_day_ms, args.receipt_sha256),
                     sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        reason = str(exc)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", reason):
            reason = "DAILY_EVIDENCE_INVALID"
        print(json.dumps({"status": "UNVERIFIED", "reason": reason}, sort_keys=True))
        raise SystemExit(1) from None
