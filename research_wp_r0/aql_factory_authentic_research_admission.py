"""Fail-closed Factory scientific research admission V1 (Issue #238).

This module never attests an original market source by trusting a caller's flag.
It validates research-plan/attempt census and immutable commitments before
returning an explicit blocked handoff. It neither evaluates strategy signals
nor opens a holdout, and never confuses synthetic descriptive fixtures with
scientific performance.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json

SCHEMA = "aql.factory.authentic-research-admission.v1"
REPORT = "aql.factory.authentic-research-gate.v1"
STATES = frozenset(("PROPOSED", "INVALID", "DUPLICATE", "FAILED",
                    "BUDGET_EXHAUSTED", "REJECTED", "UNKNOWN", "NOT_EVALUATED"))
HEX = frozenset("0123456789abcdef")


class ResearchAdmissionError(ValueError):
    pass


def _require(ok, reason):
    if not ok:
        raise ResearchAdmissionError("FACTORY_AUTHENTIC_" + reason)


def _hash(value):
    return type(value) is str and len(value) == 64 and set(value) <= HEX


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=True).encode()).hexdigest()


def _check_seal(value, field):
    _require(type(value) is dict and _hash(value.get(field)), "SEAL_MISSING")
    payload = {k: v for k, v in value.items() if k != field}
    _require(_digest(payload) == value[field], "SEAL_TAMPER")


def seal(payload):
    _require(type(payload) is dict and "artifact_sha256" not in payload,
             "SEAL_INPUT")
    value = json.loads(json.dumps(payload, allow_nan=False))
    value["artifact_sha256"] = _digest(value)
    return value


def assess_research_admission(packet):
    """Read-only strict preflight, never an authorization for authentic execution.

    Original bytes and trustworthy capture/PIT provenance MUST be verified
    independently at the Core custody boundary. A caller-supplied digest,
    receipt or 'verified' boolean cannot establish that verification.
    """
    _check_seal(packet, "artifact_sha256")
    _require(packet.get("schema") == SCHEMA, "SCHEMA")
    _require(packet.get("execution_authority") == "NONE"
             and packet.get("paper_live") is False
             and packet.get("holdout") == "SEALED_UNOPENED", "AUTHORITY")
    _require(packet.get("source_kind") in ("TEST_ONLY", "ORIGINAL_UNVERIFIED"),
             "SOURCE_CLASS")
    _require(_hash(packet.get("source_bytes_sha256"))
             and _hash(packet.get("source_manifest_sha256"))
             and _hash(packet.get("dataset_version_sha256"))
             and _hash(packet.get("plan_digest")), "SOURCE_IDENTITY")
    _require(type(packet.get("dataset_id")) is str and bool(packet["dataset_id"])
             and type(packet.get("strategy_id")) is str and bool(packet["strategy_id"])
             and type(packet.get("strategy_version")) is str
             and bool(packet["strategy_version"]), "STRATEGY_DATASET")
    _require(_hash(packet.get("strategy_definition_digest")), "STRATEGY_DIGEST")
    cutoff = packet.get("decision_cutoff_ms")
    _require(type(cutoff) is int and cutoff >= 0, "CUTOFF")
    _require(packet.get("availability") in ("UNKNOWN", "RETROSPECTIVE_NON_PIT",
                                            "SYNTHETIC_TEST"), "AVAILABILITY")
    _require(type(packet.get("expected_attempts")) is int
             and packet["expected_attempts"] >= 0, "TRIAL_BUDGET")
    attempts = packet.get("attempts")
    _require(type(attempts) is list
             and len(attempts) == packet["expected_attempts"], "ATTEMPT_DENOMINATOR")
    seen = set()
    counts = Counter()
    for attempt in attempts:
        _require(type(attempt) is dict and
                 set(attempt) == {"attempt_id", "strategy_id", "strategy_version",
                                  "plan_digest", "decision_cutoff_ms",
                                  "feature_available_ms", "state", "duplicate_of",
                                  "result", "holdout_access"}, "ATTEMPT_SHAPE")
        aid = attempt["attempt_id"]
        _require(type(aid) is str and bool(aid) and aid not in seen,
                 "DUPLICATE_ATTEMPT_ID")
        seen.add(aid)
        _require(attempt["strategy_id"] == packet["strategy_id"]
                 and attempt["strategy_version"] == packet["strategy_version"]
                 and attempt["plan_digest"] == packet["plan_digest"]
                 and type(attempt["decision_cutoff_ms"]) is int
                 and attempt["decision_cutoff_ms"] == cutoff, "ATTEMPT_BINDING")
        available = attempt["feature_available_ms"]
        _require(available is None or
                 (type(available) is int and 0 <= available <= cutoff),
                 "FEATURE_LOOKAHEAD")
        state = attempt["state"]
        _require(state in STATES, "STATE")
        _require(attempt["result"] is None and
                 attempt["holdout_access"] is False, "RESULT_OR_HOLDOUT_PROMOTION")
        _require((state == "DUPLICATE") ==
                 (type(attempt["duplicate_of"]) is str and
                  bool(attempt["duplicate_of"])), "DUPLICATE_LINEAGE")
        counts[state] += 1
    # Duplicate lineage must reference a prior claimed attempt, not itself or a
    # missing/future ID. This also rules out cyclic duplicate chains.
    prior = set()
    for attempt in attempts:
        if attempt["state"] == "DUPLICATE":
            _require(attempt["duplicate_of"] in prior, "DUPLICATE_PARENT")
        prior.add(attempt["attempt_id"])
    _require(sum(counts.values()) == packet["expected_attempts"], "CENSUS")
    result = {
        "schema": REPORT,
        "input_sha256": packet["artifact_sha256"],
        "source_bytes_sha256": packet["source_bytes_sha256"],
        "source_manifest_sha256": packet["source_manifest_sha256"],
        "dataset_id": packet["dataset_id"],
        "strategy_id": packet["strategy_id"],
        "strategy_version": packet["strategy_version"],
        "plan_digest": packet["plan_digest"],
        "attempt_count": len(attempts),
        "attempt_states": {s: counts[s] for s in sorted(STATES)},
        "admission": "TEST_ONLY_CONTRACT_VALIDATED"
                     if packet["source_kind"] == "TEST_ONLY"
                     else "AUTHENTIC_SOURCE_NOT_CONNECTED",
        "source_original_bytes_verified": False,
        "pit_verified": False,
        "strategy_rule_trigger_evaluation": "NOT_PERFORMED",
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "cost_model": "NOT_APPLIED",
        "multiple_testing": "ATTEMPT_CENSUS_ONLY",
        "holdout": "SEALED_UNOPENED",
        "execution_authority": "NONE",
    }
    result["artifact_sha256"] = _digest(result)
    return result
