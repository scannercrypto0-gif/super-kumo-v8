"""Offline scientific readiness reporting over the existing Factory and Lab outputs."""
from decimal import Decimal, localcontext
from random import Random

from research_wp_r0.aql_p2_factory_lab import HORIZONS, build_lab, digest


METRIC_POLICY = {
    "status": "PROPOSED_FOR_OWNER_FREEZE",
    "net_return": "Factory arithmetic net return per attempted entry, including zero for nonfills",
    "drawdown": "Factory trade-close drawdown, descriptive only",
    "sharpe": "Unannualized per-observation mean over sample deviation on a frozen regular equity grid",
    "sample_size": "Plan from minimum worthwhile paired effect, dependence-adjusted pilot variance and target power",
    "confidence_interval": "Predeclare paired moving-block bootstrap on chronological slots; freeze block length from development only",
    "multiplicity": "Bonferroni over every reserved hypothesis; no recycling unused attempts",
    "baseline": "Freeze BASE definition and retain identical opportunity and source windows for SHADOW",
    "regimes": "Freeze causal regime definitions and minimum coverage before evaluation",
    "stop": "Fixed horizon and budget; no holdout peeking or optional stopping",
}


def paired_lab(protocol, scanner):
    """Exercise the native descriptive BASE/SHADOW contract on the same census."""
    times = protocol["times"]
    pins = {
        "trial_id": "mock-prospective-299",
        "protocol_sha256": scanner["protocol_sha256"],
        "base_definition_sha256": protocol["baseline_sha256"],
        "shadow_definition_sha256": scanner["strategy_sha256"],
        "embargo_ms": times["embargo_ms"],
        # Allow the final validation bar acknowledgement before the embargo.
        "train_end_exclusive_ms": times["validation_end_ms"] + times["step_ms"],
        "holdout_start_ms": times["oos_start_ms"],
        "holdout_end_exclusive_ms": times["oos_end_ms"],
    }
    pairs = []
    observations = []
    source = {"source_id": "MOCK:299", "source_package_sha256": scanner["source_sha256"]}
    for row in scanner["decisions"]:
        oid = digest(row)
        pid = digest(dict(protocol_sha256=pins["protocol_sha256"], trial_id=pins["trial_id"],
                          opportunity_id=oid))
        decision = row["ack"]["commit_return_observed_at_ms"]
        pairs.append({"pair_id": pid, "opportunity": dict(
            source, trial_id=pins["trial_id"], opportunity_id=oid,
            decision_ms=decision, decision_cutoff_ms=decision,
            disposition="TRIGGERED" if row["state"] == "ENTRY" else row["state"],
            evidence_class="RETROSPECTIVE_NON_PIT"),
            "arms": [
                {"arm": "BASE", "definition_sha256": pins["base_definition_sha256"]},
                {"arm": "SHADOW", "definition_sha256": pins["shadow_definition_sha256"]},
            ]})
        for horizon in HORIZONS:
            for arm in ("BASE", "SHADOW"):
                observations.append(dict(
                    pair_id=pid, arm=arm, horizon_hours=horizon, availability="UNKNOWN",
                    availability_reason="NO_MATURED_HORIZON_DATA_ADMITTED_BY_FIXTURE",
                    market_metrics=None, directional_metrics=None, execution_status="NOT_OBSERVED"))
    schedule = dict(
        schema="aql.p2.core.paired-schedule.v1", test_only=True, evidence_class="RETROSPECTIVE_NON_PIT",
        holdout_status="SEALED_UNOPENED", outcome_evaluation="NOT_PERFORMED",
        execution_status="NOT_OBSERVED", protocol=pins, source=source,
        scheduled_total=len(pairs), pairs=pairs)
    schedule["artifact_sha256"] = digest(schedule)
    return build_lab(schedule, observations)


def classify_interval(lower, upper, minimum_effect, *, qualified_sample):
    """Classify a predeclared adjusted interval; missing evidence is inconclusive."""
    if not qualified_sample or lower is None or upper is None:
        return "INCONCLUSIVE"
    lower, upper, minimum_effect = map(Decimal, (lower, upper, minimum_effect))
    if not all(x.is_finite() for x in (lower, upper, minimum_effect)) or lower > upper:
        raise ValueError("INVALID_CONFIDENCE_INTERVAL")
    if lower > minimum_effect:
        return "PASS"
    if upper < minimum_effect:
        return "FAIL"
    return "INCONCLUSIVE"


def paired_uncertainty(pairs, *, min_slots, block_slots, resamples, seed, alpha, minimum_effect):
    """Evaluate already aligned regular-grid modeled returns using paired moving blocks."""
    alpha = Decimal(alpha)
    if (not alpha.is_finite() or not 0 < alpha < 1
            or not 2 <= block_slots <= min_slots
            or not 1 <= resamples <= 100_000
            or alpha * resamples / 2 < 1):
        raise ValueError("INVALID_FROZEN_UNCERTAINTY_POLICY")
    n = len(pairs)
    missing = sum(base is None or shadow is None for base, shadow in pairs)
    result = dict(slots=n, unknown_slots=missing, confidence_interval=None, paired_differential_sharpe=None,
                  verdict="INCONCLUSIVE")
    if missing or n < min_slots or n // block_slots < 2:
        return result
    with localcontext() as ctx:
        ctx.prec = 40
        deltas = [Decimal(shadow) - Decimal(base) for base, shadow in pairs]
        if not all(value.is_finite() for value in deltas):
            raise ValueError("NONFINITE_PAIRED_RETURN")
        mean = sum(deltas) / n
        variance = sum((value - mean) ** 2 for value in deltas) / (n - 1)
        prefix = [Decimal(0)]
        for value in deltas:
            prefix.append(prefix[-1] + value)
        blocks, tail = divmod(n, block_slots)
        rng = Random(seed)
        means = []
        for _ in range(resamples):
            starts = [rng.randrange(n - block_slots + 1) for _ in range(blocks)]
            total = sum(prefix[start + block_slots] - prefix[start] for start in starts)
            if tail:
                start = rng.randrange(n - block_slots + 1)
                total += prefix[start + tail] - prefix[start]
            means.append(total / n)
        means.sort()
        rank = int(alpha * resamples / 2)
        lower, upper = means[rank - 1], means[-rank]
        return dict(result, confidence_interval=[str(lower), str(upper)],
                    paired_differential_sharpe=str(mean / variance.sqrt()) if variance else None,
                    verdict=classify_interval(lower, upper, minimum_effect, qualified_sample=True))


def statistical_control():
    """Use identical synthetic arms to exercise the equal-arm null without market outcomes."""
    values = [("0.001", "0.001"), ("-0.002", "-0.002")] * 6
    result = paired_uncertainty(values, min_slots=12, block_slots=3, resamples=200,
                                seed=299, alpha="0.05", minimum_effect="0")
    return dict(result, scope="GENERATED_EQUAL_ARM_NEGATIVE_CONTROL",
                block_slots=3, resamples=200, seed=299, alpha="0.05")


def assess(protocol, scanner, report):
    paired = paired_lab(protocol, scanner)
    variants = {}
    with localcontext() as ctx:
        ctx.prec = 40
        for name, cell in report["comparisons"].items():
            n = cell["attempted_entry_count"]
            net = cell["net_return_sum"]
            variants[name] = dict(
                attempts=n, modeled=cell["modeled_trade_count"], unknown=cell["unknown_count"],
                nonfills=cell["nonfill_count"], partial=cell["partial_entry_count"],
                gross_return_sum=cell["gross_return_sum"],
                net_return_per_attempt=str(Decimal(net) / n) if n and net is not None else None,
                maximum_drawdown_trade_close_only=cell["max_drawdown_trade_close_only"],
                sharpe=None, confidence_interval=None,
                reason="UNRESOLVED_OUTCOMES" if cell["unknown_count"] else "FIXTURE_NO_QUALIFIED_SAMPLE",
                verdict=classify_interval(None, None, None, qualified_sample=False))
    return dict(
        scope="SYNTHETIC_ENGINEERING_ONLY", metric_policy=protocol["metric_policy"],
        native_report_sha256=report["sha256"], paired_lab=paired, variants=variants,
        alpha=protocol["alpha"], reserved_hypotheses=protocol["hypothesis_budget"],
        adjusted_alpha=protocol["bonferroni_alpha"], venue_coverage=report["coverage"],
        statistical_negative_control=statistical_control(),
        scientific_verdict="REAL_PIT_OOS_BLOCKED")
