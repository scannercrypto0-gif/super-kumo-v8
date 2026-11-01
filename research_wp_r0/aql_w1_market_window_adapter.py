"""Read-only authenticated RAW market-window builder for prospective F1 research.

A caller must supply original immutable RAW bytes AND an independent publication
receipt verifier. A self-declared valid flag, recomputed manifest or injected
synthetic True callback is not operational proof of independent custody.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Callable

from .aql_w1_opportunity_outcomes import EvidenceError, HORIZONS

BAR_MS = 900_000
SHA_FIELDS = ("source_bytes_sha256", "raw_bytes_sha256")
SOURCE_FIELDS = ("source_id", "source_version", "source_bytes_sha256",
                 "correction_generation", "decision_cutoff_ms")
REQUIRED_RECEIPT = ("source_id", "source_version", "source_bytes_sha256",
                    "correction_generation", "raw_bytes_sha256",
                    "published_at_ms", "finalized_at_ms", "receipt_sha256")


def _integer(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def _price(value):
    if not isinstance(value, str) or not value or value.startswith("+"):
        raise EvidenceError("noncanonical market price")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise EvidenceError("invalid market price") from exc
    if not number.is_finite() or number <= 0:
        raise EvidenceError("invalid market price")
    if format(number, "f") != value or value.startswith("0") and len(value) > 1 and value[1] != ".":
        raise EvidenceError("noncanonical market price")
    return number


def _canonical(value):
    if value == 0:
        return "0"
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def authenticated_market_windows(scheduled, raw_by_pair, receipt_by_pair, *,
                                 verify_receipt: Callable | None = None,
                                 asof_ms: int | None = None):
    """Return (windows, bound_verifier); all failed proofs become UNKNOWN.

    RAW format: UTF-8 JSON array of 15m finalized bars with exactly
    [open_ms, high, low, finalized_at_ms, published_at_ms] fields.
    This adapter does not sign or independently timestamp the source.
    verify_receipt(receipt)->True must be an externally trusted custody service.
    """
    if asof_ms is not None and not _integer(asof_ms):
        raise EvidenceError("invalid observation asof")
    windows = []
    accepted = set()
    seen = set()
    for plan in scheduled:
        pair = plan["pair_id"]
        if pair in seen:
            raise EvidenceError("duplicate market schedule")
        seen.add(pair)
        raw = raw_by_pair.get(pair)
        receipt = receipt_by_pair.get(pair)
        if raw is not None and type(raw) is not bytes:
            raise EvidenceError("RAW must be original bytes")
        if raw is None or not isinstance(receipt, dict):
            continue
        if not all(k in receipt for k in REQUIRED_RECEIPT):
            continue
        if any(plan.get(k) != receipt.get(k) for k in
               ("source_id", "source_version", "source_bytes_sha256",
                "correction_generation") if k in plan):
            continue
        if receipt["source_bytes_sha256"] != plan.get("source_bytes_sha256"):
            continue
        if hashlib.sha256(raw).hexdigest() != receipt["raw_bytes_sha256"]:
            continue
        if not all(_integer(receipt[k]) for k in ("published_at_ms", "finalized_at_ms")):
            continue
        if verify_receipt is None:
            continue
        try:
            if verify_receipt(receipt) is not True:
                continue
        except Exception:
            continue
        try:
            bars = json.loads(raw.decode("utf-8"), parse_float=lambda _: (_ for _ in ()).throw(ValueError("floats forbidden")))
            if not isinstance(bars, list):
                continue
        except (UnicodeError, ValueError, TypeError):
            continue
        parsed = {}
        sane = True
        for bar in bars:
            try:
                if not isinstance(bar, dict) or set(bar) != {"open_ms", "high", "low", "finalized_at_ms", "published_at_ms"}:
                    raise ValueError()
                start, finalized, published = (bar[k] for k in ("open_ms", "finalized_at_ms", "published_at_ms"))
                if not all(_integer(x) for x in (start, finalized, published)):
                    raise ValueError()
                if start % BAR_MS or finalized < start + BAR_MS or published < finalized:
                    raise ValueError()
                high, low = _price(bar["high"]), _price(bar["low"])
                if high < low or start in parsed:
                    raise ValueError()
                parsed[start] = (high, low, finalized, published)
            except (EvidenceError, ValueError, TypeError, KeyError):
                sane = False
                break
        if not sane:
            continue
        cutoff = plan["decision_cutoff_ms"]
        if not _integer(cutoff) or cutoff % BAR_MS:
            raise EvidenceError("invalid decision cutoff for 15m grid")
        for horizon in HORIZONS:
            count = horizon // BAR_MS
            expected = [cutoff + i * BAR_MS for i in range(count)]
            available = [parsed[x] for x in expected if x in parsed and
                         parsed[x][3] <= receipt["published_at_ms"] and
                         (asof_ms is None or parsed[x][3] <= asof_ms)]
            complete = len(available) == count
            last_expected = cutoff + horizon
            ended = (asof_ms is not None and asof_ms < last_expected)
            coverage = ("COMPLETE" if complete else
                        "ARCHIVE_END_CENSORED" if ended else "MISSING_DATA")
            # Missing/late data is reported, never silently dropped.
            high = _canonical(max((x[0] for x in available), default=Decimal("0"))) if available else None
            low = _canonical(min((x[1] for x in available), default=Decimal("0"))) if available else None
            window = dict(pair_id=pair, horizon_ms=horizon, decision_cutoff_ms=cutoff,
                          source_version=plan["source_version"],
                          source_bytes_sha256=plan["source_bytes_sha256"],
                          correction_generation=plan["correction_generation"],
                          coverage_status=coverage, expected_bars=count,
                          observed_bars=len(available), high=high, low=low,
                          tp_sl_first_hit="UNKNOWN",
                          raw_bytes_sha256=receipt["raw_bytes_sha256"],
                          market_receipt_sha256=receipt["receipt_sha256"],
                          market_publication_ms=receipt["published_at_ms"])
            windows.append(window)
            if complete:
                accepted.add((pair, horizon, receipt["raw_bytes_sha256"],
                              receipt["receipt_sha256"]))
    def verified(window):
        return ((window.get("pair_id"), window.get("horizon_ms"),
                 window.get("raw_bytes_sha256"), window.get("market_receipt_sha256")) in accepted)
    return windows, verified
