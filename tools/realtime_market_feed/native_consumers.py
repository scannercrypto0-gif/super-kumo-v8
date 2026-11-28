"""Real native Factory/Lab + additive Secretary WAIT receiver, generated scope only.

The pinned historical H receiver cannot accept FORWARD_UNQUALIFIED. This module
therefore does NOT forge a historical query, Core #245/#253 receipt, or ACK.
It reuses the pinned Factory immutable package store and actual Lab function,
with a complete causal Scanner census and unknown future outcomes. The native
Secretary interface is explicitly additive and WAIT-only. No original run is
permitted by this generated-interface engineering entry point.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import importlib.util
import inspect
import json
from pathlib import Path
import sqlite3
import stat
import tempfile

from tools.realtime_market_feed import forward_research as fr

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "aql.factory.forward-native-research-package.v1"


def _safe_generated_path(path):
    p = Path(path).absolute()
    fr._need(fr._is_under(p, tempfile.gettempdir()), "NATIVE_GENERATED_OUTPUT_OUTSIDE_TEMP")
    for part in (p, *p.parents):
        if part.exists() or part.is_symlink():
            fr._need(not part.is_symlink() and (not part.is_file() or part.lstat().st_nlink == 1) and not (getattr(part.lstat(), "st_file_attributes", 0) & 0x400),
                     "NATIVE_OUTPUT_LINK_DENIED")
    return p


def _safe_generated_database(path):
    """Validate every SQLite-owned path before any library opens the database."""
    database = _safe_generated_path(path)
    for candidate in (database, *(Path(str(database) + suffix)
                                 for suffix in ("-wal", "-shm", "-journal"))):
        _safe_generated_path(candidate)
        if candidate.exists():
            fr._need(stat.S_ISREG(candidate.lstat().st_mode), "NATIVE_DATABASE_FILE_TYPE_DENIED")
    return database


def _apis(baseline_root, dependency_root):
    kernel = fr._load_kernel(baseline_root, dependency_root)
    from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
    from research_wp_r0.aql_factory_h_research_package_v1 import _store_package, TABLE
    from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_immutable_ledger
    from research_wp_r0.aql_core_backbone_local_v1 import _connect
    manifest = {item["path"]: item["sha256"] for item in kernel["plan"]["dependency_files"]}
    for function, name in ((migrate_store_v2, "factory/research_wp_r0/aql_factory_e_research_results_store_v1.py"),
                           (_store_package, "factory/research_wp_r0/aql_factory_h_research_package_v1.py"),
                           (evaluate_immutable_ledger, "factory/research_wp_r0/aql_factory_h_scientific_lab_v1.py"),
                           (_connect, "core/research_wp_r0/aql_core_backbone_local_v1.py")):
        actual = Path(inspect.getfile(function)).resolve()
        expected = (Path(dependency_root) / name).resolve()
        fr._need(actual == expected and fr._sha_bytes(actual.read_bytes()) == manifest[name],
                 "NATIVE_CONSUMER_IMPORT_PIN_MISMATCH")
    secretary_path = ROOT / "src/aql/research_forward_secretary.py"
    spec = importlib.util.spec_from_file_location("_aql_additive_forward_secretary", secretary_path)
    secretary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(secretary)
    return migrate_store_v2, _store_package, TABLE, evaluate_immutable_ledger, secretary


def _validate_census(receipt):
    window, decision, source = receipt["window"], receipt["decision"], receipt["source"]
    n, start, end = window["bar_count"], window["start_ms"], window["end_exclusive_ms"]
    fr._need(type(n) is int and 8 <= n <= 672 and type(start) is int and start % fr.STEP_MS == 0 and
             end == start + n * fr.STEP_MS, "NATIVE_CENSUS_RANGE")
    rows = decision["state_by_slot"]
    fr._need(type(rows) is list and len(rows) == n and all(
        type(row) is dict and set(row) == {"close_ms", "state"} and
        row["close_ms"] == start + (i + 1) * fr.STEP_MS - 1 and
        row["state"] in {"UNKNOWN", "ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL"}
        for i, row in enumerate(rows)), "NATIVE_CENSUS_ORDER_OR_DENOMINATOR")
    fr._need(decision["latest_open_ms"] == end - fr.STEP_MS and
             decision["latest_close_exclusive_ms"] == end and
             decision["evaluated_slot_count"] == n and
             decision["warmup_unknown_count"] == sum(row["state"] == "UNKNOWN" for row in rows),
             "NATIVE_CENSUS_LATEST_OR_UNKNOWN")
    pins = source["source_receipt_sha256"]
    fr._need(type(pins) is list and len(pins) == n * 15 and len(set(pins)) == len(pins) and
             all(type(pin) is str and len(pin) == 64 and set(pin) <= fr._HEX for pin in pins), "NATIVE_SOURCE_LINEAGE")
    fr._need(decision["decision_cutoff_ms"] >= end and
             source["availability_max_ms"] <= decision["decision_cutoff_ms"], "NATIVE_CUTOFF")
    return rows


def consume_generated_forward_receipt(receipt, *, generated_feed_database, output_root, baseline_root, dependency_root,
        expected_receipt_sha256, expected_source_snapshot_sha256, expected_adapter_code_sha256,
        expected_strategy_definition_sha256, expected_config_sha256):
    """Consume externally pinned generated analysis; no historical/query relabeling."""
    fr.verify_factory_forward_receipt(receipt,
        expected_adapter_code_sha256=expected_adapter_code_sha256,
        expected_strategy_definition_sha256=expected_strategy_definition_sha256,
        expected_config_sha256=expected_config_sha256)
    fr._need(receipt["receipt_sha256"] == expected_receipt_sha256 and
             receipt["source"]["source_snapshot_sha256"] == expected_source_snapshot_sha256,
             "NATIVE_SOURCE_OR_RECEIPT_PIN")
    rows = _validate_census(receipt)
    # The native fixture/source guard is mandatory even for direct receipt intake;
    # a function name or disposable destination cannot qualify original bytes.
    source_path = _safe_generated_database(generated_feed_database)
    from tools.realtime_market_feed.atlas_integration import _feed_db
    with closing(_feed_db(source_path, allow_synthetic_fixture=True,
            expected_producer_code_sha256=receipt["source"]["ws_producer_code_sha256"])) as db:
        native_pins = [row[0] for row in db.execute(
            "SELECT receipt_sha256 FROM final_bar_lineage WHERE symbol=? AND interval='1m' AND open_ms>=? AND open_ms<? ORDER BY open_ms LIMIT 10081",
            (receipt["source"]["symbol"], receipt["window"]["start_ms"], receipt["window"]["end_exclusive_ms"]))]
        fr._need(native_pins == receipt["source"]["source_receipt_sha256"], "NATIVE_GENERATED_SOURCE_RECEIPT_MEMBERSHIP")
    root = _safe_generated_path(output_root)
    fr._need(not fr._is_under(source_path, root) and not fr._is_under(root, source_path),
             "NATIVE_SOURCE_OUTPUT_COLLISION")
    _safe_generated_database(root / "factory.sqlite")
    _safe_generated_database(root / "secretary" / "warehouse.sqlite")
    root.mkdir(parents=True, exist_ok=True)
    migrate, store, table, evaluate_lab, secretary = _apis(baseline_root, dependency_root)
    counts = Counter(row["state"] for row in rows)
    decision, source, window = receipt["decision"], receipt["source"], receipt["window"]
    # Latest recovered data remain UNKNOWN; never turn recovered historical data
    # into a forward-qualified decision or silently omit it from the denominator.
    states = [row["state"] for row in rows]
    if decision["recovered_latest_bar"]:
        states[-1] = "UNKNOWN"
    counts = Counter(states)
    experiment_id = "FORWARD-RESEARCH-" + receipt["receipt_sha256"]
    policy = {"future_outcomes": "UNAVAILABLE_NO_MODEL_OR_FILL", "trading_authority": "NONE"}
    outcomes = [{"status": "UNKNOWN_END_OF_DATA", "entry_open_ms": window["start_ms"] + i * fr.STEP_MS}
                for i, state in enumerate(states) if state == "ENTRY_SIGNAL"]
    ledger_body = {
        "schema": "aql.factory.h.generic-trade-event-ledger.v1",
        "input_sha256": receipt["receipt_sha256"],
        "source_bytes_sha256": source["source_snapshot_sha256"],
        "source_identity_kind": "VERIFIED_FORWARD_LINEAGE_SNAPSHOT_NOT_PUBLISHER_RAW_BYTES",
        "source_month": "BOUNDED_FORWARD_RANGE", "source_class": "FORWARD_UNQUALIFIED",
        "strategy_digest": receipt["strategy"]["strategy_definition_sha256"],
        "config_sha256": receipt["pins"]["config_sha256"],
        "code_sha256": fr._sha_bytes(Path(__file__).read_bytes()),
        "policy_sha256": fr._sha(policy), "scanner_receipt_sha256": receipt["receipt_sha256"],
        "economic_policy_class": "NO_FUTURE_OUTCOMES_NO_ECONOMIC_CLAIM",
        "cohort": {"cohort_class": "GENERIC_SCANNER_H", "coverage": "COMPLETE",
            "expected_bars": len(rows), "observed_bars": len(rows), "missing_bars": 0,
            "decision_slots": len(rows), "focus_bar_count": len(rows),
            "signal_unknown": counts["UNKNOWN"], "entry_signals": counts["ENTRY_SIGNAL"],
            "exit_signals": counts["EXIT_SIGNAL"], "no_signal_bars": counts["NO_SIGNAL"],
            "modeled_trades": 0, "unknown_trades": len(outcomes)},
        "decision_counts": dict(sorted(counts.items())),
        "events": [{"bar_open_ms": window["start_ms"] + i * fr.STEP_MS,
                    "signal_state": state, "scanner_event_sha256": fr._sha(rows[i]),
                    "source_observed": True, "execution_state": "NOT_OBSERVED",
                    "decision_cutoff_ms": decision["decision_cutoff_ms"]}
                   for i, state in enumerate(states)],
        "outcomes": outcomes, "historical_pit": "NOT_ATTESTED",
        "holdout": "SEALED_UNOPENED", "execution_status": "NOT_OBSERVED", "trading_authority": "NONE"}
    ledger = {**ledger_body, "sha256": fr._sha(ledger_body)}
    lab = evaluate_lab(ledger)
    package_body = {"schema": SCHEMA, "experiment_id": experiment_id,
        "analysis_receipt_sha256": receipt["receipt_sha256"],
        "source_snapshot_sha256": source["source_snapshot_sha256"],
        "source_class": "FORWARD_UNQUALIFIED", "evidence_grade": "GENERATED_NATIVE_INTERFACE_TEST",
        "decision_cutoff_ms": decision["decision_cutoff_ms"],
        "scanner_census": rows, "trade_event_ledger": ledger, "scientific_lab": lab,
        "secretary_receiver_code_sha256": fr._sha_bytes((ROOT / "src/aql/research_forward_secretary.py").read_bytes()),
        "orders": 0, "trading_authority": "NONE", "pit_oos": "NOT_ATTESTED"}
    database = root / "factory.sqlite"
    _safe_generated_database(database)
    migrate(database)
    package_sha, status = store(database, package_body)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as con:
        row = con.execute(f"SELECT canonical_sha256,document FROM {table} WHERE experiment_id=?", (experiment_id,)).fetchone()
    package = json.loads(row[1])
    fr._need(row[0] == package_sha == package["sha256"] == fr._sha(package_body), "NATIVE_FACTORY_READBACK")
    wait_body = {"schema": secretary.SCHEMA, "experiment_id": experiment_id,
        "analysis_receipt_sha256": receipt["receipt_sha256"],
        "source_snapshot_sha256": source["source_snapshot_sha256"],
        "factory_package_sha256": package_sha, "lab_sha256": lab["sha256"],
        "strategy_definition_sha256": receipt["strategy"]["strategy_definition_sha256"],
        "config_sha256": receipt["pins"]["config_sha256"],
        "decision_cutoff_ms": decision["decision_cutoff_ms"], "expected_slots": len(rows),
        "unknown_slots": counts["UNKNOWN"], "source_class": "FORWARD_UNQUALIFIED",
        "evidence_grade": "GENERATED_NATIVE_INTERFACE_TEST",
        "state": "WAIT_AUTHENTICATED_PARENTS_AND_RESEARCH_REVIEW",
        "core_245_sha256": None, "core_253_sha256": None, "source_ack_sha256": None,
        "strategy_approval_sha256": None, "factory_consumer_ack_sha256": None,
        "orders": 0, "trading_authority": "NONE", "pit_oos": "NOT_ATTESTED"}
    _safe_generated_database(root / "secretary" / "warehouse.sqlite")
    wait = secretary.route_forward_wait(root / "secretary", {**wait_body, "sha256": fr._sha(wait_body)})
    return {"schema": "aql.forward.native-consumer-result.v1", "factory_store_status": status,
            "factory_package_sha256": package_sha, "lab_sha256": lab["sha256"],
            "secretary": wait, "census": ledger["cohort"],
            "orders": 0, "trading_authority": "NONE", "pit_oos": "NOT_ATTESTED"}


def run_generated_native_chain(feed_database, research_database, *, output_root, **analysis_arguments):
    """Actual source read -> native projection/evaluation -> Factory/Lab -> WAIT."""
    fr._need(analysis_arguments.get("allow_synthetic_fixture") is True,
             "NATIVE_ORIGINAL_RUN_AUTHORIZATION_NOT_IMPLEMENTED")
    _safe_generated_database(feed_database)
    _safe_generated_database(research_database)
    root = _safe_generated_path(output_root)
    _safe_generated_database(root / "factory.sqlite")
    _safe_generated_database(root / "secretary" / "warehouse.sqlite")
    source = Path(feed_database).resolve()
    fr._need(not fr._is_under(source, root) and not fr._is_under(root, source.parent / source.name),
             "NATIVE_SOURCE_OUTPUT_COLLISION")
    value = fr.analyze_forward_window(feed_database, research_database, **analysis_arguments)
    receipt = value["receipt"]
    result = consume_generated_forward_receipt(receipt, generated_feed_database=feed_database, output_root=root,
        baseline_root=analysis_arguments["baseline_root"], dependency_root=analysis_arguments["dependency_root"],
        expected_receipt_sha256=receipt["receipt_sha256"],
        expected_source_snapshot_sha256=receipt["source"]["source_snapshot_sha256"],
        expected_adapter_code_sha256=analysis_arguments["config"]["adapter_code_sha256"],
        expected_strategy_definition_sha256=analysis_arguments["config"]["strategy_definition_sha256"],
        expected_config_sha256=analysis_arguments["expected_config_sha256"])
    return {**value, "native_consumers": result}
