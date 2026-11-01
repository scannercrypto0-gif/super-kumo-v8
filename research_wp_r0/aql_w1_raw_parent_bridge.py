"""Read-only parent RAW vault/manifest to F1 15-minute research adapter.

Exact parent object bytes and metadata are retained. Derived JSON bar bytes
are *separate* from the parent hash: a verified transformation binding is
required. This module does not issue publication clocks or source receipts.
It does NOT import, modify or depend on unmerged G7 draft #211.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .aql_w1_market_window_adapter import authenticated_market_windows
from .aql_w1_opportunity_outcomes import EvidenceError

_HEX = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED = ("schema_version", "content_sha256", "byte_length", "source_format",
             "format_version", "interval", "correction_generation",
             "parent_content_sha256", "coverage_start_utc", "coverage_end_utc",
             "admitted_at_utc", "trust_status", "evidence_class")


def _utc_ms(value):
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("invalid UTC timestamp")
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def authenticated_parent_market_windows(
    scheduled, parent_bytes_by_pair, manifest_by_pair,
    derived_bars_by_pair, derived_evidence_by_pair, *,
    verify_parent_manifest=None, verify_derivation=None,
    verify_external_receipt=None, asof_ms=None,
):
    """Return windows and proof verifier; absent parent chain -> UNKNOWN.

    Parent metadata is compatible with raw_object.v1 fields, but is accepted
    only as an independently verified *read-only snapshot*, not on a local
    trust_status=VERIFIED flag. The derivation evidence binds exact parent
    bytes digest and derived JSON bytes digest to policy and correction.
    Host verifiers must independently attest the manifest, transformation and
    publication/custody. A synthetic True verifier is never operational proof.
    """
    plans = list(scheduled)
    pairs = {plan["pair_id"] for plan in plans}
    if len(pairs) != len(plans):
        raise EvidenceError("duplicate scheduled parent market pair")
    for mapping in (parent_bytes_by_pair, manifest_by_pair,
                    derived_bars_by_pair, derived_evidence_by_pair):
        if set(mapping) - pairs:
            raise EvidenceError("orphan parent market input")
    accepted = set()
    raw_by_pair, receipt_by_pair = {}, {}
    for plan in plans:
        pair = plan["pair_id"]
        raw, meta = parent_bytes_by_pair.get(pair), manifest_by_pair.get(pair)
        derived, lineage = derived_bars_by_pair.get(pair), derived_evidence_by_pair.get(pair)
        if not (type(raw) is bytes and type(derived) is bytes
                and isinstance(meta, dict) and isinstance(lineage, dict)
                and all(key in meta for key in _REQUIRED)):
            continue
        if meta["schema_version"] != "raw_object.v1":
            continue
        parent_sha = hashlib.sha256(raw).hexdigest()
        derived_sha = hashlib.sha256(derived).hexdigest()
        if (meta["content_sha256"] != parent_sha or
                meta["byte_length"] != len(raw) or
                meta["interval"] != "15m" or
                not isinstance(meta["correction_generation"], int) or
                isinstance(meta["correction_generation"], bool) or
                meta["correction_generation"] < 0):
            continue
        if (meta["correction_generation"] > 0 and
                not _HEX.fullmatch(str(meta["parent_content_sha256"]))):
            continue
        # The scheduled source hash is that of ORIGINAL parent bytes,
        # never silently substituted by the projected/normalised bytes.
        if (plan.get("source_bytes_sha256") != parent_sha or
                str(plan.get("correction_generation")) != str(meta["correction_generation"])):
            continue
        if (lineage.get("parent_content_sha256") != parent_sha or
                lineage.get("derived_bytes_sha256") != derived_sha or
                lineage.get("source_version") != plan.get("source_version") or
                str(lineage.get("correction_generation")) != str(meta["correction_generation"]) or
                not isinstance(lineage.get("normalization_policy"), str) or
                not lineage["normalization_policy"]):
            continue
        if any(not isinstance(lineage.get(k), int) or isinstance(lineage[k], bool)
               for k in ("published_at_ms", "finalized_at_ms")):
            continue
        if lineage["finalized_at_ms"] > lineage["published_at_ms"]:
            continue
        try:
            coverage_start = _utc_ms(meta["coverage_start_utc"])
            coverage_end = _utc_ms(meta["coverage_end_utc"])
            admitted = _utc_ms(meta["admitted_at_utc"])
            if coverage_start >= coverage_end or admitted < coverage_start:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        if any(cb is None or not callable(cb) for cb in
               (verify_parent_manifest, verify_derivation, verify_external_receipt)):
            continue
        # These are externally owned witness checks, not self-issued booleans.
        try:
            if (verify_parent_manifest(meta, raw) is not True or
                    verify_derivation(lineage, raw, derived) is not True or
                    verify_external_receipt(lineage, meta) is not True):
                continue
        except Exception:
            continue
        receipt = dict(
            source_id=plan.get("source_id", meta.get("vendor", "UNKNOWN")),
            source_version=plan["source_version"],
            source_bytes_sha256=derived_sha,
            correction_generation=plan["correction_generation"],
            raw_bytes_sha256=derived_sha,
            finalized_at_ms=lineage["finalized_at_ms"],
            published_at_ms=lineage["published_at_ms"],
        )
        receipt["receipt_sha256"] = hashlib.sha256(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        # Inner adapter consumes only correctly bound derived bytes. It is
        # never supplied with a forged claim that parent_sha == derived_sha.
        raw_by_pair[pair] = derived
        receipt_by_pair[pair] = receipt
        accepted.add((pair, parent_sha, derived_sha, receipt["receipt_sha256"]))
    # Derived adapter expects a derived-content SHA; this shadow schedule is
    # used strictly internally. Output rows are rewritten to immutable parent
    # identity after validation and remain bound by the returned verifier.
    derived_schedule = []
    for plan in plans:
        p = dict(plan)
        if p["pair_id"] in raw_by_pair:
            p["source_bytes_sha256"] = hashlib.sha256(raw_by_pair[p["pair_id"]]).hexdigest()
        derived_schedule.append(p)
    windows, verify_window = authenticated_market_windows(
        derived_schedule, raw_by_pair, receipt_by_pair,
        verify_receipt=lambda receipt: any(
            key[0] in pairs and key[2] == receipt["raw_bytes_sha256"] and
            key[3] == receipt["receipt_sha256"] for key in accepted
        ), asof_ms=asof_ms)
    output = []
    accepted_output = {}
    for window in windows:
        if not verify_window(window):
            output.append({**window,
                           "source_bytes_sha256": next(p["source_bytes_sha256"]
                                                       for p in plans if p["pair_id"] == window["pair_id"]),
                           "coverage_status": window["coverage_status"]})
            continue
        original = next(p for p in plans if p["pair_id"] == window["pair_id"])
        rewritten = {**window, "source_bytes_sha256": original["source_bytes_sha256"],
                     "parent_content_sha256": original["source_bytes_sha256"]}
        output.append(rewritten)
        accepted_output[(rewritten["pair_id"], rewritten["horizon_ms"])] = json.dumps(
            rewritten, sort_keys=True, separators=(",", ":"))
    def check_market(window):
        if not isinstance(window, dict):
            return False
        key = (window.get("pair_id"), window.get("horizon_ms"))
        return (key in accepted_output and json.dumps(
            window, sort_keys=True, separators=(",", ":")) == accepted_output[key])
    return output, check_market
