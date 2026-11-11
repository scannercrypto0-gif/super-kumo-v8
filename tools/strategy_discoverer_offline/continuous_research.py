"""Bounded D1–D6 research loop over independently pinned Core fixture receipts."""
from collections import Counter
from pathlib import Path
import json
import os
import tempfile
import time

from .contracts import _canonical, _digest
from .durable_checkpoint_e import DurableDiscovererCheckpoint
from .families import FamilyDefinition
from .hypotheses import HypothesisProposal, SearchPlan
from .validation import ValidationProtocolV1

FEATURES = frozenset(("price","volume","liquidity","btc","sector","paxg","news","macro","monitor"))
MAX_BYTES = 256_000
MAX_TICKS = 64


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def seal(body):
    return {**body, "sha256":_digest(body)}


def checked(doc, expected):
    need(doc["sha256"] == expected == _digest({k:v for k,v in doc.items() if k!="sha256"}), "CORE_OR_PLAN_PIN")


def policy(*, origin, step, members, threshold=100, query_limit=64):
    """Provisional fixed fixture universe. Core supplies membership and sectors."""
    need(type(origin) is int and origin >= step and type(step) is int and step > 0
         and type(threshold) is int and 0 < threshold <= 10_000, "POLICY_CLOCK")
    need(2 <= len(members) <= 32 and {"BTC","PAXG"} <= set(members)
         and type(query_limit) is int and 1 <= query_limit <= MAX_TICKS, "POLICY_BUDGET")
    for symbol, meta in members.items():
        need(type(symbol) is str and 0 < len(symbol) <= 24 and set(meta) == {"sector","rank_eligible"}
             and type(meta["rank_eligible"]) is bool and type(meta["sector"]) is str
             and 0 < len(meta["sector"]) <= 48, "MEMBERSHIP_SHAPE")
    return seal(dict(schema="aql.discoverer.watch-policy.v1", origin=origin, step=step,
                     members=members, threshold_bps=threshold, query_limit=query_limit,
                     max_outcome_lag_ms=max(1,step//4),
                     venue="BINANCE", market="SPOT", rank="PER_WINDOW_RETURN_BPS",
                     alt_rank="CORE_PREDECLARED_NON_STABLE_NON_WRAPPED_ELIGIBILITY_THEN_RETURN",
                     authority="NONE", evidence="SYNTHETIC_ONLY"))


def watch(plan, slot, core, expected_core):
    if core is not None:
        need(len(_canonical(core)) <= MAX_BYTES, "CORE_BYTE_BOUND")
        checked(core,expected_core)
        need(core["schema"] == "aql.core.discoverer-snapshot.fixture.v1"
             and core["slot"] == slot and core["venue"] == plan["venue"]
             and core["market"] == plan["market"] and core["source_class"] == "TEST_ONLY"
             and core["authority"] == "NONE" and core["membership_sha256"] == _digest(plan["members"]),
             "CORE_SCOPE")
        need(set(core["observations"]) <= set(plan["members"]), "FOREIGN_MEMBER")
    rows = []
    for symbol, meta in sorted(plan["members"].items()):
        item = core["observations"].get(symbol) if core is not None else None
        bps = None
        state = "MISSED" if core is None else "UNKNOWN"
        if item is not None:
            need(set(item) == {"return_bps","onset","end","published","received","known_at","receipt_sha256"},
                 "OUTCOME_FIELDS")
            need(type(item["return_bps"]) is int and abs(item["return_bps"]) <= 1_000_000
                 and all(type(item[k]) is int for k in ("onset","end","published","received","known_at"))
                 and item["onset"] == slot-plan["step"]
                 and item["onset"] < item["end"] <= item["published"] <= item["received"] <= item["known_at"] <= slot,
                 "OUTCOME_CLOCK")
            need(slot-item["end"] <= plan["max_outcome_lag_ms"],"STALE_OUTCOME")
            need(is_sha(item["receipt_sha256"]), "OUTCOME_LINEAGE")
            bps = item["return_bps"]
            threshold = plan["threshold_bps"]
            state = "UP" if bps >= threshold else "DOWN" if bps <= -threshold else "NO_EVENT"
        rows.append(dict(symbol=symbol, sector=meta["sector"], rank_eligible=meta["rank_eligible"],
                         state=state, return_bps=bps, onset=slot-plan["step"], end=slot,
                         measured_end=item["end"] if item else None,
                         outcome_known_at=item["known_at"] if item else None,
                         outcome_receipt=item["receipt_sha256"] if item else None))
    known = [r for r in rows if r["return_bps"] is not None]
    gainers = sorted((r for r in known if r["state"]=="UP"), key=lambda r:(-r["return_bps"],r["symbol"]))
    losers = sorted((r for r in known if r["state"]=="DOWN"), key=lambda r:(r["return_bps"],r["symbol"]))
    alts = sorted((r for r in known if r["rank_eligible"] and r["symbol"] not in ("BTC","PAXG")),
                  key=lambda r:(-r["return_bps"],r["symbol"]))[:10]
    sectors = {}
    for row in rows:
        data = sectors.setdefault(row["sector"], {"expected":0,"observed":0,"sum_bps":0})
        data["expected"] += 1
        if row["return_bps"] is not None:
            data["observed"] += 1
            data["sum_bps"] += row["return_bps"]
    return seal(dict(schema="aql.discoverer.watch.v1",slot=slot,core_sha256=expected_core,
                     policy_sha256=plan["sha256"],rows=rows,census=dict(Counter(r["state"] for r in rows)),
                     gainers=[r["symbol"] for r in gainers],losers=[r["symbol"] for r in losers],
                     top_alts=[r["symbol"] for r in alts],sectors=sectors))


def is_sha(value):
    return type(value) is str and len(value)==64 and all(c in "0123456789abcdef" for c in value)


def context_query(plan, row):
    return seal(dict(schema="aql.core.discoverer-context-query.v1", symbol=row["symbol"],
                     venue=plan["venue"],market=plan["market"],
                     start_ms=max(0,row["onset"]-plan["step"]), cutoff_exclusive_ms=row["onset"],
                     outcome_identity_sha256=_digest(row),
                     features=sorted(FEATURES), max_records=32,
                     scanner_mode="MONITOR_ONLY", authority="NONE"))


def precursor(query, response, expected):
    """Retain visible refs only. Late publications and corrections are excluded."""
    need(len(_canonical(response)) <= MAX_BYTES, "CORE_BYTE_BOUND")
    checked(response,expected)
    need(response["schema"] == "aql.core.discoverer-context.fixture.v1"
         and response["query_sha256"] == query["sha256"] and response["source_class"] == "TEST_ONLY"
         and len(response["records"]) <= query["max_records"], "QUERY_BINDING")
    selected = {}
    visible = {}
    excluded = Counter()
    for item in response["records"]:
        need(set(item) == {"feature","value","effective","published","received","known_at","version",
                           "source_sha256","parent_sha256","mode"}, "CONTEXT_FIELDS")
        feature = item["feature"]
        need(feature in FEATURES and type(item["value"]) is int and abs(item["value"]) <= 1_000_000
             and type(item["version"]) is int and item["version"] >= 1
             and is_sha(item["source_sha256"])
             and (item["parent_sha256"] is None if item["version"] == 1 else is_sha(item["parent_sha256"])),
             "CONTEXT_LINEAGE")
        need(feature != "monitor" or item["mode"] == "MONITOR_ONLY", "SCANNER_AUTHORITY")
        times = [item[k] for k in ("effective","published","received","known_at")]
        if any(v is None for v in times):
            excluded["UNKNOWN_CLOCK"] += 1
            continue
        need(all(type(v) is int and v >= 0 for v in times) and times == sorted(times),"CONTEXT_CLOCK")
        if times[-1] >= query["cutoff_exclusive_ms"] or times[0] < query["start_ms"]:
            excluded["OUTSIDE_PRE_ONSET"] += 1
            continue
        identity = (feature,item["version"])
        need(identity not in visible or visible[identity]==item,"CONTEXT_REVISION_CONFLICT")
        visible[identity] = item
    valid = {}
    for (feature,version),item in sorted(visible.items()):
        if version > 1:
            predecessor = valid.get((feature,version-1))
            if not predecessor or predecessor["source_sha256"] != item["parent_sha256"] or predecessor["known_at"] >= item["known_at"]:
                excluded["UNVERIFIED_REVISION_PARENT"] += 1
                continue
        valid[(feature,version)] = item
        key = (version,item["known_at"])
        prior = selected.get(feature)
        if prior and key == prior[0]:
            need(item == prior[1], "CONTEXT_REVISION_CONFLICT")
        if not prior or key > prior[0]:
            selected[feature] = (key,item)
    return seal(dict(query_sha256=query["sha256"],core_response_sha256=expected,
                     features={feature:{"value":item["value"],"ref":item["source_sha256"],
                                       "version":item["version"],"parent":item["parent_sha256"]}
                               for feature,(_,item) in selected.items()},excluded=dict(excluded)))


def compare(samples, direction, feature="liquidity", trigger=1):
    """Match on symbol/sector and frozen horizon. Preserve contrary and missing."""
    need(direction in ("UP","DOWN") and feature in FEATURES and type(trigger) is int,"HYPOTHESIS_SCOPE")
    event_groups = {(s["symbol"],s["sector"],s["end"]-s["onset"]) for s in samples if s["state"]==direction}
    counters = Counter()
    parents = []
    for sample in samples:
        group = (sample["symbol"],sample["sector"],sample["end"]-sample["onset"])
        if group not in event_groups:
            counters["UNMATCHED"] += 1
            continue
        value = sample["features"].get(feature)
        if not value or sample["state"] in ("UNKNOWN","MISSED"):
            label = "MISSING"
        else:
            outcome = "EVENT" if sample["state"]==direction else "CONTROL" if sample["state"]=="NO_EVENT" else "CONTRARY"
            label = outcome+("_TRIGGER" if value["value"] >= trigger else "_NO_TRIGGER")
        counters[label] += 1
        parents.append(sample["sha256"])
    return seal(dict(direction=direction,feature=feature,trigger=trigger,denominator=len(samples),
                     counts=dict(counters),parents=parents,baseline="MATCHED_SAME_SYMBOL_SECTOR_HORIZON",
                     inference="EVENT_CONDITIONED_HYPOTHESIS_ONLY"))


def proposal(comparison, frozen_at, plan):
    family = FamilyDefinition.build(family_id="PRECURSOR_STUDY",version="1",
        description="Non-executable precursor occurrence study",
        entry_rule_template="None. Count a frozen context predicate.",
        exit_rule_template="None. Observe a frozen future window.",
        timing="CONFIRMED_CLOSE",max_candidates=2,
        counterhypothesis_template="Matched same-symbol, same-sector, same-horizon no-trigger control")
    direction = comparison["direction"]
    identity = "precursor-"+direction.lower()+"-"+comparison["sha256"][:16]
    hypothesis = HypothesisProposal.build(
        family=family,hypothesis_id=identity,parameter_config={"feature":comparison["feature"],
        "threshold":comparison["trigger"]},entry_direction="BOTH",
        hypothesis_statement=f"Frozen precursor predicts more {direction} outcomes than the matched baseline.",
        minimum_effect_size="0.05",null_hypothesis="No improvement over matched no-trigger observations.",
        counterhypothesis_id=identity+"-null",assumptions=("fixture only","all outcomes retained"))
    registry = _digest([family.family_digest])
    search = SearchPlan.build(search_plan_id=identity+"-plan",family_registry_digest=registry,
                              hypothesis_ids=(identity,),total_candidate_budget=1)
    validation = ValidationProtocolV1.build(protocol_id=identity+"-protocol",family_registry_digest=registry,
                                            search_plan_digest=search.plan_digest)
    return seal(dict(schema="aql.discoverer.precursor-proposal.v1",frozen_at=frozen_at,policy_sha256=plan["sha256"],
                     comparison=comparison,hypothesis=hypothesis.to_dict(),search=search.to_dict(),
                     validation=validation.to_dict(),holdout="SEALED_UNOPENED",authority="NONE"))


def forward(candidate, expected, observations):
    checked(candidate,expected)
    comparison = candidate["comparison"]
    counts = Counter()
    seen = set()
    for sample, pin in observations:
        checked(sample,pin)
        key = (sample["symbol"],sample["onset"])
        need(key not in seen and sample["onset"] > candidate["frozen_at"], "FORWARD_CHRONOLOGY")
        seen.add(key)
        value = sample["features"].get(comparison["feature"])
        if value is None or sample["state"] in ("UNKNOWN","MISSED"):
            label = "UNKNOWN"
        else:
            triggered = value["value"] >= comparison["trigger"]
            hit = sample["state"] == comparison["direction"]
            label = ("TP" if hit else "FP") if triggered else ("FN" if hit else "TN")
        counts[label] += 1
    return seal(dict(candidate_sha256=expected,denominator=len(seen),counts=dict(counts),
                     status="SYNTHETIC_FORWARD_CHECK_ONLY",authority="NONE"))


def freeze_predictions(root, candidate, expected, plan, *, onset, issued, sources):
    """Before onset, lock a full-universe prediction census from Core as-of refs."""
    checked(candidate,expected)
    need(candidate["policy_sha256"] == plan["sha256"]
         and type(issued) is int and type(onset) is int
         and candidate["frozen_at"] <= issued < onset,"PREDICTION_CHRONOLOGY")
    need(set(sources) <= set(plan["members"]),"FOREIGN_PREDICTION_MEMBER")
    rule = candidate["comparison"]
    predictions = {}
    for symbol in sorted(plan["members"]):
        data = sources.get(symbol)
        triggered, reference = None,None
        if data is not None:
            response,pin = data
            query = context_query(plan,{"symbol":symbol,"onset":issued})
            context = precursor(query,response,pin)
            value = context["features"].get(rule["feature"])
            triggered = value["value"] >= rule["trigger"] if value else None
            reference = context["sha256"]
        predictions[symbol] = dict(triggered=triggered,context_sha256=reference)
    record = seal(dict(candidate_sha256=expected,policy_sha256=plan["sha256"],
                       onset=onset,issued=issued,direction=rule["direction"],predictions=predictions,
                       evidence="SYNTHETIC_ONLY",authority="NONE"))
    immutable(Path(root)/f"prediction-{expected[:16]}-{onset}.json",record)
    return record


def settle_predictions(plan, predictions, expected, outcome_snapshot, outcome_pin):
    checked(predictions,expected)
    need(predictions["policy_sha256"] == plan["sha256"]
         and set(predictions["predictions"]) == set(plan["members"]),"PREDICTION_POPULATION")
    outcomes = watch(plan,predictions["onset"]+plan["step"],outcome_snapshot,outcome_pin)
    counts = Counter()
    for row in outcomes["rows"]:
        trigger = predictions["predictions"][row["symbol"]]["triggered"]
        if trigger is None or row["state"] in ("UNKNOWN","MISSED"):
            label = "UNKNOWN"
        else:
            hit = row["state"] == predictions["direction"]
            label = ("TP" if hit else "FP") if trigger else ("FN" if hit else "TN")
        counts[label] += 1
    return seal(dict(predictions_sha256=expected,outcome_sha256=outcomes["sha256"],
                     denominator=len(plan["members"]),counts=dict(counts),
                     status="SYNTHETIC_FORWARD_CHECK_ONLY",authority="NONE"))


def immutable(path, doc):
    raw = _canonical(doc)
    if path.exists():
        need(path.read_bytes() == raw,"IMMUTABLE_REPLAY_CONFLICT")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        stage = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(stage,path)
        except FileExistsError:
            need(path.read_bytes() == raw,"IMMUTABLE_REPLAY_CONFLICT")
    finally:
        stage.unlink()


class Loop:
    """Single-writer bounded polling. A trusted Core callback supplies pinned receipts."""

    def __init__(self, root, plan, expected):
        checked(plan,expected)
        need(plan["schema"] == "aql.discoverer.watch-policy.v1" and plan["evidence"] == "SYNTHETIC_ONLY"
             and plan["authority"] == "NONE","POLICY_SCOPE")
        self.root = Path(root).absolute()
        need(all(not p.is_symlink() and not (p.exists() and getattr(p.lstat(),"st_file_attributes",0)&0x400)
                 for p in (self.root,*self.root.parents)), "REPARSE_CUSTODY")
        if self.root.exists():
            need((self.root/"policy.json").is_file(),"UNOWNED_DIRECTORY")
        else:
            self.root.mkdir()
        immutable(self.root/"policy.json",plan)
        need(all(p.is_file() and not p.is_symlink()
                 and not getattr(p.lstat(),"st_file_attributes",0)&0x400 for p in self.root.iterdir()),
             "UNOWNED_CUSTODY_ENTRY")
        self.plan = json.loads(_canonical(plan))
        self.journal = DurableDiscovererCheckpoint(self.root/"checkpoint.sqlite")

    def poll(self, now, read_core, query_core, *, max_ticks=4):
        """Catch up a bounded number of due slots, including explicit misses."""
        need(type(now) is int and type(max_ticks) is int and 1 <= max_ticks <= 4, "POLL_BUDGET")
        events = self.journal.attempt_events()
        ticks = sum(e["attempt_key"].startswith("tick-") for e in events)
        due = min(self.plan["query_limit"],1+(now-self.plan["origin"])//self.plan["step"])
        need(due >= ticks, "CLOCK_REGRESSION")
        results = []
        for index in range(ticks,min(due,ticks+max_ticks)):
            slot = self.plan["origin"]+index*self.plan["step"]
            try:
                provided = read_core(slot)
            except OSError:
                provided = None
            core, pin = provided if provided is not None else (None,None)
            results.append(self.tick(slot,core,pin,query_core))
        return results

    def tick(self, slot, core, expected_core, query_core, *, crash=False):
        started, cpu = time.monotonic(),time.process_time()
        p = self.plan
        need(type(slot) is int and (core is not None or expected_core is None),"SLOT_OR_MISSING_PIN")
        index, rest = divmod(slot-p["origin"],p["step"])
        need(rest == 0 and 0 <= index < p["query_limit"],"SCHEDULE_BUDGET")
        prior = None
        acknowledged = {e["attempt_key"]:e["decision_digest"] for e in self.journal.attempt_events()}
        if index:
            parent = self.root/f"tick-{index-1}.json"
            need(parent.is_file(),"UNRECORDED_SCHEDULE_GAP")
            prior = json.loads(parent.read_bytes())
            checked(prior,prior["sha256"])
            need(prior["slot"] == slot-p["step"] and prior["policy_sha256"] == p["sha256"],"SCHEDULE_PARENT")
            need(acknowledged.get(f"tick-{index-1}") == prior["sha256"],"UNACKNOWLEDGED_PARENT")
        census = watch(p,slot,core,expected_core)
        immutable(self.root/f"watch-{index}.json",census)
        samples = []
        # Scheduled context requests run even in quiet periods. Events are
        # prioritized without deleting quiet/missing members from the census.
        ordered = sorted(census["rows"],key=lambda r:(r["state"] not in ("UP","DOWN"),r["symbol"]))
        for row in ordered:
            query = context_query(p,row)
            context, state = None, "UNAVAILABLE"
            try:
                response = query_core(query) if row["state"] not in ("UNKNOWN","MISSED") else None
                if response is not None:
                    document, pin = response
                    context = precursor(query,document,pin)
                    state = "COMPLETE"
            except (KeyError,TypeError,ValueError):
                state = "INVALID"
            except OSError:
                state = "FAILED"
            samples.append(seal(dict(**row,query_sha256=query["sha256"],
                                     context_sha256=context["sha256"] if context else None,
                                     search_status=state,
                                     features=context["features"] if context else {},
                                     excluded=context["excluded"] if context else {})))
            need(time.monotonic()-started < 5 and time.process_time()-cpu < 2,"TICK_RESOURCE_BUDGET")
        history, existing = [], set()
        for number in range(index):
            older = json.loads((self.root/f"tick-{number}.json").read_bytes())
            checked(older,older["sha256"])
            need(acknowledged.get(f"tick-{number}") == older["sha256"],"UNACKNOWLEDGED_HISTORY")
            history.extend(older["samples"])
            existing.update(c["comparison"]["direction"] for c in older["candidates"])
        comparisons = [compare(history+samples,direction) for direction in ("UP","DOWN")]
        candidates = [proposal(c,slot,p) for c in comparisons
                      if c["direction"] not in existing and c["counts"].get("EVENT_TRIGGER")
                      and c["counts"].get("CONTROL_TRIGGER")]
        result = seal(dict(slot=slot,policy_sha256=p["sha256"],parent=prior["sha256"] if prior else None,
                           watch=census,samples=samples,comparisons=comparisons,candidates=candidates,
                           search="SCHEDULED",search_census=dict(Counter(s["search_status"] for s in samples)),
                           authority="NONE"))
        need(len(_canonical(result)) <= MAX_BYTES,"TICK_STORAGE_BUDGET")
        immutable(self.root/f"tick-{index}.json",result)
        if crash:
            os._exit(73)
        self.journal.append_attempt(attempt_key=f"tick-{index}",outcome="SCHEDULED",
                                    candidate_id=f"watch-{index}",package_digest=p["sha256"],
                                    decision_digest=result["sha256"])
        return result


def accept_factory_feedback(journal, candidate, receipt, expected):
    """Consume independently pinned Factory feedback. Never promote a candidate."""
    checked(candidate,candidate["sha256"])
    checked(receipt,expected)
    need(receipt["schema"] == "aql.factory.discoverer-feedback.v1"
         and receipt["candidate_sha256"] == candidate["sha256"]
         and receipt["status"] in ("PASS","FAIL","UNKNOWN")
         and receipt["authority"] == "NONE" and receipt["holdout"] == "SEALED_UNOPENED"
         and is_sha(receipt["factory_result_sha256"]),"FACTORY_FEEDBACK_SCOPE")
    return journal.append_attempt(attempt_key="feedback-"+candidate["sha256"],outcome=receipt["status"],
                                  candidate_id=candidate["hypothesis"]["hypothesis_id"],
                                  package_digest=candidate["sha256"],decision_digest=expected,
                                  intake_digest=receipt["factory_result_sha256"])
