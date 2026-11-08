"""ATLAS H2 one-shot owner-local conditional operator. No E: access without
an independently provisioned, HMAC-authenticated, single-use owner envelope.
Never treat a declarative H2 policy preflight as source authorization.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

from tools.atlas_h2_historical_policy_v2 import assess, EXPECTED, KEYS

SCHEMA = "aql.integration.h2.local-one-shot.v1"
RECEIPT = "aql.integration.h2.local-one-shot-audit.v1"
PINS = {
    "integration": "51f3724213e836fa680f589435e418d4b0c4c20f",
    "core": EXPECTED["core"],
    "scanner": EXPECTED["scanner"],
    "factory": EXPECTED["factory"],
    "work235": EXPECTED["work235"],
}
STEP = 900000
ALLOWED = ("research_wp_r0/", "tools/", "src/")
HEX = set("0123456789abcdef")
OWNER_LIMITED_COSTS = {
    "fee_entry_bps": "10", "fee_exit_bps": "10",
    "spread_entry_bps": "2", "spread_exit_bps": "2",
    "slippage_entry_bps": "3", "slippage_exit_bps": "3",
    "funding_bps_per_bar": "0",
}


class Stop(ValueError):
    pass


def check(condition, reason):
    if not condition:
        raise Stop(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def contained(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    return path == root or root in path.parents


def verify_owner(manifest, key_path):
    """Independent HMAC key must be provisioned OUTSIDE manifest/repository.

    A signed manifest proves possession of that key, not source issuer PIT
    or the legal identity of its custodian. Key governance remains owner-local.
    """
    check(type(manifest) is dict and set(manifest) ==
          {"schema", "scope", "owner_approval_mac"}, "MANIFEST_SHAPE")
    check(manifest["schema"] == SCHEMA, "MANIFEST_VERSION")
    scope = manifest["scope"]
    check(type(scope) is dict and scope.get("single_use") is True
          and scope.get("explicit_readonly_no_export") is True
          and scope.get("source_rights_attested") is True
          and scope.get("research_class") == "RETROSPECTIVE_NON_PIT"
          and scope.get("publisher_pit_attested") is False
          and scope.get("owner_cost_authorized") is True,
          "SCOPE_NOT_AUTHORIZED")
    mac = manifest["owner_approval_mac"]
    check(type(mac) is str and len(mac) == 64 and set(mac) <= HEX,
          "OWNER_SIGNATURE_MISSING")
    key_path = Path(key_path).resolve(strict=True)
    check(key_path.is_file() and not key_path.is_symlink()
          and key_path.stat().st_size >= 32 and key_path.stat().st_size <= 4096,
          "OWNER_VERIFIER_KEY_INVALID")
    key = key_path.read_bytes()
    expected = hmac.new(key, canonical({"schema": SCHEMA, "scope": scope}),
                        hashlib.sha256).hexdigest()
    check(hmac.compare_digest(mac, expected), "OWNER_SIGNATURE_INVALID")
    check(set(scope["exact_heads"]) == set(PINS)
          and scope["exact_heads"] == PINS, "PIN_MISMATCH")
    costs = scope.get("costs")
    check(type(costs) is dict and set(costs) == set(KEYS),
          "COSTS_REQUIRED")
    from decimal import Decimal, InvalidOperation
    try:
        values = {k: Decimal(v) for k, v in costs.items()
                  if type(v) is str and v.strip() == v}
        check(set(values) == set(KEYS)
              and all(v.is_finite() and v >= 0 for v in values.values())
              and values["funding_bps_per_bar"] == 0
              and all(values[k] == Decimal(v)
                      for k, v in OWNER_LIMITED_COSTS.items()),
              "OWNER_ONE_RUN_COST_SCOPE_MISMATCH")
    except (InvalidOperation, ValueError):
        raise Stop("COSTS_INVALID") from None
    start, end, cutoff = (scope.get(k) for k in
                          ("start_ms", "end_exclusive_ms", "decision_cutoff_ms"))
    check(all(type(x) is int for x in (start, end, cutoff))
          and 0 <= start < end <= cutoff
          and (end - start) <= 4096 * STEP
          and start % STEP == 0 and end % STEP == 0,
          "BOUND_OR_CUTOFF")
    month = scope.get("month")
    check(type(month) is str
          and len(month) == 7
          and datetime.fromtimestamp(start / 1000, timezone.utc).strftime("%Y-%m") == month
          and datetime.fromtimestamp((end - 1) / 1000, timezone.utc).strftime("%Y-%m") == month,
          "CROSS_MONTH_OR_MONTH_INVALID")
    check(type(scope.get("dataset_id")) is str
          and scope["dataset_id"].startswith("BINANCE-SPOT-BTCUSDT-15M-")
          and type(scope.get("version")) is int and scope["version"] > 0
          and type(scope.get("strategy_id")) is str
          and type(scope.get("strategy_definition_sha256")) is str
          and len(scope["strategy_definition_sha256"]) == 64
          and type(scope.get("native_receipt_sha256")) is str
          and len(scope["native_receipt_sha256"]) == 64
          and type(scope.get("source_bytes_sha256")) is str
          and len(scope["source_bytes_sha256"]) == 64
          and type(scope.get("manifest_integrity_sha256")) is str
          and len(scope["manifest_integrity_sha256"]) == 64,
          "SOURCE_PINS_REQUIRED")
    return scope


def boundaries(scope, key_path, git_repo):
    """Validate no output/key overlaps with the original source."""
    roots = [Path(scope[x]).resolve(strict=True) for x in
             ("warehouse_root", "vault_root")]
    check(all(p.is_dir() and not p.is_symlink() for p in roots)
          and roots[0] != roots[1], "SOURCE_ROOTS_INVALID")
    outputs = [Path(scope[x]).absolute() for x in
               ("results_sqlite", "secretary_root", "evidence_json")]
    check(len({str(p) for p in outputs}) == len(outputs),
          "OUTPUT_COLLISION")
    for p in outputs:
        check(not p.exists() and not p.is_symlink()
              and p.parent.exists()
              and all(not contained(p, r) for r in roots),
              "OUTPUT_UNSAFE_OR_NOT_FRESH")
    check(all(not contained(key_path, r) for r in roots)
          and not contained(key_path, git_repo), "KEY_INSIDE_SOURCE_OR_REPO")
    check(all(not contained(p, git_repo) for p in outputs),
          "OUTPUT_INSIDE_CODE_REPO")
    return roots, outputs


def fingerprint(root):
    """Hash durable source bytes, never treat idle SQLite SHM as a WAL.

    SQLite SHM is lock/cache state, not committed market rows. Its content
    can change during a *read-only* WAL-aware backup. Record its existence and
    size; independently reject any nonempty WAL or rollback journal. The
    database and all durable source files must remain byte-identical.
    """
    root = Path(root)
    rows = []
    for p in sorted(root.rglob("*")):
        check(not p.is_symlink(), "SOURCE_SYMLINK")
        if p.is_dir():
            continue
        check(p.is_file(), "SOURCE_SPECIAL_FILE")
        name = p.name.lower()
        relative = str(p.relative_to(root)).replace("\\", "/")
        if name.endswith((".sqlite-wal", ".db-wal")):
            check(p.stat().st_size == 0,
                  "SOURCE_NONEMPTY_WAL_REQUIRES_OFFLINE_STABLE_SNAPSHOT")
            rows.append((relative, "EMPTY_WAL", 0))
            continue
        if name.endswith((".sqlite-shm", ".db-shm")):
            # Do not read/modify/delete SHM. It can carry transient reader
            # lock state without being an uncheckpointed data journal.
            rows.append((relative, "SQLITE_SHM_PRESENT", p.stat().st_size))
            continue
        check(not name.endswith(("-wal", "-shm", "-journal")),
              "SOURCE_UNRECOGNIZED_SQLITE_SIDECAR")
        rows.append((relative, p.stat().st_size, sha_file(p)))
    return digest(rows)


def verified_local_sqlite_snapshot(warehouse, workspace):
    """Read-only WAL-aware SQLite backup into isolated private scratch space.

    Never use immutable=1 against original live SQLite. Core's immutable
    query runs ONLY against the completed local backup and copied stage.
    """
    root = Path(warehouse)
    src = root / "warehouse.sqlite"
    check(src.is_file() and not src.is_symlink(),
          "SOURCE_WAREHOUSE_DB_MISSING")
    snapshot = Path(workspace) / "_private_warehouse_snapshot"
    check(not snapshot.exists(), "SNAPSHOT_ALREADY_EXISTS")
    snapshot.mkdir()
    copied = snapshot / "warehouse.sqlite"
    source_con = None
    dest_con = None
    try:
        source_con = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True,
                                     timeout=3)
        source_con.execute("PRAGMA query_only=ON")
        dest_con = sqlite3.connect(copied)
        source_con.backup(dest_con)
        check(dest_con.execute("PRAGMA quick_check").fetchone()[0] == "ok",
              "SNAPSHOT_SQLITE_QUICK_CHECK_FAILED")
    except sqlite3.Error:
        raise Stop("SOURCE_READONLY_SNAPSHOT_UNAVAILABLE_CLOSE_WRITERS_AND_RETRY") from None
    finally:
        if dest_con is not None:
            dest_con.close()
        if source_con is not None:
            source_con.close()
    stage = root / "stage"
    check(stage.is_dir() and not stage.is_symlink(),
          "SOURCE_STAGE_MISSING")
    # Private local copy; no upload and no hard links back to original.
    shutil.copytree(stage, snapshot / "stage", symlinks=False)
    check(not (snapshot / "warehouse.sqlite-wal").exists(),
          "SNAPSHOT_HAS_UNEXPECTED_WAL")
    return snapshot


def git_commit(repo, sha):
    out = subprocess.run(["git", "-C", str(repo), "rev-parse",
                          "--verify", sha + "^{commit}"],
                         capture_output=True, check=False, text=True)
    check(out.returncode == 0 and out.stdout.strip() == sha,
          "PIN_NOT_PRESENT_IN_LOCAL_GIT")


def isolated_overlay(repo, destination):
    """No branch checkout; archive exact commit objects; refuse unsafe entries."""
    file_hashes = {}
    for role in ("integration", "work235", "scanner", "factory", "core"):
        sha = PINS[role]
        git_commit(repo, sha)
        result = subprocess.run(["git", "-C", str(repo), "archive",
                                 "--format=tar", sha],
                                capture_output=True, check=False)
        check(result.returncode == 0, "GIT_ARCHIVE_FAILED")
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as tf:
            for member in tf:
                name = member.name.replace("\\", "/")
                if not name.startswith(ALLOWED):
                    continue
                check(not name.startswith("/") and ".." not in
                      Path(name).parts and (member.isfile() or member.isdir()),
                      "UNSAFE_CODE_ARCHIVE")
                if not member.isfile() or not (name.endswith(".py") or
                    (role == "work235" and name ==
                     "tools/strategy_service_offline/fixtures/strategies.json")):
                    continue
                data = tf.extractfile(member).read()
                dest = Path(destination) / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                file_hashes[name] = {"role": role,
                                     "sha256": hashlib.sha256(data).hexdigest()}
    required = ("tools/scanner_strategy_f/research_strategy_plugin.py",
                "research_wp_r0/aql_core_backbone_local_v1.py",
                "research_wp_r0/aql_factory_h_generic_signal_adapter_v1.py",
                "research_wp_r0/aql_core_h_research_secretary_v1.py",
                "tools/atlas_h_generic_secretary_bridge.py")
    check(all((Path(destination) / x).is_file() for x in required),
          "STAGED_CONTRACT_MISSING")
    return digest(file_hashes)


def native_receipt_check(scope, receipt):
    """Independent pre-retained Core245 receipt; not a fabricated PIT proof."""
    check(type(receipt) is dict
          and receipt.get("schema") ==
          "aql.core.historical-price-custody-query.v1"
          and receipt.get("status") == "OK", "CORE245_RECEIPT_INVALID")
    seal = receipt.get("price_query_sha256")
    check(type(seal) is str
          and digest({k: v for k, v in receipt.items()
                      if k != "price_query_sha256"}) == seal
          and sha_file(scope["native_receipt_file"]) ==
          scope["native_receipt_sha256"]
          and receipt.get("source_bytes_sha256") ==
          scope["source_bytes_sha256"]
          and receipt.get("manifest_integrity_sha256") ==
          scope["manifest_integrity_sha256"]
          and receipt.get("dataset_id") == scope["dataset_id"]
          and receipt.get("version") == scope["version"]
          and receipt.get("decision_cutoff_ms") ==
          scope["decision_cutoff_ms"]
          and receipt.get("coverage") == "COMPLETE"
          and receipt.get("required_bar_count") ==
          receipt.get("available_bar_count")
          and receipt.get("missing_bar_opens") == [],
          "CORE245_NATIVE_PARENT_MISMATCH")
    # A retained receipt from a different month, or from a sparse
    # same-count window, cannot be reused as this source's dual-query pin.
    starts = list(range(scope["start_ms"], scope["end_exclusive_ms"], STEP))
    check(receipt["required_bar_count"] == len(starts)
          and [x.get("bar_open_ms") for x in receipt.get("bars", [])] ==
          starts
          and all(x.get("bar_close_ms") == t + STEP - 1
                  for t, x in zip(starts, receipt.get("bars", []))),
          "CORE245_NATIVE_WINDOW_MISMATCH")
    return seal


def run_authorized(scope, overlay):
    """Called only AFTER owner MAC, paths and code identity; source IO starts here."""
    sys.path.insert(0, str(overlay))
    from research_wp_r0.aql_core_backbone_local_v1 import query_local
    from research_wp_r0.aql_factory_e_research_results_store_v1 import (
        digest as factory_digest, migrate_store_v2)
    from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import (
        run_factory_h_generic_research, SCHEMA as FACTORY_SCHEMA,
        COST_SCHEMA)
    from research_wp_r0.aql_factory_h_research_package_v1 import TABLE
    from research_wp_r0.strategy_definition import StrategyDefinition
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
    from tools.scanner_strategy_f import research_strategy_plugin as scanner
    from tools.strategy_service_offline.common import Frozen
    from tools.atlas_h_generic_secretary_bridge import deliver_generic_research_wait

    native = json.loads(Path(scope["native_receipt_file"]).read_text("utf-8"))
    native_sha = native_receipt_check(scope, native)
    query = query_local(
        scope["warehouse_root"], scope["dataset_id"], scope["version"],
        scope["start_ms"], scope["end_exclusive_ms"],
        scope["decision_cutoff_ms"],
        required_source_sha256=scope["source_bytes_sha256"],
        require_complete=True, sqlite_immutable=True)
    check(query["coverage"] == "COMPLETE"
          and query["required_bar_count"] == query["available_bar_count"]
          and len(query["bars"]) == query["required_bar_count"]
          and not query["missing_bar_opens"]
          and query["source_bytes_sha256"] == scope["source_bytes_sha256"]
          and query["manifest_integrity_sha256"] ==
          scope["manifest_integrity_sha256"]
          and query["query_sha256"] != native_sha
          and query["historical_pit"] == "NOT_ATTESTED"
          and query["decision_cutoff_ms"] == scope["decision_cutoff_ms"]
          and query["dataset_id"] == scope["dataset_id"]
          and query["version"] == scope["version"],
          "CORE253_COVERAGE_OR_QUERY_SHA")
    # Reuse the *accepted* declarative Option C v2 contract, but do not
    # mistake its self-declared READY for independent owner authorization.
    policy_request = {
        "schema": "aql.integration.h2.historical-policy-request.v2",
        "research_class": "RETROSPECTIVE_NON_PIT",
        "exact_heads": PINS.copy(),
        "bounded_request": {
            "dataset_id": scope["dataset_id"],
            "month": scope["month"],
            "start_ms": scope["start_ms"],
            "end_exclusive_ms": scope["end_exclusive_ms"],
            "decision_cutoff_ms": scope["decision_cutoff_ms"],
            "strategy_definition_sha256": scope["strategy_definition_sha256"],
        },
        "owner_permission": {
            "granted": True,
            "scope": "BOUNDED_ORIGINAL_HISTORY_READONLY",
            "authorization_reference": "OWNER_LOCAL_MAC:" + digest(scope),
        },
        "owner_cost_policy": {
            "owner_authorized": True,
            "authorization_reference": "OWNER_LOCAL_MAC:" + digest(scope),
            "market": "SPOT", "direction": "LONG",
            "scenario_class": "OWNER_DECLARED_RESEARCH_SCENARIO",
            "costs": scope["costs"],
        },
        "source_provenance": {
            "source_rights_attested": True,
            "publisher_pit_attested": False,
            "source_receipt_sha256": scope["source_bytes_sha256"],
            "manifest_integrity_sha256": scope["manifest_integrity_sha256"],
            "core245_native_query_sha256": native_sha,
            "core253_local_query_sha256": query["query_sha256"],
        },
    }
    check(assess(policy_request)["status"] == "READY_FOR_OWNER_AUTHORIZATION",
          "H2_V2_POLICY_REJECTION")
    definition = json.loads(Path(scope["strategy_definition_file"]).read_text("utf-8"))
    strategy = StrategyDefinition.from_dict(
        definition, registry=IndicatorRegistryV2())
    check(strategy.digest == scope["strategy_definition_sha256"]
          and strategy.spec["strategy_id"] == scope["strategy_id"],
          "MANUAL_STRATEGY_DRIFT")
    plugin = scanner.register_strategy_plugin(
        definition, config_digest=scanner.manual_config_digest(definition),
        origin="MANUAL")
    policy = scanner.research_signal_policy(
        source_class="OWNER_LOCAL_RECOVERY_DIAGNOSTIC")
    signal = scanner.evaluate_strategy_plugin(
        plugin, query, warehouse_root=scope["warehouse_root"],
        policy=policy)
    scanner.verify_factory_signal_batch(signal)
    meta = Frozen.restore(plugin).data
    cost = {
        "schema": COST_SCHEMA, "costs": scope["costs"], "market": "SPOT",
        "direction": "LONG",
        "scenario_class": "OWNER_DECLARED_RESEARCH_SCENARIO",
        "owner_operator_authorized": True,
        "fill_semantics": "NEXT_ELIGIBLE_OPEN_UNKNOWN_ON_INTRABAR_TOUCH",
        "holdout": "SEALED_UNOPENED", "trading_authority": "NONE",
    }
    cost["sha256"] = factory_digest(cost)
    packet = {
        "schema": FACTORY_SCHEMA, "experiment_id": scope["experiment_id"],
        "scanner_signal_batch": signal, "strategy_plugin": plugin,
        "scanner_signal_policy": policy, "core_query": query,
        "operator_cost_policy": cost,
        "factory_code_sha256": scope["factory_code_sha256"],
        "source_query_sha256": query["query_sha256"],
        "source_bytes_sha256": query["source_bytes_sha256"],
        "manifest_integrity_sha256": query["manifest_integrity_sha256"],
        "strategy_definition_sha256": meta["definition_digest"],
        "strategy_plugin_sha256": plugin["sha256"],
        "config_sha256": meta["config_digest"],
        "scanner_policy_sha256": policy["sha256"],
        "scanner_evaluator_code_sha256": meta["evaluator_code_sha256"],
        "decision_cutoff_ms": query["decision_cutoff_ms"],
        "holdout": "SEALED_UNOPENED", "historical_pit": "NOT_ATTESTED",
        "trading_authority": "NONE",
        "source_ack_sha256": None, "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
    }
    packet["sha256"] = factory_digest(packet)
    results = Path(scope["results_sqlite"])
    check(not results.exists(), "RESULTS_ALREADY_EXIST")
    migrate_store_v2(results)
    first = run_factory_h_generic_research(packet, results)
    replay = run_factory_h_generic_research(packet, results)
    check(first["store_status"] == "STORED_IMMUTABLE"
          and replay["store_status"] == "REPLAY_IDENTICAL"
          and first["package_sha256"] == replay["package_sha256"]
          and first["trading_authority"] == "NONE",
          "FACTORY_IMMUTABLE_REPLAY_FAILED")
    con = sqlite3.connect(results)
    try:
        stored = con.execute(f"SELECT document FROM {TABLE} WHERE experiment_id=?",
                             (packet["experiment_id"],)).fetchone()
    finally:
        con.close()
    check(stored is not None, "FACTORY_PACKAGE_NOT_PERSISTED")
    package = json.loads(stored[0])
    delivery = deliver_generic_research_wait(
        secretary_root=scope["secretary_root"], packet=packet,
        factory_package=package, factory_result=first)
    check(delivery["status"] == "WAIT_RESEARCH_REVIEW"
          and delivery["trading_authority"] == "NONE",
          "SECRETARY_ROUTE_FAILED")
    return {
        "native_core245_sha256": native_sha,
        "bounded_core253_sha256": query["query_sha256"],
        "coverage": query["coverage"],
        "required_bars": query["required_bar_count"],
        "observed_bars": query["available_bar_count"],
        "missing_bars": len(query["missing_bar_opens"]),
        "scanner_sha256": signal["sha256"],
        "factory_package_sha256": first["package_sha256"],
        "lab_sha256": first["scientific_lab_sha256"],
        "secretary_sha256": delivery["secretary_route_sha256"],
        "replay": replay["store_status"],
        "cost_policy_sha256": cost["sha256"],
    }


def receipt(status, reason, scope=None, **fields):
    data = {
        "schema": RECEIPT, "status": status, "reason": reason,
        "operation": "OWNER_LOCAL_CONDITIONAL_H2",
        "historical_pit": "NOT_ATTESTED",
        "scientific_claims_allowed": False,
        "economic_approval": "NOT_GRANTED",
        "f5": "BLOCKED_EXTERNAL_INPUT", "trading": "NONE",
        "holdout": "SEALED_UNOPENED", **fields,
    }
    if scope:
        data["authorization_scope_sha256"] = digest(scope)
    return {**data, "sha256": digest(data)}


def execute(manifest, *, key_file=None, repo=None, allow_local_run=False):
    """No original access, even metadata enumeration, before authenticated gate."""
    if not allow_local_run:
        return receipt("WAIT_SOURCE_PERMISSION", "EXPLICIT_LOCAL_RUN_FLAG_REQUIRED")
    if key_file is None or repo is None:
        return receipt("WAIT_SOURCE_PERMISSION", "EXTERNAL_OWNER_KEY_AND_LOCAL_GIT_REQUIRED")
    scope = None
    try:
        # Verify signed owner scope BEFORE checking whether private source exists.
        scope = verify_owner(manifest, key_file)
        repo = Path(repo).resolve(strict=True)
        check((repo / ".git").exists(), "LOCAL_GIT_REPOSITORY_REQUIRED")
        roots, outputs = boundaries(scope, key_file, repo)
        with tempfile.TemporaryDirectory(prefix="aql-h2-isolated-") as d:
            overlay = Path(d)
            code_sha = isolated_overlay(repo, overlay)
            # Spawn a fresh isolated interpreter to prevent current process
            # sys.modules / package path contamination from bypassing pins.
            own = Path(__file__).resolve(strict=True)
            staged_operator = overlay / "tools" / own.name
            staged_operator.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(own, staged_operator)
            code_sha = digest({"overlay": code_sha,
                               "operator_sha256": sha_file(staged_operator)})
            manifest_file = overlay / "_private_scope.json"
            manifest_file.write_text(json.dumps(scope), encoding="utf-8")
            worker = (
                "import json,sys; from pathlib import Path; "
                "root=Path(sys.argv[1]); sys.path.insert(0,str(root)); "
                "from tools.atlas_h2_owner_local_one_shot_v1 import run_authorized; "
                "scope=json.loads((root/'_private_scope.json').read_text()); "
                "print(json.dumps(run_authorized(scope,root),sort_keys=True))"
            )
            pre = [fingerprint(r) for r in roots]
            try:
                # Snapshot is created only AFTER permission, code pins and
                # source sidecar checks. No implicit mutable original read.
                snapshot_root = verified_local_sqlite_snapshot(
                    scope["warehouse_root"], overlay)
                snap_scope = dict(scope)
                snap_scope["warehouse_root"] = str(snapshot_root)
                manifest_file.write_text(
                    json.dumps(snap_scope), encoding="utf-8")
                job = subprocess.run(
                    [sys.executable, "-I", "-c", worker, str(overlay)],
                    cwd=overlay, capture_output=True, text=True,
                    check=False, timeout=3600)
                check(job.returncode == 0, "ISOLATED_SOURCE_OR_E2E_FAILED")
                detail = json.loads(job.stdout)
            finally:
                post = [fingerprint(r) for r in roots]
            check(pre == post, "ORIGINAL_SOURCE_CHANGED_STOP")
        return receipt("EXPERIMENT_ENGINEERING_PASS",
                       "BOUNDED_NON_PIT_RESEARCH_ONLY",
                       scope, isolated_code_sha256=code_sha,
                       source_no_write_sha256=digest(pre), **detail)
    except (Stop, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, Stop) else "LOCAL_VERIFICATION_OR_EXECUTION_FAILED"
        return receipt("BLOCKED", reason, scope)


def main(argv=None):
    p = argparse.ArgumentParser(description="H2 one-shot; private by default")
    p.add_argument("--private-manifest", required=True)
    p.add_argument("--owner-hmac-key-file")
    p.add_argument("--local-git-repo")
    p.add_argument("--authorize-local-readonly-run", action="store_true")
    p.add_argument("--local-audit-output")
    a = p.parse_args(argv)
    if not a.authorize_local_readonly_run:
        result = execute({}, allow_local_run=False)
    else:
        check(a.local_audit_output is not None,
              "LOCAL_AUDIT_OUTPUT_REQUIRED")
        manifest = json.loads(Path(a.private_manifest).read_text("utf-8"))
        # A caller cannot redirect evidence to a source path or unsigned location.
        signed_scope = verify_owner(manifest, a.owner_hmac_key_file)
        check(Path(a.local_audit_output).absolute() ==
              Path(signed_scope["evidence_json"]).absolute(),
              "AUDIT_OUTPUT_NOT_IN_OWNER_SCOPE")
        result = execute(manifest, key_file=a.owner_hmac_key_file,
                         repo=a.local_git_repo,
                         allow_local_run=True)
    if a.local_audit_output:
        dest = Path(a.local_audit_output).absolute()
        check(dest.parent.is_dir() and not dest.is_symlink()
              and not dest.exists(), "FRESH_AUDIT_OUTPUT_REQUIRED")
        temporary = dest.with_suffix(dest.suffix + ".tmp")
        check(not temporary.exists(), "AUDIT_TEMP_COLLISION")
        temporary.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        os.replace(temporary, dest)
    print(json.dumps({"status": result["status"], "sha256": result["sha256"],
                      "reason": result["reason"]}, sort_keys=True))
    return 0 if result["status"] == "EXPERIMENT_ENGINEERING_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
