"""TEST_ONLY compatibility gate for Core #226 and Discoverer #230 draft contracts.

Consumes JSON-shaped *read-only* envelopes, not unmerged runtime modules.
Does not turn an untrusted Scanner nomination into an executable Factory signal.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_research_consumer_seam import (
    build_research_report, digest, fail, hash_ok, require,
)

CORE_REQUEST = "aql.core-research.custody-query.v1"
CORE_RESPONSE = "aql.core-research.custody-query-result.v1"
CORE_RANGE = "aql.bridge.custody-range.v1"
DISCOVERER_EVIDENCE = "aql.discoverer.nomination-evidence.v1"
DISCOVERER_CANDIDATE = "aql.discoverer.candidate.v1"
COMPAT = "aql.factory.research-compatibility.v1"
CORE_REQUEST_FIELDS = frozenset((
    "schema", "dataset_id", "version", "start_ms", "end_exclusive_ms",
    "decision_cutoff_ms", "require_complete", "confirmed_only",
))
CENSUS = (
    "full_universe_denominator", "eligible_selected", "ineligible",
    "unscanned", "screened_rejected", "unknown", "nominated",
    "failed_attempts",
)
CANDIDATE_PROTECTION = {
    "evaluation_status": "NOT_EVALUATED",
    "scientific_acceptance": "NOT_OBTAINED",
    "execution_status": "NOT_AUTHORIZED",
    "publishable": False,
    "delivery_authorized": False,
    "holdout_status": "SEALED_UNOPENED",
    "factory_routing": "NOT_CONNECTED",
}


def _sealed_payload(obj, key, context):
    require(type(obj) is dict and hash_ok(obj.get(key)), context + "_DIGEST")
    require(digest({k: v for k, v in obj.items() if k != key}) == obj[key],
            context + "_TAMPER")


def validate_core_query(request, response):
    """Pin exact #226 request/response schema. No invented OHLCV prices."""
    require(type(request) is dict and set(request) == CORE_REQUEST_FIELDS
            and request["schema"] == CORE_REQUEST, "CORE_REQUEST")
    require(type(request["dataset_id"]) is str and bool(request["dataset_id"])
            and type(request["version"]) is int and request["version"] >= 1,
            "CORE_DATASET")
    for field in ("start_ms", "end_exclusive_ms", "decision_cutoff_ms"):
        require(type(request[field]) is int and request[field] >= 0,
                "CORE_TIME")
    require(request["start_ms"] < request["end_exclusive_ms"]
            and request["end_exclusive_ms"] <= request["decision_cutoff_ms"],
            "CORE_FUTURE_RANGE")
    require(request["require_complete"] is True
            and request["confirmed_only"] is False, "CORE_FLAGS")
    require(type(response) is dict
            and response.get("schema") == CORE_RESPONSE
            and response.get("status") == "OK"
            and response.get("error") is None
            and response.get("evidence_class") == "SYNTHETIC_TEST",
            "CORE_RESPONSE_OR_AUTHORITY")
    result = response.get("result")
    require(type(result) is dict and result.get("schema") == CORE_RANGE,
            "CORE_RANGE_SCHEMA")
    require(result.get("dataset_id") == request["dataset_id"]
            and result.get("version") == request["version"]
            and result.get("decision_cutoff_ms") == request["decision_cutoff_ms"],
            "CORE_IDENTITY_OR_CUTOFF")
    require(result.get("status") == "COMPLETE"
            and result.get("availability_class") == "SYNTHETIC_TEST"
            and result.get("source_confidence") == "LOCAL_CHECKSUM_AND_PIN_ONLY"
            and result.get("research_evaluation") == "NOT_PERFORMED",
            "CORE_COVERAGE_OR_AUTHORITY")
    require(hash_ok(result.get("source_bytes_sha256"))
            and hash_ok(result.get("manifest_integrity_sha256")),
            "CORE_SOURCE_SHA")
    bars = result.get("bars")
    count = result.get("required_bar_count")
    require(type(count) is int and count > 0 and type(bars) is list
            and len(bars) == count and result.get("available_bar_count") == count
            and result.get("missing_bar_opens") == [], "CORE_DENOMINATOR")
    width, leftover = divmod(request["end_exclusive_ms"] - request["start_ms"], count)
    require(width > 0 and leftover == 0, "CORE_GRID")
    for index, bar in enumerate(bars):
        start = request["start_ms"] + index * width
        require(type(bar) is dict and type(bar.get("bar_open")) is int
                and type(bar.get("bar_close")) is int
                and bar["bar_open"] == start
                and bar["bar_close"] == start + width - 1
                and type(bar.get("observation_cutoff_ms")) is int
                and bar["bar_close"] < bar["observation_cutoff_ms"]
                <= request["decision_cutoff_ms"]
                and bar.get("availability_kind") == "RETROSPECTIVE"
                and hash_ok(bar.get("checksum")), "CORE_BAR_AVAILABILITY_OR_GRID")
    return result


def validate_discoverer(evidence, candidate):
    """Verify exact #230 canonical commitments, census and quarantine flags."""
    _sealed_payload(evidence, "nomination_digest", "DISCOVERER_EVIDENCE")
    _sealed_payload(candidate, "package_digest", "DISCOVERER_PACKAGE")
    require(evidence.get("schema_version") == DISCOVERER_EVIDENCE
            and evidence.get("evidence_class") == "TEST_ONLY_SYNTHETIC"
            and evidence.get("quarantine_status") == "TEST_ONLY_SYNTHETIC",
            "DISCOVERER_QUARANTINE")
    require(candidate.get("schema_version") == DISCOVERER_CANDIDATE
            and candidate.get("status") == "PROPOSED_RESEARCH_ONLY",
            "DISCOVERER_CANDIDATE_STATUS")
    for field, value in CANDIDATE_PROTECTION.items():
        require(candidate.get(field) == value
                and type(candidate.get(field)) is type(value),
                "DISCOVERER_AUTHORITY_" + field.upper())
    require(candidate.get("nomination_evidence_digest") ==
            evidence["nomination_digest"]
            and candidate.get("source_manifest_sha256") ==
            evidence.get("source_manifest_sha256")
            and hash_ok(candidate.get("strategy_definition_digest"))
            and hash_ok(candidate.get("attempt_ledger_head"))
            and type(candidate.get("candidate_id")) is str
            and bool(candidate["candidate_id"]), "DISCOVERER_SOURCE_BINDING")
    require(type(evidence.get("cutoff_ms")) is int
            and evidence["cutoff_ms"] >= 0
            and hash_ok(evidence.get("source_raw_sha256"))
            and hash_ok(evidence.get("source_manifest_sha256")),
            "DISCOVERER_SOURCE_CUTOFF")
    for key in CENSUS:
        require(type(evidence.get(key)) is int and evidence[key] >= 0,
                "DISCOVERER_CENSUS_TYPE")
    require(evidence["full_universe_denominator"] ==
            evidence["eligible_selected"] + evidence["ineligible"]
            and evidence["eligible_selected"] ==
            evidence["unscanned"] + evidence["screened_rejected"] +
            evidence["unknown"] + evidence["nominated"]
            and evidence["failed_attempts"] <= evidence["unknown"] +
            evidence["unscanned"]
            and evidence["nominated"] > 0, "DISCOVERER_CENSUS")
    require(type(evidence.get("omission_reason_codes")) is list,
            "DISCOVERER_REASON_CODES")
    require(evidence["unscanned"] == 0 or
            len(evidence["omission_reason_codes"]) > 0,
            "DISCOVERER_UNSCANNED_UNEXPLAINED")
    return evidence, candidate


def build_compatibility_report(schedule, envelope, observations, request,
                               response, evidence, candidate, binding):
    """One consolidated read-only compatibility and Factory descriptive test.

    Explicit binding identifies exactly one TEST_ONLY research row. No real
    Scanner/Discoverer routing, order entry, PnL or execution authorization.
    """
    core = validate_core_query(request, response)
    evidence, candidate = validate_discoverer(evidence, candidate)
    require(core["dataset_id"] == evidence.get("source_dataset_id")
            and core["source_bytes_sha256"] == evidence.get("source_raw_sha256")
            and core["manifest_integrity_sha256"] ==
            evidence.get("source_manifest_sha256")
            and core["decision_cutoff_ms"] == evidence["cutoff_ms"],
            "CROSS_OWNER_SOURCE_JOIN")
    require(type(envelope) is dict
            and envelope.get("source_manifest_sha256") ==
            evidence["source_manifest_sha256"]
            and envelope.get("strategy_version") ==
            candidate["strategy_definition_digest"]
            and envelope.get("source_package_sha256") ==
            core["source_bytes_sha256"], "FACTORY_SOURCE_JOIN")
    require(type(binding) is dict and set(binding) == {
        "pair_id", "arm", "attempt_id", "candidate_id",
    } and binding["candidate_id"] == candidate["candidate_id"],
            "EXPLICIT_CANDIDATE_BINDING")
    matches = [
        row for row in envelope.get("rows", [])
        if row.get("pair_id") == binding["pair_id"]
        and row.get("arm") == binding["arm"]
        and row.get("attempt_id") == binding["attempt_id"]
    ]
    require(len(matches) == 1
            and matches[0]["status"] == "NOMINATED"
            and matches[0]["decision_cutoff_ms"] == evidence["cutoff_ms"],
            "FACTORY_TARGET_CUTOFF_OR_STATUS")
    report = build_research_report(schedule, envelope, observations)
    result = {
        "schema": COMPAT,
        "test_only": True,
        "scope": "PINNED_SCHEMA_COMPATIBILITY_ONLY",
        "core_contract": CORE_RESPONSE,
        "core_custody_query_status": "SYNTHETIC_TEST_COMPLETE",
        "core_source_bytes_sha256": core["source_bytes_sha256"],
        "core_manifest_integrity_sha256": core["manifest_integrity_sha256"],
        "discoverer_candidate_id": candidate["candidate_id"],
        "discoverer_nomination_digest": evidence["nomination_digest"],
        "discoverer_package_digest": candidate["package_digest"],
        "discoverer_attempt_ledger_head": candidate["attempt_ledger_head"],
        "discoverer_census": {key: evidence[key] for key in CENSUS},
        "factory_target_pair_id": binding["pair_id"],
        "factory_target_arm": binding["arm"],
        "factory_report_sha256": report["artifact_sha256"],
        "factory_arm_slots": report["arm_slots"],
        "factory_status_counts": report["status_counts"],
        "factory_observation_slots": report["descriptive_observation_slots"],
        "scanner_nomination": "TEST_ONLY_QUARANTINED",
        "authentic_core_discoverer_connection": "NOT_CONNECTED",
        "strategy_definition_semantics": "NOT_INDEPENDENTLY_REVALIDATED",
        "cross_owner_manifest_join": "EXPLICIT_TEST_ONLY_EQUAL_SHA_FIXTURE",
        "market_ohlcv_price_data": "NOT_PROVIDED_BY_CORE_QUERY_RESULT",
        "descriptive_outcomes": "EXISTING_FACTORY_TEST_ONLY",
        "modeled_trades": "NOT_EVALUATED",
        "execution_status": "NOT_OBSERVED",
        "pit_status": "NOT_ATTESTED",
        "oos_status": "NOT_ATTESTED",
        "holdout_status": "SEALED_UNOPENED",
        "trading_authority": "NONE",
    }
    result["artifact_sha256"] = digest(result)
    return result
