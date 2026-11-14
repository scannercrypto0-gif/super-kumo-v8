"""Run the bounded TEST_ONLY research cycle on the pinned #286 tree."""
import argparse
from collections import Counter
import json
from pathlib import Path
import socket
from unittest.mock import patch

from aql.journal.durable_journal import DurableJournal
from aql.g1_integrity import content, fingerprint
from aql.models.bar import MarketBar
from aql.observation.contracts import digest
from aql.observation.prospective import ProspectiveObserver, STEP
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research
from tools.atlas_april_archive import START
from tools.atlas_prospective_observe import FIXTURE, dedicated_root, read_only_g1

# Same four-bar NO_SIGNAL input recipe as test_atlas_prospective_archive.
PRICES = (99.5,) * 4


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def execute(root, *, fixture, prices=PRICES, interrupt=False, expected_plan=None):
    require(len(prices) == 4 and all(p is not None for p in prices), "FIXTURE_SOURCE_OUTAGE")
    bars = []
    for index, price in enumerate(prices):
        opening = START + index * STEP
        close = opening + STEP - 1
        bars.append(MarketBar("BTCUSDT", "15m", opening, close, price, price + 1,
                              price - 1, price, 4., True, "binance_ws", close + 1).with_checksum())

    plan = {
        "grade": "TEST_ONLY", "inputs_sha256": digest([bar.to_dict() for bar in bars]),
        "strategy_fixture_sha256": fixture["sha256"],
        "config_sha256": fixture["payload"]["config_digest"],
        "first_open_ms": START, "bar_count": len(bars), "step_ms": STEP,
        "clock": "SIMULATED_UTC", "provider_budget": 0,
    }
    pin = digest(plan)
    require(expected_plan is None or pin == expected_plan, "RESEARCH_PLAN_MISMATCH")
    root = dedicated_root(root, "atlas-bounded-research-test-only")
    plan_file = root / "plan.json"
    if not plan_file.exists():
        with plan_file.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, sort_keys=True)
    require(json.loads(plan_file.read_text(encoding="utf-8")) == plan, "RESEARCH_PLAN_MISMATCH")
    journal_path, store_path, ledger = (root / name for name in
                                       ("journal.sqlite", "market.sqlite", "decisions.sqlite"))
    journal = DurableJournal(str(journal_path))
    store = OperationalStore(str(store_path))
    observer = ProspectiveObserver(ledger, journal, store, fixture, synthetic=True)
    acknowledgments = []
    for index, bar in enumerate(bars):
        # This replay clock belongs only to the fixture. Its event time is
        # deliberately frozen across separate processes and retries.
        committed = bar.ingested_at + 2
        cutoff = committed + 1
        key = bar.stable_key()
        ack = journal.commit_receipt(key)
        if ack["status"] == "NO_RECORD":
            with patch("time.time", return_value=committed / 1000):
                journal.commit(bar)
            ack = journal.commit_receipt(key)
        require(ack["status"] == "SQLITE_COMMIT_RETURN_OBSERVED" and
                ack["commit_return_observed_at_ms"] == committed and
                ack["content_digest"] == fingerprint(content(bar)), "FIXTURE_ACK_MISMATCH")
        acknowledgments.append(digest(ack))
        if interrupt and index == 1:
            return {"status": "STOPPED_AFTER_DURABLE_ACK", "plan_sha256": pin,
                    "ack_sha256": acknowledgments}
        store.upsert(bar)
        journal.mark_persisted(key)
        with patch("aql.observation.prospective.time_ns", return_value=cutoff * 1_000_000):
            observer.tick()

    reader = ProspectiveObserver(ledger, read_only_g1(DurableJournal, journal_path),
                                 read_only_g1(OperationalStore, store_path), fixture,
                                 synthetic=True, read_only=True)
    core = reader.verified_read(as_of_ms=cutoff)
    rows = core["rows"]
    require(len(rows) == len(bars) and all(row["source_valid"] for row in rows) and
            [row["decision"]["parent"]["open_ms"] for row in rows] == [b.bar_open for b in bars] and
            [row["decision"]["parent"]["g1_receipt_sha256"] for row in rows] == acknowledgments,
            "ORDERED_RESEARCH_LINEAGE")
    require(len(reader.verified_read(as_of_ms=cutoff - 1)["rows"]) == len(bars) - 1,
            "FUTURE_CUTOFF_LEAK")
    factory = read_prospective_research(reader, as_of_ms=cutoff)
    require(factory["g2_sha256"] == core["sha256"] and factory["trading_authority"] == "NONE" and
            not factory["orders_enabled"] and not factory["secretary_enqueued"], "RESEARCH_ONLY")
    census = dict(Counter(row["decision"]["state"] for row in rows))
    require(census == factory["decision_counts"] == {"UNKNOWN": 3, "NO_SIGNAL": 1}, "FIXTURE_CENSUS")
    # Native receipts carry a per-store journal instance ID. This digest is
    # stable on reopen; distinct stores are compared via their ordered census.
    result = {
        "grade": "TEST_ONLY", "plan": plan, "plan_sha256": pin, "as_of_ms": cutoff,
        "ack_sha256": acknowledgments, "core_sha256": core["sha256"],
        "scanner_sha256": [row["decision_sha256"] for row in rows],
        "factory": factory, "factory_admission": "WAIT_AUTHENTICATED_PARENTS",
        "discoverer": "NO_MATCHING_LINEAGE", "lab": "NOT_EVALUATED",
        "strict_pit_oos": "BLOCKED", "provider_calls": 0,
    }
    return {**result, "sha256": digest(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--expected-plan")
    parser.add_argument("--interrupt-after-ack", action="store_true")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
    with patch.object(socket, "socket", side_effect=AssertionError("PROVIDER_BUDGET_ZERO")):
        result = execute(args.state, fixture=fixture, interrupt=args.interrupt_after_ack,
                         expected_plan=args.expected_plan)
    print(json.dumps(result, sort_keys=True))
    if args.interrupt_after_ack:
        raise SystemExit(73)


if __name__ == "__main__":
    main()
