"""Produce and reopen one sealed, disposable Queue 2 synthetic DEV package."""
import argparse
from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from research_wp_r0.aql_factory_e_research_results_store_v1 import (  # noqa: E402
    _check_seal, digest, migrate_store_v2, read_experiment,
)
from research_wp_r0.aql_factory_h_research_package_v1 import TABLE  # noqa: E402
from research_wp_r0.aql_queue2_synthetic_dev_v1 import (  # noqa: E402
    EXPERIMENT, code_identity, evaluate_cohort, require, run_synthetic_dev,
)


def revision():
    return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                   text=True).strip()


def produce(destination):
    from research_wp_r0.aql_core_d_permitted_cohort_v1 import create_permitted_synthetic_cohort
    from tools.atlas_factory_pkg02_execution_smoke import fixture_packet, negative_receipt
    from research_wp_r0.aql_factory_h_execution_comparison_v1 import (
        run_factory_h_execution_comparison,
    )

    destination.mkdir(parents=True, exist_ok=False)
    specs = json.loads((ROOT / "tools/strategy_service_offline/fixtures/strategies.json").read_text())
    store = destination / "results.sqlite"
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        cohort = create_permitted_synthetic_cohort(root / "core", root / "vault", specs, count=256)
        package = evaluate_cohort(root / "core", cohort)
        second = create_permitted_synthetic_cohort(root / "replay-core", root / "replay-vault",
                                                  specs, count=256)
        require(package == evaluate_cohort(root / "replay-core", second), "SOURCE_REPLAY_DRIFT")
        failures = {}
        for name in ("source_seal", "source_identity", "source_authority"):
            bad = deepcopy(cohort)
            if name == "source_seal":
                bad["local"]["query_sha256"] = "0" * 64
            elif name == "source_identity":
                bad["receipt"]["source_zip_sha256"] = "0" * 64
                bad["receipt"]["cohort_sha256"] = digest({
                    k: v for k, v in bad["receipt"].items() if k != "cohort_sha256"
                })
            else:
                bad["receipt"]["cohort_evidence_class"] = "ORIGINAL_MARKET"
                bad["receipt"]["cohort_sha256"] = digest({
                    k: v for k, v in bad["receipt"].items() if k != "cohort_sha256"
                })
            try:
                evaluate_cohort(root / "core", bad)
            except ValueError as error:
                failures[name] = str(error)
            else:
                raise ValueError("QUEUE2_ACCEPTED_INVALID_" + name)
        with closing(sqlite3.connect((root / "core/warehouse.sqlite").as_uri()
                                    + "?mode=ro", uri=True)) as con:
            outboxes = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                                   "(name LIKE '%outbox%' OR name LIKE 'd_canonical_strategy_%')").fetchall()
            for (table,) in outboxes:
                quoted = '"' + table.replace('"', '""') + '"'
                require(con.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0] == 0,
                        "SOURCE_CREATED_DISPATCH_EVENT")
        migrate_store_v2(store)
        first = run_synthetic_dev(root / "core", cohort, store)
        replay = run_synthetic_dev(root / "core", cohort, store)
        require(first["package_sha256"] == replay["package_sha256"]
                and replay["store_status"] == "REPLAY_IDENTICAL", "STORE_REPLAY_DRIFT")
    fixture = fixture_packet()
    execution = run_factory_h_execution_comparison(fixture, store)
    execution_replay = run_factory_h_execution_comparison(fixture, store)
    require(execution["package_sha256"] == execution_replay["package_sha256"]
            and execution_replay["store_status"] == "REPLAY_IDENTICAL", "COST_REPLAY_DRIFT")
    body = {"schema": "aql.queue2.offline-dev-evidence.v1", "revision": revision(),
            "code_sha256": code_identity(), "paired_package": package,
            "paired_receipt": first, "paired_replay": replay,
            "source_rejections": failures, "execution_receipt": execution,
            "execution_replay": execution_replay, "execution_negatives": negative_receipt(fixture),
            "source_class": "SYNTHETIC_FIXTURE_ONLY", "historical_pit": "NOT_ATTESTED",
            "holdout": "SEALED_UNOPENED", "validation": "RESERVED_UNEVALUATED",
            "orders_created": 0, "paper_positions": 0, "dispatches": 0,
            "secretary": "NOT_ENQUEUED", "factory_consumer_ack": None,
            "trading_authority": "NONE"}
    evidence = {**body, "sha256": digest(body)}
    (destination / "evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    return readback(destination)


def readback(destination):
    evidence = json.loads((destination / "evidence.json").read_text(encoding="utf-8"))
    _check_seal(evidence)
    require(evidence["schema"] == "aql.queue2.offline-dev-evidence.v1"
            and evidence["revision"] == revision()
            and evidence["code_sha256"] == code_identity()
            and evidence["source_class"] == "SYNTHETIC_FIXTURE_ONLY"
            and evidence["trading_authority"] == "NONE"
            and evidence["holdout"] == "SEALED_UNOPENED"
            and evidence["validation"] == "RESERVED_UNEVALUATED"
            and evidence["secretary"] == "NOT_ENQUEUED"
            and evidence["factory_consumer_ack"] is None
            and evidence["orders_created"] == evidence["paper_positions"] == evidence["dispatches"] == 0,
            "EVIDENCE_SCOPE_OR_REVISION")
    package = evidence["paired_package"]
    _check_seal(package)
    record = read_experiment(destination / "results.sqlite", EXPERIMENT, detached_snapshot=True)
    require(record["result_sha256"] == package["sha256"]
            and record["sha256"] == evidence["paired_receipt"]["experiment_sha256"]
            and record["source_status"] == "SYNTHETIC_ENGINEERING_PASS"
            and record["evidence_class"] == "TEST_ONLY", "STORED_EXPERIMENT_DRIFT")
    uri = (destination / "results.sqlite").resolve().as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        for experiment, expected in (
            (EXPERIMENT, package["sha256"]),
            ("RESEARCH-H-EXEC-CMP-PKG02-SYNTHETIC", evidence["execution_receipt"]["package_sha256"]),
        ):
            row = con.execute(f"SELECT canonical_sha256,document FROM {TABLE} WHERE experiment_id=?",
                              (experiment,)).fetchone()
            require(row is not None and row[0] == expected, "STORED_PACKAGE_MISSING")
            document = json.loads(row[1])
            _check_seal(document)
            require(document["sha256"] == expected, "STORED_PACKAGE_DRIFT")
    return {"status": "PASS_SYNTHETIC_DEV_ONLY", "evidence_sha256": evidence["sha256"],
            "package_sha256": package["sha256"], "lab": package["lab"],
            "source_rejected": len(evidence["source_rejections"]),
            "execution_rejected": evidence["execution_negatives"]["rejected_count"],
            "trading_authority": "NONE"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()

    def forbid_network(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("QUEUE2_NETWORK_FORBIDDEN")

    sys.addaudithook(forbid_network)
    result = readback(args.directory) if args.readback else produce(args.directory)
    print(json.dumps(result, sort_keys=True))
