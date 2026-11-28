"""Offline scientific readiness reporting over the existing Factory and Lab outputs."""
from decimal import Decimal, localcontext

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
        # The native Lab consumes the complete pre-holdout development population.
        "train_end_exclusive_ms": times["validation_end_ms"],
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
        # Native Lab indexes descriptive slots; it does not recompute timing.
        slot = row["open_ms"]
        pairs.append({"pair_id": pid, "opportunity": dict(
            source, trial_id=pins["trial_id"], opportunity_id=oid,
            decision_ms=slot, decision_cutoff_ms=slot,
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
        scientific_verdict="REAL_PIT_OOS_BLOCKED")
