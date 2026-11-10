"""Independent read-only comparisons and controls for the frozen WP03 receipt."""
from contextlib import closing
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

import run_wp03 as w
from research_wp_r0.aql_factory_e_research_results_store_v1 import ResultsStoreError
from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import _verified


def rejected(name, operation, expected):
    try:
        operation()
    except (AssertionError, ValueError, ResultsStoreError) as error:
        if expected and expected not in str(error):
            raise
        return name
    raise AssertionError(f"Control was accepted: {name}")


def main():
    reg_path, first, second = map(Path, sys.argv[1:])
    reg = json.loads(reg_path.read_text())
    result = json.loads((first / "result.json").read_text())
    assert (first / "result.json").read_bytes() == (second / "result.json").read_bytes()
    controls = []
    controls.append(rejected("oos_peek", lambda: w.inputs(reg, "synthetic_oos", "BASE", unlocked=False),
                             "STILL_SEALED"))
    bad = deepcopy(reg)
    bad["query_pins"]["synthetic_oos/BASE"]["start_ms"] -= w.STEP * 2
    controls.append(rejected("embargo_breach", lambda: w.validate_schedule(bad), "EMBARGO"))
    q = w.query("train")
    changed = deepcopy(q)
    changed["query_sha256"] = "0" * 64
    with patch.object(w, "query", return_value=changed):
        controls.append(rejected("source_pin_substitution",
                                 lambda: w.inputs(reg, "train", "BASE", unlocked=False), "SOURCE_PIN"))
    request = w.packet(reg, q, "BASE", result["records"]["train/BASE"]["attempt"])
    forged = {**request, "trading_authority": "LIVE"}
    forged = w.seal({k:v for k,v in forged.items() if k!="sha256"})
    controls.append(rejected("authority_escalation", lambda: _verified(forged), "PARENT_AUTHORITY"))
    fake = deepcopy(request)
    fake["operator_cost_policy"]["fill_semantics"] = "MAKER_TOUCH_IS_FILL"
    fake["operator_cost_policy"] = w.seal({k:v for k,v in fake["operator_cost_policy"].items() if k!="sha256"})
    fake = w.seal({k:v for k,v in fake.items() if k!="sha256"})
    controls.append(rejected("false_maker_touch_fill", lambda: _verified(fake), ""))
    entries = json.loads((first / "registry.json").read_text())
    controls.append(rejected("hidden_attempt_chain", lambda: w.DiscovererLedger.from_dict_list(entries[:3]+entries[4:]), ""))
    truncated = w.DiscovererLedger.from_dict_list(entries[:-1])
    assert truncated.summary()["incomplete_attempts"] == 1
    controls.append("missing_terminal_detected")
    metrics = {}
    results = {}
    db = (first / "factory.sqlite").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(db, uri=True)) as conn:
        for key, rec in result["records"].items():
            doc = json.loads(conn.execute(f"SELECT document FROM {w.TABLE} WHERE experiment_id=?",
                                          (rec["attempt"],)).fetchone()[0])
            ledger = doc["trade_event_ledger"]
            results[key] = ledger
            assert ledger["sha256"] == rec["hashes"]["trade_ledger_sha256"]
            modeled = [row for row in ledger["outcomes"] if row["status"] == "MODEL_ONLY"]
            metrics[key] = {
                "modeled_count": len(modeled),
                "gross_return_sum": str(sum((Decimal(x["modeled_gross_return"]) for x in modeled), Decimal(0))),
                "net_return_sum": str(sum((Decimal(x["modeled_net_return"]) for x in modeled), Decimal(0))),
                "unknown_outcomes": len(ledger["outcomes"]) - len(modeled),
            }
    group = {a: deepcopy(results[f"train/{a}"]) for a in w.ARMS}
    bad_trade = next(row for row in group["SHADOW"]["outcomes"] if row["status"] == "MODEL_ONLY")
    bad_trade["modeled_net_return"] = str(Decimal(bad_trade["modeled_net_return"]) - Decimal(".0018"))
    controls.append(rejected("double_cost", lambda: w.compare(group), ""))
    print(json.dumps(w.seal({"trial": reg["sha256"], "result": result["sha256"],
                            "controls": controls, "return_metrics": metrics,
                            "fresh_process_replay": "BYTE_IDENTICAL",
                            "market_inference": "NOT_ESTIMABLE_SYNTHETIC"}), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
