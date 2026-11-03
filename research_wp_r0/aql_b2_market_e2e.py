"""Factory B2 bounded integration replay using pinned actual GitHub artifacts.

The real Core consumer is exercised on the original 1970 TEST_ONLY cutoff,
and real 2024 BTCUSDT 15m market windows are checked in a *separate*
time-aligned TEST_ONLY association. No witness/clock/PIT, historical strategy
direction, execution or profitability is inferred from that association.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .aql_b2_system_integrity_gate import assess
from .aql_w1_f1_prospective_consumer import project_core_verified_f1_slots

CORE_SHA = "42005d09e3674420ddd8a761d40540c8e6509e8e79943d1f6a9821f692823b09"
B1_ARTIFACT_SHA = "265b7ade1be307bd2efafbd0a8438e6846c869df6205af717133d490e38aeb59"
B1_REPORT_SHA = "1791109fcbc7a8370ca234fbd24d27bc37db1fc078a142c3b7c54ea9d55cdb11"
BAR_MS = 900_000
HORIZONS = (14_400_000, 86_400_000, 259_200_000)
MONTHS = (2, 7)
CUTOFFS = ("2024-02-15T00:00:00+00:00", "2024-07-15T00:00:00+00:00")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def check(condition, name):
    if not condition:
        raise ValueError(name)


def parse_source_month(outer: zipfile.ZipFile, item: dict):
    name = item["name"]
    archive = outer.read("b1-originals/" + name)
    checksum = outer.read("b1-originals/" + name + ".CHECKSUM")
    check(digest(archive) == item["archive_sha256"] and len(archive) == item["archive_bytes"],
          "B1_ORIGINAL_ZIP_DIGEST_DRIFT")
    check(digest(checksum) == item["checksum_sha256"]
          and checksum.decode("ascii").strip().split() == [item["archive_sha256"], name],
          "B1_VENDOR_CHECKSUM_DRIFT")
    with zipfile.ZipFile(io.BytesIO(archive)) as inner:
        member = name.replace(".zip", ".csv")
        check(inner.namelist() == [member], "B1_SOURCE_MEMBER_IDENTITY")
        raw = inner.read(member)
    check(digest(raw) == item["member_sha256"], "B1_SOURCE_MEMBER_DIGEST_DRIFT")
    bars = {}
    lines = csv.reader(io.StringIO(raw.decode("utf-8")))
    first = item["first_open_ms"]
    for ix, row in enumerate(lines):
        check(len(row) == 12, "B1_SOURCE_SCHEMA")
        t = int(row[0])
        check(t == first + ix * BAR_MS and int(row[6]) == t + BAR_MS - 1,
              "B1_SOURCE_GRID_DRIFT")
        low, high = Decimal(row[3]), Decimal(row[2])
        check(low > 0 and high >= low and low.is_finite() and high.is_finite(),
              "B1_SOURCE_OHLC_INVALID")
        bars[t] = (high, low, row[1], row[4])
    check(len(bars) == item["bars"], "B1_SOURCE_MONTH_COUNT")
    return bars


def test_market_window(bars: dict, cutoff_ms: int, horizon_ms: int) -> dict:
    check(cutoff_ms % BAR_MS == 0 and horizon_ms in HORIZONS, "INVALID_WINDOW_GRID")
    times = range(cutoff_ms, cutoff_ms + horizon_ms, BAR_MS)
    values = [bars.get(t) for t in times]
    observed = sum(x is not None for x in values)
    complete = observed == horizon_ms // BAR_MS
    return {
        "cutoff_ms": cutoff_ms, "horizon_ms": horizon_ms,
        "asof_ms": cutoff_ms + horizon_ms,
        "expected_bars": horizon_ms // BAR_MS, "observed_bars": observed,
        "coverage_status": "COMPLETE" if complete else "CENSORED_OR_MISSING",
        "observed_high": str(max(x[0] for x in values if x is not None)) if observed else None,
        "observed_low": str(min(x[1] for x in values if x is not None)) if observed else None,
        "signed_mfe": None, "signed_mae": None, "tp_sl_ordering": "NOT_TESTED",
        "fills_pnl": None,
    }


def actual_consumer_projection(core: dict) -> dict:
    projection = project_core_verified_f1_slots(
        core["schedule"], core["original_candidates_test_only"], (),
        indicator_registry=core["indicator_registry"])
    n = core["n"]
    check(projection["scheduled_total"] == n
          and projection["arm_slots"] == 2*n
          and projection["outcome_rows"] == 6*n, "FACTORY_CONSUMER_DENOMINATOR")
    rows = projection["outcomes"]
    check(all(x["capture_status"] != "RECORDED"
              and x["coverage_status"] == "UNKNOWN"
              and x["max_favorable"] is None
              and x["max_adverse"] is None
              and x["no_fill_or_pnl_inference"] is True for x in rows),
          "FACTORY_CONSUMER_PROOF_LEAK")
    return projection


def build_report(core_bytes: bytes, b1_zip_bytes: bytes) -> dict:
    check(digest(core_bytes) == CORE_SHA, "CORE_PINNED_INPUT_DIGEST_DRIFT")
    check(digest(b1_zip_bytes) == B1_ARTIFACT_SHA, "B1_PINNED_ARTIFACT_DIGEST_DRIFT")
    core = json.loads(core_bytes)
    with zipfile.ZipFile(io.BytesIO(b1_zip_bytes)) as outer:
        market_bytes = outer.read("b1-replay/report.json")
        check(digest(market_bytes) == B1_REPORT_SHA, "B1_PINNED_REPORT_DIGEST_DRIFT")
        market = json.loads(market_bytes)
        base = assess(core, market, core_sha=CORE_SHA, market_sha=B1_REPORT_SHA)
        actual = actual_consumer_projection(core)
        originals = {x["name"]: x for x in market["originals"]}
        segments = {}
        for month in MONTHS:
            key = f"BTCUSDT-15m-2024-{month:02d}.zip"
            segments[month] = parse_source_month(outer, originals[key])
        check(len(core["schedule"]) == len(MONTHS), "B2_PAIR_COUNT")
        rows = []
        direct_join_rejections = []
        for i, plan in enumerate(core["schedule"]):
            month = MONTHS[i]
            item = originals[f"BTCUSDT-15m-2024-{month:02d}.zip"]
            cutoff = int(datetime.fromisoformat(CUTOFFS[i]).timestamp()*1000)
            # The original Core fixture has a 1970-era cutoff and fabricated
            # source pin. Never silently rewrite its original F1 identity.
            check(plan["decision_cutoff_ms"] != cutoff
                  and plan["source_bytes_sha256"] != item["member_sha256"],
                  "UNSAFE_DIRECT_HISTORICAL_JOIN")
            direct_join_rejections.append(plan["pair_id"])
            association = digest(canonical({
                "original_core_pair_id": plan["pair_id"],
                "test_2024_cutoff_ms": cutoff,
                "market_member_sha256": item["member_sha256"],
                "origin": "TEST_ONLY_TIME_ALIGNED_MARKET_ASSOCIATION_NOT_CORE_F1",
            }))
            observed_indicators = {}
            for candidate in core["original_candidates_test_only"]:
                if candidate["pair_id"] == plan["pair_id"]:
                    observed_indicators[candidate["arm"]] = [
                        {"indicator_id": ind["indicator_id"],
                         "value_kind": ind.get("value_kind"),
                         "value": ind.get("value"),
                         "missing_reason": ind.get("missing_reason")}
                        for ind in candidate.get("indicators", [])
                        if ind.get("role") == "OBSERVE_ONLY"
                    ]
            check(set(observed_indicators) == {"BASE", "SHADOW"},
                  "TEST_ONLY_INDICATOR_ARM_LOSS")
            for arm in ("BASE", "SHADOW"):
                for horizon in HORIZONS:
                    window = test_market_window(segments[month], cutoff, horizon)
                    rows.append({
                        "core_pair_id": plan["pair_id"], "arm": arm,
                        "test_association_id": association,
                        "market_source_month": month,
                        "market_source_member_sha256": item["member_sha256"],
                        "market_window": window,
                        "indicator_snapshot_class": "CORE_TEST_ONLY_UNVERIFIED",
                        "indicator_snapshot": observed_indicators[arm],
                        "research_direction": None,
                        "strategy_result": "NOT_AUTHORIZED",
                        "market_observation_only": True,
                    })
        n = core["n"]
        check(len(rows) == 6*n
              and len({(r["core_pair_id"], r["arm"], r["market_window"]["horizon_ms"])
                       for r in rows}) == 6*n, "TEST_MARKET_ASSOCIATION_DENOMINATOR")
        check(all(r["market_window"]["coverage_status"] == "COMPLETE" for r in rows),
              "UNEXPECTED_MARKET_WINDOW_INCOMPLETENESS")
        actual_status = dict(sorted(Counter(
            r["capture_status"] for r in actual["outcomes"]
            if r["horizon_ms"] == HORIZONS[0]).items()))
        return {
            "schema": "aql.b2.factory-bounded-system-integrity.v1",
            "verdict": "PASS_BOUNDED_TEST_ONLY_COMPONENTS_NOT_FULL_E2E",
            "core_input_sha256": CORE_SHA,
            "b1_original_artifact_sha256": B1_ARTIFACT_SHA,
            "b1_market_report_sha256": B1_REPORT_SHA,
            "market_lock_sha256": market["lock_sha256"],
            "n": n, "expected_2n": 2*n, "observed_2n": actual["arm_slots"],
            "expected_6n": 6*n, "factory_consumer_6n": actual["outcome_rows"],
            "test_market_association_6n": len(rows),
            "factory_consumer_captures": actual_status,
            "factory_consumer_market_coverage": "UNKNOWN_AUTHENTIC_MARKET_RECEIPT_NOT_JOINABLE",
            "historical_direct_join": {
                "status": "REJECTED_EXPECTED_SOURCE_AND_TIME_MISMATCH",
                "rejected_pair_ids": direct_join_rejections,
                "original_core_cutoff_ms": core["schedule"][0]["decision_cutoff_ms"],
                "original_2024_strategy_F1_records": "NOT_SUPPLIED"
            },
            "test_market_association": {
                "origin": "SEPARATE_CONTROLLED_TIME_ALIGNMENT_NOT_AUTHENTIC_F1",
                "rows": rows,
            },
            "interfaces": {
                "core_to_actual_factory_f1_consumer": "PASS_UNVERIFIED_2N_6N",
                "actual_2024_source_to_test_only_market_window": "PASS_12_COMPLETE",
                "core_F1_to_authenticated_2024_market": "NOT_CONNECTED",
                "core_F1_to_vault_parent_external_custody": "NOT_CONNECTED",
                "prospective_producer_to_F3": "NOT_CONNECTED",
                "actual_monitor_to_2024_market_outcome": "NOT_CONNECTED",
                "tp_sl_ordering_fee_fills": "NOT_TESTED",
                "historical_market_only": "ACCEPT_BOUNDED_PRIOR_AUDIT",
                "operational_pit": "BLOCKED_EXTERNAL_EVIDENCE",
            },
            "base_contract_gate": base["result"],
            "negative_boundary": "NO_PROMOTION_OF_TEST_ONLY_TO_HISTORICAL_F1",
            "g0_or_live_authorized": False,
            "strategy_efficacy_measured": False,
        }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core", type=Path, required=True)
    p.add_argument("--b1-artifact", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    check(not args.out.exists(), "REFUSE_OVERWRITE")
    report = build_report(args.core.read_bytes(), args.b1_artifact.read_bytes())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(report)
    args.out.write_bytes(raw)
    print("B2_REPORT_SHA256=" + digest(raw))
    print("B2_RESULT=" + report["verdict"])
    print("N/2N/6N=" + "/".join(str(report[k]) for k in ("n","observed_2n","factory_consumer_6n")))


if __name__ == "__main__":
    main()
