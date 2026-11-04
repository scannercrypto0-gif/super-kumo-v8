"""AQL Core #249: bounded chronology and opportunity universe evidence seam.

Read-only extension for previously admitted original historical data. Never
turns an asserted venue time, SHA, retrospective archive or a supplied universe
into independent proof of point-in-time availability or full market coverage.
A future independently verified trust backend can consume the typed missing
evidence, but this boundary CANNOT grant verified authority by itself.
"""
from __future__ import annotations

from collections import Counter
import re

from research_wp_r0.aql_archive_custody_bridge_v1 import digest

SCHEMA = "aql.core.chronology-universe-assessment.v1"
CHRONOLOGY_SCHEMA = "aql.core.historical-chronology-evidence.v1"
UNIVERSE_SCHEMA = "aql.core.opportunity-universe-evidence.v1"
STATES = ("ELIGIBLE", "INELIGIBLE", "UNSCANNED", "REJECTED", "UNKNOWN", "MISSING")
HEX = re.compile(r"^[a-f0-9]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
MAX_ROWS = 4096
MAX_MEMBERS = 256
MAX_TIME = (1 << 53) - 1


class EvidenceBoundaryError(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise EvidenceBoundaryError(code)


def sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def identity(value):
    return type(value) is str and IDENT.fullmatch(value) is not None


def ms(value):
    return type(value) is int and 0 <= value <= MAX_TIME


def _sealed(value, seal_key):
    need(type(value) is dict and sha(value.get(seal_key)), "EVIDENCE_SEAL_MISSING")
    body = {k: v for k, v in value.items() if k != seal_key}
    need(digest(body) == value[seal_key], "EVIDENCE_SEAL_INVALID")
    return body


def _core(admission, price):
    need(type(admission) is dict and
         admission.get("schema") == "aql.core.historical-original-admission.v1",
         "CORE_ADMISSION_SCHEMA")
    a = _sealed(admission, "manifest_record_sha256")
    need(type(price) is dict and
         price.get("schema") == "aql.core.historical-price-custody-query.v1",
         "CORE_PRICE_SCHEMA")
    p = _sealed(price, "price_query_sha256")
    need(a.get("source_bytes_sha256") == p.get("source_bytes_sha256") and
         a.get("manifest_integrity_sha256") == p.get("manifest_integrity_sha256")
         and a.get("dataset_id") == p.get("dataset_id")
         and a.get("version") == p.get("version")
         and a.get("decision_cutoff_ms") == p.get("decision_cutoff_ms")
         and a.get("coverage") == p.get("coverage")
         and a.get("missing_bar_opens") == p.get("missing_bar_opens")
         and a.get("available_bar_count") == p.get("available_bar_count")
         and a.get("required_bar_count") == p.get("required_bar_count"),
         "CORE_SOURCE_PRICE_DRIFT")
    need(p.get("status") == "OK" and
         a.get("authenticated_source") == "NOT_ATTESTED" and
         a.get("confirmed_pit") == "NOT_ATTESTED" and
         p.get("scientific_pit") == "NOT_ATTESTED" and
         p.get("source_availability") == "RETROSPECTIVE_NON_PIT",
         "CORE_RETROSPECTIVE_AUTHORITY_DRIFT")
    bars = p.get("bars")
    need(type(bars) is list and 0 <= len(bars) <= MAX_ROWS and
         len(bars) == p["available_bar_count"], "CORE_PRICE_CENSUS")
    opened = set()
    for b in bars:
        need(type(b) is dict and ms(b.get("bar_open_ms"))
             and ms(b.get("bar_close_ms"))
             and b["bar_close_ms"] >= b["bar_open_ms"]
             and b["bar_open_ms"] not in opened
             and sha(b.get("checksum"))
             and b.get("availability_kind") == "RETROSPECTIVE"
             and b.get("historical_known_at_ms") is None,
             "CORE_BAR_PROVENANCE")
        opened.add(b["bar_open_ms"])
    need(len(opened) + len(p["missing_bar_opens"]) ==
         p["required_bar_count"], "CORE_PRICE_MISSING_GRID")
    return a, p, bars


def _chronology(evidence, admission, price, bars):
    if evidence is None:
        return {
            "evidence_state": "CHRONOLOGY_EVIDENCE_NOT_AVAILABLE",
            "claimed_capture_ms": None,
            "claimed_publish_ms": None,
            "claimed_historical_known_at_ms": None,
            "bar_timestamps_claimed": 0,
            "bar_timestamps_unknown": len(bars),
            "correction_state": "UNKNOWN",
            "independent_issuer_attestation": "NOT_ATTESTED",
            "historical_pit": "NOT_ATTESTED",
            "evidence_sha256": None,
        }
    need(type(evidence) is dict and set(evidence) == {
        "schema", "dataset_id", "version", "original_zip_sha256",
        "manifest_integrity_sha256", "issuer_name",
        "evidence_reference", "evidence_bytes_sha256",
        "observed_capture_ms", "claimed_publication_ms",
        "claimed_historical_known_at_ms", "correction_state",
        "correction_parent_sha256", "bar_claims", "evidence_sha256",
    }, "CHRONOLOGY_FIELDS")
    payload = _sealed(evidence, "evidence_sha256")
    need(payload["schema"] == CHRONOLOGY_SCHEMA
         and payload["dataset_id"] == admission["dataset_id"]
         and payload["version"] == admission["version"]
         and payload["original_zip_sha256"] == admission["source_bytes_sha256"]
         and payload["manifest_integrity_sha256"] ==
             price["manifest_integrity_sha256"], "CHRONOLOGY_SOURCE_DRIFT")
    need(identity(payload["issuer_name"])
         and identity(payload["evidence_reference"])
         and sha(payload["evidence_bytes_sha256"]),
         "CHRONOLOGY_PROVENANCE_FIELDS")
    for key in ("observed_capture_ms", "claimed_publication_ms",
                "claimed_historical_known_at_ms"):
        need(payload[key] is None or ms(payload[key]),
             "CHRONOLOGY_TIME_FIELDS")
    if payload["observed_capture_ms"] is not None:
        for name in ("claimed_publication_ms", "claimed_historical_known_at_ms"):
            if payload[name] is not None:
                need(payload[name] <= payload["observed_capture_ms"],
                     "CHRONOLOGY_AFTER_CAPTURE")
    # A 2026 download is a 2026 capture, not 2024 publication proof.
    need(payload["correction_state"] in ("UNKNOWN", "ORIGINAL_CLAIM",
                                        "CORRECTION_CLAIM"),
         "CORRECTION_STATE")
    need(payload["correction_parent_sha256"] ==
         admission.get("correction_parent_source_sha256")
         and (payload["correction_state"] != "CORRECTION_CLAIM"
              or sha(payload["correction_parent_sha256"])),
         "CORRECTION_PARENT_DRIFT")
    claims = payload["bar_claims"]
    need(type(claims) is list and len(claims) <= len(bars), "CHRONOLOGY_BAR_COUNT")
    bar_index = {b["bar_open_ms"]: b for b in bars}
    seen = set()
    for item in claims:
        need(type(item) is dict and set(item) ==
             {"bar_open_ms", "bar_checksum", "claimed_known_at_ms",
              "evidence_record_sha256"}, "CHRONOLOGY_BAR_FIELDS")
        t = item["bar_open_ms"]
        need(ms(t) and t in bar_index and t not in seen
             and item["bar_checksum"] == bar_index[t]["checksum"]
             and sha(item["evidence_record_sha256"]), "CHRONOLOGY_BAR_PARENT")
        seen.add(t)
        known = item["claimed_known_at_ms"]
        need(known is None or (ms(known) and
             known >= bar_index[t]["bar_close_ms"] + 1),
             "CHRONOLOGY_BAR_FUTURE_LEAK_OR_TIME")
        if known is not None and payload["observed_capture_ms"] is not None:
            need(known <= payload["observed_capture_ms"],
                 "CHRONOLOGY_BAR_AFTER_CAPTURE")
    return {
        "evidence_state": "SUPPLIED_CLAIMS_UNVERIFIED",
        "claimed_capture_ms": payload["observed_capture_ms"],
        "claimed_publish_ms": payload["claimed_publication_ms"],
        "claimed_historical_known_at_ms": payload["claimed_historical_known_at_ms"],
        "bar_timestamps_claimed": sum(
            x["claimed_known_at_ms"] is not None for x in claims),
        "bar_timestamps_unknown": len(bars) - sum(
            x["claimed_known_at_ms"] is not None for x in claims),
        "correction_state": payload["correction_state"],
        "independent_issuer_attestation": "NOT_ATTESTED",
        "historical_pit": "NOT_ATTESTED",
        "evidence_sha256": evidence["evidence_sha256"],
    }


def _universe(evidence, admission, price, bars):
    if evidence is None:
        return {
            "evidence_state": "UNIVERSE_EVIDENCE_NOT_AVAILABLE",
            "reported_member_count": None,
            "reported_opportunity_count": None,
            "reported_status_counts": None,
            "reported_exclusions": None,
            "reported_gaps": None,
            "independent_market_opportunity_denominator": None,
            "independently_complete_universe": "NOT_ATTESTED",
            "evidence_sha256": None,
        }
    need(type(evidence) is dict and set(evidence) == {
        "schema", "dataset_id", "version", "original_zip_sha256",
        "manifest_integrity_sha256", "market", "venue", "timeframe",
        "start_ms", "end_exclusive_ms", "source_manifest_sha256",
        "inventory_observed_at_ms", "completeness_claim",
        "members", "opportunities", "evidence_sha256",
    }, "UNIVERSE_FIELDS")
    payload = _sealed(evidence, "evidence_sha256")
    need(payload["schema"] == UNIVERSE_SCHEMA
         and payload["dataset_id"] == admission["dataset_id"]
         and payload["version"] == admission["version"]
         and payload["original_zip_sha256"] == admission["source_bytes_sha256"]
         and payload["manifest_integrity_sha256"] ==
             price["manifest_integrity_sha256"], "UNIVERSE_SOURCE_DRIFT")
    need(all(identity(payload[x]) for x in
             ("market", "venue", "timeframe"))
         and sha(payload["source_manifest_sha256"]),
         "UNIVERSE_CATALOG_PROVENANCE")
    need(ms(payload["start_ms"]) and ms(payload["end_exclusive_ms"])
         and payload["start_ms"] < payload["end_exclusive_ms"]
         and (payload["inventory_observed_at_ms"] is None
              or ms(payload["inventory_observed_at_ms"]))
         and payload["completeness_claim"] in
             ("UNKNOWN", "DECLARED_COMPLETE_UNVERIFIED", "DECLARED_PARTIAL"),
         "UNIVERSE_TIME_OR_COMPLETENESS")
    members = payload["members"]
    need(type(members) is list and len(members) <= MAX_MEMBERS, "MEMBER_BOUNDS")
    member_map = {}
    total_gaps = total_exclusions = 0
    for member in members:
        need(type(member) is dict and set(member) == {
            "symbol", "market", "venue", "timeframe",
            "status", "missing_bar_opens", "exclusion_reason",
        }, "MEMBER_FIELDS")
        name = member["symbol"]
        need(identity(name) and name not in member_map
             and member["market"] == payload["market"]
             and member["venue"] == payload["venue"]
             and member["timeframe"] == payload["timeframe"]
             and member["status"] in ("INCLUDED", "EXCLUDED", "UNKNOWN"),
             "UNIVERSE_MEMBER_IDENTITY")
        gaps = member["missing_bar_opens"]
        need(type(gaps) is list and len(gaps) <= MAX_ROWS
             and all(ms(t) and payload["start_ms"] <= t <
                     payload["end_exclusive_ms"] for t in gaps)
             and gaps == sorted(set(gaps)), "UNIVERSE_MEMBER_GAPS")
        need((member["status"] == "EXCLUDED" and
              identity(member["exclusion_reason"]))
             or (member["status"] != "EXCLUDED" and
                 member["exclusion_reason"] is None),
             "UNIVERSE_EXCLUSION_PROVENANCE")
        total_gaps += len(gaps)
        total_exclusions += (member["status"] == "EXCLUDED")
        member_map[name] = member
    opportunities = payload["opportunities"]
    need(type(opportunities) is list and len(opportunities) <= MAX_ROWS,
         "OPPORTUNITY_BOUNDS")
    ids = set()
    slots = set()
    counts = Counter({x: 0 for x in STATES})
    for item in opportunities:
        need(type(item) is dict and set(item) == {
            "opportunity_id", "symbol", "bar_open_ms",
            "status", "reason", "source_bar_checksum",
        }, "OPPORTUNITY_FIELDS")
        symbol = item["symbol"]
        t = item["bar_open_ms"]
        need(identity(item["opportunity_id"]) and
             item["opportunity_id"] not in ids
             and symbol in member_map and ms(t)
             and payload["start_ms"] <= t < payload["end_exclusive_ms"]
             and (symbol,t) not in slots
             and item["status"] in STATES
             and identity(item["reason"]),
             "OPPORTUNITY_IDENTITY_OR_CLOCK")
        if member_map[symbol]["status"] != "INCLUDED":
            need(item["status"] in ("UNKNOWN","MISSING","INELIGIBLE"),
                 "EXCLUDED_MEMBER_OPPORTUNITY")
        if t in member_map[symbol]["missing_bar_opens"]:
            need(item["status"] in ("MISSING","UNKNOWN") and
                 item["source_bar_checksum"] is None,
                 "MISSING_OPPORTUNITY_PROMOTED")
        else:
            need(item["source_bar_checksum"] is None or
                 sha(item["source_bar_checksum"]),
                 "OPPORTUNITY_SOURCE_BAR_PIN")
        ids.add(item["opportunity_id"])
        slots.add((symbol,t))
        counts[item["status"]] += 1
    # Report only supplied counts: a source catalog alone cannot establish the
    # full set of eligible venues/symbols/opportunities that existed historically.
    return {
        "evidence_state": "SUPPLIED_INVENTORY_UNVERIFIED",
        "reported_member_count": len(members),
        "reported_opportunity_count": len(opportunities),
        "reported_status_counts": dict(counts),
        "reported_exclusions": total_exclusions,
        "reported_gaps": total_gaps,
        "independent_market_opportunity_denominator": None,
        "independently_complete_universe": "NOT_ATTESTED",
        "evidence_sha256": evidence["evidence_sha256"],
    }


def assess_chronology_universe(core_admission, core_price_query, *,
                               chronology_evidence=None, universe_evidence=None):
    """Bind exact Core custody/query to bounded claimed external evidence.

    The input SHA and optional self-sealed sidecars prove local identity only.
    Neither a purported publication date nor a 'complete' symbol list supplies
    independent issuer attestation or scientifically usable historical PIT.
    """
    a, p, bars = _core(core_admission, core_price_query)
    chronology = _chronology(chronology_evidence, a, p, bars)
    universe = _universe(universe_evidence, a, p, bars)
    body = {
        "schema": SCHEMA, "status": "EVIDENCE_INCOMPLETE",
        "dataset_id": a["dataset_id"], "version": a["version"],
        "source_bytes_sha256": a["source_bytes_sha256"],
        "manifest_integrity_sha256": a["manifest_integrity_sha256"],
        "admission_sha256": core_admission["manifest_record_sha256"],
        "price_query_sha256": core_price_query["price_query_sha256"],
        "decision_cutoff_ms": a["decision_cutoff_ms"],
        "core_bar_coverage": p["coverage"],
        "chronology": chronology, "universe": universe,
        "historical_pit": "NOT_ATTESTED",
        "independent_venue_issuance": "NOT_ATTESTED",
        "market_universe_completeness": "NOT_ATTESTED",
        "independent_opportunity_denominator": None,
        "factory_scientific_input": "BLOCKED",
        "work_scientific_e2e": "NOT_CONNECTED",
        "holdout": "UNTOUCHED",
        "trading_authority": "NONE",
    }
    return {**body, "assessment_sha256": digest(body)}
