"""Controlled offline RAW CSV → derived bars → prospective research outcome demo.

The source is a generated fixture, never a real vendor/custody publication.
Each externally supplied witness is a deliberate test-only stand-in. No
operational PIT, self-issued source-clock authority, F3 activation or trading.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal, InvalidOperation

from .aql_w1_market_window_adapter import BAR_MS
from .aql_w1_opportunity_outcomes import EvidenceError
from .aql_w1_f1_prospective_consumer import project_parent_authenticated_f1_slots


def _price(value):
    if not isinstance(value, str):
        raise EvidenceError("RAW price must be a string")
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise EvidenceError("invalid original RAW price") from exc
    if not d.is_finite() or d <= 0:
        raise EvidenceError("invalid original RAW price")
    return format(d, "f")


def derive_15m_bars_from_original_csv(parent_bytes: bytes, *,
                                      finalized_at_ms: int,
                                      published_at_ms: int) -> bytes:
    """Bounded deterministic original CSV projection, without timestamp claims.

    CSV rows carry open_ms, high, low; this function never fabricates a
    publication witness. Caller-provided time metadata are attested separately.
    For fixture use, each bar's finalization is its 15-minute end and the
    publication time is its finalization plus one millisecond. The two upper
    bounds must cover every bar.
    """
    if type(parent_bytes) is not bytes or len(parent_bytes) > 10_000_000:
        raise EvidenceError("original RAW bytes missing/too large")
    if any(type(x) is not int or x < 0 for x in (finalized_at_ms, published_at_ms)):
        raise EvidenceError("invalid time bound")
    if published_at_ms < finalized_at_ms:
        raise EvidenceError("publication precedes finalization")
    try:
        text = parent_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames != ["open_ms", "high", "low"]:
            raise EvidenceError("original RAW schema mismatch")
        bars = []
        seen = set()
        for row in reader:
            if set(row) != {"open_ms", "high", "low"} or None in row:
                raise EvidenceError("original RAW malformed row")
            open_text = row["open_ms"]
            if not open_text or not open_text.isascii() or not open_text.isdecimal():
                raise EvidenceError("invalid original RAW open time")
            opened = int(open_text)
            if opened % BAR_MS or opened in seen:
                raise EvidenceError("duplicate/off-grid original 15m bar")
            seen.add(opened)
            hi, lo = Decimal(_price(row["high"])), Decimal(_price(row["low"]))
            if hi < lo:
                raise EvidenceError("original RAW high below low")
            finalized = opened + BAR_MS
            published = finalized + 1
            if finalized > finalized_at_ms or published > published_at_ms:
                raise EvidenceError("original RAW not fully finalized/published")
            bars.append(dict(open_ms=opened, high=format(hi, "f"),
                             low=format(lo, "f"),
                             finalized_at_ms=finalized,
                             published_at_ms=published))
    except (UnicodeError, csv.Error, ValueError, OverflowError) as exc:
        raise EvidenceError("invalid original RAW CSV") from exc
    if not bars:
        raise EvidenceError("empty original RAW")
    bars.sort(key=lambda row: row["open_ms"])
    return json.dumps(bars, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def run_controlled_raw_research_demo(
    scheduled, captures, *, parent_bytes_by_pair, manifest_by_pair,
    indicator_registry, normalization_policy, source_witnesses,
    proof_verifier=None, asof_ms=None,
):
    """One test-only research run, retaining every preregistered arm/horizon.

    source_witnesses maps pair IDs to independent-host *interfaces*:
    parent_manifest, derivation and market_receipt. All are required, but
    this package supplies no authority; fixture callbacks never prove PIT.
    A real host must independently compare exact manifest bytes, parent RAW
    custody, source/correction publication, pre-F3 freeze and durable anchor.
    """
    plans = list(scheduled)
    if not isinstance(normalization_policy, str) or not normalization_policy:
        raise EvidenceError("missing normalization policy")
    pairs = {p["pair_id"] for p in plans}
    if len(pairs) != len(plans):
        raise EvidenceError("duplicate scheduled pair")
    if any(set(m) - pairs for m in
           (parent_bytes_by_pair, manifest_by_pair, source_witnesses)):
        raise EvidenceError("orphan RAW input or witness")
    derivatives, lineage = {}, {}
    audit_rows = []
    for plan in plans:
        pair = plan["pair_id"]
        raw, meta = parent_bytes_by_pair.get(pair), manifest_by_pair.get(pair)
        checks = source_witnesses.get(pair)
        status = "UNVERIFIED"
        reason = "PARENT_MANIFEST_OR_WITNESS_MISSING"
        if not (type(raw) is bytes and isinstance(meta, dict) and
                isinstance(checks, dict)):
            audit_rows.append(dict(pair_id=pair, status=status, reason=reason))
            continue
        # Host attestors must explicitly approve the original, derivation and
        # market receipt. Their injected booleans are not operational proof.
        if not all(callable(checks.get(k)) for k in
                   ("parent_manifest", "derivation", "market_receipt")):
            audit_rows.append(dict(pair_id=pair, status=status, reason=reason))
            continue
        try:
            from datetime import datetime
            end_ms = int(datetime.fromisoformat(
                meta["coverage_end_utc"].replace("Z", "+00:00")
            ).timestamp() * 1000)
            # The declared coverage end is only a fixture processing bound, not independent publication evidence.
            finalized = end_ms
            published = end_ms + 1
            bars = derive_15m_bars_from_original_csv(
                raw, finalized_at_ms=finalized, published_at_ms=published)
            parent_sha = hashlib.sha256(raw).hexdigest()
            derived_sha = hashlib.sha256(bars).hexdigest()
            info = dict(parent_content_sha256=parent_sha,
                        f1_source_bytes_sha256=plan["source_bytes_sha256"],
                        source_id=plan["source_id"],
                        source_version=plan["source_version"],
                        correction_generation=int(plan["correction_generation"]),
                        derived_bytes_sha256=derived_sha,
                        normalization_policy=normalization_policy,
                        published_at_ms=published,
                        finalized_at_ms=finalized)
        except (EvidenceError, KeyError, TypeError, ValueError, OverflowError):
            audit_rows.append(dict(pair_id=pair, status="UNVERIFIED",
                                   reason="INVALID_RAW_OR_COVERAGE"))
            continue
        derivatives[pair], lineage[pair] = bars, info
        audit_rows.append(dict(pair_id=pair, status="DERIVED_UNVERIFIED",
                               reason="REQUIRES_EXTERNAL_WITNESS",
                               parent_sha256=parent_sha,
                               derived_sha256=derived_sha,
                               normalization_policy=normalization_policy))
    def parent_check(meta, raw):
        pair = next((p for p in plans if
                     manifest_by_pair.get(p["pair_id"]) is meta and
                     parent_bytes_by_pair.get(p["pair_id"]) is raw), None)
        if pair is None:
            return False
        try:
            return source_witnesses[pair["pair_id"]]["parent_manifest"](meta, raw) is True
        except Exception:
            return False

    def transform_check(info, raw, derived):
        pair = next((p for p in plans if
                     lineage.get(p["pair_id"]) is info and
                     derivatives.get(p["pair_id"]) is derived), None)
        if pair is None:
            return False
        try:
            return source_witnesses[pair["pair_id"]]["derivation"](info, raw, derived) is True
        except Exception:
            return False

    def receipt_check(info, meta):
        pair = next((p for p in plans if lineage.get(p["pair_id"]) is info), None)
        if pair is None:
            return False
        try:
            return source_witnesses[pair["pair_id"]]["market_receipt"](info, meta) is True
        except Exception:
            return False

    result = project_parent_authenticated_f1_slots(
        plans, captures, parent_bytes_by_pair=parent_bytes_by_pair,
        manifest_by_pair=manifest_by_pair, derived_bars_by_pair=derivatives,
        derived_evidence_by_pair=lineage, indicator_registry=indicator_registry,
        verify_parent_manifest=parent_check,
        verify_derivation=transform_check,
        verify_external_receipt=receipt_check,
        proof_verifier=proof_verifier, asof_ms=asof_ms)
    result["controlled_demo_only"] = True
    result["real_raw_issuer_or_pit_proven"] = False
    result["source_derivation_trace"] = audit_rows
    return result
