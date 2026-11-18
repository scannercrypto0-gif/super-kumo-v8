"""Bounded original Binance WS custody using existing G1 durable stores.

This adds an isolated qualification process. It does not change a scheduled
service, strategy state or the authority of the native readiness consumer.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from aql.collector.research_ws import ENDPOINT, ResearchWebSocket
from aql.foundation.readiness import assess, FeatureRequirement
from aql.g1_integrity import content, fingerprint
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.observation.contracts import digest
from aql.storage.operational_store import OperationalStore

STEP = 900_000
CAP = 20 * 1024 * 1024
TTL_MS = 24 * 3600_000
WALL_SECONDS = 35 * 60
AUTHORITY = "https://github.com/scannercrypto0-gif/super-kumo-v8/issues/320#issuecomment-6979863455"


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def load(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= CAP, "INPUT_BOUND")
    return json.loads(path.read_bytes(), object_pairs_hook=unique_fields)


def write_once(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def write_document(path, body):
    write_once(path, (json.dumps(body, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())


def parse_frame(raw, received_ms):
    need(type(raw) is bytes and 0 < len(raw) <= 4096, "FRAME_BOUND")
    packet = json.loads(raw, object_pairs_hook=unique_fields)
    candle = packet["k"]
    need(packet["e"] == "kline" and packet["s"] == candle["s"] == "BTCUSDT"
         and candle["i"] == "15m" and type(candle["x"]) is bool, "SOURCE_IDENTITY")
    opened, closed, event = candle["t"], candle["T"], packet["E"]
    need(all(type(v) is int for v in (opened, closed, event, received_ms))
         and opened % STEP == 0 and closed == opened + STEP - 1, "SOURCE_GRID")
    need(candle["x"] is True, "FINAL_ONLY")
    need(closed < event <= received_ms + 5000 and closed < received_ms + 5000
         and received_ms <= closed + 300_000, "SOURCE_RECEIVE_TIME")
    bar = MarketBar.from_binance_ws_kline(candle)
    need(all(math.isfinite(v) for v in (bar.open, bar.high, bar.low, bar.close, bar.volume))
         and 0 < bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
         and bar.volume >= 0, "PRICE_QUALITY")
    bar.ingested_at = max(received_ms, event, closed + 1)
    return event, bar.with_checksum()


def record(root, raw, received_ms, monotonic_ns):
    event, bar = parse_frame(raw, received_ms)
    raw_path = root / f"{bar.bar_open}.frame"
    if raw_path.exists():
        need(raw_path.read_bytes() == raw, "FRAME_CONFLICT")
    else:
        write_once(raw_path, raw)
    while time.time_ns() // 1_000_000 < bar.ingested_at:
        time.sleep(0.01)
    journal = DurableJournal(str(root / "journal.sqlite"))
    store = OperationalStore(str(root / "market.sqlite"))
    journal.commit(bar)
    ack = journal.commit_receipt(bar.stable_key())
    need(ack["status"] == "SQLITE_COMMIT_RETURN_OBSERVED"
         and ack["content_digest"] == fingerprint(content(bar)), "ACK_SOURCE_BINDING")
    store.upsert(bar)
    journal.mark_persisted(bar.stable_key())
    body = {
        "slot": bar.bar_open, "raw_sha256": sha(raw), "source_event_ms": event,
        "received_ms": received_ms, "monotonic_ns": monotonic_ns,
        "ingested_at_ms": bar.ingested_at, "g1_ack": ack,
        "source_checksum": bar.compute_checksum(), "source": "BINANCE_SPOT_WS_BTCUSDT_15M",
    }
    return {**body, "sha256": digest(body)}


def readonly(cls, path):
    # Read-only handles use the existing native reader methods, without running
    # constructors/migrations or allowing the reader to create SQLite files.
    need(path.is_file() and not path.is_symlink(), "COLD_SOURCE_PATH")
    obj = cls.__new__(cls)
    obj.db_path = str(path)
    def connect():
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    obj._connect = connect
    return obj


def replay(root, *, expected_manifest_sha256=None):
    plan = load(root / "plan.json")
    need(plan["endpoint"] == ENDPOINT and plan["authority"] == AUTHORITY
         and plan["target_count"] == 2 and plan["byte_cap"] == CAP
         and plan["ttl_ms"] == TTL_MS, "PLAN_SCOPE")
    need(time.time_ns() // 1_000_000 < plan["expires_ms"], "RETENTION_EXPIRED")
    manifest = load(root / "manifest.json")
    need(manifest["sha256"] == digest({k: v for k, v in manifest.items() if k != "sha256"})
         and manifest["plan_sha256"] == digest(plan), "MANIFEST_PIN")
    if expected_manifest_sha256 is not None:
        need(manifest["sha256"] == expected_manifest_sha256, "EXTERNAL_MANIFEST_PIN")
    journal = readonly(DurableJournal, root / "journal.sqlite")
    store = readonly(OperationalStore, root / "market.sqlite")
    bars = journal.replay("BTCUSDT", "15m", limit=3)
    need(len(bars) == len(manifest["records"]) == 2, "COMPLETE_SOURCE_COUNT")
    opens = []
    for row, retained in zip(manifest["records"], bars):
        need(row["sha256"] == digest({k: v for k, v in row.items() if k != "sha256"}), "RECORD_SEAL")
        need(type(row["slot"]) is int and row["slot"] >= 0 and row["slot"] % STEP == 0,
             "RETAINED_SLOT_PATH")
        raw_path = root / f'{row["slot"]}.frame'
        need(raw_path.is_file() and not raw_path.is_symlink()
             and raw_path.stat().st_size <= 4096, "RETAINED_FRAME_PATH_OR_BOUND")
        raw = raw_path.read_bytes()
        need(sha(raw) == row["raw_sha256"], "RETAINED_FRAME_DIGEST")
        _, parsed = parse_frame(raw, row["received_ms"])
        need(parsed.compute_checksum() == row["source_checksum"] == retained.compute_checksum(),
             "RAW_G1_IDENTITY")
        ack = journal.commit_receipt(parsed.stable_key())
        need(ack == row["g1_ack"] and ack["content_digest"] == fingerprint(content(parsed)),
             "RETAINED_ACK_IDENTITY")
        opens.append(parsed.bar_open)
    need(opens[1] - opens[0] == STEP, "SOURCE_SEQUENCE")
    assessment = assess(
        journal, store, symbol="BTCUSDT", interval="15m", opens=opens,
        requirements=[FeatureRequirement("source-readback", "v1", 1)],
        available_versions={"source-readback": "v1"}, decision_ms=manifest["decision_ms"],
        clock_verified=False, interval_ms=STEP,
    )
    need(assessment["features"][0]["reasons"] == ["CLOCK_UNVERIFIED"]
         and len(assessment["source_checksums"]) == 2, "NATIVE_CONSUMER_SOURCE_FAILURE")
    result = {
        "schema": "aql.stage6.durable-source-readback.v1",
        "manifest_sha256": manifest["sha256"], "source_count": len(bars),
        "source_digests": [r["raw_sha256"] for r in manifest["records"]],
        "native_consumer": assessment, "secretary": "WAIT", "orders": 0, "dispatch": None,
        "source_authenticity": "TLS_ENDPOINT_OBSERVED_NOT_INDEPENDENTLY_ATTESTED",
        "clock": "LOCAL_OS_UNVERIFIED", "external_custody": "NOT_ATTESTED",
        "pit_oos": "NOT_ATTESTED",
    }
    return {**result, "sha256": digest(result)}


def acquire(root, *, authority_pin, qualification_file):
    need(authority_pin == AUTHORITY, "OWNER_AUTHORITY_REQUIRED")
    qualification = load(qualification_file)
    need(qualification["endpoint"] == ENDPOINT and all(
        isinstance(qualification.get(k), str) and qualification[k].strip()
        for k in ("source_rights_ref", "network_permission_ref", "region_ref", "custody_ref")),
        "SOURCE_PERMISSION_REFERENCES")
    need(root.is_dir() and {p.name for p in root.iterdir()} == {"retention-owner.json"},
         "NEW_PRIVATE_DIRECTORY_REQUIRED")
    started = time.time_ns() // 1_000_000
    retention = load(root / "retention-owner.json")
    need(retention["scope"] == "ATLAS_STAGE6_ISOLATED_TEST"
         and retention["root"] == str(root.resolve()) and retention["byte_cap"] == CAP
         and started < retention["expires_ms"] <= started + TTL_MS, "RETENTION_OWNER_SCOPE")
    plan = {
        "schema": "aql.stage6.durable-capture-plan.v1", "endpoint": ENDPOINT,
        "authority": AUTHORITY, "started_ms": started, "expires_ms": retention["expires_ms"],
        "ttl_ms": TTL_MS, "byte_cap": CAP, "wall_seconds": WALL_SECONDS, "target_count": 2,
        "connections": 1, "application_subscriptions": 0, "rest_requests": 0,
        "maximum_outbound_pongs_per_second": 1,
        "shared_ip_headroom": "NOT_INDEPENDENTLY_VERIFIED_OWNER_BOUNDED_TEST_SCOPE",
        "qualification_reference_sha256": digest({k: qualification[k] for k in (
            "source_rights_ref", "network_permission_ref", "region_ref", "custody_ref")}),
        "clock": "LOCAL_OS_UNVERIFIED", "orders": 0, "secretary": "WAIT",
        "revision": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
    }
    write_document(root / "plan.json", plan)
    transport = ResearchWebSocket()
    records = []
    received_bytes = 0
    deadline = time.monotonic() + WALL_SECONDS
    last_pong = 0.0
    try:
        # One connection only. Any broken frame/transport ends the bounded
        # attempt and preserves partial evidence; no shared-service retry.
        with transport.stream(25) as connection:
            while len(records) < 2:
                need(time.monotonic() < deadline, "ACQUISITION_TIME_BOUND")
                kind, raw = transport.frame(connection, min(40, deadline - time.monotonic()))
                received_bytes += len(raw)
                need(received_bytes <= CAP, "ACQUISITION_BYTE_BOUND")
                if kind == "ping":
                    need(time.monotonic() - last_pong >= 1, "PONG_RATE_BOUND")
                    connection.pong(raw)
                    last_pong = time.monotonic()
                    continue
                packet = json.loads(raw, object_pairs_hook=unique_fields)
                need(packet.get("e") == "kline" and packet.get("s") == "BTCUSDT"
                     and packet["k"].get("i") == "15m", "STREAM_IDENTITY")
                if packet["k"]["x"] is False:
                    continue
                received = time.time_ns() // 1_000_000
                row = record(root, raw, received, time.monotonic_ns())
                if records:
                    need(row["slot"] == records[-1]["slot"] + STEP, "FINAL_SEQUENCE")
                records.append(row)
                need(sum(p.stat().st_size for p in root.iterdir() if p.is_file()) <= CAP,
                     "RETAINED_BYTE_BOUND")
                print(json.dumps({"captured": len(records), "slot": row["slot"],
                                  "raw_sha256": row["raw_sha256"]}), flush=True)
        decision = time.time_ns() // 1_000_000
        body = {"schema": "aql.stage6.durable-capture.v1", "plan_sha256": digest(plan),
                "records": records, "decision_ms": decision,
                "received_bytes": received_bytes, "tls": "CERT_REQUIRED_HOSTNAME_CHECKED"}
        write_document(root / "manifest.json", {**body, "sha256": digest(body)})
    except BaseException as error:
        write_document(root / "failure.json", {"type": type(error).__name__, "reason": str(error),
                                               "captured": len(records), "received_bytes": received_bytes})
        raise
    return replay(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "readback"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--authority")
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.mode == "capture":
        result = acquire(args.directory, authority_pin=args.authority, qualification_file=args.qualification)
    else:
        need(args.manifest_sha256 is not None, "EXTERNAL_MANIFEST_PIN_REQUIRED")
        result = replay(args.directory, expected_manifest_sha256=args.manifest_sha256)
    print(json.dumps(result, sort_keys=True))
