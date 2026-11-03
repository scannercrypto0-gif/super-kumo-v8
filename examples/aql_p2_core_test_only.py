"""Offline TEST_ONLY example. No downloaded data, evaluated outcomes or live orders."""
import json
from research_wp_r0.aql_p2_core_producer import (
    BAR_MS, EMBARGO_MIN_MS, FrozenTrialV1, HistoricalBarV1,
    HistoricalSourceV1, P2HistoricalOpportunityV1, schedule_pair,
)

def main():
    h, j, k, l = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    start = 1704067200000
    source = HistoricalSourceV1("TEST_ONLY_SOURCE", "BINANCE", "SPOT",
                                "BTCUSDT", h, j, k, "TEST_ONLY_CORRECTION")
    bars = [HistoricalBarV1(start + i * BAR_MS,
                            start + (i + 1) * BAR_MS - 1, h) for i in range(5)]
    cutoff = start + 2 * BAR_MS
    trial = FrozenTrialV1.seal(
        trial_id="TEST_ONLY_TRIAL", hypothesis_sha256=h,
        base_definition_sha256=j, shadow_definition_sha256=k,
        preregistration_sha256=l,
        train_end_exclusive_ms=start + 6 * BAR_MS,
        holdout_start_ms=start + 6 * BAR_MS + EMBARGO_MIN_MS,
        holdout_end_exclusive_ms=start + 6 * BAR_MS + EMBARGO_MIN_MS + BAR_MS)
    opportunity = P2HistoricalOpportunityV1(
        trial_id=trial.trial_id, opportunity_id="TEST_ONLY_OPP",
        producer_event_id="TEST_ONLY_EVENT", source_id=source.source_id,
        source_package_sha256=source.source_package_sha256,
        feature_prefix_sha256=h, policy_sha256=j,
        decision_cutoff_ms=cutoff, decision_ms=cutoff + 2000,
        disposition="NO_SIGNAL", direction=None, direction_evidence_ref=None,
        regime=None, regime_source_sha256=None)
    result = schedule_pair(trial, source, bars, [opportunity])
    result["test_only"] = True
    # Demo display flag is outside the cryptographically sealed source output.
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
