"""Synthetic descriptive results to frozen trial accounting and guarded replay."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import _check_seal, digest
from research_wp_r0.durable_journal import DurableTrialJournal
from research_wp_r0.evaluation import OpportunityOutcome, OpportunityPair, Resolution, evaluate_paired
from research_wp_r0.owner_checkpoints import OwnerCheckpoint, export_checkpoint
from research_wp_r0.temporal_contract import FrozenTemporalManifest, TemporalOpportunity
from research_wp_r0.trial_holdout import Attempt, AttemptState, FrozenSearchFamily


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def context(package):
    _check_seal(package)
    require(package["schema"] == "aql.queue2.synthetic-dev-package.v1"
            and package["source_class"] == "SYNTHETIC_FIXTURE_ONLY"
            and package["historical_pit"] == "NOT_ATTESTED"
            and package["winner"] is None
            and package["actual_fills"] is None
            and package["orders_created"] == package["paper_positions"] == package["dispatches"] == 0,
            "QUEUE4_SOURCE_SCOPE")
    schedule = package["schedule"]
    protocol = schedule["protocol"]
    require(schedule["artifact_sha256"] == digest({
                key: value for key, value in schedule.items() if key != "artifact_sha256"})
            and schedule["source"]["source_package_sha256"]
                == package["cohort_receipt"]["source_zip_sha256"]
            and schedule["scheduled_total"] == len(schedule["pairs"])
            and schedule["test_only"] is True,
            "QUEUE4_SCHEDULE_SOURCE_OR_DENOMINATOR")
    require(package["splits"]["holdout_status"] == "SEALED_UNOPENED"
            and package["splits"]["validation_status"] == "RESERVED_UNEVALUATED",
            "QUEUE4_FOLD_CONTAMINATION")
    events = []
    pairs = []
    for pair in schedule["pairs"]:
        opportunity = pair["opportunity"]
        candidate = opportunity["opportunity_id"]
        cutoff = opportunity["decision_cutoff_ms"]
        require(opportunity["source_package_sha256"]
                == package["cohort_receipt"]["source_zip_sha256"]
                and opportunity["decision_ms"] <= cutoff
                and cutoff < protocol["train_end_exclusive_ms"],
                "QUEUE4_OPPORTUNITY_SOURCE_OR_CUTOFF")
        decision = datetime.fromtimestamp(cutoff / 1000, timezone.utc)
        # These are synthetic structural availability bounds for market windows.
        # Directional execution outcomes remain MISSING in both arms.
        end = decision + timedelta(hours=4)
        events.append(TemporalOpportunity(candidate, decision, decision, decision,
                                         end, end, end, end, candidate))
        pairs.append(OpportunityPair(
            OpportunityOutcome(candidate, candidate, Resolution.MISSING),
            OpportunityOutcome(candidate, candidate, Resolution.MISSING),
        ))
    manifest = FrozenTemporalManifest(
        digest(protocol), package["cohort_receipt"]["source_zip_sha256"],
        "SYNTHETIC_4H_MARKET_WINDOW_ONLY", tuple(events), 4 * 3600,
    )
    family = FrozenSearchFamily(
        "queue4:" + package["sha256"], digest(protocol), manifest.digest,
        manifest.source_version, "UNVERIFIED_DIRECTIONAL_OUTCOME", "MAXIMIZE",
        tuple(event.opportunity_id for event in events), 0.05,
        events[0].decision_at - timedelta(seconds=1),
    )
    return family, manifest, pairs


def record_methods(package, directory):
    """Create-only trial journal. Existing results and research folds are read-only."""
    family, manifest, pairs = context(package)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    with DurableTrialJournal(directory / "trials.jsonl", family) as journal:
        evaluation = evaluate_paired(
            pairs, block_length=1, replicates=100, seed=4, minimum_paired=2,
            temporal_manifest=manifest,
        )
        require(evaluation.decision == "NO_PROMOTION"
                and evaluation.missing_pairs == len(pairs), "QUEUE4_FALSE_PROMOTION")
        for candidate in family.candidate_ids:
            journal.record_attempt(Attempt(
                candidate, AttemptState.INELIGIBLE,
                digest({"package": package["sha256"], "candidate": candidate,
                        "reason": "NO_VERIFIED_DIRECTIONAL_OUTCOME"}),
                manifest.ordered[-1].baseline_horizon_end_at,
            ), event_id="trial:" + candidate)
        report = asdict(journal.report())
        checkpoint = export_checkpoint(journal)
    (directory / "checkpoint.json").write_bytes(checkpoint.to_json_bytes())
    body = {
        "schema": "aql.queue4.synthetic-methods.v1",
        "source_package_sha256": package["sha256"], "family_sha256": family.digest,
        "temporal_manifest_sha256": manifest.digest,
        "checkpoint_digest": checkpoint.receipt_digest,
        "evaluation": asdict(evaluation), "trial_report": report,
        "source_class": "SYNTHETIC_FIXTURE_ONLY", "holdout": "SEALED_UNOPENED",
        "external_custody_verified": False, "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0, "dispatches": 0,
    }
    return {**body, "sha256": digest(body)}


def replay_methods(package, directory, receipt):
    """Require the caller's retained receipt before checking mutable local files."""
    _check_seal(receipt)
    family, manifest, pairs = context(package)
    require(receipt["schema"] == "aql.queue4.synthetic-methods.v1"
            and receipt["source_package_sha256"] == package["sha256"]
            and receipt["family_sha256"] == family.digest
            and receipt["temporal_manifest_sha256"] == manifest.digest,
            "QUEUE4_REPLAY_IDENTITY")
    directory = Path(directory)
    checkpoint = OwnerCheckpoint.from_json_bytes((directory / "checkpoint.json").read_bytes())
    require(checkpoint.receipt_digest == receipt["checkpoint_digest"]
            and checkpoint.family_digest == family.digest, "QUEUE4_CHECKPOINT_DRIFT")
    with DurableTrialJournal(directory / "trials.jsonl", family,
                             expected_head=checkpoint.head,
                             expected_sequence=checkpoint.sequence) as journal:
        report = asdict(journal.report())
        # JSON receipts normalize immutable tuples to lists.
        require(digest(report) == digest(receipt["trial_report"]), "QUEUE4_REPORT_DRIFT")
        require(journal.sequence == checkpoint.sequence, "QUEUE4_UNEXPECTED_NEW_EVENT")
    evaluation = evaluate_paired(pairs, block_length=1, replicates=100, seed=4,
                                 minimum_paired=2, temporal_manifest=manifest)
    require(digest(asdict(evaluation)) == digest(receipt["evaluation"]),
            "QUEUE4_EVALUATION_DRIFT")
    return {"status": "PASS_SYNTHETIC_METHODS_ONLY", "receipt_sha256": receipt["sha256"],
            "external_custody_verified": False, "trading_authority": "NONE"}
