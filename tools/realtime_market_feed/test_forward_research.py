"""Off-host forward Analyzer integration tests against the exact pinned kernel."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = ROOT / ".integration" / "warehouse"
sys.path.insert(0, str(WAREHOUSE / "src"))
from tools.realtime_market_feed.service import Store as FeedStore, PRODUCER_CODE_SHA256

BASELINE = ROOT / ".integration" / "research-baseline"
DEPENDENCIES = ROOT / ".integration" / "research-kernel"
REST_CODE_SHA256 = "a" * 64
STRATEGY_SHA256 = "bab9bac7e8cbb6dca5db21ba685a5027d2f197babbc2ec7c60468233a724aabf"

_CALL = r"""
import hashlib, json, os, sys
from pathlib import Path
root=Path(os.environ["AQL_WORKTREE"])
sys.path.insert(0,str(root))
from tools.realtime_market_feed import forward_research as fr
args=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
mode=args.pop("mode",None)
if mode in ("recovered","future"):
    original=fr.project_feed_window
    def injected(*a,**kw):
        value=original(*a,**kw)
        if mode=="recovered":
            value["lineage"][-1]["source_class"]="BINANCE_SPOT_PUBLIC_REST_MARKET_DATA"
        else:
            value["lineage"][-1]["available_at_ms"]=args["decision_cutoff_ms"]+1
        return value
    fr.project_feed_window=injected
try:
    result=fr.analyze_forward_window(
        args.pop("feed_database"), args.pop("research_database"),
        symbol=args.pop("symbol"), start_ms=args.pop("start_ms"),
        bar_count=args.pop("bar_count"),
        decision_cutoff_ms=args.pop("decision_cutoff_ms"),
        clock_evidence=args.pop("clock_evidence"),
        config=args.pop("config"),
        expected_config_sha256=args.pop("expected_config_sha256"),
        expected_ws_producer_code_sha256=args.pop("expected_ws_producer_code_sha256"),
        expected_rest_producer_code_sha256=args.pop("expected_rest_producer_code_sha256"),
        baseline_root=args.pop("baseline_root"),
        dependency_root=args.pop("dependency_root"),
        warehouse_root=args.pop("warehouse_root"),
        allow_synthetic_fixture=True)
    print(json.dumps({"ok":True,"result":result},sort_keys=True))
except Exception as exc:
    print(json.dumps({"ok":False,"error":str(exc)},sort_keys=True))
    raise SystemExit(3)
"""


def _feed(path: Path, *, count=180):
    # A rising, generated 1m series gives the pinned SMA3/8 evaluator a
    # deterministic, non-trading ENTRY_SIGNAL after its UNKNOWN warmup.
    start = (time.time_ns() // 1_000_000 // 900_000 - 30) * 900_000
    store = FeedStore(path)
    for i in range(count):
        opened = start + i * 60_000
        price = 100 + i
        payload = {
            "e": "kline", "s": "BTCUSDT", "E": opened + 59_999,
            "k": {"s": "BTCUSDT", "i": "1m", "x": True, "t": opened,
                  "T": opened + 59_999, "o": str(price), "h": str(price + 1),
                  "l": str(price - 1), "c": str(price), "v": "3", "n": 1},
        }
        store.ingest(json.dumps(payload, separators=(",", ":")),
                     received_ms=opened + 60_000)
    store.db.execute("CREATE TABLE engineering_fixture(schema TEXT, fixture_id TEXT)")
    store.db.execute("INSERT INTO engineering_fixture VALUES(?,?)",
                     ("aql.realtime-feed.generated-fixture.v1", "generated-in-test-helper"))
    store.db.commit()
    store.db.close()
    return start, start + count * 60_000


def _config(start, count):
    adapter = ROOT / "tools" / "realtime_market_feed" / "forward_research.py"
    config = {
        "schema": "atlas.realtime-market-feed.forward-analysis-config.v1",
        "symbol": "BTCUSDT", "window_start_ms": start, "bar_count": count,
        "strategy_definition_sha256": STRATEGY_SHA256,
        "adapter_code_sha256": hashlib.sha256(adapter.read_bytes()).hexdigest(),
        "max_age_ms": 120_000, "max_signal_lag_ms": 60_000,
    }
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return config, hashlib.sha256(canonical).hexdigest()


def _call(tmp_path, source, start, end, *, count=12, mode=None,
          cutoff=None, expected_ws=PRODUCER_CODE_SHA256, bad_config_pin=False,
          clock=None, baseline=BASELINE, dependencies=DEPENDENCIES):
    config, pin = _config(start, count)
    if bad_config_pin:
        pin = "0" * 64
    cutoff = end + 1_000 if cutoff is None else cutoff
    args = {
        "feed_database": str(source),
        "research_database": str(tmp_path / ("research-" + str(time.time_ns()) + ".sqlite")),
        "symbol": "BTCUSDT", "start_ms": start, "bar_count": count,
        "decision_cutoff_ms": cutoff,
        "clock_evidence": clock or {
            "schema": "atlas.realtime-market-feed.validated-clock.v1",
            "method": "WALL_MONOTONIC_BRACKET_V1",
            "observed_at_ms": cutoff, "uncertainty_ms": 0,
        },
        "config": config, "expected_config_sha256": pin,
        "expected_ws_producer_code_sha256": expected_ws,
        "expected_rest_producer_code_sha256": REST_CODE_SHA256,
        "baseline_root": str(baseline), "dependency_root": str(dependencies),
        "warehouse_root": str(WAREHOUSE), "mode": mode,
    }
    request = tmp_path / ("call-" + str(time.time_ns()) + ".json")
    request.write_text(json.dumps(args), encoding="utf-8")
    env = os.environ.copy()
    env["AQL_WORKTREE"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-B", "-c", _CALL, str(request)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, result.stdout + result.stderr
    return json.loads(lines[-1])


def test_native_analyzer_kernel_repeat_and_causal_prefix_parity(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = _feed(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    full = _call(tmp_path, source, start, end, count=12)
    repeat = _call(tmp_path, source, start, end, count=12)
    prefix_end = start + 8 * 900_000
    prefix = _call(tmp_path, source, start, prefix_end, count=8, cutoff=prefix_end+1_000)
    assert full["ok"] and repeat["ok"] and prefix["ok"], (full, repeat, prefix)
    a = full["result"]["receipt"]
    b = repeat["result"]["receipt"]
    p = prefix["result"]["receipt"]
    assert a == b
    assert a["decision"]["evaluated_slot_count"] == 12
    assert a["decision"]["state_by_slot"][:8] == p["decision"]["state_by_slot"]
    assert a["decision"]["warmup_unknown_count"] >= 1
    assert a["decision"]["state"] in {"ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL", "UNKNOWN"}
    assert a["strategy"]["strategy_definition_sha256"] == STRATEGY_SHA256
    assert a["pins"]["baseline_commit"] == "eb49308d61ffdfc24ed5032df2cb541f37c48bfe"
    assert a["pins"]["warehouse_commit"] == "ae60b3e367241fec14753ac78e08147603b7af84"
    assert a["evidence"]["source_feed_mutation"] == "NONE"
    assert a["orders"] == 0 and a["trading_authority"] == "NONE"
    factory = full["result"]["factory_forward_intake"]
    assert factory["status"] == "FORWARD_RECEIPT_VALIDATED_RESEARCH_ONLY"
    assert factory["historical_factory_consumer"] == "NOT_CALLED"
    assert factory["lab"] == "NOT_EVALUATED" and factory["paper"] == "NOT_ACTIVATED"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_recovered_latest_constituent_is_unknown_not_retroactive(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = _feed(source)
    result = _call(tmp_path, source, start, end, mode="recovered")
    assert result["ok"], result
    decision = result["result"]["receipt"]["decision"]
    assert decision["state"] == "UNKNOWN_RECOVERED_INPUT"
    assert decision["recovered_latest_bar"] is True
    assert result["result"]["factory_forward_intake"]["historical_factory_consumer"] == "NOT_CALLED"


def test_future_availability_stale_input_and_code_drift_fail_closed(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = _feed(source)
    future = _call(tmp_path, source, start, end, mode="future")
    drift = _call(tmp_path, source, start, end, expected_ws="0" * 64)
    stale_cutoff = end + 300_000
    stale = _call(tmp_path, source, start, end, cutoff=stale_cutoff,
                   clock={"schema":"atlas.realtime-market-feed.validated-clock.v1",
                          "method":"WALL_MONOTONIC_BRACKET_V1",
                          "observed_at_ms":stale_cutoff,"uncertainty_ms":0})
    assert not future["ok"] and future["error"] == "ANALYZER_INPUT_UNAVAILABLE_AT_CUTOFF"
    assert not drift["ok"] and "PRODUCER_IDENTITY_MISMATCH" in drift["error"]
    assert not stale["ok"] and stale["error"] == "FEED_STALE"


def test_config_clock_import_origin_and_resource_bounds_fail_closed(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = _feed(source)
    bad_config = _call(tmp_path, source, start, end, bad_config_pin=True)
    bad_clock = _call(tmp_path, source, start, end,
        clock={"schema":"unknown","method":"WALL_MONOTONIC_BRACKET_V1",
               "observed_at_ms":end+1_000,"uncertainty_ms":0})
    wrong_origin = _call(tmp_path, source, start, end, baseline=WAREHOUSE)
    over_bound = _call(tmp_path, source, start, end, count=673)
    assert not bad_config["ok"] and bad_config["error"] == "ANALYZER_CONFIG_PIN_MISMATCH"
    assert not bad_clock["ok"] and bad_clock["error"] == "ANALYZER_CLOCK_EVIDENCE_INVALID"
    assert not wrong_origin["ok"] and wrong_origin["error"] == "ANALYZER_BASELINE_COMMIT_MISMATCH"
    assert not over_bound["ok"] and over_bound["error"] == "ANALYZER_WINDOW_INVALID"


def test_missing_slot_open_gap_and_tampered_receipt_fail_closed(tmp_path):
    source = tmp_path / "feed.sqlite"
    start, end = _feed(source)
    with sqlite3.connect(source) as db:
        db.execute("DELETE FROM final_bar_lineage WHERE symbol='BTCUSDT' AND open_ms=?",
                   (start + 5 * 60_000,))
    missing = _call(tmp_path, source, start, end)
    assert not missing["ok"]
    assert missing["error"] in {"FEED_LINEAGE_MISSING", "FEED_WINDOW_INCOMPLETE",
                                "FEED_LINEAGE_ROW_MISSING"}

    source2 = tmp_path / "feed-gap.sqlite"
    start2, end2 = _feed(source2)
    with sqlite3.connect(source2) as db:
        db.execute("INSERT INTO open_gap(symbol,interval,start_ms,end_ms,reason,detected_ms,status) "
                   "VALUES(?,?,?,?,?,?,?)",
                   ("BTCUSDT","1m",start2,start2+60_000,"INJECTED_GAP",start2+60_000,"OPEN"))
    gap = _call(tmp_path, source2, start2, end2)
    assert not gap["ok"] and gap["error"] == "OPEN_HISTORY_GAP"

    source3 = tmp_path / "feed-tampered.sqlite"
    start3, end3 = _feed(source3)
    with sqlite3.connect(source3) as db:
        db.execute("UPDATE final_bar_lineage SET receipt_json='{}' "
                   "WHERE symbol='BTCUSDT' AND open_ms=?", (start3,))
    tampered = _call(tmp_path, source3, start3, end3)
    assert not tampered["ok"] and "LINEAGE" in tampered["error"]
