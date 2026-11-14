"""Lab-origin Shadow admission and immutable research-only Factory handoff."""
from decimal import Decimal, localcontext
from contextlib import closing
from hashlib import sha256
import json
from math import comb
from pathlib import Path
import re
import sqlite3

from .aql_factory_e_research_results_store_v1 import (
    ResultsStoreError, _attempts, _check_seal, _seal, _sha, digest,
)
from .aql_factory_h_research_package_v1 import TABLE, _store_package
from .aql_factory_shadow_exits_v1 import (
    COST_CASES, FAMILIES, compare, need, number, summarize, validate_costs, validate_family,
)


DOSSIER = "aql.factory.lab-shadow-dossier.v1"
PROTOCOL = "aql.factory.shadow-protocol.v1"
EVALUATION = "aql.factory.shadow-evaluation.v1"
HANDOFF = "aql.factory.shadow-promotion-handoff.v1"
CATEGORIES = {"SCALP", "INTRADAY", "SWING", "LONG_TERM"}
GRADES = {"TEST_ONLY", "RETROSPECTIVE_NON_PIT", "PROSPECTIVE_UNATTESTED"}


def token(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value) is not None


def positive(value):
    return type(value) is int and value > 0


def identity(value):
    return type(value) is dict and set(value) == {
        "id", "version", "code_sha256", "parameters_sha256"
    } and token(value["id"]) and positive(value["version"]) and all(
        _sha(value[key]) for key in ("code_sha256", "parameters_sha256"))


def check_protocol(protocol, expected, dossier):
    _check_seal(protocol)
    need(protocol["sha256"] == expected == dossier["protocol_sha256"], "PROTOCOL_PIN")
    need(set(protocol) == {
        "schema", "sha256", "category", "evaluator", "protocol_custodian", "frozen_at",
        "train", "validation", "evaluation", "holdout", "embargo_ms", "step_ms",
        "holding_horizon_ms", "min_pairs", "min_net_delta", "alpha", "family_tests",
        "primary_family", "exit_families", "baseline_exit", "costs", "market",
    } and protocol["schema"] == PROTOCOL, "PROTOCOL_FIELDS")
    need(protocol["category"] == dossier["category"] and protocol["market"] == dossier["market"],
         "CATEGORY_OR_MARKET")
    need(all(token(protocol[key]) and protocol[key] != dossier["proposer"]
             for key in ("evaluator", "protocol_custodian")), "SELF_APPROVAL")
    windows = [protocol[key] for key in ("train", "validation", "evaluation", "holdout")]
    for window in windows:
        need(type(window) is list and len(window) == 2 and
             all(type(value) is int and 0 <= value < 253402300800000 for value in window)
             and window[0] < window[1], "CHRONOLOGY_WINDOW")
    embargo = protocol["embargo_ms"]
    need(positive(embargo) and positive(protocol["holding_horizon_ms"])
         and embargo >= protocol["holding_horizon_ms"]
         and all(right[0] - left[1] >= embargo for left, right in zip(windows, windows[1:]))
         and type(protocol["frozen_at"]) is int
         and windows[1][1] <= protocol["frozen_at"] < windows[2][0], "FROZEN_CHRONOLOGY")
    need(protocol["step_ms"] == dossier["candle_ms"]
         and protocol["holding_horizon_ms"] == dossier["holding_horizon_ms"]
         and protocol["holding_horizon_ms"] >= protocol["step_ms"], "CATEGORY_POLICY")
    families = protocol["exit_families"]
    need(type(families) is dict and set(families) == set(FAMILIES), "FAMILY_SET")
    for name in FAMILIES:
        validate_family(name, families[name])
    primary = protocol["primary_family"]
    need(type(primary) is str and primary in FAMILIES and families[primary]["applicable"],
         "PRIMARY_NOT_APPLICABLE")
    baseline = protocol["baseline_exit"]
    need(type(baseline) is dict and set(baseline) == {"family", "policy"}
         and baseline["family"] in FAMILIES, "BASELINE_POLICY")
    validate_family(baseline["family"], baseline["policy"])
    need(baseline["policy"]["applicable"], "BASELINE_REQUIRED")
    need(positive(protocol["min_pairs"]) and protocol["min_pairs"] <= 1000
         and positive(protocol["family_tests"])
         and protocol["family_tests"] >= sum(spec["applicable"] for spec in families.values())
         and protocol["family_tests"] <= 10000
         and 0 < number(protocol["alpha"]) < 1
         and number(protocol["min_net_delta"]) >= 0, "FROZEN_THRESHOLDS")
    validate_costs(protocol["costs"])


def check_dossier(dossier, protocol, *, expected_protocol, expected_dossier, attachments):
    _check_seal(dossier)
    need(dossier["sha256"] == expected_dossier, "DOSSIER_PIN")
    need(set(dossier) == {
        "schema", "sha256", "experiment_id", "baseline", "shadow", "category", "origin",
        "proposer", "hypothesis", "falsification", "counterexamples_sha256", "market",
        "candle_ms", "holding_horizon_ms", "protocol_sha256", "decision_sha256",
        "monitor_sha256", "dependencies_sha256", "previous_admission_sha256",
    } and dossier["schema"] == DOSSIER and dossier["origin"] == "LAB", "DOSSIER_FIELDS")
    need(token(dossier["experiment_id"]) and token(dossier["proposer"])
         and identity(dossier["baseline"]) and identity(dossier["shadow"])
         and dossier["shadow"]["id"] != dossier["baseline"]["id"]
         and dossier["category"] in CATEGORIES, "DOSSIER_IDENTITY")
    need(all(type(dossier[k]) is str and 0 < len(dossier[k]) <= 4000
             for k in ("hypothesis", "falsification"))
         and positive(dossier["candle_ms"]) and positive(dossier["holding_horizon_ms"]),
         "DOSSIER_RESEARCH")
    market = dossier["market"]
    need(type(market) is list and len(market) == 5 and all(token(k) for k in market)
         and market[1] == "SPOT", "MARKET_SCOPE")
    attached = {
        dossier["baseline"][key] for key in ("code_sha256", "parameters_sha256")
    } | {
        dossier["shadow"][key] for key in ("code_sha256", "parameters_sha256")
    } | {dossier[k] for k in (
        "counterexamples_sha256", "decision_sha256", "monitor_sha256", "dependencies_sha256")}
    need(all(_sha(pin) and pin in attachments and digest(attachments[pin]) == pin
             for pin in attached), "ATTACHMENT_PIN")
    need(dossier["decision_sha256"] != dossier["monitor_sha256"]
         and type(attachments[dossier["decision_sha256"]]) is dict
         and type(attachments[dossier["monitor_sha256"]]) is dict
         and attachments[dossier["decision_sha256"]].get("mode") == "DECISION"
         and attachments[dossier["monitor_sha256"]].get("mode") == "MONITOR_ONLY",
         "INDICATOR_AUTHORITY")
    check_protocol(protocol, expected_protocol, dossier)


def check_dataset(data, data_pin, protocol):
    _check_seal(data)
    need(data["sha256"] == data_pin and set(data) == {
        "schema", "sha256", "market", "source_sha256", "grade", "universe", "entries",
        "attempts", "known_at_attested", "holdout", "native_factory_receipt_sha256",
    } and data["schema"] == "aql.factory.shadow-cohort.v1", "COHORT_PIN")
    need(data["market"] == protocol["market"] and data["grade"] in GRADES
         and data["known_at_attested"] is False and data["holdout"] == "SEALED_UNOPENED"
         and _sha(data["source_sha256"]) and (data["native_factory_receipt_sha256"] is None
              or _sha(data["native_factory_receipt_sha256"])), "COHORT_AUTHORITY")
    _attempts(data["attempts"])
    need(all(row["source_receipt_sha256"] == data["source_sha256"] for row in data["attempts"]),
         "ATTEMPT_SOURCE")
    universe = data["universe"]
    entries = data["entries"]
    need(type(universe) is list and 0 < len(universe) <= 1000
         and all(token(item) for item in universe) and len(set(universe)) == len(universe)
         and type(entries) is list and len(entries) <= len(universe), "OPPORTUNITY_UNIVERSE")
    attempts = {attempt["attempt_id"]: attempt for attempt in data["attempts"]}
    selected = {key for key, value in attempts.items() if value["state"] == "SELECTED"}
    seen, used = set(), set()
    start, end = protocol["evaluation"]
    step = protocol["step_ms"]
    last_end = start
    for row in entries:
        need(type(row) is dict and set(row) == {
            "id", "attempt_id", "signal_at", "entry_at", "price", "maker_fraction", "bars"
        } and token(row["id"]) and row["id"] in universe and row["id"] not in seen
             and token(row["attempt_id"]) and row["attempt_id"] in selected
             and row["attempt_id"] not in used
             and attempts[row["attempt_id"]]["candidate_id"] == row["id"], "MATCHED_ENTRY")
        seen.add(row["id"])
        used.add(row["attempt_id"])
        t = row["entry_at"]
        need(type(t) is int and type(row["signal_at"]) is int
             and last_end <= t < end and start <= row["signal_at"] < t and t % step == 0
             and number(row["price"]) > 0 and (row["maker_fraction"] is None
             or 0 <= number(row["maker_fraction"]) <= 1), "ENTRY_CHRONOLOGY_OR_FILL")
        bars = row["bars"]
        need(type(bars) is list and 0 < len(bars) <= 4096, "BARS")
        previous = t - step
        for bar in bars:
            need(type(bar) is dict and set(bar) == {"at", "open", "high", "low", "close"}
                 and type(bar["at"]) is int and t <= bar["at"] < end
                 and bar["at"] > previous and bar["at"] % step == 0
                 and bar["at"] + step <= min(end, t + protocol["holding_horizon_ms"]),
                 "BAR_CHRONOLOGY")
            o, h, low, c = (number(bar[key]) for key in ("open", "high", "low", "close"))
            need(0 < low <= min(o, c) <= max(o, c) <= h, "BAR_OHLC")
            previous = bar["at"]
        need(bars[0]["at"] == t and number(bars[0]["open"]) == number(row["price"]),
             "NEXT_OPEN_PRICE")
        last_end = previous + step
    need(used == selected, "SELECTED_ATTEMPT_CENSUS")


def classify(deltas, protocol):
    """Exact paired sign test with family correction; ties remain in census."""
    threshold = number(protocol["min_net_delta"])
    if len(deltas) < protocol["min_pairs"] or any(value is None for value in deltas):
        return {"verdict": "INCONCLUSIVE", "adjusted_p": None, "pairs": len(deltas)}
    wins = sum(value > threshold for value in deltas)
    losses = sum(value < threshold for value in deltas)
    n = wins + losses
    if n < protocol["min_pairs"]:
        return {"verdict": "INCONCLUSIVE", "adjusted_p": None, "pairs": len(deltas)}
    p = min(Decimal(1), Decimal(sum(comb(n, k) for k in range(max(wins, losses), n + 1)))
            * 2 * protocol["family_tests"] / Decimal(2 ** n))
    verdict = "INCONCLUSIVE"
    if p <= number(protocol["alpha"]):
        verdict = "SCIENTIFIC_PASS" if wins > losses else "SCIENTIFIC_FAIL"
    return {"verdict": verdict, "adjusted_p": str(p), "pairs": len(deltas),
            "wins": wins, "losses": losses, "ties": len(deltas) - n}


def evaluate(protocol, data):
    with localcontext() as ctx:
        ctx.prec = 50
        return _evaluate(protocol, data)


def _evaluate(protocol, data):
    by_id = {row["id"]: row for row in data["entries"]}
    census = {}
    for attempt in data["attempts"]:
        census.setdefault(attempt["candidate_id"], set()).add(attempt["state"])
    end = protocol["evaluation"][1]
    step = protocol["step_ms"]

    def lane(policy):
        results = {}
        for case in COST_CASES:
            rows = []
            for key in data["universe"]:
                if key in by_id:
                    row = compare(by_id[key], policy, case, protocol["costs"][case], step, end)
                else:
                    states = census.get(key, set())
                    known = bool(states) and states <= {"REJECTED", "INELIGIBLE"}
                    value = "0" if known else None
                    row = {"opportunity_id": key, "cost_case": case,
                           "status": "NOT_SELECTED" if known else "UNKNOWN_DECISION",
                           "filled_fraction": value, "gross": value, "net": value, "cost_bps": value,
                           "legs": [], "provenance": "COUNTERFACTUAL_MODEL_ONLY"}
                rows.append(row)
            results[case] = {"rows": rows, "summary": summarize(rows)}
        return results

    baseline = lane(protocol["baseline_exit"]["policy"])
    families = {
        name: lane(spec) for name, spec in protocol["exit_families"].items() if spec["applicable"]
    }
    trials = [
        {"lane": name, "cost_case": case, "status": "EXCLUDED" if results is None else
         "UNKNOWN" if results[case]["summary"]["net"] is None else "MODELED",
         "reason": protocol["exit_families"][name]["reason"] if results is None else None}
        for name in ("BASELINE", *FAMILIES)
        for results in (baseline if name == "BASELINE" else families.get(name),)
        for case in COST_CASES
    ]
    primary = families[protocol["primary_family"]]
    deltas = []
    for left, right in zip(baseline["TAKER"]["rows"], primary["TAKER"]["rows"], strict=True):
        if left["opportunity_id"] not in by_id:
            continue
        deltas.append(None if left["net"] is None or right["net"] is None
                      else Decimal(right["net"]) - Decimal(left["net"]))
    diagnostic = classify(deltas, protocol)
    root = Path(__file__).resolve().parent
    implementation = {name: sha256((root / name).read_text(encoding="utf-8").encode()).hexdigest()
                      for name in (Path(__file__).name, "aql_factory_shadow_exits_v1.py",
                                   "aql_factory_historical_rule_projection.py")}
    return _seal({
        "schema": EVALUATION, "protocol_sha256": protocol["sha256"], "cohort_sha256": data["sha256"],
        "source_sha256": data["source_sha256"], "evidence_grade": data["grade"],
        "implementation": implementation,
        "native_factory_receipt_sha256": data["native_factory_receipt_sha256"],
        "baseline": baseline, "families": families, "attempts": data["attempts"], "trials": trials,
        "denominators": {"attempts": len(data["attempts"]), "opportunities": len(data["universe"]),
                         "matched_entries": len(data["entries"])},
        "engineering_classifier_only": diagnostic,
        "research_state": ("STOPPED_ENGINEERING_REHEARSAL" if
                           diagnostic["verdict"] == "SCIENTIFIC_FAIL" else "BOUNDED_OBSERVATION"),
        "factory_verdict": "BLOCKED",
        "blockers": ["REAL_PIT_OOS_NOT_ATTESTED"], "holdout": "SEALED_UNOPENED",
    })


def run(dossier, protocol, cohort, store, *, expected_protocol, expected_dossier,
        expected_cohort, attachments, previous=None):
    """Register each attempt in the existing H store and return deterministic artifacts."""
    path = Path(store)
    need(path.is_file() and path.suffix == ".sqlite", "EXISTING_STORE")
    request = digest({"dossier": dossier, "protocol": protocol, "cohort": cohort,
                      "pins": [expected_dossier, expected_protocol, expected_cohort],
                      "attachments": {key: digest(value) for key, value in attachments.items()},
                      "previous": previous})
    attempt_id = "LAB-SHADOW-" + request
    error = None
    try:
        check_dossier(dossier, protocol, expected_protocol=expected_protocol,
                      expected_dossier=expected_dossier, attachments=attachments)
        check_lineage(path, dossier, previous)
        check_dataset(cohort, expected_cohort, protocol)
    except (ResultsStoreError, KeyError, TypeError) as exc:
        error = str(exc) if isinstance(exc, ResultsStoreError) else "SHADOW_MALFORMED_INPUT"

    admission = _seal({
        "schema": "aql.factory.shadow-admission.v1", "attempt_id": attempt_id,
        "dossier_sha256": digest(dossier), "state": "RETURN_TO_LAB" if error else "ADMITTED",
        "reasons": [error] if error else [], "request_sha256": request,
    })
    dossier_metadata = {
        key: dossier.get(key) for key in ("experiment_id", "baseline", "shadow", "protocol_sha256")
    } if type(dossier) is dict else {}
    attempt_body = {"experiment_id": attempt_id, "schema": "aql.factory.shadow-attempt.v1",
                    "admission": admission, "identity": dossier_metadata}
    _store_package(path, attempt_body)
    evaluation = None if error else evaluate(protocol, cohort)
    handoff = None if error else promotion_handoff(dossier, protocol, admission, evaluation)
    status = None
    if not error:
        _, status = _store_package(path, {
            "experiment_id": "LAB-SHADOW-RESULT-" + digest(dossier["shadow"]),
            "schema": "aql.factory.shadow-result-package.v1", "attempt": admission,
            "evaluation": evaluation, "handoff": handoff,
        })
    return {"admission": admission, "evaluation": evaluation, "handoff": handoff,
            "store_status": status}


def check_lineage(path, dossier, previous):
    if dossier["previous_admission_sha256"] is None:
        need(previous is None and dossier["shadow"]["version"] == 1, "FIRST_VERSION")
        return
    _check_seal(previous)
    need(previous["sha256"] == dossier["previous_admission_sha256"]
         and previous["state"] == "RETURN_TO_LAB" and token(previous["attempt_id"]), "RETRY_RECEIPT")
    # H's immutable table is the sole authority for previous attempt identities.
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            row = conn.execute(f"SELECT canonical_sha256,document,immutable FROM {TABLE} "
                               "WHERE experiment_id=?", (previous["attempt_id"],)).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        raise ResultsStoreError("SHADOW_RETRY_NOT_PERSISTED") from exc
    need(row is not None and row[2] == 1, "RETRY_NOT_PERSISTED")
    parent = json.loads(row[1])
    _check_seal(parent)
    old = parent["identity"]
    need(row[0] == parent["sha256"] and parent["admission"] == previous
         and identity(old.get("shadow")) and old["shadow"]["id"] == dossier["shadow"]["id"]
         and old["shadow"]["version"] + 1 == dossier["shadow"]["version"]
         and old["baseline"] == dossier["baseline"], "RETRY_VERSION_LINEAGE")


def promotion_handoff(dossier, protocol, admission, evaluation):
    families = {}
    for name, spec in protocol["exit_families"].items():
        results = evaluation["families"].get(name)
        complete = results is not None and all(
            case["summary"]["net"] is not None for case in results.values())
        families[name] = {
            "applicable": spec["applicable"],
            "reason": None if complete else spec["reason"] or "UNKNOWN_COUNTERFACTUAL_COVERAGE",
            "results_sha256": digest(results) if complete else None,
        }
    return _seal({
        "schema": HANDOFF, "experiment_id": dossier["experiment_id"],
        "baseline": dossier["baseline"], "shadow": dossier["shadow"], "category": dossier["category"],
        "protocol_sha256": protocol["sha256"], "evidence_grade": evaluation["evidence_grade"],
        "costs_sha256": digest(protocol["costs"]),
        "exit_families": families,
        "factory_verdict": evaluation["factory_verdict"], "research_state": "BOUNDED_OBSERVATION",
        "blockers": evaluation["blockers"],
        "receipts": {"dossier_sha256": dossier["sha256"], "admission_sha256": admission["sha256"],
                     "evaluation_sha256": evaluation["sha256"]},
        "eligibility": {"paper": "PAPER_BLOCKED", "live": "NOT_AUTHORIZED", "selected_live_exit": None},
    })


def verify_handoff(doc, expected_digest):
    """Consumer-side fixture verifier, with digest from an independent producer pin."""
    _check_seal(doc)
    need(doc["sha256"] == expected_digest, "HANDOFF_PIN")
    need(set(doc) == {
        "schema", "sha256", "experiment_id", "baseline", "shadow", "category",
        "protocol_sha256", "evidence_grade", "costs_sha256", "exit_families",
        "factory_verdict", "research_state", "blockers", "receipts", "eligibility",
    } and doc["schema"] == HANDOFF and identity(doc["baseline"]) and identity(doc["shadow"])
         and token(doc["experiment_id"]) and doc["category"] in CATEGORIES, "HANDOFF_SCHEMA")
    need(doc["evidence_grade"] in GRADES and doc["factory_verdict"] == "BLOCKED"
         and doc["research_state"] == "BOUNDED_OBSERVATION"
         and doc["blockers"] == ["REAL_PIT_OOS_NOT_ATTESTED"]
         and doc["eligibility"] == {"paper": "PAPER_BLOCKED", "live": "NOT_AUTHORIZED",
                                    "selected_live_exit": None}, "HANDOFF_AUTHORITY")
    need(set(doc["receipts"]) == {"dossier_sha256", "admission_sha256", "evaluation_sha256"}
         and all(_sha(pin) for pin in (
             doc["protocol_sha256"], doc["costs_sha256"], *doc["receipts"].values())),
         "HANDOFF_RECEIPTS")
    need(set(doc["exit_families"]) == set(FAMILIES), "HANDOFF_FAMILIES")
    for family in doc["exit_families"].values():
        need(set(family) == {"applicable", "reason", "results_sha256"}
             and type(family["applicable"]) is bool
             and ((family["applicable"] and family["reason"] is None
                   and _sha(family["results_sha256"])) or
                  (type(family["reason"]) is str and bool(family["reason"])
                   and family["results_sha256"] is None)), "HANDOFF_FAMILY_SCOPE")
    return doc


def read_handoff(raw, expected_digest):
    """Decode untrusted wire bytes without silently accepting duplicate keys."""
    def unique(items):
        value = dict(items)
        need(len(value) == len(items), "HANDOFF_DUPLICATE_KEY")
        return value

    def reject_constant(_):
        raise ResultsStoreError("SHADOW_HANDOFF_NONFINITE")

    need(type(raw) is bytes and len(raw) <= 32768, "HANDOFF_SIZE")
    return verify_handoff(json.loads(raw, object_pairs_hook=unique,
                                     parse_constant=reject_constant), expected_digest)
