"""Acquire and verify one permitted April 2024 partition. Keep all bytes private."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from time import sleep
from urllib.request import HTTPRedirectHandler, build_opener
from zipfile import ZipFile

from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager, digest
from research_wp_r0.aql_authenticated_historical_admission_v1 import PIN_SCHEMA
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.historical_library import HistoricalLibrary
from tools.atlas_prospective_observe import dedicated_root

NAME = "BTCUSDT-15m-2024-04.zip"
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/"
TERMS = "https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md"
START, END = 1711929600000, 1714521600000
DATASET = "BINANCE-SPOT-BTCUSDT-15M-2024-04-P1"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected publisher redirect")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def pressure(p0):
    if p0 is None:
        return
    db = p0 / "runner-lock.sqlite"
    if db.exists():
        try:
            with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=rw", uri=True, timeout=0)) as lock:
                lock.execute("BEGIN IMMEDIATE")
                lock.rollback()
        except sqlite3.OperationalError as exc:
            raise RuntimeError("P1_PAUSED_FOR_P0_OBSERVER") from exc


def fetch(root, name, limit, p0):
    checkpoint = root / (name + ".capture")
    path = root / name
    if checkpoint.is_file() and path.is_file():
        record = json.loads(checkpoint.read_text())
        raw = path.read_bytes()
        if len(raw) > limit or sha(raw) != record.get("sha256") or record.get("url") != BASE + name:
            raise ValueError("P1_CAPTURE_CHECKPOINT_DRIFT")
        return raw, record
    url = BASE + name
    started = datetime.now(timezone.utc).isoformat()
    pressure(p0)
    with build_opener(NoRedirect).open(url, timeout=20) as response:
        if response.status != 200 or response.url != url:
            raise ValueError("P1_PUBLISHER_RESPONSE_SCOPE")
        data = bytearray()
        while chunk := response.read(64 * 1024):
            pressure(p0)
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError("P1_DOWNLOAD_LIMIT")
            sleep(0.05)
        record = {"url": url, "status": response.status, "content_type": response.headers.get("Content-Type"),
                  "started_utc": started, "received_utc": datetime.now(timezone.utc).isoformat(),
                  "sha256": sha(data), "bytes": len(data)}
    atomic(path, data)
    atomic(checkpoint, json.dumps(record, sort_keys=True).encode())
    return bytes(data), record


def admit_partition(root, raw, checksum, *, start=START, end=END, test_only=False,
                    version=1, parent_sha=None, check_progress=None):
    match = re.fullmatch(rb"([a-fA-F0-9]{64})[ \t]+BTCUSDT-15m-2024-04\.zip\s*", checksum)
    if not match or match[1].decode().lower() != sha(raw):
        raise ValueError("P1_PUBLISHER_CHECKSUM_MISMATCH")
    member = NAME[:-4] + ".csv"
    with ZipFile(BytesIO(raw)) as z:
        if z.namelist() != [member] or z.getinfo(member).file_size > 2_000_000:
            raise ValueError("P1_ARCHIVE_MEMBER_SCOPE")
        member_sha = sha(z.read(member))
    pin = dict(schema=PIN_SCHEMA, source_kind="BINANCE_KLINES_ZIP", original_object_id=DATASET,
               original_sha256=sha(raw), provenance_reference="BINANCE_VISION_P1_CHECKSUM",
               captured_at_ms=None, claimed_available_at_ms=None, expected_inventory_sha256=None,
               vault_object_metadata=None, universe_manifest_sha256=None, universe_member_count=None,
               test_only=test_only, archive_name=NAME, csv_member_name=member,
               csv_member_sha256=member_sha, checksum_file_sha256=sha(checksum))
    cutoff = end + 1_000
    spec = dict(dataset_id=DATASET, version=version, symbol="BTCUSDT", interval="15m",
                exchange="BINANCE", market="SPOT", source_label="BINANCE_VISION_P1",
                start_ms=start, end_exclusive_ms=end, as_of_ms=cutoff,
                parent_source_sha256=parent_sha, correction_reason="PUBLISHER_REVISION" if parent_sha else None,
                test_only=test_only)
    admission = admit_local_original(root, raw, checksum, pin, spec, decision_cutoff_ms=cutoff,
                                     check_progress=check_progress)
    # Core stage is the retained original-byte authority. SQLite is derived.
    warehouse = root / "warehouse.sqlite"
    with closing(sqlite3.connect(warehouse)) as con:
        if con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] != 0:
            raise RuntimeError("P1_QUIESCENT_SNAPSHOT_REQUIRED")
    local = query_local(root, DATASET, version, start, end, cutoff,
                        required_source_sha256=sha(raw), require_complete=True, sqlite_immutable=True)
    library = HistoricalLibrary()
    OfflineBridgeStager(root / "stage").replay_committed(library)
    request = dict(schema=REQUEST_SCHEMA, dataset_id=DATASET, version=version, start_ms=start,
                   end_exclusive_ms=end, decision_cutoff_ms=cutoff, require_complete=True, confirmed_only=False)
    native = query_price_custody(library, request, expected_source_sha256=sha(raw),
                                expected_manifest_integrity_sha256=admission["manifest_integrity_sha256"])
    expected = (end - start) // 900_000
    if (native.get("status") != "OK" or local["coverage"] != "COMPLETE"
            or len(native["bars"]) != expected or len(local["bars"]) != expected
            or native["price_query_sha256"] == local["query_sha256"]
            or native["source_bytes_sha256"] != local["source_bytes_sha256"]
            or native["manifest_integrity_sha256"] != local["manifest_integrity_sha256"]):
        raise ValueError("P1_DUAL_QUERY_SCOPE_DRIFT")
    for left, right in zip(native["bars"], local["bars"], strict=True):
        if any(left[key] != right[key] for key in ("bar_open_ms", "bar_close_ms", "open", "high", "low", "close", "volume")):
            raise ValueError("P1_DUAL_QUERY_BAR_DRIFT")
    return {"dataset_id": DATASET, "version": version, "bars": expected,
            "source_sha256": sha(raw), "manifest_sha256": local["manifest_integrity_sha256"],
            "core245_sha256": native["price_query_sha256"], "core253_sha256": local["query_sha256"],
            "historical_pit": "NOT_ATTESTED", "scope": "RETROSPECTIVE_NON_PIT"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", required=True)
    p.add_argument("--p0-state", required=True, type=Path)
    p.add_argument("--personal-noncommercial", action="store_true", required=True)
    args = p.parse_args()
    root = dedicated_root(args.state, "atlas-april-p1-v1")
    p0 = args.p0_state.resolve()
    if root.resolve().is_relative_to(p0) or p0.is_relative_to(root.resolve()):
        p.error("P0 and P1 state trees must be disjoint")
    free = shutil.disk_usage(root).free
    if free < 128 * 1024 * 1024:
        p.error("Insufficient isolated storage")
    with closing(sqlite3.connect(root / "archive-lock.sqlite", timeout=0)) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        checksum, checksum_capture = fetch(root, NAME + ".CHECKSUM", 4096, p0)
        if not re.fullmatch(rb"[a-fA-F0-9]{64}[ \t]+BTCUSDT-15m-2024-04\.zip\s*", checksum):
            raise ValueError("P1_UNPARSEABLE_PUBLISHER_CHECKSUM")
        raw, source_capture = fetch(root, NAME, 8_000_000, p0)
        pressure(p0)
        try:
            summary = admit_partition(root / "core", raw, checksum,
                                      check_progress=lambda: pressure(p0))
        except ValueError:
            atomic(root / "QUARANTINED", sha(raw).encode())
            raise
        summary.update(terms=TERMS, terms_version="1.0 / 2026-08-26",
                       source_capture=source_capture, checksum_capture=checksum_capture,
                       free_bytes_at_start=free)
        sealed = {**summary, "sha256": digest(summary)}
        atomic(root / "summary.json", json.dumps(sealed, sort_keys=True).encode())
        print(json.dumps(sealed, sort_keys=True))


if __name__ == "__main__":
    main()
