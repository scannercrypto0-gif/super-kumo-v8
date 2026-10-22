"""WP-R12: actually execute and measure synthetic end-to-end research flow.

Run: python -m research_wp_r0.measured_pipeline
Outputs JSON measurements and raises on failed invariants. Synthetic offline
fixtures and in-memory fake external store ONLY: no measured trading returns,
no actual external custody, no real provider or production deployment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import statistics
import tempfile
import time

from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.evaluation import (
    OpportunityOutcome, OpportunityPair, Resolution, evaluate_paired,
)
from research_wp_r0.external_custody import (
    CustodyPolicy, publish_checkpoint, verify_stored_checkpoint,
)
from research_wp_r0.opportunity_clusters import (
    ClusteredPair, FrozenAccountingPolicy, evaluate_opportunity_clusters,
)
from research_wp_r0.temporal_contract import (
    FrozenTemporalManifest, TemporalOpportunity,
)
from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, HoldoutEvent,
)

T0 = datetime(2026, 10, 22, 0, tzinfo=timezone.utc)
N_OPPORTUNITIES = 120
N_ATTEMPTS = 32


class TestDoubleStore:
    """Strictly in-memory contract double, NOT independent owner custody."""
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def put_once(self, key: str, content: bytes) -> None:
        if key in self.data and self.data[key] != content:
            raise JournalIntegrityError("Conflicting external fake-store write")
        self.data.setdefault(key, content)

    def read(self, key: str) -> bytes:
        return self.data[key]


@dataclass(frozen=True)
class Measurement:
    opportunities: int
    attempted_candidates: int
    failed_trials: int
    journal_events: int
    journal_bytes: int
    total_ms: float
    evaluate_ms: float
    journal_ms: float
    restore_ms: float
    checkpoint_ms: float
    tamper_detected: bool
    rollback_detected: bool
    positive_nomination_blocked: bool
    positive_screen_blocked: bool
    custody_is_simulated: bool

    def as_json(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))


def _fixtures():
    events = []
    rows = []
    for i in range(N_OPPORTUNITIES):
        decision = T0 + timedelta(hours=2 * i)
        market = f"shock-{i // 4}"
        events.append(TemporalOpportunity(
            opportunity_id=f"op-{i:04d}",
            decision_at=decision,
            baseline_feature_available_at=decision - timedelta(seconds=30),
            candidate_feature_available_at=decision - timedelta(seconds=15),
            baseline_horizon_end_at=decision + timedelta(hours=1),
            candidate_horizon_end_at=decision + timedelta(hours=1),
            baseline_label_available_at=decision + timedelta(hours=1, minutes=2),
            candidate_label_available_at=decision + timedelta(hours=1, minutes=4),
            opportunity_group_id=market,
        ))
        # Positive *relative* lift only. No evidence of real profitability.
        baseline = OpportunityOutcome(
            f"op-{i:04d}", market, Resolution.KNOWN,
            gross_return=-0.02, execution_cost=0.001,
        )
        candidate = OpportunityOutcome(
            f"op-{i:04d}", market,
            Resolution.NO_FILL if i % 17 == 0 else Resolution.KNOWN,
            **({} if i % 17 == 0 else {
                "gross_return": -0.01, "execution_cost": 0.001
            }),
        )
        rows.append(ClusteredPair(OpportunityPair(baseline, candidate),
                                  market, f"sector-{i % 8}"))
    manifest = FrozenTemporalManifest("protocol-fixture-v1", "source-fixture-v1",
                                     "60m", tuple(events))
    return manifest, tuple(rows)


def run_measurement(*, directory: Path | None = None) -> Measurement:
    """Returns real durations from one actual run and asserts its invariants.

    Whole operation uses tempfile when directory is None. A supplied directory
    must be empty to avoid modifying existing evidence or worktree data.
    """
    if directory is None:
        with tempfile.TemporaryDirectory(prefix="aql-r12-") as temp:
            return run_measurement(directory=Path(temp))
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("Require a new, empty measurement directory")

    start = time.perf_counter()
    manifest, rows = _fixtures()
    ordered_pairs = [row.pair for row in rows]
    evaluated = evaluate_paired(
        ordered_pairs, block_length=4, replicates=160, seed=42,
        minimum_paired=40, temporal_manifest=manifest,
    )
    clustered = evaluate_opportunity_clusters(
        rows, policy=FrozenAccountingPolicy("zero-exposure-v1", True, True),
        replicates=160, seed=42, temporal_manifest=manifest,
    )
    elapsed_evaluate = (time.perf_counter() - start) * 1000
    if evaluated.decision == "HISTORICAL_CANDIDATE_ONLY" or clustered.screening_positive:
        raise AssertionError("Unproven positive research decision escaped fail-closed gate")
    if evaluated.opportunities != N_OPPORTUNITIES or clustered.denominator != N_OPPORTUNITIES:
        raise AssertionError("Lost an opportunity in synthetic denominator")
    if clustered.candidate_no_fills != 8:
        raise AssertionError("Synthetic NO_FILL count changed")
    if not math.isfinite(clustered.realized_policy_net_lift):
        raise AssertionError("Invalid comparison result")

    family = FrozenSearchFamily(
        family_id="r12-synthetic-family", protocol_digest="protocol-fixture-v1",
        temporal_manifest_digest=manifest.digest,
        dataset_version="source-fixture-v1",
        metric_name="paired-net-lift", metric_direction="MAXIMIZE",
        candidate_ids=tuple(f"candidate-{i:03d}" for i in range(N_ATTEMPTS)),
        alpha=0.05, declared_at=T0,
    )
    path = directory / "trials.jsonl"
    policy = CustodyPolicy("owner-fixture", "fake-store", "synthetic", True)
    store = TestDoubleStore()

    journal_start = time.perf_counter()
    with DurableTrialJournal(path, family) as journal:
        for i in range(N_ATTEMPTS):
            candidate = f"candidate-{i:03d}"
            state = AttemptState.FAILED if i % 7 == 0 else AttemptState.COMPLETE
            journal.record_attempt(Attempt(
                candidate_id=candidate, state=state,
                result_digest=f"result-{i:03d}",
                recorded_at=T0 + timedelta(hours=1, seconds=i),
                marginal_p_value=None if state == AttemptState.FAILED else 0.4,
            ), event_id=f"attempt-{i:03d}")
        journal.select("candidate-001",
                       at=T0 + timedelta(hours=2),
                       event_id="selection-1")
        journal.holdout_event(HoldoutEvent(
            "OPEN", T0 + timedelta(hours=3), "fixture-only-access",
        ), event_id="holdout-open")
        before = journal.report()
        receipt = publish_checkpoint(journal, policy=policy, store=store)
        journal_events = journal.sequence
        if before.failed != 5 or before.complete != 27:
            raise AssertionError("Trial family accounting changed")
        if before.confirmatory_eligible:
            raise AssertionError("Holdout was falsely certified")
    elapsed_journal = (time.perf_counter() - journal_start) * 1000

    recovery_start = time.perf_counter()
    with DurableTrialJournal(path, family) as journal:
        verified = verify_stored_checkpoint(
            journal, policy=policy, store=store,
            checkpoint=receipt.checkpoint,
        )
        if verified.key != receipt.key or journal.report().status != "EXPLORATORY_HOLDOUT_OPENED":
            raise AssertionError("Durable replay/custody check failed")
    elapsed_restore = (time.perf_counter() - recovery_start) * 1000

    evidence_check_start = time.perf_counter()
    # Change a byte without updating the hash, even though original owner
    # checkpoint is retained in the separate simulated store.
    original = path.read_bytes()
    changed = original.replace(b"result-001", b"result-991")
    if changed == original:
        raise AssertionError("Tamper fixture could not be constructed")
    path.write_bytes(changed)
    tamper = False
    try:
        with DurableTrialJournal(path, family) as journal:
            verify_stored_checkpoint(journal, policy=policy, store=store,
                                     checkpoint=receipt.checkpoint)
    except JournalIntegrityError:
        tamper = True
    path.write_bytes(original)

    # Roll back last evidence event (checkpoint sequence now too high).
    lines = original.splitlines(keepends=True)
    path.write_bytes(b"".join(lines[:-1]))
    rollback = False
    try:
        with DurableTrialJournal(path, family) as journal:
            verify_stored_checkpoint(journal, policy=policy, store=store,
                                     checkpoint=receipt.checkpoint)
    except JournalIntegrityError:
        rollback = True
    elapsed_checkpoint = (time.perf_counter() - evidence_check_start) * 1000

    if not tamper or not rollback:
        raise AssertionError("Journal tampering or rollback undetected")
    total_ms = (time.perf_counter() - start) * 1000
    return Measurement(
        opportunities=N_OPPORTUNITIES, attempted_candidates=N_ATTEMPTS,
        failed_trials=before.failed, journal_events=journal_events,
        journal_bytes=len(original), total_ms=round(total_ms, 3),
        evaluate_ms=round(elapsed_evaluate, 3),
        journal_ms=round(elapsed_journal, 3),
        restore_ms=round(elapsed_restore, 3),
        checkpoint_ms=round(elapsed_checkpoint, 3),
        tamper_detected=tamper, rollback_detected=rollback,
        positive_nomination_blocked=True, positive_screen_blocked=True,
        custody_is_simulated=True,
    )


def main() -> None:
    print(run_measurement().as_json())


if __name__ == "__main__":
    main()
