"""Joined Scanner P0 contract witness. No provider or operational routes."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from tools.atlas_scanner_p0_receivers import ResearchReceivers
from tools.scanner_strategy_f import p0_slice as p
from tools.scanner_strategy_f.p0_delivery import Store, canonical
from tools.scanner_strategy_f.secretary_factory_handoff import create_research_handoff
from tools.scanner_strategy_f.test_p0_slice import ORIGIN, STEP, custody, plugin, request, schedule
from tools.strategy_service_offline.common import Frozen


def rows(path, query):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(query).fetchall()


def replay(root):
    root.mkdir()
    core = root / "core"
    source, strategy = custody(core), plugin()
    plan = schedule(source, [strategy])
    outbox = Store(root / "scanner", plan, plan["sha256"])
    inbox = ResearchReceivers(root / "receivers", outbox, plan["sha256"])
    now = ORIGIN + STEP
    sources = {"BTCUSDT": (source, core)}
    monitor = {"BTCUSDT": [request(strategy), request(strategy, period=8)]}
    event = outbox.poll(now, [strategy], sources, monitor)["rows"][0]
    assert event["state"] == "ENTRY_SIGNAL"
    with pytest.raises(ValueError, match="F3_SOURCE_AND_POLICY_GRAPH_NOT_READY_FOR_PROPOSAL"):
        create_research_handoff(Frozen.build(event).receipt())

    def lose_ack():
        raise OSError("consumer committed but ACK was lost")

    assert outbox.deliver(now, lambda doc: inbox.receive(doc, now), fault=lose_ack) == "PENDING"
    persisted = sum(len(rows(path, "SELECT id FROM effects")) for path in inbox.root.glob("*.sqlite"))
    assert persisted == 1
    outbox = Store(root / "scanner", plan, plan["sha256"])
    inbox = ResearchReceivers(root / "receivers", outbox, plan["sha256"])
    # Retry delay equals the last admissible instant for this fixture.
    retry = now + 1000
    for _ in range(3):
        assert outbox.deliver(retry, lambda doc: inbox.receive(doc, retry)) == "ACKED_FIXTURE"
    assert outbox.deliver(retry, lambda doc: pytest.fail("unexpected dispatch")) == "IDLE"

    now += STEP
    missing = outbox.poll(now, [strategy], {"BTCUSDT": (None, None)}, {})["rows"][0]
    assert missing["state"] == "UNKNOWN"
    now += STEP
    outbox.poll(now, [strategy], sources, {})
    assert outbox.deliver(now + plan["lag_ms"] + 1, lambda _: pytest.fail("expired dispatch")) == "EXPIRED"
    census = inbox.record_census()
    assert inbox.record_census() == census
    assert sorted(proof["disposition"] for proof in census) == [
        "EXPIRED_RESEARCH_ONLY", "RESEARCH_CENSUS", "RESEARCH_CENSUS", "RESEARCH_CENSUS",
    ]

    with outbox.tx() as db:
        delivered = db.execute("SELECT raw,ack FROM outbox WHERE state='ACKED' ORDER BY id").fetchall()
        batches = [json.loads(raw) for raw, in db.execute("SELECT raw FROM batches ORDER BY id")]
    assert len(batches) == 2
    for batch in batches:
        native = p.native.verify_factory_signal_batch(batch).data
        assert native["trading_authority"] == "NONE" and not native["cost_or_pnl_computed"]

    records = {}
    for route, count in (("secretary", 5), ("lab", 2)):
        saved = rows(inbox.root / (route + ".sqlite"), "SELECT body,receipt FROM effects ORDER BY id")
        assert len(saved) == count
        records[route] = [(json.loads(body), json.loads(proof)) for body, proof in saved]
    assert {row["availability"] for row, _ in records["lab"]} == {"UNKNOWN", "AVAILABLE"}
    assert {row["state"] for row, _ in records["secretary"]} == {"ENTRY_SIGNAL", "UNKNOWN"}

    for raw, ack in delivered:
        envelope = json.loads(raw)
        route = envelope["route"]
        assert json.loads(ack)["effect_sha256"] == envelope["sha256"]
        assert any(proof["effect_sha256"] == envelope["sha256"] for _, proof in records[route.lower()])
        body = p.seal({**{k: v for k, v in envelope["body"].items() if k != "sha256"},
                       "authority": "PAPER"})
        bad = p.seal({**{k: v for k, v in envelope.items() if k != "sha256"}, "body": body})
        with pytest.raises(ValueError, match="RECEIVER_ENVELOPE_SCOPE"):
            inbox.receive(bad, retry)
        if route == "SECRETARY":
            with pytest.raises(ValueError, match="RECEIVER_EXPIRED_OR_NOT_SIGNAL"):
                inbox.receive(envelope, retry + 1)
        else:
            forged = p.seal({**{k: v for k, v in envelope["body"].items() if k != "sha256"},
                             "decision_sha256": "a" * 64})
            with pytest.raises(ValueError, match="RECEIVER_UNBOUND_OUTBOX"):
                inbox.receive(outbox._envelope("LAB", forged), retry)

    return dict(plan_sha256=plan["sha256"], records=records, acks=[json.loads(ack) for _, ack in delivered],
                batch_sha256=[batch["sha256"] for batch in batches], network_calls=0, authority="NONE")


def test_two_joined_replays(tmp_path):
    first = replay(tmp_path / "first")
    second = replay(tmp_path / "second")
    assert canonical(first) == canonical(second)
    (Path.cwd() / "receiver-proof.json").write_bytes(canonical(first))
    print("RECEIVER_PROOF_SHA256=" + p.digest(first))


def test_no_signal_and_bad_lab_payload_are_separate(tmp_path):
    from research_wp_r0.strategy_definition import StrategyDefinition

    core = tmp_path / "core"
    source = custody(core)
    definition = Frozen.restore(plugin()).data["definition"]["definition"]
    definition["entry"]["right"]["value"] = 999
    definition = StrategyDefinition(definition, registry=p.IndicatorRegistryV2()).to_dict()
    strategy = p.native.register_strategy_plugin(definition, config_digest=p.native.manual_config_digest(definition))
    plan = schedule(source, [strategy])
    outbox = Store(tmp_path / "scanner", plan, plan["sha256"])
    inbox = ResearchReceivers(tmp_path / "receivers", outbox, plan["sha256"])
    now = ORIGIN + STEP
    decision = outbox.poll(now, [strategy], {"BTCUSDT": (source, core)},
                           {"BTCUSDT": [request(strategy)]})["rows"][0]
    assert decision["state"] == "NO_SIGNAL"
    assert outbox.evidence()["routes"] == {"LAB": 1}

    with outbox.tx() as db:
        (key, raw) = db.execute("SELECT id,raw FROM outbox").fetchone()
        doc = json.loads(raw)
        body = p.seal({**{k: v for k, v in doc["body"].items() if k != "sha256"}, "version": None})
        invalid = outbox._envelope("LAB", body)
        db.execute("UPDATE outbox SET id=?,raw=? WHERE id=?",
                   (invalid["sha256"], canonical(invalid), key))
    assert outbox.deliver(now, lambda doc: inbox.receive(doc, now)) == "QUARANTINED"
    assert not (inbox.root / "lab.sqlite").exists()
    assert inbox.record_census()[0]["body_sha256"] == decision["sha256"]
