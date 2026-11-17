"""Fixture-only native Core, Scanner and Factory prospective read contract."""
import json
from pathlib import Path
from unittest.mock import patch

from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.observation import prospective
from aql.observation.forward_evidence import read_forward_evidence
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research


def test_native_prospective_reopen_and_forward_read(tmp_path):
    fixture_path = Path(__file__).resolve().parents[1] / "tools/strategy_service_offline/fixtures/strategies.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))[0]
    journal = DurableJournal(str(tmp_path / "g1.sqlite"))
    store = OperationalStore(str(tmp_path / "store.sqlite"))
    db = tmp_path / "g2.sqlite"
    observer = prospective.ProspectiveObserver(db, journal, store, fixture, synthetic=True)
    for index in range(4):
        opened = index * prospective.STEP
        close = opened + prospective.STEP - 1
        received = close + 1
        bar = MarketBar("BTCUSDT", "15m", opened, close, 101., 102., 100., 101.,
                        4., True, "binance_ws", received).with_checksum()
        with patch("time.time", return_value=(received + 2) / 1000):
            journal.commit(bar)
            store.upsert(bar)
            journal.mark_persisted(bar.stable_key())
        as_of = received + 3
        with patch.object(prospective, "time_ns", return_value=as_of * 1_000_000):
            observer.tick()
    initial = read_prospective_research(observer, as_of_ms=as_of)
    readonly = prospective.ProspectiveObserver(db, journal, store, fixture,
                                               synthetic=True, read_only=True)
    assert initial == read_prospective_research(readonly, as_of_ms=as_of)
    assert sum(initial["decision_counts"].values()) == 4
    assert initial["trading_authority"] == "NONE"
    assert not initial["orders_enabled"] and not initial["secretary_enqueued"]
    forward = read_forward_evidence(readonly, as_of_ms=as_of)
    assert forward == read_forward_evidence(readonly, as_of_ms=as_of)
    assert forward["evidence_mode"] == "SYNTHETIC_TESTED"
    assert forward["historical_pit"] == "NOT_ATTESTED"
