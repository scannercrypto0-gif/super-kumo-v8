"""Read-only projection of a pinned upstream synthetic read receipt.

Expected receipt SHA and run identity must be retained independently by caller.
This checks integrity/identity, not authenticated publisher origin or live PIT.
No G2 horizon outcome enters a signal projection.
"""
from .contracts import need, sha, signal
from ..observation.contracts import digest


def signals_from_prospective(document, *, expected_sha, expected_run, as_of_ms):
    need(type(document) is dict and sha(expected_sha), "EXPECTED_RECEIPT")
    body = {k:v for k,v in document.items() if k != "sha256"}
    need(document.get("sha256") == expected_sha == digest(body), "READ_SEAL")
    run = document.get("run")
    need(run == expected_run and type(run) is dict and run.get("evidence_mode") == "SYNTHETIC_TESTED",
         "PINNED_SYNTHETIC_RUN")
    need(document.get("schema") == "aql.g2.prospective-verified-read.v1"
         and document.get("trading_authority") == "NONE"
         and type(as_of_ms) is int and document.get("as_of_ms") == as_of_ms, "READ_SCOPE")
    rows = document.get("rows")
    need(type(rows) is list and len(rows) <= 672 and document.get("visible_sha256") == digest(rows), "READ_ROWS")
    results, seen, census = [], set(), {}
    for row in rows:
        need(type(row) is dict and type(row.get("decision")) is dict, "READ_ROW")
        decision = row["decision"]
        row_sha = digest(decision)
        need(row.get("decision_sha256") == row_sha and row_sha not in seen, "ROW_SEAL_DUPLICATE")
        seen.add(row_sha)
        need(decision.get("run") == run and decision.get("trading_authority") == "NONE", "ROW_RUN")
        state = decision.get("state")
        need(state in {"ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL", "REJECTED", "UNKNOWN"}, "DECISION_STATE")
        census[state] = census.get(state, 0) + 1
        need(row.get("source_valid") is True, "REVISED_OR_UNVERIFIED_SOURCE")
        parent = decision.get("parent", {})
        cutoff = decision.get("cutoff_ms")
        need(all(type(x) is int for x in (parent.get("close_ms"),parent.get("ingested_ms"),
                                          parent.get("commit_ms"),cutoff))
             and parent["close_ms"] < parent["ingested_ms"] <= parent["commit_ms"] <= cutoff <= as_of_ms,
             "DECISION_ASOF")
        if state != "ENTRY_SIGNAL":
            continue
        need(decision.get("opportunity_id") == digest({k:v for k,v in decision.items() if k != "opportunity_id"}),
             "OPPORTUNITY_ID")
        key = parent.get("key", "").split(":")
        need(len(key) == 3 and key[1] == "15m" and key[2].isdigit(), "SOURCE_INTERVAL")
        opened=int(key[2])
        need(parent.get("open_ms")==opened and opened%900000==0
             and parent["close_ms"]==opened+899999, "SOURCE_GRID")
        need(all(sha(parent.get(k)) for k in ("bar_checksum","content_sha256","g1_receipt_sha256")),
             "SOURCE_RECEIPTS")
        results.append(signal(dict(schema="aql.paper-sim.signal.v1", signal_id=decision["opportunity_id"],
            strategy_id=run.get("strategy_id"), strategy_version=run.get("strategy_version"),
            definition_sha256=run.get("definition_sha256"), config_sha256=run.get("config_sha256"),
            evaluator_sha256=run.get("evaluator_sha256"), source_sha256=row_sha,
            symbol=key[0], interval_ms=900000, decision_ms=cutoff, source_close_ms=parent["close_ms"],
            available_ms=parent["commit_ms"], evidence_mode="SYNTHETIC_TESTED",trading_authority="NONE")))
    return {"signals":results,"census":census,"source_sha256":expected_sha,
            "trading_authority":"NONE", "horizon_values_used":False}
