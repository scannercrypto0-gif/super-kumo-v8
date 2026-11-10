"""G1-only offline acceptance; real existing journal/store, synthetic clocks."""
from dataclasses import replace
import sqlite3
from unittest.mock import patch
import pytest
from aql.foundation.census import census
from aql.foundation.readiness import FeatureRequirement, assess
from aql.foundation.scheduler import AdaptiveScheduler, Job
from aql.recovery.rest_budget import RestBudget
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.lanes import JournalConsumer
from aql.models.bar import MarketBar
from aql.g1_integrity import ContentConflictError


def bar(i=0):
    return MarketBar("BTCUSDT", "1m", i*60000, (i+1)*60000-1,
                     10., 11., 9., 10., 1., True, "synthetic", (i+1)*60000).with_checksum()


def snapshot():
    return {"symbols": [dict(symbol="BTCUSDT", status="TRADING", isSpotTradingAllowed=True),
                         dict(symbol="OLDUSDT", status="BREAK", isSpotTradingAllowed=False),
                         dict(symbol="BADUSDT"), None]}


def test_complete_census_preserves_every_discovered_row_and_replay():
    out = census(snapshot(), observed_ms=1, decision_ms=2)
    assert out == census(snapshot(), observed_ms=1, decision_ms=2)
    assert out["counts"] == {"ELIGIBLE": 1, "UNSUPPORTED": 1, "ERROR": 2}
    assert len(out["records"]) == sum(out["counts"].values()) == out["discovered"]


def test_duplicate_symbols_cannot_be_eligible():
    rows = snapshot(); rows["symbols"] = [rows["symbols"][0]] * 2
    assert census(rows, observed_ms=1, decision_ms=2)["counts"]["ERROR"] == 2


@pytest.mark.parametrize("value", [None, {}, {"symbols": "bad"}, {"symbols": [None]*3}])
def test_invalid_or_oversized_universe_never_silently_truncates(value):
    with pytest.raises(ValueError):
        census(value, observed_ms=1, decision_ms=2, max_symbols=2)


def test_future_snapshot_blocked():
    with pytest.raises(ValueError):
        census(snapshot(), observed_ms=3, decision_ms=2)


def test_unknown_market_status_is_error_not_unsupported():
    value=snapshot(); value["symbols"][0]["status"]="NEW_UNKNOWN_STATUS"
    assert census(value,observed_ms=1,decision_ms=2)["records"][0]["reason"] == "UNKNOWN_MARKET_STATUS"


@pytest.mark.parametrize("pressure", [-1,2,float("nan"),True])
def test_invalid_pressure_cannot_admit_jobs(pressure):
    s=scheduler([0.])
    with pytest.raises(ValueError): s.take(pressure=pressure)


@pytest.fixture
def pipeline(tmp_path):
    j = DurableJournal(str(tmp_path/"j.sqlite"))
    s = OperationalStore(str(tmp_path/"s.sqlite"))
    with patch("time.time", return_value=200):
        for i in range(3):
            b = bar(i); j.commit(b)
    JournalConsumer(j, s, "BTCUSDT", "1m").drain_once()
    return j, s


def ready(pipeline, **changes):
    args = dict(symbol="BTCUSDT", interval="1m", opens=[0, 60000, 120000],
                requirements=[FeatureRequirement("SMA", "v1", 3)],
                available_versions={"SMA": "v1"}, decision_ms=210000, clock_verified=True)
    args.update(changes)
    return assess(*pipeline, **args)


def test_decision_specific_readiness_and_deterministic_restart(pipeline):
    j, s = pipeline
    out = ready(pipeline)
    assert out["ready"], out
    assert out == ready((DurableJournal(j.db_path), OperationalStore(s.db_path)))
    assert not ready(pipeline, requirements=[FeatureRequirement("SMA", "v1", 4)])["ready"]
    assert not ready(pipeline, available_versions={"SMA": "v2"})["ready"]
    assert not ready(pipeline, requirements=[FeatureRequirement("EMA", "v1", 2)])["ready"]


@pytest.mark.parametrize("changes,reason", [
    ({"clock_verified": False}, "CLOCK_UNVERIFIED"),
    ({"clock_verified": 1}, "CLOCK_UNVERIFIED"),
    ({"decision_ms": 150000}, "FUTURE_OR_INVALID_BAR"),
    ({"decision_ms": 190000}, "COMMIT_NOT_AVAILABLE_ASOF"),
    ({"opens": [60000,120000,180000]}, "MISSING_BAR")])
def test_asof_clock_warmup_fail_closed(pipeline, changes, reason):
    out = ready(pipeline, **changes)
    assert not out["ready"]
    assert reason in out["features"][0]["reasons"]


def test_conflict_quarantines_existing_readiness(pipeline):
    j, s = pipeline
    assert ready(pipeline)["ready"]
    changed = replace(bar(), close=10.5).with_checksum()
    with pytest.raises(ContentConflictError):
        j.commit(changed)
    assert not ready(pipeline)["ready"]


@pytest.mark.parametrize("field,value", [("is_final",0),("checksum","bad"),("ingested_at",999999)])
def test_store_tamper_or_future_cannot_admit(pipeline, field, value):
    j,s = pipeline
    with sqlite3.connect(s.db_path) as conn:
        conn.execute(f"UPDATE market_bars SET {field}=? WHERE bar_open=0", (value,))
    assert not ready(pipeline)["ready"]


def test_failed_store_restart_and_duplicate_delivery_are_idempotent(tmp_path):
    from unittest.mock import Mock
    j = DurableJournal(str(tmp_path/"j.sqlite"))
    s = OperationalStore(str(tmp_path/"s.sqlite"))
    with patch("time.time", return_value=200):
        for i in range(3): j.commit(bar(i))
    consumer = JournalConsumer(j, Mock(upsert=Mock(side_effect=ConnectionError)), "BTCUSDT", "1m")
    with pytest.raises(ConnectionError): consumer.drain_once()
    assert not ready((j,s))["ready"]
    s.upsert(bar())  # committed remote/local effect before ACK, then crash
    j = DurableJournal(j.db_path)
    consumer = JournalConsumer(j, s, "BTCUSDT", "1m", batch_size=2)
    assert consumer.drain_once() == 2
    assert consumer.drain_once() == 1
    assert consumer.drain_once() == 0
    assert s.count() == 3
    assert ready((j,s))["ready"]


def scheduler(clock, **kwargs):
    return AdaptiveScheduler(RestBudget(limit=10,reserve=2,clock=lambda:clock[0]),
                             RestBudget(limit=10,reserve=2,clock=lambda:clock[0]),
                             capacity=6,core_reserve=2,max_batch=4,**kwargs)


def test_bounded_backlog_p0_reserve_and_pressure():
    clock=[0.]; s=scheduler(clock)
    for i in range(4): assert s.submit(Job(str(i),1,1,1))
    assert not s.submit(Job("overflow",1))
    assert s.submit(Job("core",0,2,2))
    assert not s.submit(Job("core",0))
    assert [j.identity for j in s.take(pressure=.9)] == ["core"]
    assert s.batch == 2
    assert s.take(pressure=.9) == []
    assert len(s.take(pressure=.1)) == 2
    assert s.metrics["peak_backlog"] <= 6


def test_shared_api_budget_db_quota_cooldown_and_rollover():
    clock=[0.]; s=scheduler(clock)
    s.api.acquire(8)  # another cooperative consumer uses shared allowance
    assert s.submit(Job("background",1,1,1))
    assert s.take(pressure=.1) == []
    assert s.submit(Job("core",0,2,2))
    assert [j.identity for j in s.take(pressure=.9)] == ["core"]
    s.api.cooldown(60)
    clock[0]=61
    assert [j.identity for j in s.take(pressure=.1)] == ["background"]
    assert s.metrics["api_weight_reserved"] == 3
    assert s.metrics["db_writes_reserved"] >= 3


def test_db_pressure_does_not_spend_api_allowance():
    clock=[0.]; s=scheduler(clock)
    s.db.acquire(8)
    s.submit(Job("background",1,1,1))
    assert s.take(pressure=.1) == []
    assert s.api.used == 0
    s.submit(Job("core",0,2,2))
    assert [j.identity for j in s.take(pressure=.1)] == ["core"]


@pytest.mark.parametrize("cost", [-1,True,1.2])
def test_invalid_cost_never_bypasses_budget(cost):
    with pytest.raises(ValueError): Job("bad",0,cost,1)
