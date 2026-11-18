"""Bounded synthetic prospective capture chain and retained host-claim intake."""

from datetime import datetime
from research_wp_r0.aql_f1_decision_capture_v1 import validate_f1
from research_wp_r0.aql_factory_e_research_results_store_v1 import _check_seal, digest
from tools.pit_oos_readiness.promotion import review


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate_capture_chain(records, registry, admissions, *, methods_receipt):
    _check_seal(methods_receipt)
    require(methods_receipt["source_class"] == "SYNTHETIC_FIXTURE_ONLY"
            and methods_receipt["holdout"] == "SEALED_UNOPENED"
            and methods_receipt["external_custody_verified"] is False
            and methods_receipt["trial_report"]["selected_candidate"] is None
            and methods_receipt["evaluation"]["decision"] == "NO_PROMOTION",
            "QUEUE5_FROZEN_METHODS_REQUIRED")
    require(len(records) == len(admissions) > 0, "QUEUE5_CAPTURE_DENOMINATOR")
    previous = None
    cutoff = -1
    identity = None
    for index, (record, admission) in enumerate(zip(records, admissions)):
        validate_f1(record, registry)
        _check_seal(admission, field="receipt_sha256")
        source = (record["source_id"], record["source_version"],
                  record["correction_generation"], record["experiment_plan_sha256"])
        require(record["producer_sequence"] == index
                and record["previous_event_sha256"] == previous
                and record["decision_cutoff_ms"] > cutoff, "QUEUE5_SEQUENCE_OR_REPLAY")
        require(identity is None or identity == source, "QUEUE5_SOURCE_DRIFT")
        require(admission["status"] == "PASS_SYNTHETIC_ADMISSION_ONLY"
                and admission["independent_pit"] == "NOT_ATTESTED"
                and admission["real_cohort_status"] == "BLOCKED_OWNER_AUTHORIZATION"
                and record["source_bytes_sha256"] == admission["content_sha256"]
                and record["source_available_at_ms"] == admission["available_at_ms"]
                and record["decision_cutoff_ms"] == admission["commit_return_observed_at_ms"]
                and record["source_version"] == methods_receipt["sha256"],
                "QUEUE5_CAPTURE_ADMISSION_BINDING")
        previous = record["f1_record_sha256"]
        cutoff = record["decision_cutoff_ms"]
        identity = source
    promotion = review({
        "first_open_utc": "2026-11-23T00:00:00Z",
        "earliest_evaluation_utc_date": "2026-12-06",
        "planning_dates_are_authorization": False,
        "methods_receipt_sha256": methods_receipt["sha256"],
    }, evidence_grade="SYNTHETIC_TESTED")
    body = {
        "schema": "aql.queue5.synthetic-readiness.v1",
        "capture_count": len(records), "capture_tail": previous,
        "admission_sha256": [value["receipt_sha256"] for value in admissions],
        "methods_receipt_sha256": methods_receipt["sha256"],
        "promotion": promotion, "holdout": "SEALED_UNOPENED",
        "source_class": "SYNTHETIC_FIXTURE_ONLY", "original_pit_oos": "AUTHORITY_BLOCKED",
        "orders_created": 0, "paper_positions": 0, "dispatches": 0,
        "trading_authority": "NONE",
    }
    return {**body, "sha256": digest(body)}


def inspect_host_claim(claim):
    require(claim["evidence_grade"] == "OWNER_REPORTED_LOCAL",
            "QUEUE5_HOST_GRADE")
    prior = claim["prior_segment"]
    following = claim["next_segment"]
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(prior["id"] < following["id"]
            and parse(prior["started_at"]) < parse(prior["completed_at"])
            <= parse(following["started_at"]) <= parse(claim["readback_at"]),
            "QUEUE5_HOST_REPORTED_CHRONOLOGY")
    receipt = claim["finalized_receipt_sha256"]
    require(type(receipt) is str and len(receipt) == 64
            and all(c in "0123456789abcdef" for c in receipt), "QUEUE5_HOST_RECEIPT_FORMAT")
    return {
        "evidence_grade": "OWNER_REPORTED_LOCAL",
        "reported_segment_order": "CONSISTENT",
        "original_receipt_bytes_verified": False,
        "source_authenticity": "UNVERIFIED",
        "automatic_fault_recovery": "UNVERIFIED",
        "original_pit_oos": "AUTHORITY_BLOCKED",
        "claim_sha256": digest(claim),
    }
