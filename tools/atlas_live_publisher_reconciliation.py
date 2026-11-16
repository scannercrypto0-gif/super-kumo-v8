"""Read-only reconciliation of sealed Spot observations and saved Vision custody."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import socket
from unittest.mock import patch

from aql.observation.contracts import digest
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from tools.atlas_authorized_archive_research import verify
from tools.atlas_live_research_cycle import ENDPOINT, STEP
from tools.atlas_saved_research_disposition import publish, require, without_seal
from tools.atlas_single_receipt import parse_final, unique_json_keys

SCHEMA = "atlas.live-publisher-reconciliation.v1"
DAY = 86_400_000
MINUTE = 60_000


def sealed(body):
    return {**body, "sha256": digest(body)}


def is_pin(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def load(path):
    with path.open("rb") as stream:
        raw = stream.read(65_537)
    require(len(raw) <= 65_536, "RECONCILIATION_INPUT_BOUND")
    return json.loads(raw, object_pairs_hook=unique_json_keys)


def observation_meta(row, plan_pin, uncertainty):
    return dict(slot=row["slot"], received=row["received_ms"], event=row["event_ms"],
                uncertainty=uncertainty, session=plan_pin, payload_sha256=row["payload_sha256"])


def live_rows(live, live_pin, plan, plan_pin, uncertainty, as_of_ms):
    require(is_pin(live_pin) and live.get("sha256") == live_pin == without_seal(live)
            and is_pin(plan_pin) and digest(plan) == plan_pin == live["plan_sha256"], "LIVE_PARENT_PIN")
    start = plan["slot"]
    require(type(start) is int and start > 0 and start % STEP == 0
            and plan["endpoint"] == ENDPOINT and plan["bar_count"] == 4 and plan["wall_ms"] == 3_900_000
            and plan["rest_requests"] == live["rest_requests"] == 0
            and plan["retention"] == live["retention"] == "SANITIZED_RECEIPTS_ONLY"
            and type(uncertainty) is int and 0 <= uncertainty <= 250
            and type(as_of_ms) is int, "LIVE_PLAN_SCOPE")
    factory = live["factory"]
    require(factory["schema"] == "aql.factory.prospective-research-read.v1"
            and factory["evidence_mode"] in {"PUBLIC_WS_OBSERVATION", "SYNTHETIC_TESTED"}
            and factory["sha256"] == without_seal(factory)
            and factory["orders_enabled"] is False and factory["secretary_enqueued"] is False
            and factory["trading_authority"] == "NONE"
            and live["admission"] == "WAIT_AUTHENTICATED_PARENTS", "FACTORY_PARENT_SCOPE")
    rows = live["bars"]
    require([row["slot"] for row in rows] == list(range(start, start + 4 * STEP, STEP)),
            "LIVE_FINAL_ORDER_OR_GAP")
    last_received = -1
    for row in rows:
        end = row["slot"] + STEP
        event, received, committed = (row[key] for key in ("event_ms", "received_ms", "committed_ms"))
        require(all(type(x) is int for x in (event, received, committed))
                and end - 1 <= event <= received + uncertainty
                and max(received, end + uncertainty) <= committed <= factory["as_of_ms"] <= as_of_ms
                and received > last_received and end - 1 < received + uncertainty <= end - 1 + 300_000,
                "LIVE_SOURCE_CLOCK")
        require(all(is_pin(row[key]) for key in ("source_sha256", "payload_sha256", "ack_sha256", "scanner_sha256"))
                and row["source_sha256"] == digest(observation_meta(row, plan_pin, uncertainty)),
                "LIVE_SOURCE_SESSION")
        last_received = received
    return rows


def publisher_day(run, original, result_pin):
    manifest = load(run / "source.json")
    opening, end = (manifest[key] for key in ("start_ms", "end_exclusive_ms"))
    require(type(opening) is int and opening > 0 and opening % DAY == 0 and end == opening + DAY
            and manifest["market"] == ["BINANCE", "SPOT", "BTCUSDT", "BTC", "USDT", "UTC"]
            and manifest["native_interval"] == "1m" and manifest["rights_status"] == "VERIFIED_FOR_EXACT_USE",
            "PUBLISHER_SOURCE_SCOPE")
    day = datetime.fromtimestamp(opening / 1000, timezone.utc).date().isoformat()
    experiment = "ATLAS-RETROSPECTIVE-BTCUSDT-" + day.replace("-", "")
    result = verify(run, experiment)
    require(is_pin(result_pin) and result["sha256"] == result_pin, "PUBLISHER_RESULT_PIN")
    archive = f"BTCUSDT-1m-{day}.zip"
    with (original / (archive + ".CHECKSUM")).open("rb") as stream:
        checksum = stream.read(513)
    match = re.fullmatch(rb"([0-9a-f]{64})\s+\*?" + re.escape(archive.encode()), checksum.strip())
    with (original / archive).open("rb") as stream:
        raw = stream.read(4 * 1024**2 + 1)
    archive_pin = sha256(raw).hexdigest()
    require(0 < len(raw) <= 4 * 1024**2 and len(checksum) <= 512 and match is not None
            and archive_pin == match[1].decode() == result["archive_sha256"] == manifest["archive_sha256"]
            and sha256(checksum).hexdigest() == result["checksum_sha256"] == manifest["checksum_sha256"],
            "PUBLISHER_ZIP_CHECKSUM_CUSTODY")
    scanner = load(run / "scanner.json")
    cutoff = scanner["decision_cutoff_ms"]
    native = query_local(run / "core", experiment, 1, opening, end, cutoff,
                         required_source_sha256=archive_pin, require_complete=True, sqlite_immutable=True)
    require(native["query_sha256"] == result["core253"] == scanner["core253"]
            and [bar["bar_open_ms"] for bar in native["bars"]] == list(range(opening, end, MINUTE))
            and all(bar["bar_close_ms"] == bar["bar_open_ms"] + MINUTE - 1 for bar in native["bars"]),
            "PUBLISHER_NATIVE_GRID_OR_PIN")
    published = manifest["publisher_first_available_at_ms"]
    require(published is None or (type(published) is int and end <= published <= cutoff), "PUBLISHER_RELEASE_CLOCK")
    return dict(start_ms=opening, end_ms=end, manifest_sha256=digest(manifest), archive_sha256=archive_pin,
                checksum_sha256=result["checksum_sha256"], result_sha256=result_pin, core253=native["query_sha256"],
                published_at_ms=published, source_cutoff_ms=cutoff, bars=native["bars"])


def publisher_slot(day, slot):
    first = (slot - day["start_ms"]) // MINUTE
    bars = day["bars"][first:first + 15]
    if ([bar["bar_open_ms"] for bar in bars] != list(range(slot, slot + STEP, MINUTE))
            or any(bar["bar_close_ms"] != bar["bar_open_ms"] + MINUTE - 1 for bar in bars)):
        return None, None
    parent = {key: day[key] for key in ("manifest_sha256", "archive_sha256", "checksum_sha256",
                                       "result_sha256", "core253", "published_at_ms", "source_cutoff_ms")}
    parent["row_sha256"] = digest(bars)
    return parent, (Decimal(str(bars[0]["open"])), max(Decimal(str(b["high"])) for b in bars),
                    min(Decimal(str(b["low"])) for b in bars), Decimal(str(bars[-1]["close"])),
                    sum(Decimal(str(b["volume"])) for b in bars))


def reconcile(live, live_pin, plan, plan_pin, uncertainty, as_of_ms, publishers=(), *,
              live_frames=None, previous=None, previous_pin=None):
    rows = live_rows(live, live_pin, plan, plan_pin, uncertainty, as_of_ms)
    by_day = {day["start_ms"]: day for day in publishers}
    require(len(by_day) == len(publishers), "PUBLISHER_DUPLICATE_DAY")
    require((previous is None) == (previous_pin is None), "PREVIOUS_PAIR_REQUIRED")
    if previous is not None:
        require(is_pin(previous_pin) and previous["sha256"] == previous_pin == without_seal(previous)
                and previous["schema"] == SCHEMA and previous["live_summary_sha256"] == live_pin
                and previous["plan_sha256"] == plan_pin and previous["as_of_ms"] <= as_of_ms
                and [row["slot"] for row in previous["rows"]] == [row["slot"] for row in rows],
                "PREVIOUS_RECEIPT_SCOPE")
    previous_rows = {row["slot"]: row for row in previous["rows"]} if previous else {}
    matched_frames = live_frames or {}
    require(set(matched_frames) <= {row["slot"] for row in rows}, "FOREIGN_COMPARABLE_SLOT")
    slots = []
    for row in rows:
        slot = row["slot"]
        day = by_day.get(slot - slot % DAY)
        parent, values = publisher_slot(day, slot) if day else (None, None)
        raw = matched_frames.get(slot)
        if raw is not None:
            require(sha256(raw).hexdigest() == row["payload_sha256"], "COMPARABLE_LIVE_PIN")
            event, _ = parse_final(raw, slot, row["received_ms"], uncertainty)
            require(event == row["event_ms"], "COMPARABLE_LIVE_EVENT")
            observed = json.loads(raw, object_pairs_hook=unique_json_keys)["k"]
        available = parent is not None and parent["published_at_ms"] is not None
        if parent and parent["source_cutoff_ms"] > as_of_ms:
            parent, values, available = None, None, False
        publisher_status = "SOURCE_MISSING" if day is not None else "PUBLISHER_PENDING"
        comparison = "COMPARISON_NOT_POSSIBLE"
        reason = "LIVE_VALUES_NOT_RETAINED" if raw is None else "PUBLISHER_NOT_AVAILABLE"
        if parent:
            publisher_status = "PUBLISHER_CUSTODY_VERIFIED"
            if raw is not None and not available:
                reason = "PUBLISHER_FIRST_AVAILABLE_UNKNOWN"
            elif raw is not None and parent["published_at_ms"] <= as_of_ms:
                live_values = tuple(Decimal(str(observed[field])) for field in ("o", "h", "l", "c", "v"))
                comparison = "MATCH" if live_values == values else "MISMATCH"
                publisher_status = ("PUBLISHER_ARCHIVE_VERIFIED" if comparison == "MATCH"
                                    else "DISCREPANCY_QUARANTINED")
                reason = None
        prior = previous_rows.get(slot, {}).get("publisher")
        changed = bool(prior and parent and any(prior[key] != parent[key]
                       for key in ("archive_sha256", "checksum_sha256", "row_sha256")))
        if changed:
            publisher_status = "DISCREPANCY_QUARANTINED"
            reason = "PUBLISHER_ARCHIVE_REVISION"
        slots.append(dict(
            slot=slot, close_ms=slot + STEP - 1, final=True, live_status="PROVISIONAL_FINAL_BAR",
            live_receipt_sha256=row["source_sha256"], core_ack_sha256=row["ack_sha256"],
            scanner_sha256=row["scanner_sha256"], event_ms=row["event_ms"], observed_at_ms=row["received_ms"],
            live_quality="VALID_FINAL_ORDER_AND_CLOCK",
            freshness_at_as_of="STALE" if as_of_ms - row["received_ms"] > 300_000 else "RECENT_RECEIPT",
            actionable_now=False,
            publisher=parent, publisher_status=publisher_status, comparison=comparison, reason=reason))
    coverage = [{k: day[k] for k in ("start_ms", "end_ms", "result_sha256", "archive_sha256", "checksum_sha256",
                                    "core253", "published_at_ms")}
                for day in sorted(publishers, key=lambda item: item["start_ms"]) if day["source_cutoff_ms"] <= as_of_ms]
    return sealed(dict(schema=SCHEMA, as_of_ms=as_of_ms, market="BINANCE:SPOT:BTCUSDT", interval="15m",
                       comparison_basis="CORE_NATIVE_NUMERIC_DOMAIN_V1",
                       live_summary_sha256=live_pin, plan_sha256=plan_pin, previous_sha256=previous_pin,
                       evidence_mode=live["factory"]["evidence_mode"], publisher_custody=coverage, rows=slots,
                       factory_parent_sha256=live["factory"]["sha256"], secretary="WAIT", dispatch=None,
                       current_entry="NO_CURRENT_ENTRY", orders=0, telegram="NOT_SENT", scientific="REAL_PIT_OOS_BLOCKED"))


def factory_view(receipt, pin):
    require(is_pin(pin) and receipt["sha256"] == pin == without_seal(receipt)
            and receipt["schema"] == SCHEMA and receipt["secretary"] == "WAIT"
            and receipt["dispatch"] is None and receipt["orders"] == 0
            and receipt["current_entry"] == "NO_CURRENT_ENTRY", "RECONCILIATION_RECEIPT_PIN")
    return {key: receipt[key] for key in ("sha256", "factory_parent_sha256", "evidence_mode", "rows",
                                          "secretary", "dispatch", "orders", "current_entry", "scientific")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read", type=Path)
    parser.add_argument("--receipt-pin")
    parser.add_argument("--live", type=Path)
    parser.add_argument("--live-pin")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-pin")
    parser.add_argument("--uncertainty", type=int)
    parser.add_argument("--as-of-ms", type=int)
    parser.add_argument("--publisher", nargs=3, action="append", default=[], metavar=("RUN", "ORIGINAL", "RESULT_PIN"))
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--previous-pin")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        if args.read:
            print(json.dumps(factory_view(load(args.read), args.receipt_pin), sort_keys=True))
            return
        require(args.live and args.plan and args.output_dir and args.as_of_ms is not None,
                "RECONCILIATION_ARGUMENTS")
        days = [publisher_day(Path(run), Path(original), pin) for run, original, pin in args.publisher]
        receipt = reconcile(load(args.live), args.live_pin, load(args.plan), args.plan_pin,
                            args.uncertainty, args.as_of_ms, days,
                            previous=load(args.previous) if args.previous else None, previous_pin=args.previous_pin)
        publish(args.output_dir / (receipt["sha256"] + ".json"), receipt)
        print(receipt["sha256"])


if __name__ == "__main__":
    main()
