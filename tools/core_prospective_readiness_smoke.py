"""One-command, network-free provider mock; fixed clocks/UUID are fixture-only."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import UUID

from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from research_wp_r0.aql_archive_custody_bridge_v1 import canonical, digest
from research_wp_r0.aql_core_prospective_readiness_v1 import (
    DAY_MS, ReadinessError, admit_sample, seal_readiness,
)
from research_wp_r0.frozen_research_plan import commit_research_plan


def fixture(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with patch("aql.journal.durable_journal.uuid.uuid4", return_value=UUID(int=1)):
        journal = DurableJournal(str(root / "journal.sqlite"))
    config = dict(
        journal=journal,
        source=dict(provider="MOCK_COINBASE_EXCHANGE", source_version="fixture-v1",
                    symbol="BTC-USD", market="SPOT", interval="15m", source_label="MOCK:COINBASE",
                    rights_reference="fixture-only-no-real-rights", rights_sha256=digest("mock-rights"),
                    observed_at_ms=2000, available_at_ms=1000, committed_at_ms=3000,
                    evidence_class="SYNTHETIC_PROVIDER_MOCK"),
        times=dict(freeze_at_ms=4000, first_eligible_open_ms=900_000,
                   train_end_ms=2_700_000, validation_end_ms=4_500_000,
                   oos_start_ms=4_500_000 + 3 * DAY_MS,
                   oos_end_ms=6_300_000 + 3 * DAY_MS, step_ms=900_000, embargo_ms=3 * DAY_MS),
        bindings={k: digest(k) for k in ("evaluator_sha256", "search_space_sha256",
                                       "all_attempt_inventory_sha256", "risk_exit_sha256")},
        witnessed_at_ms=5000)
    plan, plan_sha = commit_research_plan(
        "mock-prospective-family", [("candidate-1", digest("candidate"))],
        protocol_digest=digest(config["bindings"]), dataset_digest=digest(config["source"]),
        split_digest=digest(config["times"]), metrics=["net_r"],
        selection_rule={"rule": "predeclared-no-post-oos-tuning"},
        cost_model={"model": "mock-taker-only", "fee_bps": 10},
        baseline_digest=digest("independent-null-baseline"))
    config.update(plan_raw=plan, plan_sha256=plan_sha)
    return config


def mock_bar(open_ms=900_000, **updates):
    values = dict(symbol="BTC-USD", interval="15m", bar_open=open_ms,
                  bar_close=open_ms + 899_999, open=100.0, high=102.0,
                  low=99.0, close=101.0, volume=1.0, is_final=True,
                  source="MOCK:COINBASE", ingested_at=open_ms + 900_002)
    values.update(updates)
    return MarketBar(**values).with_checksum()


def commit_mock(journal, bar):
    with patch("time.time", return_value=(bar.ingested_at + 1) / 1000):
        return journal.commit(bar)


def sample_args(config, freeze, bar):
    return dict(expected_freeze_sha256=freeze, plan_raw=config["plan_raw"],
                journal=config["journal"], stable_key=bar.stable_key(),
                observed_at_ms=bar.bar_close + 2, available_at_ms=bar.bar_close + 1,
                decision_cutoff_ms=bar.ingested_at + 1)


def run(root):
    config = fixture(root)
    seal = Path(root) / "freeze.json"
    freeze = seal_readiness(seal, **config)
    bar = mock_bar()
    assert commit_mock(config["journal"], bar)
    accepted = admit_sample(seal, **sample_args(config, freeze, bar))
    restarted = DurableJournal(str(Path(root) / "journal.sqlite"))
    args = sample_args(config, freeze, bar)
    args["journal"] = restarted
    assert admit_sample(seal, **args) == accepted
    assert not commit_mock(restarted, mock_bar())
    negative = []

    def reject(name, action):
        try:
            action()
        except ReadinessError as exc:
            negative.append(dict(case=name, rejection=str(exc)))
        else:
            raise AssertionError("Negative unexpectedly accepted: " + name)

    for name, update in (
        ("missing_rights", {"rights_sha256": None}),
        ("retrospective_checksum_is_not_pit", {"evidence_class": "RETROSPECTIVE_NON_PIT"}),
        ("g2_is_not_g4_oos", {"evidence_class": "G2_OBSERVER"}),
        ("source_unavailable_at_freeze", {"available_at_ms": 6000}),
    ):
        c = {**config, "source": {**config["source"], **update}}
        reject(name, lambda c=c: seal_readiness(Path(root) / (name + ".json"), **c))
    for name, update in (
        ("first_bar_not_future", {"first_eligible_open_ms": 0}),
        ("embargo_too_short", {"embargo_ms": 0}),
    ):
        c = {**config, "times": {**config["times"], **update}}
        reject(name, lambda c=c: seal_readiness(Path(root) / (name + ".json"), **c))
    reject("freeze_after_first_bar", lambda: seal_readiness(Path(root) / "late.json", **config))
    c = deepcopy({k: v for k, v in config.items() if k != "journal"})
    c["bindings"]["search_space_sha256"] = digest("post-sample-tune")
    reject("no_post_sample_tuning", lambda: seal_readiness(seal, journal=restarted, **c))
    reject("future_commit_at_cutoff", lambda: admit_sample(
        seal, **{**args, "decision_cutoff_ms": bar.ingested_at - 1}))
    oos = mock_bar(config["times"]["oos_start_ms"])
    commit_mock(restarted, oos)
    reject("no_oos_peek", lambda: admit_sample(seal, **{
        **sample_args(config, freeze, oos), "journal": restarted}))
    result = dict(status="PASS_SYNTHETIC_SAFETY_AND_RESTART_REPLAY", freeze_sha256=freeze,
                  sealed_presample_manifest=json.loads(seal.read_bytes()),
                  accepted_receipt=accepted, negative_rejections=negative,
                  fixed_clock_and_uuid="MOCK_ONLY_NOT_EXTERNAL_WITNESS",
                  real_cohort_status="BLOCKED_OWNER_AUTHORIZATION", trading_authority="NONE")
    return {**result, "report_sha256": digest(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="core-prospective-mock-") as root:
        result = run(root)
    raw = canonical(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw + b"\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
