"""Offline one-bar receipt adapter. Uses native G1 and prospective readers."""
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from time import time_ns

from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.observation.contracts import digest
from aql.observation.prospective import ProspectiveObserver, STEP
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research
from tools.atlas_prospective_observe import FIXTURE, read_only_g1
from tools.binance_live_feed.quota import Quota

MAX_RAW = 65536
STREAM = "btcusdt@kline_15m"


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def reserve_once(quota, now):
    """Consume a local attempt even if a subsequent handshake never succeeds."""
    with quota.tx() as db:
        need(not Quota.get(db, "receipt_attempt"), "ONE_SHOT_CONSUMED")
        Quota.set(db, "receipt_attempt", 1)
    need(quota.connect("receipt-15m", now, [STREAM]), "WS_RESERVATION_DENIED")
    return "SHARED_EGRESS_UNVERIFIED"


def unique_json_keys(pairs):
    values = dict(pairs)
    need(len(values) == len(pairs), "DUPLICATE_JSON_KEY")
    return values


def parse_final(raw, slot, received, uncertainty):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_RAW, "RAW_LIMIT")
    need(all(type(t) is int for t in (slot, received, uncertainty)) and slot >= 0
         and slot % STEP == 0 and 0 <= uncertainty <= 250, "CLOCK_OR_SLOT")
    data = json.loads(raw, object_pairs_hook=unique_json_keys)
    kline = data["k"]
    end = slot + STEP - 1
    need(kline["s"] == "BTCUSDT" and kline["i"] == "15m" and
         type(kline["t"]) is int and type(kline["T"]) is int and
         kline["t"] == slot and kline["T"] == end, "CANDLE_IDENTITY")
    need(kline["x"] is True, "CANDLE_NOT_FINAL")
    need(type(data["E"]) is int and data["E"] >= end and
         data["E"] <= received + uncertainty, "EVENT_CLOCK")
    need(received - uncertainty > end and received + uncertainty <= end + 300000,
         "RECEIPT_OUTSIDE_WINDOW")
    bar = MarketBar.from_binance_ws_kline(kline)
    need(all(math.isfinite(x) for x in (bar.open, bar.high, bar.low, bar.close, bar.volume)) and
         0 < bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
         and bar.volume >= 0, "CANDLE_VALUES")
    bar.ingested_at = received
    return data["E"], bar.with_checksum()


def persist_frame(root, raw, *, slot, received, uncertainty, monotonic_ns, session):
    # Caller provides a private dedicated root. No network or retries here.
    need(type(monotonic_ns) is int and monotonic_ns >= 0 and
         isinstance(session, str) and 0 < len(session) <= 64, "SESSION_CLOCK")
    event, _ = parse_final(raw, slot, received, uncertainty)
    metadata = dict(slot=slot, received=received, uncertainty=uncertainty, event=event,
                    monotonic_ns=monotonic_ns, session=session, version=1,
                    payload_sha256=hashlib.sha256(raw).hexdigest(),
                    fixture_sha256=json.loads(FIXTURE.read_text())[0]["sha256"])
    with closing(sqlite3.connect(root / "receipt.sqlite")) as db, db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS frame (id INTEGER PRIMARY KEY CHECK(id=1),"
                   " raw BLOB NOT NULL, metadata TEXT NOT NULL, seal TEXT NOT NULL)")
        prior = db.execute("SELECT raw FROM frame WHERE id=1").fetchone()
        if prior:
            need(prior[0] == raw, "CANDLE_REVISION")
        else:
            db.execute("INSERT INTO frame VALUES (1,?,?,?)",
                       (raw, json.dumps(metadata, sort_keys=True), digest(metadata)))


def load_frame(root):
    with closing(sqlite3.connect((root / "receipt.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        raw, encoded, seal = db.execute("SELECT raw, metadata, seal FROM frame WHERE id=1").fetchone()
    meta = json.loads(encoded)
    need(digest(meta) == seal and hashlib.sha256(raw).hexdigest() == meta["payload_sha256"],
         "CUSTODY_TAMPER")
    event, bar = parse_final(raw, meta["slot"], meta["received"], meta["uncertainty"])
    need(event == meta["event"] and meta["fixture_sha256"] ==
         json.loads(FIXTURE.read_text())[0]["sha256"], "CUSTODY_METADATA")
    return meta, seal, bar


def observer(root, synthetic, *, write):
    if write:
        journal = DurableJournal(str(root / "journal.sqlite"))
        store = OperationalStore(str(root / "market.sqlite"))
    else:
        journal = read_only_g1(DurableJournal, root / "journal.sqlite")
        store = read_only_g1(OperationalStore, root / "market.sqlite")
    return ProspectiveObserver(root / "decision.sqlite", journal, store,
                               json.loads(FIXTURE.read_text())[0], synthetic=synthetic,
                               read_only=not write)


def materialize(root, *, synthetic):
    meta, _, bar = load_frame(root)
    obs = observer(root, synthetic, write=True)
    obs.journal.commit(bar)
    obs.store.upsert(bar)
    obs.journal.mark_persisted(bar.stable_key())
    ack = obs.journal.commit_receipt(bar.stable_key())
    committed = ack["commit_return_observed_at_ms"]
    need(ack["status"] == "SQLITE_COMMIT_RETURN_OBSERVED" and committed >= meta["received"]
         and time_ns() // 1000000 >= committed + meta["uncertainty"], "CUTOFF_CLOCK_OVERLAP")
    obs.tick()


def readback(root, *, cutoff_ms, synthetic, expected_receipt_sha256=None):
    meta, seal, bar = load_frame(root)
    need((synthetic and expected_receipt_sha256 is None) or seal == expected_receipt_sha256,
         "RECEIPT_PIN")
    obs = observer(root, synthetic, write=False)
    ack = obs.journal.commit_receipt(bar.stable_key())
    need(ack["status"] == "SQLITE_COMMIT_RETURN_OBSERVED" and
         ack["commit_return_observed_at_ms"] + meta["uncertainty"] <= cutoff_ms,
         "CUTOFF_CLOCK_OVERLAP")
    view = obs.verified_read(as_of_ms=cutoff_ms)
    rows = view["rows"]
    need(len(rows) == 1 and rows[0]["source_valid"] and
         rows[0]["decision"]["parent"]["g1_receipt_sha256"] == digest(ack) and
         rows[0]["decision"]["cutoff_ms"] >= ack["commit_return_observed_at_ms"] + meta["uncertainty"],
         "SCANNER_PARENT_OR_CUTOFF")
    factory = read_prospective_research(obs, as_of_ms=cutoff_ms)
    need(factory["orders_enabled"] is False and factory["secretary_enqueued"] is False,
         "RESEARCH_ONLY")
    body = dict(grade="TEST_ONLY" if synthetic else "RECEIPT_TIME_OBSERVATION_ONLY",
                source_receipt_sha256=seal, payload_sha256=meta["payload_sha256"],
                commit_receipt_sha256=digest(ack), committed_ms=ack["commit_return_observed_at_ms"],
                receipt=meta, scanner_sha256=rows[0]["decision_sha256"], factory=factory,
                factory_admission="WAIT_AUTHENTICATED_PARENTS", lab="NOT_EVALUATED",
                strict_pit_oos="BLOCKED", trading_authority="NONE")
    return {**body, "sha256": digest(body)}


def ws_upgrade_status(status):
    need(status not in (418, 429), "PROVIDER_RATE_STOP")
    need(status == 101, "WS_UPGRADE")
