"""Pre-G0 promotion decisions and a read-only projection of the Paper journal."""
from decimal import Decimal, localcontext
import json
from pathlib import Path

from .observation.position_journal import DurablePositionJournal
from .observation.positions import PositionEvent
from .paper_sim.contracts import canonical, digest, ms, need, sha


EXITS = ("SINGLE_FIXED", "SINGLE_TRAILING", "MULTI_FIXED", "MULTI_TRAILING")
RECEIPT = "aql.factory.promotion-result.v1"
FACTORY_HANDOFF = "aql.factory.shadow-promotion-handoff.v1"
IDENTITY = ("strategy_id", "strategy_version", "category", "shadow_id", "code_sha256",
            "config_sha256", "protocol_sha256")
GATES = ("original_source", "source_rights", "historical_pit", "sealed_oos", "risk", "paper_operations")


def seal(body):
    return {**body, "sha256": digest(body)}


def check(document, expected, schema, fields):
    need(type(document) is dict and set(document) == {"schema", "sha256", *fields}, "PROMOTION_FIELDS")
    need(document["schema"] == schema and sha(expected) and document["sha256"] == expected
         and digest({k: v for k, v in document.items() if k != "sha256"}) == expected, "PROMOTION_PIN")


def read_factory_receipt(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 65536, "FACTORY_RECEIPT_SIZE")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "FACTORY_DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("PAPER_SIM_FACTORY_NONFINITE_JSON")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject_constant)


def assess_factory(result, *, factory_pin, policy, policy_pin, evidence, evidence_pins, at_ms):
    check(result, factory_pin, FACTORY_HANDOFF,
          ("experiment_id", "baseline", "shadow", "category", "protocol_sha256", "evidence_grade",
           "costs_sha256", "exit_families", "factory_verdict", "research_state", "blockers",
           "receipts", "eligibility"))
    for strategy in (result["baseline"], result["shadow"]):
        need(type(strategy) is dict and set(strategy) == {"id", "version", "code_sha256", "parameters_sha256"}
             and type(strategy["id"]) is str and bool(strategy["id"])
             and type(strategy["version"]) is int and strategy["version"] > 0
             and sha(strategy["code_sha256"]) and sha(strategy["parameters_sha256"]), "FACTORY_STRATEGY")
    need(result["eligibility"] == {"paper": "PAPER_BLOCKED", "live": "NOT_AUTHORIZED",
                                   "selected_live_exit": None}, "FACTORY_AUTHORITY")
    need(result["evidence_grade"] == "TEST_ONLY", "FACTORY_GRADE_UNSUPPORTED")
    receipts = result["receipts"]
    need(type(receipts) is dict and set(receipts) == {"dossier_sha256", "admission_sha256", "evaluation_sha256"}
         and all(sha(pin) for pin in receipts.values()), "FACTORY_RECEIPTS")
    families = result["exit_families"]
    need(type(families) is dict and set(families) == set(EXITS), "FACTORY_FAMILIES")
    scenarios = {}
    for method, value in families.items():
        need(type(value) is dict and set(value) == {"applicable", "reason", "results_sha256"}
             and type(value["applicable"]) is bool, "FACTORY_APPLICABILITY")
        receipt = value["results_sha256"]
        status = ("MEASURED" if receipt else "UNKNOWN") if value["applicable"] else "N/A"
        scenarios[method] = dict(status=status, reason=value["reason"], receipt_sha256=receipt)
    shadow = result["shadow"]
    normalized = seal(dict(schema=RECEIPT, strategy_id=shadow["id"], strategy_version=str(shadow["version"]),
                           category=result["category"], shadow_id=result["experiment_id"],
                           code_sha256=shadow["code_sha256"], config_sha256=shadow["parameters_sha256"],
                           protocol_sha256=result["protocol_sha256"], costs_sha256=result["costs_sha256"],
                           grade="SYNTHETIC_TESTED", verdict=result["factory_verdict"], blockers=result["blockers"],
                           attempts_sha256=receipts["evaluation_sha256"], scenarios=scenarios))
    return _assess(normalized, factory_pin=normalized["sha256"], external_pin=factory_pin, policy=policy,
                   policy_pin=policy_pin, evidence=evidence, evidence_pins=evidence_pins, at_ms=at_ms)


def _assess(result, *, factory_pin, policy, policy_pin, evidence, evidence_pins, at_ms, external_pin=None):
    """Trust roots are supplied by the caller's independent configuration."""
    ms(at_ms)
    check(result, factory_pin, RECEIPT, (*IDENTITY, "grade", "verdict", "blockers", "costs_sha256",
                                         "attempts_sha256", "scenarios"))
    factory_pin = external_pin or factory_pin
    check(policy, policy_pin, "aql.promotion.protocol.v1",
          (*IDENTITY, "costs_sha256", "applicability", "exclusions", "shadow_until_ms", "source_max_age_ms"))
    need(all(result[key] == policy[key] for key in (*IDENTITY, "costs_sha256")), "PROMOTION_IDENTITY")
    need(all(type(result[key]) is str and 0 < len(result[key]) <= 128 for key in IDENTITY[:4])
         and all(sha(result[key]) for key in (*IDENTITY[4:], "costs_sha256", "attempts_sha256")),
         "PROMOTION_IDENTITY_FORMAT")
    need(result["verdict"] in ("SCIENTIFIC_PASS", "SCIENTIFIC_FAIL", "INCONCLUSIVE", "BLOCKED")
         and result["grade"] in ("SYNTHETIC_TESTED", "ORIGINAL_PIT_OOS")
         and type(result["blockers"]) is list
         and all(type(item) is str and item for item in result["blockers"]), "PROMOTION_VERDICT")
    need(set(result["scenarios"]) == set(policy["applicability"]) == set(EXITS), "PROMOTION_SCENARIO_CENSUS")
    need(set(policy["exclusions"]) == {method for method in EXITS if policy["applicability"][method] is False},
         "PROMOTION_EXCLUSIONS")
    for method in EXITS:
        scenario = result["scenarios"][method]
        applicable = policy["applicability"][method]
        need(type(applicable) is bool and type(scenario) is dict
             and set(scenario) == {"status", "reason", "receipt_sha256"}
             and (scenario["status"] in ("MEASURED", "UNKNOWN") if applicable else scenario["status"] == "N/A")
             and (sha(scenario["receipt_sha256"]) if scenario["status"] == "MEASURED"
                  else scenario["receipt_sha256"] is None and type(scenario["reason"]) is str and bool(scenario["reason"])),
             "PROMOTION_SCENARIO")
        if not applicable:
            need(scenario["reason"] == policy["exclusions"][method], "PROMOTION_EXCLUSION_DRIFT")
    need(0 < ms(policy["source_max_age_ms"]), "PROMOTION_FRESHNESS_POLICY")
    horizon = ms(policy["shadow_until_ms"])
    blockers = set(result["blockers"])
    blockers.update("SCENARIO_UNKNOWN_" + method for method in EXITS
                    if result["scenarios"][method]["status"] == "UNKNOWN")
    if result["verdict"] != "SCIENTIFIC_PASS":
        blockers.add(result["verdict"])
    if result["grade"] != "ORIGINAL_PIT_OOS":
        blockers.add("ORIGINAL_PIT_OOS_NOT_ATTESTED")
    risk_pin = None
    for gate in GATES:
        if gate not in evidence or gate not in evidence_pins:
            blockers.add(gate.upper() + "_MISSING")
            continue
        entry = evidence[gate]
        check(entry, evidence_pins[gate], "aql.promotion.gate.v1",
              ("gate", "result_sha256", "policy_sha256", "status", "valid_from_ms", "expires_ms"))
        need(entry["gate"] == gate and entry["result_sha256"] == factory_pin
             and entry["policy_sha256"] == policy_pin, "PROMOTION_GATE_BINDING")
        if entry["status"] != "PASS" or not ms(entry["valid_from_ms"]) <= at_ms < ms(entry["expires_ms"]):
            blockers.add(gate.upper() + "_NOT_CURRENT")
        elif gate == "risk":
            risk_pin = evidence_pins[gate]
    promotion = not blockers.difference({"PAPER_OPERATIONS_MISSING", "PAPER_OPERATIONS_NOT_CURRENT"})
    return seal(dict(schema="aql.promotion.assessment.v1", **{key: result[key] for key in IDENTITY},
                     factory_sha256=factory_pin, policy_sha256=policy_pin, scientific=result["verdict"],
                     promotion="PROMOTION_PASS" if promotion else "PROMOTION_BLOCKED",
                     paper="PAPER_ELIGIBLE" if not blockers else "PAPER_BLOCKED",
                     shadow="OBSERVATION_ONLY" if blockers and at_ms < horizon
                     and result["verdict"] != "SCIENTIFIC_FAIL" else "INACTIVE",
                     blockers=sorted(blockers), scenarios=result["scenarios"], assessed_at_ms=at_ms,
                     source_max_age_ms=policy["source_max_age_ms"], costs_sha256=result["costs_sha256"],
                     risk_sha256=risk_pin, authority="NONE"))


def check_assessment(assessment, pin):
    check(assessment, pin, "aql.promotion.assessment.v1",
          (*IDENTITY, "factory_sha256", "policy_sha256", "scientific", "promotion", "paper",
           "shadow", "blockers", "scenarios", "assessed_at_ms", "source_max_age_ms",
           "costs_sha256", "risk_sha256", "authority"))
    need(assessment["authority"] == "NONE", "ASSESSMENT_AUTHORITY")


def live_candidate(assessment, selected_exit, *, assessment_pin, strategy_version, risk_sha256, costs_sha256):
    check_assessment(assessment, assessment_pin)
    need(assessment["paper"] == "PAPER_ELIGIBLE" and selected_exit in EXITS
         and assessment["scenarios"][selected_exit]["status"] == "MEASURED"
         and strategy_version == assessment["strategy_version"]
         and sha(risk_sha256) and risk_sha256 == assessment["risk_sha256"]
         and sha(costs_sha256) and costs_sha256 == assessment["costs_sha256"],
         "LIVE_CANDIDATE_EVIDENCE")
    return seal(dict(schema="aql.promotion.live-candidate.v1", assessment_sha256=assessment["sha256"],
                     strategy_version=strategy_version, exit_method=selected_exit, risk_sha256=risk_sha256,
                     costs_sha256=costs_sha256, recommendation="LIVE_CANDIDATE", authority="NONE"))


class Lifecycle:
    """Durable research/fixture lifecycle. Pins come from independent configuration."""

    source = "PROMOTION_RESEARCH_FIXTURE_ONLY_V1"

    def __init__(self, path, assessment, *, assessment_pin, owner_pins=(), max_events=128):
        check_assessment(assessment, assessment_pin)
        need(type(max_events) is int and 1 <= max_events <= 1024, "LIFECYCLE_SCOPE")
        self._assessment = json.loads(canonical(assessment))
        self._owner_pins = frozenset(owner_pins)
        need(all(sha(pin) for pin in self._owner_pins), "OWNER_PIN")
        path = Path(path)
        need(not path.exists() or path.stat().st_size <= max_events * 4096, "LIFECYCLE_SIZE")
        self._journal = DurablePositionJournal(path)
        self._commands = {}
        self._limit = max_events
        self._state = dict(status="PAPER_BLOCKED" if assessment["paper"] == "PAPER_BLOCKED"
                           else "PAPER_ELIGIBLE", started_at_ms=None,
                           updated_at_ms=assessment["assessed_at_ms"], uptime_ms=0, alert=None)
        for event in self._journal.ledger.events.values():
            need(event.position_id == assessment_pin and event.source == self.source
                 and event.price is None, "LIFECYCLE_JOURNAL_SCOPE")
            payload = json.loads(event.reason)
            command = payload["command"]
            state = self._transition(command)
            need(digest(state) == payload["state_sha256"] and event.event_ms == event.received_ms == command["at_ms"],
                 "LIFECYCLE_REPLAY")
            self._state = state
            self._commands[event.event_id] = command
        need(len(self._commands) <= max_events, "LIFECYCLE_CAPACITY")

    @property
    def assessment(self):
        return json.loads(canonical(self._assessment))

    @property
    def state(self):
        return self._state.copy()

    def _transition(self, command):
        need(type(command) is dict and set(command) == {"op", "at_ms", "proof"}, "LIFECYCLE_COMMAND")
        now = ms(command["at_ms"])
        prior = self._state
        need(now >= prior["updated_at_ms"] and prior["status"] != "RETIRED", "LIFECYCLE_CLOCK_OR_RETIRED")
        operation, proof = command["op"], command["proof"]
        started, uptime, alert = prior["started_at_ms"], prior["uptime_ms"], None
        if prior["status"] == "PAPER_ACTIVE_FIXTURE":
            uptime += now - prior["updated_at_ms"]
        if operation == "simulate_activation":
            need(prior["status"] == "PAPER_ELIGIBLE" and now == self._assessment["assessed_at_ms"]
                 and proof == "DISPOSABLE_TEST_ONLY", "PAPER_ACTIVATION_DENIED")
            status, started = "PAPER_ACTIVE_FIXTURE", now
        elif operation == "safety_pause":
            need(prior["status"] == "PAPER_ACTIVE_FIXTURE", "PAPER_PAUSE_STATE")
            need(type(proof) is dict and set(proof) == {"source_at_ms", "source_valid"}
                 and type(proof["source_valid"]) is bool, "PAPER_PAUSE_PROOF")
            source_at = proof["source_at_ms"]
            need(source_at is None or ms(source_at) <= now, "PAPER_SOURCE_FUTURE")
            need(not proof["source_valid"] or source_at is None
                 or now - source_at > self._assessment["source_max_age_ms"], "PAPER_SOURCE_HEALTHY")
            status, alert = "TECHNICAL_PAUSE", "SOURCE_UNAVAILABLE_INVALID_OR_STALE"
        elif operation == "retire":
            need(type(proof) is dict and proof.get("sha256") in self._owner_pins, "OWNER_APPROVAL_REQUIRED")
            check(proof, proof["sha256"], "aql.promotion.owner-decision.v1",
                  ("assessment_sha256", "operation", "valid_from_ms", "expires_ms"))
            need(proof["operation"] == "retire" and proof["assessment_sha256"] == self._assessment["sha256"]
                 and ms(proof["valid_from_ms"]) <= now < ms(proof["expires_ms"]), "OWNER_APPROVAL_SCOPE")
            status = "RETIRED"
        else:
            raise ValueError("PAPER_SIM_ACTION_DENIED")
        return dict(status=status, started_at_ms=started, updated_at_ms=now, uptime_ms=uptime, alert=alert)

    def apply(self, command_id, command):
        need(type(command_id) is str and 0 < len(command_id) <= 128, "LIFECYCLE_COMMAND_ID")
        encoded = canonical(command)
        need(len(encoded) <= 2048, "LIFECYCLE_COMMAND_SIZE")
        frozen = json.loads(encoded)
        if command_id in self._commands:
            need(frozen == self._commands[command_id], "LIFECYCLE_CONFLICT")
            return self.state
        need(len(self._commands) < self._limit, "LIFECYCLE_CAPACITY")
        state = self._transition(frozen)
        kind = "opened" if not self._commands else "closed" if state["status"] == "RETIRED" else "quote"
        at = frozen["at_ms"]
        event = PositionEvent(self._assessment["sha256"], command_id, kind, at, at, self.source,
                              reason=canonical(dict(command=frozen, state_sha256=digest(state))))
        self._journal.append(event)
        self._commands[command_id] = frozen
        self._state = state
        return self.state

    def apply_simulated(self, simulator, simulation_id, command_id, command, *, source_at_ms, source_valid):
        """Gate writes to the existing simulator while the fixture is active."""
        need(self._state["status"] == "PAPER_ACTIVE_FIXTURE", "PAPER_SIMULATION_INACTIVE")
        now = ms(command.get("at_ms"))
        need(now >= self._state["updated_at_ms"], "PAPER_SIMULATION_CLOCK")
        need(type(source_valid) is bool and (source_at_ms is None or ms(source_at_ms) <= now),
             "PAPER_SOURCE_PROOF")
        if not source_valid or source_at_ms is None or now - source_at_ms > self._assessment["source_max_age_ms"]:
            proof = {"source_at_ms": source_at_ms, "source_valid": source_valid}
            self.apply("safety:" + digest([now, proof]), dict(op="safety_pause", at_ms=now, proof=proof))
            raise ValueError("PAPER_SIM_SOURCE_SAFETY_PAUSE")
        if command.get("op") == "watch":
            instance, signal = command.get("instance"), command.get("signal", {})
        else:
            prior = simulator.states.get(simulation_id, {})
            instance, signal = prior.get("instance"), prior.get("signal", {})
        need(instance == self._assessment["sha256"]
             and all(signal.get(key) == self._assessment[key]
                     for key in ("strategy_id", "strategy_version", "config_sha256")),
             "PAPER_SIMULATION_IDENTITY")
        return simulator.apply(simulation_id, command_id, command)


def dashboard(manager, simulator, *, as_of_ms, source_at_ms=None):
    """Read journal-derived simulated effects. Unavailable marks remain null."""
    ms(as_of_ms)
    lifecycle = manager.state
    assessment = manager.assessment
    start = lifecycle["started_at_ms"]
    need(as_of_ms >= lifecycle["updated_at_ms"], "DASHBOARD_AS_OF")
    source_age = None if source_at_ms is None else as_of_ms - ms(source_at_ms)
    need(source_age is None or source_age >= 0, "DASHBOARD_FUTURE_SOURCE")
    trades = []
    with localcontext() as context:
        context.prec = 160
        for key, item in simulator.states.items():
            if item["instance"] != assessment["sha256"]:
                continue
            signal = item["signal"]
            need(start is not None and signal["decision_ms"] >= start
                 and all(signal[k] == assessment[k] for k in ("strategy_id", "strategy_version", "config_sha256"))
                 and item["updated_ms"] <= as_of_ms, "DASHBOARD_JOURNAL_BINDING")
            complete = item["phase"] == "CLOSED"
            gross = Decimal(item["exit_notional"]) - Decimal(item["entry_notional"]) if complete else None
            fees, adverse = Decimal(item["fees"]), Decimal(item["adverse_cost"])
            net = Decimal(item["net_pnl"]) if complete else None
            need(not complete or gross - fees - adverse == net, "DASHBOARD_NET")
            trades.append(dict(simulation_id=key, phase=item["phase"], reason=item["reason"],
                               updated_ms=item["updated_ms"], gross=None if gross is None else str(gross),
                               net=None if net is None else str(net), fees=str(fees), adverse=str(adverse),
                               fills=item["fills"], evidence_grade=item["evidence_grade"]))
        trades.sort(key=lambda item: (item["updated_ms"], item["simulation_id"]))
        closed = [item for item in trades if item["phase"] == "CLOSED"]
        equity = peak = drawdown = gross = Decimal(0)
        for item in closed:
            equity += Decimal(item["net"])
            gross += Decimal(item["gross"])
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        uptime = lifecycle["uptime_ms"]
        if lifecycle["status"] == "PAPER_ACTIVE_FIXTURE":
            uptime += as_of_ms - lifecycle["updated_at_ms"]
        days = Decimal(uptime) / 86400000
        freshness = ("UNKNOWN" if source_age is None else "FRESH"
                     if source_age <= assessment["source_max_age_ms"] else "STALE")
        return dict(schema="aql.promotion.dashboard.v1", **{key: assessment[key] for key in IDENTITY},
                    status=lifecycle["status"], start_ms=start, uptime_ms=uptime, trades=trades,
                    closed_trades=len(closed), active_day_denominator=str(days),
                    mean_closed_trades_per_active_day=str(Decimal(len(closed) * 86400000) / uptime)
                    if uptime else None,
                    realized_gross=str(gross) if closed else None, realized_net=str(equity) if closed else None,
                    closed_trade_drawdown=str(drawdown) if closed else None,
                    source_age_ms=source_age, freshness=freshness, actual_execution="NONE",
                    scenarios={"classification":"COUNTERFACTUAL_RESEARCH", "results":assessment["scenarios"]},
                    recommendation="CONTINUE" if lifecycle["status"] == "PAPER_ACTIVE_FIXTURE" and freshness == "FRESH"
                    else "CLOSE" if lifecycle["status"] == "RETIRED" else None,
                    assessment_sha256=assessment["sha256"], authority="NONE")
