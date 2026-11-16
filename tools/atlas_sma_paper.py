"""Bounded SMA3/12 acceptance. The only producer uses generated TEST_ONLY bars."""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from aql.observation.contracts import PaperIntent, digest
from aql.paper_sim.adapter import signals_from_prospective
from aql.paper_sim.contracts import Policy, bar, sha
from aql.paper_sim.engine import PaperSimulator
from research_wp_r0.strategy_definition import StrategyDefinition
from tools.actual_research_batch_bridge.bridge import alternate_plan
from tools.atlas_saved_research_disposition import publish, require, without_seal
from tools.scanner_strategy_f.research_e2e_diagnostic import _code_sha, _eval_strategy

STEP = 900_000
START = 1_700_001_000_000 // STEP * STEP
STRATEGY = "79c6f9ff291b14bf55434367ef039c61f8899f63c351fe47a85d647dc33a9f58"
POLICY = Policy()
PHASES = {"CLOSED", "CANCELLED", "EXPIRED", "NO_FILL", "UNKNOWN", "REJECTED"}
HERE = Path(__file__).resolve().parent


def seal(body):
    return {**body, "sha256": digest(body)}


def fixture():
    rows = []
    for i in range(19):
        start = START + i * STEP
        close = "100" if i < 12 else "100.1"
        rows.append(dict(symbol="BTCUSDT", open_ms=start, close_ms=start + STEP - 1,
                         received_ms=start + STEP + 1000, open="100",
                         high="104" if i == 14 else "100.2", low="99.9", close=close,
                         final=True, clock_verified=True, synthetic=True,
                         taker_qty="2" if i == 14 else "0", maker_volume=None))
    return rows


def frozen_definition():
    plan = json.loads((HERE / "first_research_cycle/market-plan.json").read_bytes())
    definition = StrategyDefinition.from_dict(alternate_plan(plan)["strategy"])
    require(definition.digest == STRATEGY, "SMA_PAPER_STRATEGY_PIN")
    return definition


def verify_bars(bars):
    require(len(bars) == 19, "SMA_PAPER_FIXTURE_SIZE")
    for i, row in enumerate(bars):
        start = START + i * STEP
        require(row["symbol"] == "BTCUSDT" and row["open_ms"] == start
                and row["close_ms"] == start + STEP - 1, "SMA_PAPER_SOURCE_GRID")
        require(row["final"] is True and row["clock_verified"] is True
                and row["received_ms"] == start + STEP + 1000, "SMA_PAPER_SOURCE_CLOCK")
        bar(row, as_of_ms=row["received_ms"])
    require(bars == fixture(), "SMA_PAPER_SOURCE_GENERATED_ONLY")


def build_receipt(bars, definition):
    verify_bars(bars)
    source = digest(bars)
    run = dict(strategy_id=definition.spec["strategy_id"], strategy_version="v1",
               definition_sha256=STRATEGY, evaluator_sha256=_code_sha(),
               config_sha256=digest(dict(policy=asdict(POLICY), interval_ms=STEP,
                                         fill="FIRST_STRICTLY_POST_DECISION_OPEN",
                                         source=source, cohort="GENERATED_ACCEPTANCE_V1")),
               evidence_mode="SYNTHETIC_TESTED")
    shaped = [dict(bar_open_ms=b["open_ms"], bar_close_ms=b["close_ms"],
                   volume=1, **{key: float(b[key]) for key in ("open", "high", "low", "close")})
              for b in bars]
    decisions = _eval_strategy(definition, shaped)
    rows = []
    for i, (b, (close_ms, state)) in enumerate(zip(bars, decisions, strict=True)):
        require(decisions[i] == _eval_strategy(definition, shaped[:i + 1])[-1],
                "SMA_PAPER_PREFIX_DRIFT")
        row_hash = digest(b)
        parent = dict(key=f"BTCUSDT:15m:{b['open_ms']}", open_ms=b["open_ms"], close_ms=close_ms,
                      ingested_ms=b["received_ms"], commit_ms=b["received_ms"],
                      bar_checksum=row_hash, content_sha256=row_hash,
                      g1_receipt_sha256=digest({"simulated_source": source, "row": row_hash}))
        decision = dict(run=run, parent=parent, cutoff_ms=b["received_ms"], state=state,
                        trading_authority="NONE")
        if state == "ENTRY_SIGNAL":
            decision["opportunity_id"] = digest(decision)
        rows.append(dict(decision=decision, decision_sha256=digest(decision), source_valid=True))
    return seal(dict(schema="aql.g2.prospective-verified-read.v1", trading_authority="NONE",
                     run=run, rows=rows, visible_sha256=digest(rows),
                     as_of_ms=bars[-1]["received_ms"], fixture_source_sha256=source))


def admit(receipt, bars, definition, expected):
    require(receipt.get("schema") == "aql.g2.prospective-verified-read.v1"
            and receipt.get("run", {}).get("evidence_mode") == "SYNTHETIC_TESTED",
            "SMA_PAPER_RETROSPECTIVE_OR_UNSUPPORTED_SOURCE")
    require(receipt["run"].get("definition_sha256") == STRATEGY, "SMA_PAPER_FOREIGN_STRATEGY")
    require(receipt.get("sha256") == expected == without_seal(receipt), "SMA_PAPER_RECEIPT_PIN")
    trusted = build_receipt(bars, definition)
    require(receipt["fixture_source_sha256"] == trusted["fixture_source_sha256"],
            "SMA_PAPER_SOURCE_PARENT")
    require(receipt == trusted, "SMA_PAPER_SCANNER_PARENT")
    return signals_from_prospective(receipt, expected_sha=expected, expected_run=trusted["run"],
                                    as_of_ms=trusted["as_of_ms"])


def simulate(sim, bars, receipt, projection, definition):
    signals = {item["source_sha256"]: item for item in projection["signals"]}
    run_id = digest({"scanner_receipt": receipt["sha256"], "config": receipt["run"]["config_sha256"]})
    risk = definition.spec["risk"]
    active = None
    decisions = []
    for i, (b, row) in enumerate(zip(bars, receipt["rows"], strict=True)):
        decision = row["decision"]
        at = decision["cutoff_ms"]
        step = row["decision_sha256"]
        if active is not None:
            key, first_open, expiry, opened = active
            if b["open_ms"] >= first_open:
                state = sim.apply(key, "bar-" + step, dict(op="bar", at_ms=at, bar=b))
                if state["phase"] not in PHASES and state["entry_remaining"] != "0" and at > expiry:
                    state = sim.apply(key, "expire-" + step, dict(op="expire", at_ms=at))
                if state["phase"] in PHASES:
                    active = None
                elif state["phase"] == "TRIGGERED" and state["exit_due_ms"] is None and (
                        decision["state"] == "EXIT_SIGNAL" or i - opened >= risk["holding_bars"]):
                    sim.apply(key, "exit-" + step, dict(op="exit", at_ms=at))
        signal = signals.get(step)
        proposed = signal is not None and active is None and i + 1 + risk["entry_ttl_bars"] < len(bars)
        intent = PaperIntent(step, digest({"run": run_id, "decision": step}),
                             "proposed" if proposed else "declined")
        key = None
        reason = "ACCEPTED_ISOLATED_SIMULATION" if proposed else decision["state"]
        if signal is not None and not proposed:
            reason = "POSITION_ALREADY_ACTIVE" if active else "BOUNDED_FOLLOWUP_UNAVAILABLE"
        if proposed:
            watch = dict(op="watch", at_ms=at, instance=intent.intent_id,
                         signal=signal, policy=asdict(POLICY))
            key = sim.identity(watch)
            sim.apply(key, "watch", watch)
            price = Decimal(b["close"])
            first = (at // STEP + 1) * STEP
            expiry = first + risk["entry_ttl_bars"] * STEP - 1
            arm = dict(op="arm", at_ms=at, mode="taker", qty="1", limit=str(price), queue_ahead="0",
                       stop=str(price * (1 - Decimal(str(risk["stop_fraction"])))),
                       target=str(price * (1 + Decimal(str(risk["target_fraction"])))),
                       expiry_ms=expiry)
            sim.apply(key, "arm", arm)
            active = key, first, expiry, i
        decisions.append(dict(intent=asdict(intent), simulation_id=key, reason=reason,
                              scanner_decision_sha256=step))
    require(active is None, "SMA_PAPER_UNFINISHED_FIXTURE")
    return run_id, decisions


def denied(label, expected, operation):
    try:
        operation()
    except ValueError as exc:
        require(str(exc) == expected, "SMA_PAPER_UNEXPECTED_ERROR_" + label)
        return dict(case=label, reason=str(exc), recovery="DENIED_NO_NEW_EVENT")
    raise ValueError("SMA_PAPER_UNEXPECTED_ACCEPTANCE_" + label)


def run(root):
    bars = fixture()
    definition = frozen_definition()
    receipt = build_receipt(bars, definition)
    pin = receipt["sha256"]
    root.mkdir()
    path = root / "virtual.jsonl"
    publish(root / "scanner.json", receipt)
    projection = admit(receipt, bars, definition, pin)
    sim = PaperSimulator(path)
    run_id, decisions = simulate(sim, bars, receipt, projection, definition)
    before = path.read_bytes()
    event = next(iter(sim.journal.ledger.events.values()))
    watch = json.loads(event.reason)["command"]
    require(sim.apply(event.position_id, event.event_id, watch) == sim.states[event.position_id]
            and path.read_bytes() == before, "SMA_PAPER_DUPLICATE_WRITE")
    errors = []
    conflict = {**watch, "instance": "different"}
    errors.append(denied("conflicting_duplicate", "PAPER_SIM_COMMAND_CONFLICT",
                         lambda: sim.apply(event.position_id, event.event_id, conflict)))
    errors.append(denied("retrospective_census", "SMA_PAPER_RETROSPECTIVE_OR_UNSUPPORTED_SOURCE",
                         lambda: admit({"schema": "aql.first-cycle.scanner-census-receipt.v1"},
                                       bars, definition, pin)))
    for label, reason in (("tamper", "RECEIPT_PIN"), ("source", "SOURCE_PARENT"),
                          ("clock", "SOURCE_CLOCK"), ("foreign_strategy", "FOREIGN_STRATEGY"),
                          ("scanner_parent", "SCANNER_PARENT")):
        changed = deepcopy(receipt)
        input_bars = deepcopy(bars)
        expected = pin
        if label == "tamper":
            changed["rows"].pop()
        elif label == "source":
            changed["fixture_source_sha256"] = "0" * 64
        elif label == "clock":
            input_bars[0]["clock_verified"] = False
        elif label == "scanner_parent":
            changed["rows"][0]["decision"]["parent"]["g1_receipt_sha256"] = "0" * 64
        else:
            changed["run"]["definition_sha256"] = "0" * 64
        if label not in {"tamper", "clock"}:
            changed["sha256"] = expected = without_seal(changed)
        errors.append(denied(label, "SMA_PAPER_" + reason,
                             lambda: admit(changed, input_bars, definition, expected)))
    require(path.read_bytes() == before, "SMA_PAPER_DENIAL_WROTE_EVENT")
    phases = Counter(state["phase"] for state in sim.states.values())
    require(phases == {"CLOSED": 1, "NO_FILL": 1}
            and projection["census"]["NO_SIGNAL"] > 0, "SMA_PAPER_ACCEPTANCE_COVERAGE")
    handoff = seal(dict(schema="atlas.sma-paper.acceptance.v1", run_id=run_id, scanner_sha256=pin,
                        strategy_sha256=STRATEGY, decisions=decisions, errors=errors,
                        journal_sha256=sha256(before).hexdigest(), replay_state_sha256=digest(sim.states),
                        duplicate="IDENTICAL_COMMAND_NO_NEW_EVENT", evidence="GENERATED_TEST_ONLY"))
    publish(root / "acceptance.json", handoff)
    return handoff["sha256"]


def replay(root, pin):
    handoff = json.loads((root / "acceptance.json").read_bytes())
    require(sha(pin) and handoff["sha256"] == pin == without_seal(handoff), "SMA_PAPER_HANDOFF_PIN")
    receipt = json.loads((root / "scanner.json").read_bytes())
    admit(receipt, fixture(), frozen_definition(), handoff["scanner_sha256"])
    path = root / "virtual.jsonl"
    require(sha256(path.read_bytes()).hexdigest() == handoff["journal_sha256"], "SMA_PAPER_JOURNAL_PIN")
    sim = PaperSimulator(path)
    states = sim.states
    require(digest(states) == handoff["replay_state_sha256"], "SMA_PAPER_REPLAY_STATE")
    proposed = {row["simulation_id"]: row for row in handoff["decisions"] if row["simulation_id"]}
    run_id = digest({"scanner_receipt": receipt["sha256"], "config": receipt["run"]["config_sha256"]})
    require(handoff["run_id"] == run_id and handoff["strategy_sha256"] == STRATEGY,
            "SMA_PAPER_RUN_LINK")
    require(set(states) == set(proposed)
            and [row["scanner_decision_sha256"] for row in handoff["decisions"]]
            == [row["decision_sha256"] for row in receipt["rows"]], "SMA_PAPER_DECISION_LINKS")
    for row in handoff["decisions"]:
        decision_id = row["scanner_decision_sha256"]
        intent = PaperIntent(decision_id, digest({"run": run_id, "decision": decision_id}),
                             "proposed" if row["simulation_id"] else "declined")
        require(row["intent"] == asdict(intent), "SMA_PAPER_DECISION_INTENT")
    for key, state in states.items():
        row = proposed[key]
        require(state["instance"] == row["intent"]["intent_id"]
                and state["signal"]["source_sha256"] == row["scanner_decision_sha256"],
                "SMA_PAPER_INTENT_LINK")
    parents = {row["decision_sha256"]: row["decision"]["parent"] for row in receipt["rows"]}
    for event in sim.journal.ledger.events.values():
        command = json.loads(event.reason)["command"]
        if command["op"] == "bar":
            row_id = event.event_id.removeprefix("bar-")
            require(digest(command["bar"]) == parents.get(row_id, {}).get("bar_checksum"),
                    "SMA_PAPER_EXECUTION_SOURCE")
    from tools.atlas_strategy_operations import isolated_paper_view
    return isolated_paper_view(handoff, receipt, states, len(sim.journal.ledger.events), POLICY)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "replay"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    args = parser.parse_args()
    if args.mode == "run":
        print(run(args.root))
    else:
        print(json.dumps(replay(args.root, args.pin), sort_keys=True))


if __name__ == "__main__":
    main()
