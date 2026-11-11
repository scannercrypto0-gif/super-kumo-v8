"""Joined prospective readiness rehearsal, using only internally generated data."""
import argparse
from collections import Counter
from decimal import Decimal, localcontext
import hmac
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
from uuid import UUID

from tools.pit_oos_readiness.dependencies import CORE, FACTORY, activate, verify

activate()

from aql.g1_integrity import content, fingerprint
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from research_wp_r0.aql_archive_custody_bridge_v1 import canonical, decode, digest
from research_wp_r0.aql_core_prospective_readiness_v1 import admit_sample, seal_readiness
from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
from research_wp_r0.aql_factory_h_execution_comparison_v1 import run_factory_h_execution_comparison
from research_wp_r0.frozen_research_plan import commit_research_plan, verify_research_plan
from tools.atlas_factory_pkg02_execution_smoke import fixture_packet, seal

STEP = 900_000
EMBARGO = 72 * 3_600_000
MOCK_KEYS = {role: f"public-fixture-only-{role}".encode() for role in ("witness", "publisher")}
BLOCKERS = {
    "BLOCKED_OWNER_PROVIDER_PROOF": "Approve venue, jurisdiction, instrument, endpoint, dated provider terms and explicit personal noncommercial research and retention rights.",
    "BLOCKED_INDEPENDENT_PREFREEZE": "Supply a trusted witness key/issuer and externally retained timestamp receipt over exact protocol bytes before first eligible source availability.",
    "BLOCKED_FIRST_RELEASE_EVIDENCE": "Supply independently verifiable publisher release/version and received-at evidence with clock and correction policy.",
    "BLOCKED_OWNER_CUSTODY_PROOF": "Approve separate least-privilege collection and blind holdout custody, retention, immutable ACK and independent readback.",
    "BLOCKED_FUTURE_COHORT": "Authorize exact future UTC slots and budget in the owner envelope; complete genuine train/validation and untouched OOS later.",
    "BLOCKED_EXECUTION_OBSERVABILITY": "Provide rights and evidence for venue spread/depth/queue/fill/fees if empirical execution claims are required.",
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def immutable(path, raw):
    """Publish an fsynced file without overwriting an existing commitment."""
    if path.exists():
        require(path.is_file() and path.read_bytes() == raw, "IMMUTABLE_CONFLICT")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stage = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            stage.unlink()
            raise
    try:
        try:
            os.link(stage, path)
        except FileExistsError:
            require(path.read_bytes() == raw, "IMMUTABLE_CONFLICT")
    finally:
        stage.unlink()


def mock_receipt(role, payload):
    mac = hmac.new(MOCK_KEYS[role], canonical(payload), "sha256").hexdigest()
    return {"role": role, "mode": "PUBLIC_MOCK_KEY_ONLY", "payload": payload, "mac": mac}


def verify_mock(role, receipt):
    require(receipt == mock_receipt(role, receipt["payload"]), "MOCK_RECEIPT_INTEGRITY")
    return receipt["payload"]


def configuration():
    train_end = 3 * STEP
    validation_start = train_end + EMBARGO
    validation_end = validation_start + 48 * STEP
    times = dict(freeze_at_ms=4000, first_eligible_open_ms=STEP, train_end_ms=train_end,
                 validation_end_ms=validation_end, oos_start_ms=validation_end + EMBARGO,
                 oos_end_ms=validation_end + EMBARGO + 2 * STEP,
                 step_ms=STEP, embargo_ms=EMBARGO)
    rights = dict(mode="FIXTURE_ONLY", provider="MOCK_PROVIDER_299", version="fixture-v1",
                  terms_as_of_ms=1000, expires_at_ms=times["oos_end_ms"] + STEP,
                  use="PERSONAL_NONCOMMERCIAL_RESEARCH_REHEARSAL",
                  redistribution=False, cost_ceiling=0)
    source = dict(provider=rights["provider"], source_version=rights["version"],
                  symbol="BTC-USD", market="SPOT", interval="15m", source_label="MOCK:299",
                  rights_reference="fixture-only-299", rights_sha256=digest(rights),
                  available_at_ms=1000, observed_at_ms=2000, committed_at_ms=3000,
                  evidence_class="SYNTHETIC_PROVIDER_MOCK")
    packet = fixture_packet()
    packet.update(experiment_id="RESEARCH-H-EXEC-CMP-PROSPECTIVE-299-MOCK",
                  frozen_at_ms=times["freeze_at_ms"], train_end_ms=train_end,
                  evaluation_start_ms=validation_start)
    features = {"family": "FROZEN_SIGNAL_SCHEDULE_FIXTURE", "signal": "PREDECLARED_SLOT",
                "feature_availability": "AFTER_PUBLICATION_AND_DURABLE_ACK",
                "null": "SEPARATE_PREDECLARED_PLACEBO_SEED_2702"}
    groups = packet["entries"] + packet["null_entries"]
    for index, row in enumerate(groups):
        entry = validation_start + (index * 6 + 2) * STEP
        delta = entry - row["entry_ms"]
        row.update(entry_ms=entry, signal_ms=entry - STEP + 3)
        for bar in row["bars"]:
            bar["open_ms"] += delta
            bar["close_ms"] += delta
    packet["strategy_sha256"] = digest(features)
    packet["scanner_entry_batch_sha256"] = digest(packet["entries"])
    packet["attempts"][0]["source_receipt_sha256"] = packet["scanner_entry_batch_sha256"]
    seal(packet)
    protocol = dict(
        schema="aql.pit-oos.protocol.v1", authority="NONE", evidence="MOCK_ONLY",
        source=source, rights=rights, times=times, validation_start_ms=validation_start,
        features=features, candidates=packet["attempts"], trial_budget=3, evaluated_trials=1,
        opportunity_budget=50, scenario_budget=18, hypothesis_budget=54, alpha="0.05",
        bonferroni_alpha=str(Decimal("0.05") / 54), p_values="NOT_ESTIMABLE",
        stop="FIXED_POPULATION_NO_OPTIONAL_STOP", holdout="SEALED_UNOPENED",
        risk_exit={k: packet[k] for k in ("initial_risk_fraction", "target_r_multiples", "allocations", "stop_order")},
        sizing="NORMALIZED_UNIT_NOTIONAL_FIXTURE", costs=packet["costs"],
        regime_labels={row["entry_id"]: ("RANGE_FIXTURE", "TREND_FIXTURE", "AMBIGUITY_FIXTURE")[index % 3]
                       for index, row in enumerate(groups)},
        model_inputs_sha256=packet["sha256"], baseline_sha256=packet["baseline_sha256"],
        evaluator_commit=FACTORY, core_commit=CORE, g2_maturity="SEPARATE_OPERATIONAL_EVIDENCE",
    )
    return protocol, packet


def prepare(root, protocol):
    source, times = protocol["source"], protocol["times"]
    bindings = dict(evaluator_sha256=digest(FACTORY), search_space_sha256=digest(protocol),
                    all_attempt_inventory_sha256=digest(protocol["candidates"]),
                    risk_exit_sha256=digest(protocol["risk_exit"]))
    plan, plan_sha = commit_research_plan(
        "mock-prospective-299", [(r["candidate_id"], digest(r)) for r in protocol["candidates"]],
        protocol_digest=digest(bindings), dataset_digest=digest(source), split_digest=digest(times),
        metrics=["gross_return", "net_return", "unknown_count"],
        selection_rule={"rule": protocol["stop"], "holdout": protocol["holdout"]},
        cost_model=protocol["costs"], baseline_digest=protocol["baseline_sha256"])
    immutable(root / "protocol.json", canonical(protocol))
    immutable(root / "plan.json", plan)
    with patch("aql.journal.durable_journal.uuid.uuid4", return_value=UUID(int=299)):
        journal = DurableJournal(str(root / "journal.sqlite"))
    freeze = seal_readiness(root / "freeze.json", journal=journal, plan_raw=plan,
                            plan_sha256=plan_sha, source=source, times=times,
                            bindings=bindings, witnessed_at_ms=5000)
    witness = mock_receipt("witness", dict(freeze_sha256=freeze, protocol_sha256=digest(protocol),
                                          plan_sha256=plan_sha, witnessed_at_ms=5000))
    immutable(root / "witness.json", canonical(witness))
    immutable(root / "holdout-lock.json", canonical(dict(
        freeze_sha256=freeze, start_ms=times["oos_start_ms"], end_ms=times["oos_end_ms"],
        status="SEALED_UNOPENED", stored_prices=0, read_operations=0)))
    return journal, plan, freeze, witness


def publication(protocol, bar, freeze):
    return mock_receipt("publisher", dict(
        source_sha256=digest(protocol["source"]), rights_sha256=digest(protocol["rights"]),
        freeze_sha256=freeze, stable_key=bar.stable_key(), content_sha256=fingerprint(content(bar)),
        release_version=1, correction_of=None, available_at_ms=bar.bar_close + 1,
        first_known_at_ms=bar.bar_close + 1, received_at_ms=bar.bar_close + 2))


def validate_publication(protocol, bar, freeze, witness, receipt):
    source, times, rights = protocol["source"], protocol["times"], protocol["rights"]
    attestation = verify_mock("witness", witness)
    pub = verify_mock("publisher", receipt)
    require(set(pub) == {"source_sha256", "rights_sha256", "freeze_sha256", "stable_key",
                        "content_sha256", "release_version", "correction_of", "available_at_ms",
                        "first_known_at_ms", "received_at_ms"}
            and all(type(pub[k]) is int and 0 <= pub[k] <= 2**53-1
                    for k in ("available_at_ms", "first_known_at_ms", "received_at_ms", "release_version")),
            "FIRST_RELEASE_FIELDS")
    require(attestation["freeze_sha256"] == freeze and attestation["protocol_sha256"] == digest(protocol),
            "WITNESS_SCOPE")
    require(times["freeze_at_ms"] <= attestation["witnessed_at_ms"] < times["first_eligible_open_ms"],
            "LATE_WITNESS")
    require(pub["freeze_sha256"] == freeze and pub["source_sha256"] == digest(source)
            and pub["stable_key"] == bar.stable_key() and pub["content_sha256"] == fingerprint(content(bar)),
            "FOREIGN_OR_CHANGED_SOURCE")
    require(source["evidence_class"] == "SYNTHETIC_PROVIDER_MOCK" and
            (bar.symbol, bar.interval, bar.source) == (source["symbol"], source["interval"], source["source_label"]),
            "FOREIGN_OR_REAL_SOURCE")
    require(pub["rights_sha256"] == source["rights_sha256"] == digest(rights)
            and rights["mode"] == "FIXTURE_ONLY" and rights["provider"] == source["provider"]
            and rights["version"] == source["source_version"]
            and rights["terms_as_of_ms"] <= pub["available_at_ms"] < rights["expires_at_ms"],
            "RIGHTS_OR_TERMS")
    require(pub["release_version"] == 1 and pub["correction_of"] is None, "CORRECTION_QUARANTINE")
    require(bar.bar_open < times["oos_start_ms"], "OOS_SEALED_NO_PEEK")
    require(times["first_eligible_open_ms"] <= bar.bar_open < times["train_end_ms"]
            or protocol["validation_start_ms"] <= bar.bar_open < times["validation_end_ms"],
            "OUTSIDE_ELIGIBLE_SPLIT")
    require(type(bar.is_final) is bool and bar.is_final and bar.bar_open % STEP == 0
            and bar.bar_close == bar.bar_open + STEP - 1, "FINAL_GRID")
    require(all(math.isfinite(v) for v in (bar.open, bar.high, bar.low, bar.close, bar.volume))
            and 0 < bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
            and bar.volume >= 0, "PRICE_QUALITY")
    require(bar.bar_close < pub["available_at_ms"] == pub["first_known_at_ms"]
            <= pub["received_at_ms"] <= bar.ingested_at == bar.bar_close + 3
            and pub["received_at_ms"] <= bar.bar_close + STEP, "FIRST_RELEASE_CHRONOLOGY")
    return pub


def admit(root, protocol, journal, plan, freeze, witness, bar, receipt):
    pub = validate_publication(protocol, bar, freeze, witness, receipt)
    immutable(root / ("publication-%d.json" % bar.bar_open), canonical(receipt))
    with patch("time.time", return_value=(bar.ingested_at + 1) / 1000):
        journal.commit(bar)
    return admit_sample(root / "freeze.json", expected_freeze_sha256=freeze,
                        plan_raw=plan, journal=journal, stable_key=bar.stable_key(),
                        available_at_ms=pub["available_at_ms"], observed_at_ms=pub["received_at_ms"],
                        decision_cutoff_ms=bar.ingested_at + 1)


def market_bar(open_ms, values):
    return MarketBar(symbol="BTC-USD", interval="15m", source="MOCK:299",
                     bar_open=open_ms, bar_close=open_ms + STEP - 1,
                     open=float(values["open"]), high=float(values["high"]),
                     low=float(values["low"]), close=float(values["close"]), volume=1.0,
                     is_final=True, ingested_at=open_ms + STEP + 2).with_checksum()


def opportunities(protocol, packet):
    rows = packet["entries"] + packet["null_entries"]
    marks = {bar["open_ms"]: bar for row in rows for bar in row["bars"]}
    times = protocol["times"]
    slots = list(range(times["first_eligible_open_ms"], times["train_end_ms"], STEP))
    slots += list(range(protocol["validation_start_ms"], times["validation_end_ms"], STEP))
    candidates = {r["entry_ms"] - 2 * STEP for r in packet["entries"]}
    placebo = {r["entry_ms"] - 2 * STEP for r in packet["null_entries"]}
    for slot in slots:
        values = marks.get(slot, dict(open="100", high="101", low="99", close="100"))
        state = ("ENTRY" if slot in candidates else "UNKNOWN" if slot == STEP
                 else "REJECTED" if slot == 2 * STEP else "NO_SIGNAL")
        yield market_bar(slot, values), state, slot in placebo


def validate_report(report, packet):
    require(report["sha256"] == digest({k: v for k, v in report.items() if k != "sha256"}), "REPORT_SEAL")
    require(report["input_sha256"] == packet["sha256"] and report["actual_fills"] is None
            and report["orders_created"] == 0 and report["winner"] is None
            and report["trading_authority"] == "NONE" and report["holdout"] == "SEALED_UNOPENED"
            and report["historical_pit"] == "NOT_ATTESTED", "REPORT_AUTHORITY")
    keys = {(r["cohort"], r["entry_id"], r["scenario"], r["policy"]) for r in report["outcomes"]}
    require(len(keys) == len(report["outcomes"]) == 72 and len(report["comparisons"]) == 18,
            "MODEL_POPULATION")
    with localcontext() as ctx:
        ctx.prec = 40
        for row in report["outcomes"]:
            if row["status"].startswith("UNKNOWN"):
                require(row["net_return"] is None and row["gross_return"] is None, "UNKNOWN_PROFIT")
            elif row["status"] == "NONFILL":
                require(not row["legs"] and Decimal(row["net_return"]) == 0, "NONFILL_PROFIT")
            elif row["status"] == "MODEL_ONLY":
                legs = row["legs"]
                fraction = Decimal(row["filled_fraction"])
                cost = Decimal(row["total_cost_bps"])
                fees = sum(map(Decimal, packet["costs"][row["scenario"]].values()))
                require(sum(Decimal(x["fraction_of_initial_notional"]) for x in legs) == fraction
                        and sum(Decimal(x["total_cost_bps"]) for x in legs) == cost == fees * fraction
                        and abs(Decimal(row["gross_return"]) - Decimal(row["net_return"]) - cost / 10000)
                        < Decimal("1e-30"), "COST_ONCE")
            else:
                raise ValueError("MODEL_STATUS")


def verify_journal_scope(root, expected):
    """Check only index metadata before native replay reads payloads."""
    path = root / "journal.sqlite"
    if not path.exists():
        require(not (root / "decision.json").exists(), "MISSING_FINAL_CUSTODY")
        return
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT stable_key,bar_open,symbol,interval,source FROM journal_entries LIMIT 51").fetchall()
    finally:
        db.close()
    observed = set(rows)
    require(len(rows) == len(observed) and observed <= expected, "FOREIGN_OR_HOLDOUT_CUSTODY")
    if (root / "decision.json").exists():
        require(observed == expected, "MISSING_FINAL_CUSTODY")


def run(root, crash=False):
    verify()
    root = Path(root).absolute()
    for path in (root, *root.parents):
        require(not path.is_symlink() and not (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400),
                "CUSTODY_REPARSE")
    if root.exists():
        require((root / "protocol.json").is_file(), "UNOWNED_CUSTODY")
        for path in root.iterdir():
            require(not path.is_symlink() and not getattr(path.lstat(), "st_file_attributes", 0) & 0x400,
                    "CUSTODY_REPARSE")
    else:
        root.mkdir()
    protocol, packet = configuration()
    samples = list(opportunities(protocol, packet))
    verify_journal_scope(root, {(bar.stable_key(), bar.bar_open, bar.symbol, bar.interval, bar.source)
                               for bar, _, _ in samples})
    envelope = decode(Path(__file__).with_name("owner-envelope.json").read_bytes())
    require(envelope["status"] == "PENDING_OWNER_DECISION"
            and envelope["collection"] == "NOT_ACTIVATED"
            and all(v is None for v in envelope["owner_decision"].values()), "OWNER_ENVELOPE_SCOPE")
    journal, plan, freeze, witness = prepare(root, protocol)
    rows = []
    for bar, state, placebo in samples:
        ack = admit(root, protocol, journal, plan, freeze, witness, bar, publication(protocol, bar, freeze))
        rows.append(dict(open_ms=bar.bar_open, state=state, placebo=placebo, ack=ack))
        if crash:
            os._exit(73)
    require(len(rows) == protocol["opportunity_budget"] == len({r["open_ms"] for r in rows}), "OPPORTUNITY_CENSUS")
    require(len(journal.replay(symbol="BTC-USD", interval="15m", limit=51)) == len(rows), "JOURNAL_CENSUS")
    acks = {r["open_ms"]: r["ack"] for r in rows}
    for entry in packet["entries"] + packet["null_entries"]:
        require(acks[entry["entry_ms"] - 2 * STEP]["commit_return_observed_at_ms"] <= entry["signal_ms"]
                < entry["entry_ms"], "FUTURE_FEATURE")
        for mark in entry["bars"]:
            bar = market_bar(mark["open_ms"], mark)
            require(acks[mark["open_ms"]]["content_sha256"] == fingerprint(content(bar)), "MODEL_SOURCE_SWAP")
    verify_research_plan(plan, witness["payload"]["plan_sha256"])
    require(packet["sha256"] == protocol["model_inputs_sha256"], "UNAPPROVED_MODEL_OR_TRIAL")
    store = root / "factory.sqlite"
    if not store.exists():
        migrate_store_v2(store)
    result = run_factory_h_execution_comparison(packet, store)
    db = sqlite3.connect(store.as_uri() + "?mode=ro", uri=True)
    try:
        stored = db.execute("SELECT document FROM factory_h_research_results_v1 WHERE experiment_id=?",
                            (packet["experiment_id"],)).fetchone()
    finally:
        db.close()
    package = json.loads(stored[0])
    require(package["sha256"] == result["package_sha256"]
            == digest({k: v for k, v in package.items() if k != "sha256"}), "FACTORY_ACK")
    report = package["comparison"]
    require(report["sha256"] == result["report_sha256"], "FACTORY_REPORT_ACK")
    validate_report(report, packet)
    immutable(root / "factory-report.json", canonical(report))
    regimes = {}
    for row in report["outcomes"]:
        regime = protocol["regime_labels"][row["entry_id"]]
        regimes.setdefault(regime, Counter())[row["status"]] += 1
    body = dict(schema="aql.pit-oos.readiness-receipt.v1", status="PIT_OOS_READINESS_ARMED",
                real_science="REAL_PIT_OOS_BLOCKED", collection="NOT_ACTIVATED", authority="NONE",
                protocol_sha256=digest(protocol), freeze_sha256=freeze,
                plan_sha256=witness["payload"]["plan_sha256"], report_sha256=report["sha256"],
                package_sha256=package["sha256"],
                holdout="SEALED_UNOPENED", cohort_prices_opened=0,
                opportunities=rows, opportunity_census=dict(Counter(r["state"] for r in rows)),
                trial_census=dict(Counter(r["state"] for r in protocol["candidates"])),
                outcome_census=dict(Counter(r["status"] for r in report["outcomes"])),
                comparisons=18, regime_outcome_census=regimes, scientific_inference="NOT_ESTIMABLE",
                owner_envelope_sha256=digest(envelope), blockers=BLOCKERS)
    receipt = {**body, "sha256": digest(body)}
    immutable(root / "decision.json", canonical(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--crash", action="store_true")
    args = parser.parse_args()
    result = run(args.root, args.crash)
    print(json.dumps({k: v for k, v in result.items() if k != "opportunities"}, sort_keys=True))


if __name__ == "__main__":
    main()
