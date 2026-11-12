"""Bounded TEST_ONLY Core → Discoverer → Factory E → dashboard read model."""
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path

from aql.archive.contracts import parse
from aql.archive.discoverer_view import DiscovererView, factory_inputs

from .continuous_research import Loop, checked, immutable, need, seal
from .contracts import _canonical, _digest


SCHEMA = "aql.discoverer.weekly-review.v1"
COLUMNS = ("kind", "id", "state", "direction", "sha256", "canonical_json")
MAX_REVIEW_BYTES = 2_000_000
WEEK_MS = 7 * 86400000


def _factory_record(factory, *, store, candidate, tick, plan, samples, context, source_pin,
                    code_pin, environment_pin, crash_before_ack=False):
    """Project a hypothesis into the existing native blocked E experiment lane."""
    checked(candidate, candidate["sha256"])
    need(candidate in tick["candidates"] and candidate["policy_sha256"] == plan["sha256"]
         and candidate["frozen_at"] == tick["slot"] and candidate["authority"] == "NONE"
         and candidate["holdout"] == "SEALED_UNOPENED", "CANDIDATE_LINEAGE")
    supporting = []
    for sample in samples:
        if sample["sha256"] not in candidate["comparison"]["parents"]:
            continue
        if sample["state"] != candidate["comparison"]["direction"]:
            continue
        proof = context.get(sample["query_sha256"])
        need(proof is not None, "CANDIDATE_CONTEXT_MISSING")
        checked(proof, proof["sha256"])
        query = proof["request"]
        need(proof["inventory_sha256"] == source_pin
             and proof["request_sha256"] == sample["query_sha256"]
             and proof["cutoff_exclusive_ms"] == sample["onset"]
             and query["symbol"] == sample["symbol"], "CANDIDATE_CONTEXT_BINDING")
        typed = factory_inputs(candidate, candidate["sha256"], proof, proof["sha256"])
        need(typed["availability"] == "ADMITTED" and typed["source_class"] == "TEST_ONLY",
             "FACTORY_SOURCE_UNAVAILABLE")
        supporting.append(typed)
    need(bool(supporting), "NO_MATCHED_CORE_PARENT")

    candidate_id = candidate["hypothesis"]["hypothesis_id"]
    # Generation attempts are actual candidates. Search/watch slots and
    # independent Factory trials are separate populations.
    attempts = [{
        "attempt_id": "discoverer-" + item["sha256"], "candidate_id": item["hypothesis"]["hypothesis_id"],
        "state": "SELECTED", "source_receipt_sha256": item["sha256"],
    } for item in tick["candidates"]]
    parent = seal({
        "candidate_sha256": candidate["sha256"], "policy_sha256": plan["sha256"],
        "checkpoint_tick_sha256": tick["sha256"], "source_sha256": source_pin,
        "context_inputs_sha256": _digest(supporting), "attempts_sha256": _digest(attempts),
    })
    experiment_id = "DISC-REVIEW-" + candidate["sha256"]
    record = factory.build_experiment(
        experiment_id=experiment_id, lane="DISCOVERER", source_status="HISTORICAL_SOURCE_BLOCKED",
        source_sha256=source_pin, source_query_245_sha256=None, source_query_253_sha256=None,
        strategy_definition_sha256=None, config_sha256=plan["sha256"], code_sha256=code_pin,
        environment_sha256=environment_pin, parent_receipt_sha256=parent["sha256"],
        attempts=attempts, evidence_class="TEST_ONLY",
    )
    write = factory.register_experiment(store, record)
    if crash_before_ack:
        raise InterruptedError("FIXTURE_AFTER_FACTORY_COMMIT_BEFORE_ACK")
    fresh = factory.read_experiment(store, experiment_id)
    need(fresh == record and write["experiment_sha256"] == fresh["sha256"]
         and write["trading_authority"] == "NONE" and fresh["actual_fills"] is None
         and fresh["result_sha256"] is None, "FACTORY_NATIVE_READBACK")
    # Native write status differs across replays; stable receipt uses exact
    # persisted experiment and verified parent only.
    return seal({
        "schema": "aql.discoverer.factory-e-blocked-receipt.v1", "candidate_id": candidate_id,
        "candidate_sha256": candidate["sha256"], "experiment_id": experiment_id,
        "factory_experiment_sha256": fresh["sha256"], "parent": parent,
        "state": "EVALUATION_PENDING", "owner": "FACTORY_LAB",
        "blockers": ["NON_EXECUTABLE_D6_HYPOTHESIS", "INDEPENDENT_PIT_OOS_UNATTESTED"],
        "candidate_generation_attempts": fresh["attempt_count"], "factory_trials": 0,
        "paper": "PAPER_BLOCKED", "authority": "NONE",
    })


def run_review(root, *, inventory, inventory_pin, plan, plan_pin, access_ms, slots,
               factory, code_pin, environment_pin, missed_slots=(), crash_before_ack=False):
    """Run against a caller-owned disposable root. No production dataset accepted."""
    need(inventory["mode"] == "TEST_ONLY", "REVIEW_FIXTURE_ONLY")
    need(type(slots) is list and 0 < len(slots) <= 8 and
         slots == [plan["origin"] + i * plan["step"] for i in range(len(slots))],
         "REVIEW_SLOT_BUDGET")
    need(set(missed_slots) <= set(slots), "REVIEW_MISSED_SCOPE")
    root = Path(root)
    root.mkdir(exist_ok=True)
    view = DiscovererView(inventory, inventory_pin, access_ms=access_ms)
    loop = Loop(root / "discoverer", plan, plan_pin)
    contexts = {}
    watch_proofs = []

    def context(query):
        document, proof = view.context(query, query["sha256"])
        contexts[query["sha256"]] = proof
        return document, document["sha256"]

    ticks = []
    for slot in slots:
        if slot in missed_slots:
            ticks.append(loop.tick(slot, None, None, context))
            watch_proofs.append(None)
            continue
        snapshot, proof = view.snapshot(slot, plan, plan_pin)
        watch_proofs.append(proof)
        ticks.append(loop.tick(slot, snapshot, snapshot["sha256"], context))
    samples = [sample for tick in ticks for sample in tick["samples"]]
    candidates = []
    for tick in ticks:
        for candidate in tick["candidates"]:
            receipt = _factory_record(factory, store=root / "factory.sqlite", candidate=candidate,
                                     tick=tick, plan=plan, samples=samples, context=contexts,
                                     source_pin=inventory_pin, code_pin=code_pin,
                                     environment_pin=environment_pin, crash_before_ack=crash_before_ack)
            candidates.append({"candidate": candidate, "factory": receipt})
    need(len({item["candidate"]["sha256"] for item in candidates}) == len(candidates),
         "DUPLICATE_CANDIDATE")
    alerts = [
        seal({"kind": "RESEARCH_EVENT_PREVIEW", "sample_sha256": sample["sha256"],
              "symbol": sample["symbol"], "direction": sample["state"],
              "onset": sample["onset"], "sent": False})
        for sample in samples if sample["state"] in ("UP", "DOWN")
    ]
    need(len({alert["sha256"] for alert in alerts}) == len(alerts), "DUPLICATE_ALERT")
    # UTC ISO week starts Monday. Inputs spanning weeks must be exported
    # separately so weekly counts cannot claim out-of-window observations.
    first = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=slots[0])
    monday = first.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=first.weekday())
    start = (monday - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1)
    need(slots[-1] < start + WEEK_MS, "MIXED_WEEK")
    result = seal({
        "schema": SCHEMA, "grade": "TEST_ONLY", "authority": "NONE",
        "source_sha256": inventory_pin, "market": inventory["market"], "venue": inventory["venue"],
        "policy_sha256": plan_pin, "access_ms": access_ms,
        "week": {"start_ms": start, "end_exclusive_ms": start + WEEK_MS, "timezone": "UTC"},
        "ticks": [tick["sha256"] for tick in ticks], "watch_proofs": watch_proofs,
        "contexts": contexts, "samples": samples, "candidates": candidates, "alerts": alerts,
        "counts": {
            "observations": len(samples), "watch_states": dict(Counter(s["state"] for s in samples)),
            "search_states": dict(Counter(s["search_status"] for s in samples)),
            "candidate_generation_attempts": len(candidates), "nominated": len(candidates),
            "rejected_candidates": 0, "evaluation_pending": len(candidates), "factory_trials": 0,
        },
    })
    need(len(_canonical(result)) <= MAX_REVIEW_BYTES, "REVIEW_BYTE_BUDGET")
    immutable(root / "weekly-review.json", result)
    return result


def verify_review(doc, expected):
    checked(doc, expected)
    need(doc["schema"] == SCHEMA and doc["grade"] == "TEST_ONLY" and doc["authority"] == "NONE",
         "REVIEW_AUTHORITY")
    samples = doc["samples"]
    need(len({sample["sha256"] for sample in samples}) == len(samples)
         and doc["counts"]["observations"] == len(samples)
         and doc["counts"]["watch_states"] == dict(Counter(sample["state"] for sample in samples))
         and doc["counts"]["search_states"] == dict(Counter(sample["search_status"] for sample in samples))
         and doc["counts"]["candidate_generation_attempts"] == len(doc["candidates"]),
         "REVIEW_CENSUS")
    for sample in samples:
        checked(sample, sample["sha256"])
    for key, context in doc["contexts"].items():
        checked(context, context["sha256"])
        need(context["request_sha256"] == key and context["inventory_sha256"] == doc["source_sha256"]
             and context["source_class"] == "TEST_ONLY" and context["authority"] == "NONE",
             "REVIEW_CONTEXT_BINDING")
    for item in doc["candidates"]:
        candidate, factory = item["candidate"], item["factory"]
        checked(candidate, candidate["sha256"])
        checked(factory, factory["sha256"])
        parent = factory["parent"]
        checked(parent, parent["sha256"])
        need(factory["candidate_sha256"] == parent["candidate_sha256"] == candidate["sha256"]
             and parent["source_sha256"] == doc["source_sha256"]
             and parent["policy_sha256"] == candidate["policy_sha256"] == doc["policy_sha256"]
             and factory["state"] == "EVALUATION_PENDING" and factory["factory_trials"] == 0
             and factory["authority"] == "NONE" and factory["paper"] == "PAPER_BLOCKED",
             "REVIEW_FACTORY_BINDING")
    return doc


def read_review(path, expected):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_REVIEW_BYTES + 1)
    need(len(raw) <= MAX_REVIEW_BYTES, "REVIEW_BYTE_BUDGET")
    return verify_review(parse(raw), expected)


def dashboard_section(existing, path, expected, *, search="", direction=None, status=None,
                      as_of_ms, max_age_ms):
    """Compose a section in the existing Promotion dashboard read model."""
    need(existing.get("schema") == "aql.promotion.dashboard.v1"
         and "discoverer" not in existing, "DASHBOARD_HOST_SCHEMA")
    need(type(as_of_ms) is int and type(max_age_ms) is int and max_age_ms >= 0
         and type(search) is str and len(search) <= 160
         and direction in (None, "UP", "DOWN")
         and status in (None, "EVALUATION_PENDING", "REJECTED"),
         "DASHBOARD_QUERY")
    doc = read_review(path, expected)
    need(as_of_ms >= doc["access_ms"], "DASHBOARD_FUTURE")
    candidates = []
    for item in doc["candidates"]:
        candidate, factory = item["candidate"], item["factory"]
        identity = factory["candidate_id"]
        event = candidate["comparison"]["direction"]
        if direction is not None and event != direction or status is not None and factory["state"] != status:
            continue
        if search.casefold() not in identity.casefold():
            continue
        parents = set(candidate["comparison"]["parents"])
        evidence = [sample for sample in doc["samples"] if sample["sha256"] in parents]
        candidates.append({
            "identity": identity, "version": 1, "direction": event, "state": factory["state"],
            "frozen_at": candidate["frozen_at"], "candidate_sha256": candidate["sha256"],
            "protocol": candidate["validation"], "factory": factory,
            "comparison": candidate["comparison"],
            "evidence": evidence,
            "source_context": {sample["query_sha256"]: doc["contexts"][sample["query_sha256"]]
                               for sample in evidence if sample["query_sha256"] in doc["contexts"]},
        })
    return {**existing, "discoverer": {
        "grade": "TEST_ONLY", "authority": "NONE", "strategy_author": "HUMAN_OWNER_GATED",
        "source_sha256": doc["source_sha256"], "venue": doc["venue"], "market": doc["market"],
        "review_sha256": expected, "counts": doc["counts"], "alert_previews": doc["alerts"],
        "freshness": "FRESH" if as_of_ms - doc["access_ms"] <= max_age_ms else "STALE",
        "candidates": sorted(candidates, key=lambda row: (row["frozen_at"], row["identity"])),
    }}


def csv_export(doc):
    """Lossless canonical CSV. JSON cells preserve nested evidence and nulls."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)

    def row(kind, identity, state, direction, value):
        writer.writerow((kind, identity, state, direction, _digest(value), _canonical(value).decode()))

    if doc["schema"] == RETROSPECTIVE_SCHEMA:
        row("retrospective-review", doc["sha256"], "", "", doc)
        return out.getvalue()

    header = {key: value for key, value in doc.items()
              if key not in ("samples", "candidates", "alerts", "contexts")}
    row("review", doc["sha256"], "", "", header)
    for sample in doc["samples"]:
        row("observation", sample["sha256"], sample["search_status"], sample["state"], sample)
    for item in doc["candidates"]:
        row("candidate", item["factory"]["candidate_id"], item["factory"]["state"],
            item["candidate"]["comparison"]["direction"], item)
    for alert in doc["alerts"]:
        row("alert-preview", alert["sha256"], "NOT_SENT", alert["direction"], alert)
    for key, context in sorted(doc["contexts"].items()):
        row("context", key, context["coverage"], "", context)
    return out.getvalue()


def import_csv(text, expected):
    need(len(text.encode()) <= 2 * MAX_REVIEW_BYTES, "CSV_BYTE_BUDGET")
    reader = csv.reader(io.StringIO(text, newline=""))
    need(tuple(next(reader, ())) == COLUMNS, "CSV_COLUMNS")
    body = None
    targets = {"observation": "samples", "candidate": "candidates", "alert-preview": "alerts"}
    for record in reader:
        need(len(record) == len(COLUMNS), "CSV_ROW")
        kind, identity, _, _, digest, raw = record
        value = parse(raw)
        need(_digest(value) == digest, "CSV_ROW_DIGEST")
        if kind == "retrospective-review":
            need(body is None and csv_export(value) == text, "CSV_CANONICAL")
            return _verify_retrospective_projection(value, expected)
        if kind == "review":
            need(body is None, "CSV_HEADER_DUPLICATE")
            body = {**value, **{key: [] for key in targets.values()}, "contexts": {}}
        elif kind == "context":
            need(body is not None and identity not in body["contexts"], "CSV_CONTEXT_DUPLICATE")
            body["contexts"][identity] = value
        else:
            need(body is not None and kind in targets, "CSV_KIND")
            body[targets[kind]].append(value)
    need(body is not None and csv_export(body) == text, "CSV_CANONICAL")
    return verify_review(body, expected)


def weekly_report(doc):
    if doc["schema"] == RETROSPECTIVE_SCHEMA:
        counts = doc["counts"]
        return "\n".join((
            "# Retrospective research review",
            f"Source {doc['source_sha256']} · review {doc['sha256']}",
            f"Scanner slots {counts['scanner_slots']} · Factory trials {counts['factory_trials']}",
            "Outcomes " + json.dumps(doc["outcomes"], sort_keys=True),
            f"{doc['core']} / {doc['known_at']} / {doc['lab']} / {doc['paper']}",
            "Modeled results · zero actual fills · authority NONE",
            "", "```json", _canonical(doc).decode(), "```", "",
        ))
    week = doc["week"]
    def date(value):
        return (datetime(1970, 1, 1, tzinfo=timezone.utc) +
                timedelta(milliseconds=value)).strftime("%Y-%m-%d")
    counts = doc["counts"]
    lines = [
        "# Discoverer weekly research review",
        f"UTC week {date(week['start_ms'])} through {date(week['end_exclusive_ms'])} (exclusive)",
        f"Source {doc['source_sha256']} · {doc['venue']} {doc['market']}",
        f"Observations {counts['observations']} · generation attempts {counts['candidate_generation_attempts']}",
        f"Nominated {counts['nominated']} · rejected {counts['rejected_candidates']} · "
        f"evaluation pending {counts['evaluation_pending']} · Factory trials {counts['factory_trials']}",
        "Watch states " + json.dumps(counts["watch_states"], sort_keys=True),
        "Search states " + json.dumps(counts["search_states"], sort_keys=True),
        "Research only · human selection requires owner review · authority NONE",
    ]
    lines.extend(f"- {a['symbol']} {a['direction']} at {a['onset']} ms · {a['sample_sha256']}"
                 for a in doc["alerts"])
    return "\n".join(lines) + "\n"


RETROSPECTIVE_SCHEMA = "aql.discoverer.retrospective-review.v1"


def retrospective_review(result, plan, source, factory, readbacks, *, pins):
    """Project an externally pinned, independently verified detached research run."""
    checked(result, pins["result"])
    checked(factory, pins["factory"])
    need(_digest(plan) == pins["plan"] == result["plan_sha256"]
         and _digest(source) == pins["source"], "RETROSPECTIVE_PROVENANCE")
    need(result["schema"] == "aql.first-cycle.actual-market-result.v1"
         and result["source_class"] == "RETAINED_ACTUAL_MARKET_RETROSPECTIVE_NON_PIT"
         and result["science"] == "REAL_PIT_OOS_BLOCKED"
         and result["actual_fills"] is None and result["trading_authority"] == "NONE"
         and source["evidence_class"] == "RETROSPECTIVE_NON_PIT"
         and source["known_at"] == "UNKNOWN" and source["publisher_first_available_at_ms"] is None
         and source["rights_status"] == "VERIFIED_FOR_EXACT_USE"
         and source["archive_sha256"] == result["source"][0]["sha256"]
         and len(result["source"]) == len(plan["archives"]) == 1
         and source["archive_sha256"] == plan["archives"][0]["sha256"]
         and source["start_ms"] == plan["first_open_ms"]
         and source["end_exclusive_ms"] == plan["end_exclusive_ms"], "RETROSPECTIVE_SOURCE")
    need(factory["sha256"] == result["factory_experiment_sha256"]
         and factory["parent_receipt_sha256"] == result["candidate_package_sha256"]
         and factory["strategy_definition_sha256"] == plan["strategy"]["digest"]
         and factory["config_sha256"] == _digest(plan["strategy"])
         and factory["actual_fills"] is None and factory["trading_authority"] == "NONE"
         and factory["orders_created"] == factory["paper_positions"] == 0
         and factory["lab_receipt_sha256"] is None
         and factory["attempt_count"] == len(factory["attempts"]) == 1
         and result["populations"]["factory_trials"] == result["discoverer"]["total_attempts"] == 1,
         "RETROSPECTIVE_FACTORY")
    attempt = factory["attempts"][0]
    need(0 < len(readbacks) <= 64 and len(readbacks) == len(pins["entries"]), "RETROSPECTIVE_ENTRY_COUNT")
    entries = {}
    for readback in readbacks:
        member = readback["scanner_membership"]
        link = member["opportunity"]
        identity = link["entry_id"]
        need(identity not in entries and identity in pins["entries"], "RETROSPECTIVE_DUPLICATE_OR_FOREIGN_ENTRY")
        checked(readback, pins["entries"][identity])
        row = link["decision"]
        position = link["position"]
        need(readback["schema"] == "aql.first-cycle.independent-verification.v1"
             and readback["result_sha256"] == result["sha256"]
             and readback["trading_authority"] == "NONE" and readback["actual_fills"] is None
             and readback["native_experiments"] == readback["native_result_packages"] == 1
             and readback["verified_cost_rows"] == result["populations"]["cost_rows"]
             and member["receipt_sha256"] == result["scanner_receipt_sha256"]
             and member["status"] == "LINK_PROVED_RETROSPECTIVE_NON_PIT"
             and member["core"] == "SOURCE_BLOCKED" and member["known_at"] == "KNOWN_AT_UNATTESTED"
             and link["attempt_id"] == attempt["attempt_id"] and link["candidate_id"] == attempt["candidate_id"]
             and link["experiment_id"] == factory["experiment_id"] and link["decision_sha256"] == _digest(row)
             and type(position) is int and position >= 0 and identity == f"entry{position}"
             and row["open_ms"] == plan["first_open_ms"] + position * 900_000
             and row["decision_cutoff_ms"] == row["open_ms"] + 900_000 < plan["validation_end_ms"]
             and row["state"] == "ENTRY_SIGNAL" and row["known_at_ms"] is None
             and row["availability"] == "RETROSPECTIVE_NON_PIT"
             and row["strategy_sha256"] == plan["strategy"]["digest"], "RETROSPECTIVE_MEMBERSHIP")
        entries[identity] = link
    return seal({
        "schema": RETROSPECTIVE_SCHEMA, "grade": "RETROSPECTIVE_NON_PIT", "authority": "NONE",
        "source_sha256": source["archive_sha256"], "source_manifest_sha256": pins["source"],
        "plan_sha256": pins["plan"], "census_sha256": result["decision_census_sha256"],
        "result_sha256": result["sha256"], "factory_sha256": factory["sha256"],
        "core": "CORE_SOURCE_BLOCKED", "known_at": "KNOWN_AT_UNATTESTED", "lab": "LAB_LINK_BLOCKED",
        "paper": "PAPER_BLOCKED", "actual_fills": None, "access_ms": plan["frozen_at_ms"],
        "counts": result["populations"], "outcomes": result["outcome_status_counts"],
        "comparisons": result["comparisons"], "entries": entries,
    })


def read_retrospective_review(path, expected):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_REVIEW_BYTES + 1)
    need(len(raw) <= MAX_REVIEW_BYTES, "REVIEW_BYTE_BUDGET")
    return _verify_retrospective_projection(parse(raw), expected)


def _verify_retrospective_projection(doc, expected):
    checked(doc, expected)
    need(doc["schema"] == RETROSPECTIVE_SCHEMA and doc["grade"] == "RETROSPECTIVE_NON_PIT"
         and doc["authority"] == "NONE" and doc["actual_fills"] is None
         and doc["core"] == "CORE_SOURCE_BLOCKED" and doc["lab"] == "LAB_LINK_BLOCKED"
         and doc["known_at"] == "KNOWN_AT_UNATTESTED" and doc["paper"] == "PAPER_BLOCKED",
         "RETROSPECTIVE_PROJECTION_AUTHORITY")
    return doc


def retrospective_dashboard_section(existing, path, expected, *, search="", state=None, as_of_ms, max_age_ms):
    """Reuse the Promotion dashboard envelope without invoking promotion."""
    need(existing.get("schema") == "aql.promotion.dashboard.v1"
         and "retrospective_research" not in existing, "DASHBOARD_HOST_SCHEMA")
    need(type(search) is str and len(search) <= 160 and state in (None, "ENTRY_SIGNAL")
         and type(as_of_ms) is int and type(max_age_ms) is int and max_age_ms >= 0, "DASHBOARD_QUERY")
    doc = read_retrospective_review(path, expected)
    need(as_of_ms >= doc["access_ms"], "DASHBOARD_FUTURE")
    entries = {
        key: row for key, row in doc["entries"].items()
        if search.casefold() in key.casefold() and (state is None or row["decision"]["state"] == state)
    }
    return {**existing, "retrospective_research": {
        **{k: v for k, v in doc.items() if k not in ("sha256", "entries")},
        "review_sha256": expected, "entries": entries,
        "freshness": "FRESH" if as_of_ms - doc["access_ms"] <= max_age_ms else "STALE",
    }}

def import_retrospective_markdown(text, expected):
    """Reopen a canonical Markdown export using its sealed JSON block."""
    need(len(text.encode()) <= 2 * MAX_REVIEW_BYTES, "REVIEW_BYTE_BUDGET")
    _, marker, block = text.rpartition("\n```json\n")
    need(marker and block.endswith("\n```\n"), "MARKDOWN_REVIEW_BLOCK")
    doc = _verify_retrospective_projection(parse(block.removesuffix("\n```\n")), expected)
    need(weekly_report(doc) == text, "MARKDOWN_CANONICAL")
    return doc
