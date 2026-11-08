"""R4/H2 Option B: separately authenticated OWNER personal-research assertion.

This is a deliberately INERT research authority *classification*, NOT an
alternative original-source runner or a replacement for independent licensing.
Existing strict/official Binance one-shot source/rights gates stay unchanged.
No E: source access, publisher fetch, key generation or HMAC signing here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
from pathlib import Path
import re

SCHEMA = "aql.integration.h2.owner-personal-research-authority.v1"
AUTHORITY = "OWNER_PERSONAL_NONCOMMERCIAL_RESEARCH_ASSERTED"
EXTERNAL_AUTHORITY = "INDEPENDENTLY_REVIEWED_LICENSE"
COST_SCHEMA = "aql.integration.h2.owner-explicit-spot-cost-approval.v1"
STEP = 900000
HEX = re.compile(r"[0-9a-f]{64}\Z")
MONTH = re.compile(r"20[0-9]{2}-(0[1-9]|1[0-2])\Z")
SCOPE_FIELDS = frozenset((
    "dataset_id", "version", "month", "start_ms", "end_exclusive_ms",
    "decision_cutoff_ms", "source_bytes_sha256",
    "manifest_integrity_sha256", "core245_native_receipt_sha256",
    "core253_query_sha256", "strategy_id",
    "strategy_definition_sha256", "strategy_config_sha256",
    "evaluator_code_sha256", "cost_policy_sha256",
    "experiment_id", "owner_authorization_ref", "one_use_nonce",
    "research_class", "historical_pit", "publisher_pit_attested",
    "explicit_readonly_no_export", "source_output_separate", "single_use",
))
COST_KEYS = frozenset((
    "fee_entry_bps", "fee_exit_bps", "spread_entry_bps",
    "spread_exit_bps", "slippage_entry_bps", "slippage_exit_bps",
    "funding_bps_per_bar",
))
# These domains MUST be independent: a scope-only approval cannot approve fees.
SCOPE_DOMAIN = b"ATLAS-H2-OWNER-PERSONAL-SCOPE-V1\x00"
COST_DOMAIN = b"ATLAS-H2-OWNER-EXPLICIT-COST-V1\x00"


class AuthorityBlocked(ValueError):
    """Fail-closed validation: this exception must never grant source access."""


def _need(ok, reason):
    if not ok:
        raise AuthorityBlocked(reason)


def _sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, UnicodeError, ValueError):
        raise AuthorityBlocked("OWNER_AUTHORITY_NONCANONICAL_DOCUMENT") from None


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _trusted_key(key_path):
    """Read an ALREADY trusted out-of-band verifier key; never create one."""
    _need(key_path is not None, "OWNER_TRUST_ROOT_NOT_PROVISIONED")
    path = Path(key_path)
    _need(not path.is_symlink() and path.is_file()
          and 32 <= path.stat().st_size <= 4096,
          "OWNER_TRUST_ROOT_INVALID")
    return path.read_bytes()


def _check_mac(actual, key, domain, body, reason):
    _need(_sha(actual), reason)
    expect = hmac.new(key, domain + _canonical(body),
                      hashlib.sha256).hexdigest()
    _need(hmac.compare_digest(actual, expect), reason)


def _check_scope(scope):
    _need(type(scope) is dict and set(scope) == SCOPE_FIELDS,
          "OWNER_SCOPE_FIELDS")
    _need(scope["research_class"] == "RETROSPECTIVE_NON_PIT"
          and scope["historical_pit"] == "NOT_ATTESTED"
          and scope["publisher_pit_attested"] is False
          and scope["explicit_readonly_no_export"] is True
          and scope["source_output_separate"] is True
          and scope["single_use"] is True,
          "OWNER_SCOPE_PIT_EXPORT_OR_ONE_USE")
    month = scope["month"]
    start = scope["start_ms"]
    end = scope["end_exclusive_ms"]
    cutoff = scope["decision_cutoff_ms"]
    _need(type(month) is str and MONTH.fullmatch(month) is not None
          and all(type(x) is int for x in (start, end, cutoff))
          and 0 <= start < end == cutoff
          and start % STEP == 0 and end % STEP == 0
          and 0 < (end-start)//STEP <= 4096,
          "OWNER_SCOPE_MONTH_CUTOFF")
    try:
        first = datetime.fromtimestamp(start / 1000, timezone.utc)
        final = datetime.fromtimestamp((end-1) / 1000, timezone.utc)
        following = (datetime(first.year + 1, 1, 1, tzinfo=timezone.utc)
                     if first.month == 12 else
                     datetime(first.year, first.month + 1, 1,
                              tzinfo=timezone.utc))
    except (OverflowError, ValueError, OSError):
        raise AuthorityBlocked("OWNER_SCOPE_MONTH_CUTOFF") from None
    _need(first.strftime("%Y-%m") == month
          and final.strftime("%Y-%m") == month
          and (first.day, first.hour, first.minute, first.second) == (1,0,0,0)
          and start == int(first.timestamp()*1000)
          and end == int(following.timestamp()*1000)
          and (end-start)//STEP == 2976 and month == "2024-03",
          "OWNER_SCOPE_NOT_SINGLE_MARCH_COMPLETE_MONTH")
    _need(type(scope["one_use_nonce"]) is str
          and re.fullmatch(r"[0-9a-f]{32}", scope["one_use_nonce"]) is not None,
          "OWNER_SCOPE_UNIQUE_NONCE_REQUIRED")
    _need(type(scope["dataset_id"]) is str
          and scope["dataset_id"].startswith("BINANCE-SPOT-BTCUSDT-15M-")
          and type(scope["version"]) is int and scope["version"] > 0
          and scope["strategy_id"] == "h_manual_distinct_test"
          and all(type(scope[k]) is str and scope[k] and len(scope[k]) <= 160
                  for k in ("experiment_id", "owner_authorization_ref"))
          and all(_sha(scope[k]) for k in (
              "source_bytes_sha256", "manifest_integrity_sha256",
              "core245_native_receipt_sha256", "core253_query_sha256",
              "strategy_definition_sha256", "strategy_config_sha256",
              "evaluator_code_sha256", "cost_policy_sha256"))
          and scope["core245_native_receipt_sha256"] !=
              scope["core253_query_sha256"],
          "OWNER_SCOPE_SOURCE_OR_STRATEGY_IDENTITY")


def _check_cost(policy, scope):
    _need(type(policy) is dict
          and set(policy) == {"schema", "costs", "market", "direction",
                              "research_class", "authorization_class",
                              "single_use_experiment_id"},
          "OWNER_COST_FIELDS")
    _need(policy["schema"] == COST_SCHEMA
          and policy["market"] == "SPOT"
          and policy["direction"] == "LONG"
          and policy["research_class"] == "RETROSPECTIVE_NON_PIT"
          and policy["authorization_class"] == "OWNER_EXPLICIT_COST_ONLY"
          and policy["single_use_experiment_id"] == scope["experiment_id"]
          and type(policy["costs"]) is dict
          and set(policy["costs"]) == COST_KEYS
          and _digest(policy) == scope["cost_policy_sha256"],
          "OWNER_COST_POLICY_BINDING")
    try:
        costs = {}
        for field in COST_KEYS:
            raw = policy["costs"][field]
            _need(type(raw) is str and raw.strip() == raw
                  and len(raw) <= 32, "OWNER_COST_DECIMAL")
            value = Decimal(raw)
            _need(value.is_finite() and value >= 0, "OWNER_COST_DECIMAL")
            costs[field] = value
    except (InvalidOperation, ValueError):
        raise AuthorityBlocked("OWNER_COST_DECIMAL") from None
    _need(all(costs[k] > 0 for k in COST_KEYS
              if k != "funding_bps_per_bar")
          and costs["funding_bps_per_bar"] == 0,
          "OWNER_COST_NONZERO_SPOT_REQUIRED")


def inspect_owner_assertion(packet, *, trusted_owner_verifier_key):
    """Authenticate two separate owner MACs, always return INERT/BLOCKED.

    It does NOT attest to third-party rights, genuine source/custody,
    Core245/Core253 actual queries, costs' external market realism,
    filesystem read-only guarantees, PIT, or original execution authority.
    In particular, no code here calls the original one-shot operator.
    """
    _need(type(packet) is dict and set(packet) == {
        "schema", "authority_class", "scope", "cost_policy",
        "owner_scope_mac", "owner_cost_mac",
        "independent_license_review_status",
    }, "OWNER_AUTHORITY_PACKET_FIELDS")
    _need(packet["schema"] == SCHEMA
          and packet["authority_class"] == AUTHORITY
          and packet["independent_license_review_status"] ==
              "NOT_ATTESTED",
          "OWNER_ASSERTION_NOT_INDEPENDENT_LICENSE")
    scope = packet["scope"]
    policy = packet["cost_policy"]
    _check_scope(scope)
    _check_cost(policy, scope)
    key = _trusted_key(trusted_owner_verifier_key)
    _check_mac(packet["owner_scope_mac"], key, SCOPE_DOMAIN, scope,
               "OWNER_SCOPE_MAC_INVALID")
    _check_mac(packet["owner_cost_mac"], key, COST_DOMAIN, policy,
               "OWNER_SEPARATE_COST_MAC_INVALID")
    return {
        "schema": "aql.integration.h2.owner-authority-assessment.v1",
        "authority_class": AUTHORITY,
        "status": "OWNER_SCOPE_AND_COST_MAC_VERIFIED_ONLY",
        "owner_scope_verified": True,
        "owner_separate_cost_verified": True,
        "independent_license_review": "NOT_ATTESTED",
        "actual_source_receipts_verified": False,
        "publisher_pit": "NOT_ATTESTED",
        "historical_pit": "NOT_ATTESTED",
        "original_source_io_performed": False,
        "original_h2_execution_permitted": False,
        "terminal_gate": "BLOCKED_INDEPENDENT_RIGHTS_AND_PRIVATE_SOURCE_RECEIPTS",
        "scope_sha256": _digest(scope),
        "cost_policy_sha256": _digest(policy),
    }
