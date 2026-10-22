"""Batch 01: isolated synthetic research; no exchange, credentials or promotion.

Run: python -B -m research_wp_r0.strategy_factory --output <NEW_DIRECTORY>
The reserved final partition is deliberately inaccessible. Synthetic validation
is visible exploratory evidence, never an independent historical holdout.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

from research_wp_r0.durable_journal import DurableTrialJournal
from research_wp_r0.evaluation import OpportunityOutcome, OpportunityPair, Resolution, evaluate_paired
from research_wp_r0.owner_checkpoints import export_checkpoint
from research_wp_r0.opportunity_clusters import ClusteredPair, FrozenAccountingPolicy, evaluate_opportunity_clusters
from research_wp_r0.statistics import LabelWindow, holm, purged_forward_folds, paired_moving_block_interval
from research_wp_r0.temporal_contract import FrozenTemporalManifest, TemporalOpportunity
from research_wp_r0.trial_holdout import Attempt, AttemptState, FrozenSearchFamily

T = datetime(2026, 10, 22, tzinfo=timezone.utc)  # fixture clock, not wall-clock custody proof
PROTOCOL_PATH = Path(__file__).with_name("batch01_protocol.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Protocol:
    """Immutable canonical bytes, not a shallow-frozen mutable dictionary."""
    payload: bytes

    @classmethod
    def load(cls):
        return cls(canonical(json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True)
class Candidate:
    family: str
    lookback: int
    threshold: float

    @property
    def candidate_id(self):
        return f"{self.family}-L{self.lookback}-T{self.threshold:g}"


def candidates(protocol):
    return tuple(Candidate(f["name"], n, t) for f in protocol.spec["families"]
                 for n in f["lookbacks"] for t in f["thresholds"])


@dataclass(frozen=True)
class Bar:
    index: int
    open: float
    high: float
    low: float
    close: float
    regime: str
    entry_executable: bool = True

    @property
    def available_at(self):
        return T + timedelta(minutes=self.index + 1, microseconds=-1)


def synthetic_prefix(protocol, end):
    """Generate only allowed prefix. No final holdout loading API or bypass flag."""
    s = protocol.spec["source"]
    if type(end) is not int or not 0 < end <= s["validation_end"]:
        raise PermissionError("Final holdout access is not authorized in Batch 01")
    rng, price, rows = random.Random(s["seed"]), 100., []
    for i in range(end):
        regime = ("UP", "DOWN", "RANGE", "VOLATILE")[(i // 64) % 4]
        drift = {"UP": .002, "DOWN": -.002, "RANGE": -.05 * math.log(price / 100), "VOLATILE": 0.}[regime]
        sigma = .009 if regime == "VOLATILE" else .003
        opening = price * math.exp(rng.gauss(0, sigma * .2))
        closing = opening * math.exp(drift + rng.gauss(0, sigma))
        spread = abs(rng.gauss(0, sigma * .7))
        rows.append(Bar(i, opening, max(opening, closing) * (1 + spread),
                        min(opening, closing) / (1 + spread), closing, regime,
                        i % 29 not in (10, 11)))
        price = closing
    return tuple(rows)


def signal(candidate, prefix):
    """Only completed decision-time prefix; regime labels are never read."""
    n = candidate.lookback
    if len(prefix) < n + 1:
        return False
    last, prior = prefix[-1], prefix[-n-1:-1]
    if candidate.family == "momentum":
        return last.close / prefix[-n-1].close - 1 > candidate.threshold
    if candidate.family == "breakout":
        return last.close > max(b.high for b in prior) * (1 + candidate.threshold)
    if candidate.family == "mean_reversion":
        closes = [b.close for b in prior]
        sd = statistics.pstdev(closes)
        return sd > 0 and (statistics.mean(closes) - last.close) / sd > candidate.threshold
    if candidate.family == "random_baseline":
        key = f"batch01-random-v1:{last.index}".encode()
        return int(hashlib.sha256(key).hexdigest()[:8], 16) % 2 == 0
    raise ValueError("Unknown frozen strategy family")


def execution_cost(entry, exit_price, rules):
    # Entry-notional denominator. Exact adverse slippage on both legs plus fees
    # on actual transacted notionals; no double-counting of slippage in prices.
    slip, fee = rules["slippage_per_side"], rules["fee_per_side"]
    bought, sold = entry * (1 + slip), exit_price * (1 - slip)
    return (bought - entry + exit_price - sold + fee * (bought + sold)) / entry


def execute(rows, i, enters, rules):
    """Fixed disjoint opportunity windows; bounded OHLC ambiguity, no fake fill."""
    empty = {"attempted": enters, "entry_index": None, "exit_index": None,
             "gross": None, "net": None, "cost": None, "low_net": 0., "high_net": 0.,
             "risk_path": []}
    if not enters:
        return dict(empty, state="NO_SIGNAL")
    ttl, hold = rules["entry_ttl_bars"], rules["holding_bars"]
    entry_index = next((j for j in range(i + 1, i + ttl + 1) if rows[j].entry_executable), None)
    if entry_index is None:
        return dict(empty, state="NO_FILL_EXPIRED")
    price = rows[entry_index].open
    stop, target = price * (1 - rules["stop_fraction"]), price * (1 + rules["target_fraction"])
    risk_path = []
    for j in range(entry_index, entry_index + hold):
        bar = rows[j]
        # Opening price precedes intrabar extremes, so gaps resolve first.
        if bar.open <= stop or bar.open >= target:
            exit_price, reason = bar.open, "GAP_STOP" if bar.open <= stop else "GAP_TARGET"
        elif bar.low <= stop and bar.high >= target:
            lo = stop / price - 1 - execution_cost(price, stop, rules)
            hi = target / price - 1 - execution_cost(price, target, rules)
            risk_path.append(lo)
            return dict(empty, state="AMBIGUOUS", entry_index=entry_index, exit_index=j,
                        low_net=lo, high_net=hi, risk_path=risk_path)
        elif bar.low <= stop:
            exit_price, reason = stop, "STOP"
        elif bar.high >= target:
            exit_price, reason = target, "TARGET"
        elif j == entry_index + hold - 1:
            exit_price, reason = bar.close, "TIME_EXIT"
        else:
            risk_path.append(bar.close / price - 1 - execution_cost(price, bar.close, rules))
            continue
        gross, cost = exit_price / price - 1, execution_cost(price, exit_price, rules)
        net = gross - cost
        risk_path.append(net)
        return dict(empty, state=reason, entry_index=entry_index, exit_index=j,
                    gross=gross, cost=cost, net=net, low_net=net, high_net=net, risk_path=risk_path)
    raise AssertionError("Unresolved fixed horizon")


def max_drawdown(records):
    """Close-marked additive unit-notional curve; ambiguity takes lower scenario.

    Not intrabar worst equity or compounded account drawdown; no capital/leverage
    claim. Return drawdown divided by initial unit equity, explicit in reports.
    """
    balance, peak, dd = 1., 1., 0.
    for r in records:
        for pnl in r["risk_path"]:
            equity = balance + pnl
            peak = max(peak, equity)
            dd = max(dd, peak - equity)
        balance += r["low_net"]
    return dd


def metrics(records, minimum):
    known = [r for r in records if r["net"] is not None]
    nets = [r["net"] for r in known]
    return {"opportunities": len(records), "attempts": sum(r["attempted"] for r in records),
            "executed": sum(r["entry_index"] is not None for r in records),
            "known_trades": len(known), "ambiguous": sum(r["state"] == "AMBIGUOUS" for r in records),
            "no_signal": sum(r["state"] == "NO_SIGNAL" for r in records),
            "no_fill": sum(r["state"] == "NO_FILL_EXPIRED" for r in records),
            "gross_sum_known": math.fsum(r["gross"] for r in known),
            "cost_sum_known": math.fsum(r["cost"] for r in known),
            "net_sum_known": math.fsum(nets),
            "net_bounds_sum": [math.fsum(r["low_net"] for r in records), math.fsum(r["high_net"] for r in records)],
            "close_marked_lower_scenario_drawdown_initial_equity": max_drawdown(records),
            "known_trade_stddev": statistics.pstdev(nets) if nets else None,
            "known_trade_worst": min(nets) if nets else None,
            "sample_adequate_for_descriptive_screen": len(known) >= minimum,
            "profitability_status": "INSUFFICIENT_EVIDENCE"}


def indices(protocol, partition):
    s, e = protocol.spec["source"], protocol.spec["execution"]
    if partition == "development":
        start, end = e["warmup"], s["development_end"]
    elif partition == "synthetic_validation":
        # Warm-up belongs strictly to this partition; no outcome or feature overlap.
        start, end = s["development_end"] + e["warmup"], s["validation_end"]
    else:
        raise PermissionError("Unknown or reserved partition")
    horizon = e["entry_ttl_bars"] + e["holding_bars"]
    return tuple(range(start, end - horizon, e["opportunity_stride"]))


def temporal_manifest(protocol, selected_indices, partition):
    horizon = protocol.spec["execution"]["entry_ttl_bars"] + protocol.spec["execution"]["holding_bars"]
    events = []
    for i in selected_indices:
        at = T + timedelta(minutes=i + 1, microseconds=-1)
        end = at + timedelta(minutes=horizon)
        events.append(TemporalOpportunity(f"{partition}:{i}", at, at, at, end, end,
                                         end, end, f"synthetic-block-{i // 64}"))
    return FrozenTemporalManifest(protocol.digest, protocol.spec["source"]["generator"],
                                  "fixed-opportunity-window", tuple(events), horizon_seconds=horizon * 60)


def records_for(candidate, rows, protocol, partition):
    e = protocol.spec["execution"]
    records = []
    for i in indices(protocol, partition):
        # Strict slice before strategy code; outcomes are only read by simulator.
        prefix = rows[:i + 1]
        record = execute(rows, i, signal(candidate, prefix), e)
        record.update(opportunity_id=f"{partition}:{i}", decision_index=i,
                      regime=rows[i].regime, group_id=f"synthetic-block-{i // 64}",
                      feature_start=i-candidate.lookback, feature_end=i,
                      decision_at=rows[i].available_at.isoformat(),
                      source_kind="SYNTHETIC", protocol_digest=protocol.digest)
        records.append(record)
    return records


def outcome(record):
    args = (record["opportunity_id"], record["group_id"])
    if record["state"] == "AMBIGUOUS":
        return OpportunityOutcome(*args, Resolution.AMBIGUOUS,
                                  bound_low=record["low_net"], bound_high=record["high_net"])
    if record["net"] is None:
        # Both explicit no-order and failed-entry branches establish no exposure
        # in THIS simulator. Detailed records retain their distinct reasons.
        return OpportunityOutcome(*args, Resolution.NO_FILL)
    return OpportunityOutcome(*args, Resolution.KNOWN, record["gross"], record["cost"])


def compare(records, baseline, manifest, protocol):
    pairs = [OpportunityPair(outcome(b), outcome(c)) for b, c in zip(baseline, records)]
    inf = protocol.spec["inference"]
    report = asdict(evaluate_paired(pairs, block_length=inf["block_length"],
                  replicates=inf["bootstrap_replicates"], seed=4301,
                  minimum_paired=12, temporal_manifest=manifest))
    # Conditional both-long returns can be identical despite different entry
    # selection. Also compare the full predeclared opportunity population using
    # the EXISTING explicit zero-exposure policy; do not silently zero ambiguity.
    report["opportunity_accounting"] = asdict(evaluate_opportunity_clusters(
        [ClusteredPair(pair,pair.baseline.group_id,"ONE_SYNTHETIC_INSTRUMENT") for pair in pairs],
        policy=FrozenAccountingPolicy("batch01-explicit-zero-exposure-v1",True,True),
        replicates=inf["bootstrap_replicates"],seed=4301,temporal_manifest=manifest))
    complete = all(p.baseline.resolution != Resolution.AMBIGUOUS and
                   p.candidate.resolution != Resolution.AMBIGUOUS for p in pairs)
    report["opportunity_block_interval"] = None
    if complete and len(pairs) >= 3 * inf["block_length"]:
        report["opportunity_block_interval"] = asdict(paired_moving_block_interval(
            [p.baseline.known_net if p.baseline.known_net is not None else 0. for p in pairs],
            [p.candidate.known_net if p.candidate.known_net is not None else 0. for p in pairs],
            block_length=inf["block_length"],replicates=inf["bootstrap_replicates"],seed=4301))
    report["adapter_note"] = "Existing NO_FILL adapter includes confirmed zero-exposure NO_SIGNAL; factory counts distinguish them. Opportunity block interval is uncalibrated descriptive sensitivity, not multiple-testing-adjusted significance. Sector CI suppressed: one synthetic instrument."
    return report


def rank_development(results):
    def key(row):
        m = row["development"]
        return (-int(m["sample_adequate_for_descriptive_screen"]),
                -m["net_bounds_sum"][0] / m["opportunities"],
                m["close_marked_lower_scenario_drawdown_initial_equity"], row["candidate_id"])
    return [row["candidate_id"] for row in sorted(results, key=key)]


def frozen_family(protocol, manifest):
    return FrozenSearchFamily(protocol.spec["protocol_id"], protocol.digest, manifest.digest,
                              protocol.spec["source"]["generator"], "worst_bound_per_opportunity",
                              "MAXIMIZE", tuple(c.candidate_id for c in candidates(protocol)),
                              protocol.spec["inference"]["alpha"], T)


def run_batch(output):
    output = Path(output)
    # Create-only run directory: reruns never silently overwrite evidence.
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    protocol = Protocol.load()
    (output / "frozen_protocol.json").write_bytes(protocol.payload + b"\n")
    rows = synthetic_prefix(protocol, protocol.spec["source"]["validation_end"])
    manifests = {p: temporal_manifest(protocol, indices(protocol, p), p)
                 for p in ("development", "synthetic_validation")}
    all_indices = indices(protocol, "development") + indices(protocol, "synthetic_validation")
    horizon = protocol.spec["execution"]["entry_ttl_bars"] + protocol.spec["execution"]["holding_bars"]
    windows = [LabelWindow(T + timedelta(minutes=i), T + timedelta(minutes=i+horizon)) for i in all_indices]
    folds = purged_forward_folds(windows, minimum_training=24, test_size=12)
    baseline_candidates = {"random": Candidate("random_baseline", 8, 0.),
                           "momentum": Candidate("momentum", 8, 0.)}
    baselines = {p: {name: records_for(c, rows, protocol, p) for name, c in baseline_candidates.items()}
                 for p in manifests}
    results, detailed = [], []
    for c in candidates(protocol):
        evidence_start = len(detailed)
        row = {"candidate_id": c.candidate_id, "family": c.family,
               "parameters": asdict(c), "status": "INSUFFICIENT_EVIDENCE",
               "reason": "Synthetic only; no independently custodied historical holdout or forward evidence",
               "target_regimes": next(f["target_regimes"] for f in protocol.spec["families"] if f["name"] == c.family),
               "comparisons": {}, "regimes": {}}
        for partition, manifest in manifests.items():
            records = records_for(c, rows, protocol, partition)
            row[partition] = metrics(records, protocol.spec["ranking"]["minimum_known_trades"])
            row["regimes"][partition] = {r: metrics([x for x in records if x["regime"] == r], 12)
                                         for r in ("UP", "DOWN", "RANGE", "VOLATILE")}
            row["comparisons"][partition] = {name: compare(records, base, manifest, protocol)
                                              for name, base in baselines[partition].items()}
            detailed.extend(dict(r, candidate_id=c.candidate_id, partition=partition) for r in records)
        row["opportunity_records_digest"] = digest(detailed[evidence_start:])
        results.append(row)
    # Rank only the development table; validation cannot change this order.
    ranking = rank_development(results)
    dataset_digest = digest([asdict(b) for b in rows])
    baseline_metrics = {p: {n: dict(metrics(rs,12),opportunity_records_digest=digest([
        dict(r,candidate_id="baseline-"+n,partition=p) for r in rs]))
        for n,rs in bs.items()} for p,bs in baselines.items()}
    family = frozen_family(protocol, manifests["development"])
    with DurableTrialJournal(output / "trial_journal.jsonl", family) as journal:
        for row in results:
            evidence = {"protocol": protocol.digest, "dataset": dataset_digest,
                        "candidate_result": row, "baseline_metrics": baseline_metrics}
            journal.record_attempt(Attempt(row["candidate_id"], AttemptState.COMPLETE,
                 digest(evidence), T + timedelta(days=1), 1.), event_id="attempt-"+row["candidate_id"])
        report = asdict(journal.report())
        checkpoint = export_checkpoint(journal)
        (output / "checkpoint.json").write_bytes(checkpoint.to_json_bytes())
    with DurableTrialJournal(output / "trial_journal.jsonl", family,
                             expected_head=checkpoint.head, expected_sequence=checkpoint.sequence) as journal:
        if asdict(journal.report()) != report:
            raise AssertionError("Replay changed the trial family")
    for p, bs in baselines.items():
        for name, records in bs.items():
            detailed.extend(dict(r, candidate_id="baseline-"+name, partition=p) for r in records)
    summary = {"project_id": "AQL-CRYPTO-RESEARCH-001", "source_kind": "SYNTHETIC",
        "protocol_digest": protocol.digest, "dataset_prefix_digest": dataset_digest,
        "source_prefix_bars": len(rows), "reserved_tail_bars_not_read": protocol.spec["source"]["bars"]-len(rows),
        "manifest_digests": {p: m.digest for p, m in manifests.items()},
        "candidate_count": len(results), "purged_fold_count": len(folds),
        "selection_order_development_only": ranking, "selected_for_promotion": None,
        "historical_real_data": "NOT_AVAILABLE_NOT_TESTED", "forward_shadow": "NOT_STARTED_NOT_TESTED",
        "final_holdout": "NOT_OPENED", "external_owner_custody_verified": False,
        "multiple_testing": {"marginal_p_values": [1.] * len(results),
                             "holm_adjusted": list(holm([1.] * len(results))),
                             "interpretation": "Conservative placeholders, no calibrated strategy significance claimed"},
        "ledger": report, "candidates": results,
        "baseline_metrics": baseline_metrics,
        "metric_units": "Fraction of one entry notional, additive sums; no portfolio/compounded return claim",
        "uncertainty": "Unadjusted conditional paired block-bootstrap sensitivity only; missing/no-fill/ambiguous pairs excluded, not zero; no calibrated profitability claim",
        "risk_scope": "Close-marked lower-ambiguity scenario drawdown / initial unit equity; excludes unobserved intrabar equity extremes"}
    (output / "results.json").write_bytes(canonical(summary)+b"\n")
    (output / "opportunities.jsonl").write_bytes(b"".join(canonical(r)+b"\n" for r in detailed))
    fields = ["candidate_id", "family", "rank", "partition", "opportunities", "attempts", "executed",
              "known_trades", "no_signal", "no_fill", "ambiguous", "gross_sum_known", "net_sum_known",
              "close_marked_lower_scenario_drawdown_initial_equity", "status"]
    with (output / "candidates.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for r in results:
            for p in manifests:
                writer.writerow({k: {**r[p], **r, "rank": ranking.index(r["candidate_id"])+1, "partition": p}.get(k) for k in fields})
    evidence = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
    (output / "artifact_hashes.json").write_bytes(canonical(evidence)+b"\n")
    # Timing intentionally outside deterministic evidence hash tree.
    timing = {"elapsed_seconds": time.perf_counter()-started, "candidate_count": len(results),
              "opportunities_evaluated_including_baselines": len(detailed)}
    (output / "timing.json").write_bytes(canonical(timing)+b"\n")
    verify_batch(output)
    return summary, timing


def verify_batch(output):
    """Detect accidental/tampered bytes against local manifest and replay anchor.

    Local replaceable hashes are NOT independently trusted custody. An attacker
    replacing every file and receipt cannot be authenticated by this check.
    """
    output = Path(output)
    hashes = json.loads((output / "artifact_hashes.json").read_bytes())
    required = {"frozen_protocol.json","results.json","opportunities.jsonl",
                "trial_journal.jsonl","checkpoint.json","candidates.csv"}
    if set(hashes) != required:
        raise ValueError("Artifact manifest scope changed")
    for name, expected in hashes.items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Artifact digest mismatch: " + name)
    protocol = Protocol(canonical(json.loads((output / "frozen_protocol.json").read_bytes())))
    manifest = temporal_manifest(protocol,indices(protocol,"development"),"development")
    from research_wp_r0.owner_checkpoints import OwnerCheckpoint
    checkpoint = OwnerCheckpoint.from_json_bytes((output / "checkpoint.json").read_bytes())
    with DurableTrialJournal(output / "trial_journal.jsonl",frozen_family(protocol,manifest),
                             expected_head=checkpoint.head,expected_sequence=checkpoint.sequence) as journal:
        summary = json.loads((output / "results.json").read_bytes())
        # JSON-normalize tuple fields before comparing serialized ledger report.
        if summary["ledger"] != json.loads(canonical(asdict(journal.report()))):
            raise ValueError("Result ledger differs from replay")
        if summary["protocol_digest"] != protocol.digest:
            raise ValueError("Result protocol differs from frozen protocol")
        events = [json.loads(line) for line in (output / "trial_journal.jsonl").read_bytes().splitlines()]
        commitments = {event["data"]["candidate_id"]:event["data"]["result_digest"]
                       for event in events if event["kind"] == "ATTEMPT"}
        if [r["candidate_id"] for r in summary["candidates"]] != list(frozen_family(protocol,manifest).candidate_ids):
            raise ValueError("Candidate universe/order changed")
        for row in summary["candidates"]:
            evidence = {"protocol": protocol.digest, "dataset": summary["dataset_prefix_digest"],
                        "candidate_result": row, "baseline_metrics": summary["baseline_metrics"]}
            if commitments.get(row["candidate_id"]) != digest(evidence):
                raise ValueError("Result commitment differs from journal")
        details = [json.loads(line) for line in (output / "opportunities.jsonl").read_bytes().splitlines()]
        expected_ids = {r["candidate_id"] for r in summary["candidates"]} | {"baseline-random","baseline-momentum"}
        if {r["candidate_id"] for r in details} != expected_ids:
            raise ValueError("Opportunity evidence universe changed")
        for row in summary["candidates"]:
            actual = [r for r in details if r["candidate_id"] == row["candidate_id"]]
            if digest(actual) != row["opportunity_records_digest"]:
                raise ValueError("Opportunity commitment differs from journal-bound result")
        for partition, baselines in summary["baseline_metrics"].items():
            for name, baseline in baselines.items():
                actual = [r for r in details if r["candidate_id"] == "baseline-"+name and r["partition"] == partition]
                if digest(actual) != baseline["opportunity_records_digest"]:
                    raise ValueError("Baseline opportunity commitment differs")
        if summary["selection_order_development_only"] != rank_development(summary["candidates"]):
            raise ValueError("Development ranking changed")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary, timing = run_batch(args.output)
    print(json.dumps({"status": "INSUFFICIENT_EVIDENCE", "candidate_count": summary["candidate_count"],
                      "final_holdout": summary["final_holdout"], **timing}, sort_keys=True))


if __name__ == "__main__":
    main()
