"""R1 historical MARKET_ONLY producer from accepted 2024 BTCUSDT 15m bytes.

This is a deterministic research observation/scheduling adapter, NOT an
original historical strategy decision, genuine PIT or simulated fill.
Only the two previously accepted month ZIP members needed by the bounded
sample are parsed; no network acquisition, broad B1 replay or F3 call.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .indicator_library_v2 import _ema

SCHEMA = "aql.r1-core-research-handoff.v1"
BAR_MS = 900_000
B1_ARTIFACT_SHA256 = "265b7ade1be307bd2efafbd0a8438e6846c869df6205af717133d490e38aeb59"
B1_REPORT_SHA256 = "1791109fcbc7a8370ca234fbd24d27bc37db1fc078a142c3b7c54ea9d55cdb11"
MONTHS = (2, 7)
SAMPLE_DAY = 15
SAMPLE_BARS_PER_MONTH = 16
WARMUP_BARS = 252
INDICATOR_VERSION = "core-pinned-indicator-library-v2._ema/r1-ema8-21-sma20.v1"
REGIME_VERSION = "aql.r1-market-regime-ema8-21.v1"
STRATEGY_VERSION = "NOT_CONNECTED"
SOURCE_STATUS = "RETROSPECTIVE_MARKET_ONLY"
PROOF_STATUS = "BLOCKED_EXTERNAL_EVIDENCE"
ARMS = ("BASE", "SHADOW")


class R1Rejected(ValueError):
    pass


def _check(yes: bool, why: str) -> None:
    if not yes:
        raise R1Rejected(why)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _int_time(month: int, day: int = SAMPLE_DAY) -> int:
    return int(datetime(2024, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def _safe_decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
        _check(number.is_finite(), "NONFINITE_MARKET_VALUE")
        return number
    except (InvalidOperation, TypeError) as exc:
        raise R1Rejected("INVALID_MARKET_VALUE") from exc


def parse_pinned_month(outer: zipfile.ZipFile, item: Mapping[str, Any]) -> list[dict]:
    """Verify actual vendor compressed/checksum/member bytes + entire 15m grid."""
    name = item["name"]
    _check(name.startswith("BTCUSDT-15m-2024-") and name.endswith(".zip")
           and name.count("/") == 0, "UNSAFE_MONTH_NAME")
    archive = outer.read("b1-originals/" + name)
    checksum = outer.read("b1-originals/" + name + ".CHECKSUM")
    _check(len(archive) == item["archive_bytes"] and
           _sha(archive) == item["archive_sha256"], "ARCHIVE_PIN_DRIFT")
    _check(_sha(checksum) == item["checksum_sha256"] and
           checksum.decode("ascii").strip().split() == [item["archive_sha256"], name],
           "VENDOR_CHECKSUM_DRIFT")
    with zipfile.ZipFile(io.BytesIO(archive)) as nested:
        member = name[:-4] + ".csv"
        _check(nested.namelist() == [member] and
               nested.infolist()[0].file_size <= 32*1024*1024,
               "UNSAFE_CSV_MEMBER")
        member_bytes = nested.read(member)
    _check(_sha(member_bytes) == item["member_sha256"], "CSV_MEMBER_SHA_DRIFT")
    rows = []
    for i, line in enumerate(csv.reader(io.StringIO(member_bytes.decode("utf-8")))):
        _check(len(line) == 12, "MARKET_ROW_SCHEMA")
        start = int(line[0])
        end = int(line[6]) + 1
        _check(start == item["first_open_ms"] + i * BAR_MS and end == start + BAR_MS,
               "MISSING_DUPLICATE_OR_FUTURE_GRID")
        o,h,l,c,v = [_safe_decimal(line[j]) for j in (1,2,3,4,5)]
        _check(0 < l <= min(o,c) <= max(o,c) <= h and v >= 0,
               "INVALID_OHLC")
        rows.append({
            "open_ms": start, "close_exclusive_ms": end,
            "open": str(o), "high": str(h), "low": str(l),
            "close": str(c), "volume": str(v),
        })
    _check(len(rows) == item["bars"], "MONTH_DENOMINATOR_DRIFT")
    return rows


def load_pinned_originals(artifact_bytes: bytes) -> tuple[dict[int, list[dict]], dict]:
    """Read ONLY accepted B1 artifact bytes, not network/Binance live."""
    _check(_sha(artifact_bytes) == B1_ARTIFACT_SHA256, "B1_ARTIFACT_SHA_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(artifact_bytes)) as outer:
        report_raw = outer.read("b1-replay/report.json")
        _check(_sha(report_raw) == B1_REPORT_SHA256, "B1_REPORT_SHA_MISMATCH")
        report = json.loads(report_raw)
        _check(report["scope"] == SOURCE_STATUS and
               report["observed_bars"] == 35136 and
               report["missing_bars"] == 0 and
               report["duplicate_bars"] == 0 and
               len(report["originals"]) == 12, "B1_ACCEPTED_SOURCE_LOCK_INVALID")
        index = {x["name"]: x for x in report["originals"]}
        months = {}
        items = []
        for month in MONTHS:
            name = f"BTCUSDT-15m-2024-{month:02d}.zip"
            _check(name in index, "MISSING_PINNED_MONTH")
            item = index[name]
            _check(item["first_open_ms"] == _int_time(month, 1),
                   "MONTH_SOURCE_GRID_DRIFT")
            months[month] = parse_pinned_month(outer, item)
            items.append({
                "name": name, "archive_sha256": item["archive_sha256"],
                "member_sha256": item["member_sha256"],
                "checksum_sha256": item["checksum_sha256"],
                "first_open_ms": item["first_open_ms"], "bars": item["bars"],
            })
    return months, {
        "symbol": "BTCUSDT", "market": "SPOT", "interval": "15m",
        "vendor": "Binance Vision", "year": 2024,
        "mode": SOURCE_STATUS, "archive_artifact_sha256": B1_ARTIFACT_SHA256,
        "accepted_market_report_sha256": B1_REPORT_SHA256,
        "market_lock_sha256": report["lock_sha256"],
        "source_version": "2024-retrospective-original-archive-snapshot",
        "correction_generation": "UNKNOWN_UNATTESTED",
        "source_available_at_ms": None,
        "source_published_at_ms": None,
        "correction_published_at_ms": None,
        "source_availability": "UNKNOWN_NOT_INFERRED_FROM_BAR_CLOSE",
        "external_evidence": PROOF_STATUS,
        "months": items,
    }


def validate_clock(
    row: Mapping[str, Any], cutoff: int, *,
    source_available_at_ms: int | None = None,
    correction_published_at_ms: int | None = None,
) -> None:
    _check(row["close_exclusive_ms"] <= cutoff, "FUTURE_BAR_LOOKAHEAD")
    _check(row["close_exclusive_ms"] == row["open_ms"] + BAR_MS,
           "BAR_GRID_INVALID")
    if source_available_at_ms is not None:
        _check(type(source_available_at_ms) is int and
               source_available_at_ms <= cutoff, "SOURCE_AFTER_CUTOFF")
    if correction_published_at_ms is not None:
        _check(type(correction_published_at_ms) is int and
               correction_published_at_ms <= cutoff, "CORRECTION_AFTER_CUTOFF")


def compute_features(prefix: Sequence[Mapping[str, Any]], cutoff: int) -> dict:
    """Only explicit <= cutoff prefix. Warmup failures retain an UNKNOWN slot."""
    if not prefix:
        return {"readiness": "MISSING_BARS", "ema8": None,
                "ema21": None, "sma20": None}
    previous = None
    for bar in prefix:
        validate_clock(bar, cutoff)
        if previous is not None:
            _check(bar["open_ms"] == previous + BAR_MS,
                   "PREFIX_MISSING_OR_DUPLICATE_BAR")
        previous = bar["open_ms"]
    if len(prefix) < WARMUP_BARS:
        return {"readiness": "INSUFFICIENT_WARMUP",
                "ema8": None, "ema21": None, "sma20": None}
    closes = [float(_safe_decimal(x["close"])) for x in prefix]
    _check(all(math.isfinite(x) and x > 0 for x in closes),
           "INVALID_FEATURE_INPUT")
    fast = _ema(closes, 8)
    slow = _ema(closes, 21)
    _check(bool(fast and slow), "INDICATOR_NOT_READY")
    return {
        "readiness": "READY_RESEARCH_ONLY",
        "ema8": format(fast[-1], ".8f"),
        "ema21": format(slow[-1], ".8f"),
        "sma20": format(math.fsum(closes[-20:])/20, ".8f"),
    }


def regime_snapshot(features: Mapping[str, Any], close: str) -> dict:
    """Versioned descriptive classifier, not an SF strategy rule."""
    if features["readiness"] != "READY_RESEARCH_ONLY":
        return {"version": REGIME_VERSION, "state": "UNKNOWN",
                "reason": features["readiness"]}
    fast, slow, price = (
        Decimal(features["ema8"]), Decimal(features["ema21"]), _safe_decimal(close)
    )
    state = ("UP_TREND" if fast > slow and price > slow else
             "DOWN_TREND" if fast < slow and price < slow else
             "RANGE_OR_MIXED")
    return {"version": REGIME_VERSION, "state": state,
            "reason": "RESEARCH_EMA8_EMA21_PRICE_ONLY_NOT_TRADING_SIGNAL"}


def make_opportunity(
    prefix: Sequence[Mapping[str, Any]],
    source: Mapping[str, Any],
    *,
    month_member_sha256: str,
    source_available_at_ms: int | None = None,
    correction_published_at_ms: int | None = None,
) -> dict:
    _check(bool(prefix), "EMPTY_OPPORTUNITY_PREFIX")
    last = prefix[-1]
    cutoff = last["close_exclusive_ms"]
    validate_clock(last, cutoff,
                   source_available_at_ms=source_available_at_ms,
                   correction_published_at_ms=correction_published_at_ms)
    features = compute_features(prefix, cutoff)
    regime = regime_snapshot(features, last["close"])
    identity = {
        "symbol": source["symbol"], "market": source["market"],
        "interval": source["interval"], "bar_close_exclusive_ms": cutoff,
        "source_member_sha256": month_member_sha256,
        "feature_version": INDICATOR_VERSION, "regime_version": REGIME_VERSION,
    }
    identity_sha = _sha(canonical(identity))
    return {
        "opportunity_id": "R1-" + identity_sha,
        "pair_id": _sha(canonical({"identity_sha256": identity_sha,
                                   "arms": list(ARMS)})),
        "symbol": source["symbol"], "market": source["market"],
        "interval": source["interval"], "bar_open_ms": last["open_ms"],
        "bar_close_exclusive_ms": cutoff,
        "decision_cutoff_ms": cutoff,
        "decision_time_kind": "MODELED_BAR_CLOSE_LOWER_BOUND_NOT_ACTUAL_DECISION",
        "source_version": source["source_version"],
        "source_member_sha256": month_member_sha256,
        "source_available_at_ms": None,  # original issuer time not attested
        "correction_generation": source["correction_generation"],
        "correction_published_at_ms": None,
        "feature_version": INDICATOR_VERSION,
        "features": features,
        "feature_input_bars": len(prefix),
        "feature_last_bar_close_exclusive_ms": prefix[-1]["close_exclusive_ms"],
        "regime_version": REGIME_VERSION, "regime": regime,
        "strategy_version": STRATEGY_VERSION,
        "strategy_signal": None,
        "original_decision_provenance": "NOT_SUPPLIED",
        "decision_status": "UNKNOWN_ORIGINAL_DECISION",
        "arms": [
            {"arm": arm, "capture_status": "MISSING_CAPTURE",
             "direction": None, "decision_status": "UNKNOWN_ORIGINAL_DECISION"}
            for arm in ARMS
        ],
        "pit_status": PROOF_STATUS,
        "market_observation_only": True,
        "trade_or_alpha_evidence": False,
    }


def build_handoff(months: Mapping[int, list[dict]], source: Mapping[str, Any]) -> dict:
    """Bounded, reproducible time-aligned producer using actual month arrays."""
    _check(source.get("mode") == SOURCE_STATUS and
           source.get("external_evidence") == PROOF_STATUS and
           source.get("source_available_at_ms") is None and
           source.get("correction_published_at_ms") is None and
           source.get("source_version") == "2024-retrospective-original-archive-snapshot" and
           source.get("correction_generation") == "UNKNOWN_UNATTESTED" and
           source.get("archive_artifact_sha256") == B1_ARTIFACT_SHA256 and
           source.get("accepted_market_report_sha256") == B1_REPORT_SHA256 and
           source.get("market_lock_sha256") ==
               "267964c81772b1a118cd740c8d8a6bc6a757e615a98d80769a68e5a12df34679",
           "SOURCE_SCOPE_OR_PROVENANCE_DRIFT")
    sources = {int(x["name"][-6:-4]): x for x in source["months"]}
    items = []
    identities = set()
    for month in MONTHS:
        _check(month in months and month in sources,
               "MISSING_SOURCE_MONTH")
        bars = months[month]
        target = _int_time(month)
        slots = {b["open_ms"]: i for i,b in enumerate(bars)}
        _check(target in slots, "R1_SAMPLE_ANCHOR_MISSING")
        for position in range(slots[target], slots[target] + SAMPLE_BARS_PER_MONTH):
            _check(position < len(bars), "R1_SAMPLE_OUT_OF_MONTH")
            row = bars[position]
            _check(row["open_ms"] == target +
                   (position-slots[target])*BAR_MS, "R1_SAMPLE_GRID_DRIFT")
            prefix = bars[:position+1]
            rec = make_opportunity(
                prefix, source,
                month_member_sha256=sources[month]["member_sha256"],
            )
            _check(rec["opportunity_id"] not in identities,
                   "DUPLICATE_OPPORTUNITY_IDENTITY")
            identities.add(rec["opportunity_id"])
            items.append(rec)
    items.sort(key=lambda r:r["decision_cutoff_ms"])
    _check(all(items[i]["decision_cutoff_ms"] <
               items[i+1]["decision_cutoff_ms"]
               for i in range(len(items)-1)), "NONMONOTONIC_OPPORTUNITIES")
    counts = {
        "n_opportunities": len(items),
        "arm_slots_2n": 2*len(items),
        "expected_outcome_rows_6n": 6*len(items),
        "missing_capture": 2*len(items),
        "verified_original_strategy_decisions": 0,
        "features_ready": sum(r["features"]["readiness"] == "READY_RESEARCH_ONLY"
                              for r in items),
    }
    handoff = {
        "schema_version": SCHEMA,
        "scope": "HISTORICAL_MARKET_ONLY_RESEARCH_NOT_OPERATIONAL_PIT",
        "source": dict(source),
        "feature_version": INDICATOR_VERSION,
        "regime_version": REGIME_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "sample_policy": {
            "months": list(MONTHS), "day_utc": SAMPLE_DAY,
            "bars_per_month": SAMPLE_BARS_PER_MONTH,
            "warmup_bars": WARMUP_BARS,
            "description": "Two bounded time-aligned 2024 samples. Full year market lock already accepted.",
        },
        "counts": counts,
        "opportunities": items,
        "original_f1_strategy_decisions": "NOT_SUPPLIED",
        "external_issuer_correction_clock_and_freeze": PROOF_STATUS,
        "g0_merge_paper_shadow_live_authorized": False,
    }
    handoff["handoff_sha256"] = _sha(canonical(handoff))
    return handoff
