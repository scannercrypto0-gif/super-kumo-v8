"""Frozen P2 Breakout BASE/SHADOW decisions for separately authenticated real cohorts.

Inputs are the *already retained* Work #223 bar index, independently attested
against its ZIP, member, index, handoff and manifest in the private Work runner.
This code does not fetch historical data, evaluate outcomes or execute trades.
Its immutable pre-outcome policy is anchored by the GitHub commit carrying it.
An independent reviewer MUST verify that anchor predates outcome observation.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from .aql_p2_core_producer import (
    BAR_MS, EMBARGO_MIN_MS, ContractError, FrozenTrialV1,
    HistoricalSourceV1, HistoricalBarV1, P2HistoricalOpportunityV1,
    _hash, _require, schedule_pair, validate_bars,
)

FEB_START, FEB_END = 1706745600000, 1709251200000
AUG_START, AUG_END = 1722470400000, 1725148800000
HOLDOUT_START, HOLDOUT_END = 1761955200000, 1764547200000
LOOKBACK = 20
VOL_LIMIT = Decimal("0.03")
HORIZONS = (4, 24, 72)
MANIFEST_SHA = "9b34e972e05002a7d6b11152e72164af825960b60e36c65ccf8049ce411eb4ff"
BAR_INDEX_SHA = "0988fda2d3fa04d3ec99b135e549aa08a684a2c9d77157811d6b882af757cc17"
HANDOFF_SHA = "4031aea0b421d3749441cf40a09699d8bb0b27cee9320b848b3d1fd1345101bc"
WORK_VERIFIED_SOURCE_RECEIPT_SHA = "c224025885b5186732fa21755c0f3fa7042f03c44d19f1b566be454a31518b44"
SOURCE_ARCHIVES = {
    "BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1": (
        FEB_START, FEB_END,
        "55066890cd3a76c97c05e94213311b17a4146d697f6abe8762b3edae8495b20e",
        "c34057c955be726ebcbc96a8c047c3dae6dee6db41a6bf89cc4ac3244cfe1527",
    ),
    "BINANCE-SPOT-BTCUSDT-15M-2024-08-DEV-v1": (
        AUG_START, AUG_END,
        "44e084e916a4c661b2177741d71438916388c0d34554f63cb147973aac13b094",
        "8ed69f76d2f61ee4c85387010f5c6e68a07525b26c5af18df824042fdc377d6c",
    ),
}


def frozen_prespec():
    """Complete intended policy, frozen *before* downstream outcome observation."""
    return {
        "schema": "aql.p2.breakout-policy.v1",
        "trial_id": "P2_BREAKOUT_20_VOL3_EXIT10_DEV_20261103_v1",
        "strategy_family": "BREAKOUT",
        "evidence_class": "RETROSPECTIVE_NON_PIT",
        "license_scope": "PERSONAL_NONCOMMERCIAL_NONPRODUCTION_RESEARCH_ONLY",
        "manifest_sha256": MANIFEST_SHA,
        "bar_index_sha256": BAR_INDEX_SHA,
        "original_handoff_sha256": HANDOFF_SHA,
        "source_pins": {
            k: {"start_ms": v[0], "end_exclusive_ms": v[1],
                "archive_sha256": v[2], "dataset_normalized_sha256": v[3]}
            for k, v in SOURCE_ARCHIVES.items()
        },
        "development": "FEB2024",
        "validation": "AUG2024_REUSED_PREVIOUSLY_EXPOSED_NOT_UNSEEN_OOS",
        "interval_ms": BAR_MS,
        "lookback": LOOKBACK,
        "indexing": (
            "zero-based: signal index i=20..N-2; cutoff=close_ms[i]+1; "
            "prior 20 indices i-20..i-1; breakout close[i]>max(prior.high); "
            "previous close=close[i-1]; next-open entry open[i+1]; "
            "ten-bar modeled exit=open[i+11]"
        ),
        "decision_grid": "exactly one pair per index i=20..N-2, even NO_SIGNAL/REJECTED/UNKNOWN",
        "direction": "NEW_P2_MODELED_RESEARCH_LONG_NOT_ORIGINAL_P0_SIGNAL",
        "base": "close-confirmed LONG breakout above highest high of 20 preceding 15m bars",
        "shadow": "same BASE signal; only difference is one volatility exclusion",
        "volatility": "(max(high[i-20:i])-min(low[i-20:i]))/close[i-1]",
        "shadow_exclude": "volatility > 0.03; equality allowed",
        "modeled_entry": "open[i+1], requires finalized same-cohort bar; NO_ACTUAL_FILL",
        "modeled_exit": "open[i+11], requires finalized same-cohort bar; NO_ACTUAL_FILL",
        "modeled_trade_missingness": (
            "trigger signal unchanged if exit unavailable; arm disposition UNKNOWN "
            "and direction null; separate signal_disposition TRIGGERED retained"
        ),
        "no_signal": "NO_SIGNAL for both arms when close confirmation fails",
        "rejected": "SHADOW REJECTED if BASE signal and prior volatility > 3 percent",
        "fee_per_side": "0.001",
        "slippage_per_side": "0.0005",
        "fee_round_trip_bps": "20",
        "slippage_round_trip_bps": "10",
        "cost_scope": "MODEL_ONLY_NOT_EXECUTION; no actual trade/fill/PnL",
        "horizons_hours": list(HORIZONS),
        "outcome_rule": "CUTOFF_REFERENCE_TO_4_24_72H_CLOSE_AND_EXCURSIONS_V1",
        "outcome_scope": (
            "Factory descriptive close/excursions relative to cutoff reference; "
            "NOT ten-bar entry/exit modeled trade return"
        ),
        "primary_hypothesis": (
            "SHADOW 3pct volatility exclusion reduces adverse directional excursion "
            "versus BASE on fixed scheduled cutoffs, preserving all rejected and "
            "unknown observations and reporting coverage; no tuning after results"
        ),
        "comparison_protocol": (
            "fixed pair denominator incl NO_SIGNAL, REJECTED, UNKNOWN; "
            "report per-cohort coverage and nulls; no claim of PIT/OOS/alpha"
        ),
        "missing_bars": "reject gaps/nonfinal/invalid OHLC; never cross cohorts",
        "horizon_missingness": (
            "16/96/288 subsequent bars only within same month; "
            "Factory CENSORED/UNKNOWN and null metrics for incomplete windows"
        ),
        "embargo_ms": EMBARGO_MIN_MS,
        "holdout_start_ms": HOLDOUT_START,
        "holdout_end_exclusive_ms": HOLDOUT_END,
        "holdout_status": "SEALED_UNOPENED",
        "time_registration": (
            "complete contract must be anchored on GitHub before outcomes; "
            "commit timestamps independently verified by Work; not self-attested"
        ),
    }


def seal_protocol():
    spec = frozen_prespec()
    hypothesis = {"claim": spec["primary_hypothesis"],
                  "denominator": spec["comparison_protocol"],
                  "outcome_rule": spec["outcome_rule"]}
    base = {
        "rule": spec["base"], "indexing": spec["indexing"],
        "entry": spec["modeled_entry"], "exit": spec["modeled_exit"],
        "missingness": spec["modeled_trade_missingness"],
        "fee": spec["fee_per_side"], "slippage": spec["slippage_per_side"],
        "outcome_rule": spec["outcome_rule"],
    }
    shadow = {**base, "rule": spec["shadow"],
              "filter": spec["shadow_exclude"], "volatility": spec["volatility"]}
    hashes = {
        "hypothesis_sha256": _hash(hypothesis),
        "base_definition_sha256": _hash(base),
        "shadow_definition_sha256": _hash(shadow),
        "preregistration_sha256": _hash(spec),
    }
    trial = FrozenTrialV1.seal(
        trial_id=spec["trial_id"], **hashes,
        train_end_exclusive_ms=AUG_END,
        holdout_start_ms=HOLDOUT_START,
        holdout_end_exclusive_ms=HOLDOUT_END,
        embargo_ms=EMBARGO_MIN_MS,
    )
    return spec, trial


def _work_canonical(row):
    """Exact Work #223 canonical JSONL hashing domain (including newline)."""
    return (json.dumps(row, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\\n").encode("utf-8")


def _work_sha(raw):
    return sha256(raw).hexdigest()


def _decimal(value):
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ContractError("INVALID_OHLC") from exc
    _require(x.is_finite() and x > 0, "INVALID_OHLC")
    return x


def _check_trial(trial):
    _, expected = seal_protocol()
    _require(isinstance(trial, FrozenTrialV1) and trial == expected,
             "UNFROZEN_OR_DRIFTED_PROTOCOL")


def _check_source(source, bars, rows, trial):
    """Checks exact Work pins; independent private-byte proof remains upstream."""
    _check_trial(trial)
    _require(isinstance(source, HistoricalSourceV1)
             and source.source_id in SOURCE_ARCHIVES, "UNDECLARED_COHORT")
    start, end, archive_sha, normalized_sha = SOURCE_ARCHIVES[source.source_id]
    _require((source.exchange, source.market, source.symbol, source.interval_ms,
              source.evidence_class, source.correction_generation) ==
             ("BINANCE", "SPOT", "BTCUSDT", BAR_MS, "RETROSPECTIVE_NON_PIT",
              "UNKNOWN_NOT_ATTESTED"), "UNSUPPORTED_SOURCE_SCOPE")
    _require(source.source_package_sha256 == archive_sha
             and source.manifest_sha256 == MANIFEST_SHA
             and source.normalized_sha256 == normalized_sha,
             "SOURCE_PIN_DRIFT")
    valid = validate_bars(source, bars)
    rows = tuple(rows)
    _require(len(rows) == len(valid) == (end - start) // BAR_MS,
             "COHORT_COVERAGE_MISMATCH")
    _require(valid[0].open_ms == start and valid[-1].close_ms + 1 == end,
             "COHORT_BOUNDARY_DRIFT")
    prices = []
    indexed_bytes = []
    for b, row in zip(valid, rows):
        _require(isinstance(row, dict)
                 and row.get("availability_mode") == "RETROSPECTIVE_NON_PIT"
                 and row.get("historical_known_at_ms") is None
                 and row.get("historical_receipt_ms") is None
                 and row.get("historical_publication_ms") is None
                 and row.get("finality") == "ARCHIVED_CLOSED_INTERVAL"
                 and row.get("is_final") is True,
                 "HISTORICAL_SOURCE_FINALITY_OR_PIT_DRIFT")
        _require(row.get("dataset_id") == source.source_id
                 and row.get("open_ms") == b.open_ms
                 and row.get("close_ms") == b.close_ms
                 and row.get("bar_sha256") == b.content_sha256,
                 "UNVERIFIED_BAR_MAPPING")
        unsealed_row = {k: v for k, v in row.items() if k != "bar_sha256"}
        _require(_work_sha(_work_canonical(unsealed_row)) == b.content_sha256,
                 "BAR_CONTENT_HASH_MISMATCH")
        indexed_bytes.append(_work_canonical(row))
        op, high, low, close = (_decimal(row.get(k))
                                for k in ("open", "high", "low", "close"))
        _require(low <= op <= high and low <= close <= high,
                 "INVALID_OHLC_RANGE")
        prices.append((op, high, low, close))
    _require(_work_sha(b"".join(indexed_bytes)) == normalized_sha,
             "FULL_COHORT_INDEX_SHA_MISMATCH")
    return valid, prices


def _analyze_cohort(source, bars, rows, trial):
    valid, prices = _check_source(source, bars, rows, trial)
    opportunities, evidence_rows = [], []
    for i in range(LOOKBACK, len(valid) - 1):
        cutoff = valid[i].close_ms + 1
        prefix = valid[:i+1]
        _require(all(b.available_at_ms is None or b.available_at_ms <= cutoff
                     for b in prefix), "KNOWN_AFTER_CUTOFF")
        previous = prices[i - LOOKBACK:i]
        highest = max(p[1] for p in previous)
        lowest = min(p[2] for p in previous)
        vol = (highest - lowest) / prices[i - 1][3]
        breakout = prices[i][3] > highest
        exit_index = i + 11
        trade_availability = ("COMPLETE" if exit_index < len(valid)
                              else "UNKNOWN")
        # Signal truth depends ONLY on previous bars and signal close[i].
        # This separate eligibility is NOT used to change breakout truth.
        signal_disposition = "TRIGGERED" if breakout else "NO_SIGNAL"
        identity = _hash({"trial": trial.protocol_sha256,
                          "source": source.source_id, "cutoff": cutoff})
        prefix_sha = _hash({"source": source.source_package_sha256,
                            "bar_sha256": [b.content_sha256 for b in prefix]})
        signal_evidence = _hash({
            "schema": "aql.p2.breakout.signal-evidence.v1",
            "source_id": source.source_id,
            "source_package_sha256": source.source_package_sha256,
            "normalized_sha256": source.normalized_sha256,
            "feature_prefix_sha256": prefix_sha,
            "signal_bar_sha256": valid[i].content_sha256,
            "cutoff": cutoff,
            "highest_prior_high": str(highest),
            "lowest_prior_low": str(lowest),
            "previous_close": str(prices[i - 1][3]),
            "signal_close": str(prices[i][3]),
            "volatility": str(vol),
            "signal_disposition": signal_disposition,
        })
        # Common opportunity stays a signal/denominator record; its direction
        # is modeled provenance, never an invented historical original signal.
        opportunity = P2HistoricalOpportunityV1(
            trial_id=trial.trial_id,
            opportunity_id=identity, producer_event_id="P2_RESEARCH:" + identity,
            source_id=source.source_id, source_package_sha256=source.source_package_sha256,
            feature_prefix_sha256=prefix_sha,
            policy_sha256=trial.base_definition_sha256,
            decision_cutoff_ms=cutoff, decision_ms=cutoff,
            disposition=signal_disposition,
            direction="LONG" if breakout else None,
            direction_evidence_ref=("P2_MODELED_BREAKOUT:" + signal_evidence
                                    if breakout else None),
            regime=None, regime_source_sha256=None,
            reason_code=("BREAKOUT_SHADOW_EXCLUDED_VOL_GT_3PCT"
                         if breakout and vol > VOL_LIMIT
                         else "BREAKOUT_BOTH_ARMS" if breakout else "NO_BREAKOUT"),
        )
        opportunities.append(opportunity)
        evidence_rows.append({
            "identity": identity,
            "signal_evidence_sha256": signal_evidence,
            "signal_disposition": signal_disposition,
            "shadow_excluded": breakout and vol > VOL_LIMIT,
            "modeled_trade_availability": trade_availability,
            "modeled_entry_open_ms": valid[i + 1].open_ms,
            "modeled_exit_open_ms": (valid[exit_index].open_ms
                                     if exit_index < len(valid) else None),
            "modeled_exit_missingness_reason": (
                None if exit_index < len(valid) else "END_OF_COHORT_NO_I_PLUS_11"),
            "cutoff": cutoff,
            "feature_prefix_sha256": prefix_sha,
            "signal_bar_sha256": valid[i].content_sha256,
        })
    return tuple(opportunities), tuple(evidence_rows)


def produce_cohort(source: HistoricalSourceV1, bars, rows, trial: FrozenTrialV1):
    """Genuine opportunity schema, subject to independently verified Work input."""
    return _analyze_cohort(source, bars, rows, trial)[0]


def _factory_seal(obj):
    obj["artifact_sha256"] = _hash(obj)
    return obj


def build_factory_prereg(source: HistoricalSourceV1, trial: FrozenTrialV1):
    """Complete source-specific prereg and cost contract; no time-proof forgery."""
    _check_trial(trial)
    _require(source.source_id in SOURCE_ARCHIVES, "UNDECLARED_COHORT")
    _, _, archive_sha, normalized_sha = SOURCE_ARCHIVES[source.source_id]
    _require(source.source_package_sha256 == archive_sha
             and source.normalized_sha256 == normalized_sha
             and source.manifest_sha256 == MANIFEST_SHA, "SOURCE_PIN_DRIFT")
    spec = frozen_prespec()
    prereg = _factory_seal({
        "schema": "aql.p2.breakout.preregistration.v1",
        "test_only": False,
        "trial_id": trial.trial_id,
        "protocol_sha256": trial.protocol_sha256,
        "hypothesis_sha256": trial.hypothesis_sha256,
        "preregistration_sha256": trial.preregistration_sha256,
        "base_definition_sha256": trial.base_definition_sha256,
        "shadow_definition_sha256": trial.shadow_definition_sha256,
        "strategy_family": "BREAKOUT",
        "source_id": source.source_id,
        "source_package_sha256": archive_sha,
        "source_manifest_sha256": MANIFEST_SHA,
        "source_index_sha256": BAR_INDEX_SHA,
        "source_normalized_sha256": normalized_sha,
        "full_protocol": spec,
        "horizons_hours": list(HORIZONS),
        "outcome_rule": spec["outcome_rule"],
        "modeled_trade_entry_rule": spec["modeled_entry"],
        "modeled_trade_exit_rule": spec["modeled_exit"],
        "modeled_trade_missingness_rule": spec["modeled_trade_missingness"],
        "cohort_role": ("DEVELOPMENT" if source.source_id.endswith("02-DEV-v1")
                        else "VALIDATION_PREVIOUSLY_EXPOSED"),
        "embargo_ms": trial.embargo_ms,
        "holdout_status": "SEALED_UNOPENED",
        "registration_proof_status": "REQUIRES_INDEPENDENT_GITHUB_PRE_OUTCOME_ATTESTATION",
        "evidence_class": "RETROSPECTIVE_NON_PIT",
        "execution_status": "NOT_OBSERVED",
    })
    cost = _factory_seal({
        "schema": "aql.p2.factory.modeled-costs.v1",
        "test_only": False,
        "model_kind": "MODEL_ONLY_NOT_EXECUTION",
        "trial_id": trial.trial_id,
        "preregistration_sha256": prereg["artifact_sha256"],
        "round_trip_fee_bps": "20",
        "round_trip_slippage_bps": "10",
        "no_actual_fills": True,
    })
    return prereg, cost


def build_factory_handoff(source, bars, authenticated_rows, trial,
                          *, source_authentication_receipt_sha256=None):
    """Construct all Core-owned inputs; caller separately supplies market windows.

    Fail closed if the Work-private independent byte attestation is not supplied.
    This method never asserts that a local row hash authenticates a vendor archive.
    Registration time anchor MUST ALSO be checked by Work before Factory invocation.
    """
    from .aql_p2_core_producer import _sha
    _require(_sha(source_authentication_receipt_sha256),
             "MISSING_INDEPENDENT_SOURCE_ATTESTATION")
    _require(source_authentication_receipt_sha256 == WORK_VERIFIED_SOURCE_RECEIPT_SHA,
             "UNRECOGNIZED_WORK_SOURCE_ATTESTATION")
    # Construct frozen consumer envelope BEFORE reading any price observations.
    # An external GitHub timestamp and artifact hash check is still mandatory.
    prereg, cost = build_factory_prereg(source, trial)
    opportunities, evidences = _analyze_cohort(
        source, bars, authenticated_rows, trial)
    schedule = schedule_pair(trial, source, bars, opportunities, test_only=False)
    decisions = []
    for pair, ev in zip(schedule["pairs"], evidences):
        _require(pair["opportunity"]["opportunity_id"] == ev["identity"],
                 "PAIR_OPPORTUNITY_ORDER_MISMATCH")
        for arm in ("BASE", "SHADOW"):
            is_rejected = arm == "SHADOW" and ev["shadow_excluded"]
            triggered = ev["signal_disposition"] == "TRIGGERED"
            # Keep source-only signal truth distinct from post-cutoff trade
            # eligibility. No modeled trade if required exit open unavailable.
            status = ("NO_SIGNAL" if not triggered else
                      "REJECTED" if is_rejected else
                      "UNKNOWN" if ev["modeled_trade_availability"] != "COMPLETE" else
                      "TRIGGERED")
            policy = (trial.base_definition_sha256 if arm == "BASE"
                      else trial.shadow_definition_sha256)
            decision_evidence = _hash({
                "schema": "aql.p2.breakout.arm-decision-evidence.v1",
                "pair_id": pair["pair_id"], "arm": arm,
                "policy_sha256": policy,
                "signal_evidence_sha256": ev["signal_evidence_sha256"],
                "feature_prefix_sha256": ev["feature_prefix_sha256"],
                "source_package_sha256": source.source_package_sha256,
                "source_authentication_receipt_sha256":
                    source_authentication_receipt_sha256,
                "decision_cutoff_ms": ev["cutoff"],
                "signal_disposition": ev["signal_disposition"],
                "shadow_volatility_excluded": is_rejected,
            })
            decision = {
                "pair_id": pair["pair_id"], "arm": arm,
                "policy_sha256": policy,
                "decision_cutoff_ms": ev["cutoff"],
                "decision_evidence_sha256": decision_evidence,
                "direction": "LONG" if status == "TRIGGERED" else None,
                "disposition": status,
                "signal_disposition": ev["signal_disposition"],
                "modeled_trade_availability":
                    ev["modeled_trade_availability"] if triggered else "NOT_APPLICABLE",
                "modeled_entry_open_ms":
                    ev["modeled_entry_open_ms"] if triggered else None,
                "modeled_exit_open_ms":
                    ev["modeled_exit_open_ms"] if triggered else None,
                "modeled_exit_missingness_reason":
                    ev["modeled_exit_missingness_reason"] if triggered else None,
                "feature_prefix_sha256": ev["feature_prefix_sha256"],
                "source_package_sha256": source.source_package_sha256,
                "evidence_class": "RETROSPECTIVE_NON_PIT",
                "execution_status": "NOT_OBSERVED",
            }
            decision["decision_sha256"] = _hash(decision)
            decisions.append(decision)
    _require(len(decisions) == 2 * schedule["scheduled_total"],
             "INCOMPLETE_ARM_DENOMINATOR")
    return {
        "schedule": schedule, "preregistration": prereg,
        "cost_model": cost, "arm_decisions": decisions,
        "source_authentication_receipt_sha256":
            source_authentication_receipt_sha256,
        "registration_proof_status":
            "REQUIRES_INDEPENDENT_GITHUB_PRE_OUTCOME_ATTESTATION",
        "windows": None,
        "factory_invoked": False,
        "outcome_evaluation": "NOT_PERFORMED",
        "holdout_status": "SEALED_UNOPENED",
    }


def build_development_schedule(source, bars, authenticated_rows, trial):
    """Legacy Core scheduling entry; does not imply real Factory readiness."""
    opportunities = produce_cohort(source, bars, authenticated_rows, trial)
    return schedule_pair(trial, source, bars, opportunities, test_only=False)
