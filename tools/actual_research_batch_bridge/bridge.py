"""Retrospective dispatch over A evaluation and B resource/store primitives."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from tools.actual_research_batch_bridge.stage import PINS

ROOT = Path(__file__).resolve().parents[2]
ACTUAL = "RETAINED_ACTUAL_MARKET_RETROSPECTIVE_NON_PIT"
FIXTURE = "SIMULATED_ADAPTER_TEST"
BUDGET = dict(worker_cpu_s=35, worker_wall_s=60, worker_memory_mb=512,
              result_bytes=32 * 1024**2, worker_io_bytes=256 * 1024**2,
              batch_wall_s=120, local_bytes=160 * 1024**2, max_workers=2, max_claims=2)


def need(condition, code):
    if not condition:
        raise ValueError(code)


def read(path):
    return json.loads(path.read_bytes())


def digest_bytes(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def activate(stage, deps):
    expected = read(Path(__file__).with_name("module-pins.json"))
    actual = {f"{role}/{path.relative_to(stage / role).as_posix()}": digest_bytes(path)
              for role in PINS for path in (stage / role).rglob("*.py")}
    need(actual == expected, "STAGED_SOURCE_PIN")
    sys.path[:0] = [str(stage / "a"), str(stage / "b"), str(ROOT)]
    from tools.first_research_cycle import market_cycle as a
    baseline = read(stage / "a/tools/first_research_cycle/market-plan.json")
    need(a.sha(baseline) == (stage / "a/tools/first_research_cycle/market-plan.sha256").read_text().strip(),
         "A_PLAN_PIN")
    a.configure(deps, baseline)
    return a, baseline


def source_files(source, plan):
    files = {}
    for archive in plan["archives"]:
        name = archive["name"]
        need(Path(name).name == name and name.endswith(".zip"), "ARCHIVE_NAME")
        for suffix in ("", ".CHECKSUM"):
            path = source / (name + suffix)
            need(not path.is_symlink() and not getattr(path.lstat(), "st_file_attributes", 0) & 0x400
                 and path.stat().st_size <= 8_000_000, "SOURCE_FILE")
            files[name + suffix] = digest_bytes(path)
        need(files[name] == archive["sha256"], "SOURCE_SHA_SWAP")
    return files


def plans(a, baseline, stage, source, fixture):
    if fixture:
        from tools.first_research_cycle.test_market import fixture as make_fixture
        baseline = make_fixture(source)
    need(baseline["source_class"] == (FIXTURE if fixture else ACTUAL), "SOURCE_CLASS")
    alternate = alternate_plan(baseline)
    snapshots = source_files(source, baseline)
    modules = {f"{role}/{path.relative_to(stage / role).as_posix()}": digest_bytes(path)
               for role in PINS for path in (stage / role).rglob("*.py")}
    tasks = []
    for label, plan in (("sma3-8", baseline), ("sma3-12", alternate)):
        body = dict(id=label, plan=plan, plan_sha256=a.sha(plan), strategy_sha256=plan["strategy"]["digest"])
        tasks.append({**body, "sha256": a.sha(body)})
    body = dict(schema="aql.actual-research-batch-bridge.plan.v1", pins=PINS, tasks=tasks,
                source_class=baseline["source_class"], source_files=snapshots,
                source_availability="UNKNOWN", pit="NOT_ATTESTED", science="REAL_PIT_OOS_BLOCKED",
                holdout="SEALED_UNOPENED", trading_authority="NONE", actual_fills=None,
                ack=None, winner=None, budgets=BUDGET, modules=modules)
    return {**body, "sha256": a.sha(body)}


def alternate_plan(baseline):
    alternate = deepcopy(baseline)
    alternate["seed"] = 29812
    from research_wp_r0.strategy_definition import StrategyDefinition, digest
    spec = alternate["strategy"]["definition"]
    slow = next(item for item in spec["indicators"] if item["name"] == "slow")
    need(slow["parameters"]["period"] == 8, "FROZEN_BASELINE_PERIOD")
    slow["parameters"]["period"] = 12
    spec["strategy_id"] = "first_cycle_sma3_12"
    alternate["strategy"]["digest"] = digest(spec)
    StrategyDefinition.from_dict(alternate["strategy"])
    return alternate


def validate(a, plan, stage, source):
    need(plan["sha256"] == a.sha({k: v for k, v in plan.items() if k != "sha256"}), "BATCH_SEAL")
    need(plan["schema"] == "aql.actual-research-batch-bridge.plan.v1" and plan["pins"] == PINS
         and plan["budgets"] == BUDGET, "CONTRACT")
    need(plan["pit"] == "NOT_ATTESTED" and plan["source_availability"] == "UNKNOWN"
         and plan["science"] == "REAL_PIT_OOS_BLOCKED" and plan["holdout"] == "SEALED_UNOPENED"
         and plan["trading_authority"] == "NONE"
         and all(plan[key] is None for key in ("actual_fills", "ack", "winner")), "EVIDENCE_BOUNDARY")
    tasks = plan["tasks"]
    need(len(tasks) == 2 and [task["id"] for task in tasks] == ["sma3-8", "sma3-12"]
         and len({t["strategy_sha256"] for t in tasks}) == 2
         and len({t["plan"]["seed"] for t in tasks}) == 2, "TASK_POPULATION")
    approved = read(stage / "a/tools/first_research_cycle/market-plan.json")
    if plan["source_class"] == ACTUAL:
        need(tasks[0]["plan"] == approved, "ACTUAL_SCOPE_SWAP")
    need(tasks[1]["plan"] == alternate_plan(tasks[0]["plan"]), "VARIANT_SCOPE_SWAP")
    for task in tasks:
        native = task["plan"]
        need(task["sha256"] == a.sha({k: v for k, v in task.items() if k != "sha256"})
             and task["plan_sha256"] == a.sha(native)
             and task["strategy_sha256"] == native["strategy"]["digest"], "TASK_SEAL")
        need(native["source_class"] == plan["source_class"] in (ACTUAL, FIXTURE)
             and native["real_pit"] == "NOT_ATTESTED" and native["holdout"] == "SEALED_UNOPENED"
             and native["trading_authority"] == "NONE"
             and all(native.get(key) is None for key in ("actual_fills", "ack", "winner", "claimed_pnl")),
             "NATIVE_EVIDENCE_BOUNDARY")
        need({k:v for k,v in native.items() if k not in ("strategy","seed")} ==
             {k:v for k,v in tasks[0]["plan"].items() if k not in ("strategy","seed")}, "NATIVE_SCOPE_SWAP")
        need(source_files(source, native) == plan["source_files"], "SOURCE_CUSTODY")
    modules = {f"{role}/{path.relative_to(stage / role).as_posix()}": digest_bytes(path)
               for role in PINS for path in (stage / role).rglob("*.py")}
    need(modules == plan["modules"], "EVALUATOR_PIN")


def readback(a, task, folder):
    from tools.first_research_cycle.verify_run import verify
    from tools.research_capacity_scale.runtime import catalog
    report = read(folder / "result.json")
    checked = verify(folder)
    docs = catalog(folder / "factory.sqlite")
    evaluation = docs["FIRST-CYCLE-294"]
    need(evaluation["schema"] == "aql.first-cycle.actual-market-evaluation.v1"
         and report["schema"] == "aql.first-cycle.actual-market-result.v1"
         and report["plan_sha256"] == task["plan_sha256"]
         and report["source_class"] == evaluation["source_class"] == task["plan"]["source_class"]
         and report["source"] == [
             dict(name=item["name"], sha256=item["sha256"], rows=item["rows"],
                  checksum="MATCH_RETAINED_NOT_EXTERNAL_WITNESS") for item in task["plan"]["archives"]]
         and report["science"] == "REAL_PIT_OOS_BLOCKED" and report["holdout"] == "SEALED_UNOPENED"
         and report["actual_fills"] is None and report["trading_authority"] == "NONE"
         and evaluation["source_sha256"] == a.sha(report["source"])
         and evaluation["native_plan_sha256"] == report["native_plan_sha256"]
         and evaluation["factory_experiment_sha256"] == report["factory_experiment_sha256"]
         and evaluation["candidate_package_sha256"] == report["candidate_package_sha256"], "A_RESULT_PARENT")
    candidate = read(folder / "candidate.json")
    need(candidate["strategy_definition_digest"] == task["strategy_sha256"]
         and candidate["package_digest"] == report["candidate_package_sha256"]
         and candidate["package_digest"] == a.sha({k:v for k,v in candidate.items() if k!="package_digest"}),
         "CANDIDATE_PARENT")
    rows = evaluation["outcomes"]
    need(all(row["status"] == "UNKNOWN_FILL" and row["net_return"] is None
             and not row["legs"] for row in rows if row["scenario"] == "PASSIVE_ENTRY_MARKET_EXIT"),
         "PASSIVE_UNKNOWN_PROMOTION")
    need(sum(report["outcome_status_counts"].values()) == report["populations"]["cost_rows"]
         and sum(report["populations"]["scanner_census"].values()) == report["populations"]["source_bars"],
         "POPULATION_RECONCILIATION")
    return dict(result_sha256=report["sha256"], evaluation_sha256=evaluation["sha256"],
                verification_sha256=checked["sha256"], populations=report["populations"],
                outcome_status_counts=report["outcome_status_counts"], attempt_id="attempt294",
                trial_id="FIRST-CYCLE-294", identity_namespace=task["sha256"])


def worker(args, a, plan):
    from tools.research_capacity_scale.resources import enforce, counters
    guard = enforce(BUDGET, args.parent, args.output.parent.parent / "cancel")
    task = next(item for item in plan["tasks"] if item["id"] == args.worker)
    a.checkpoint(args.output.parent / (args.worker + ".lease.json"),
                 dict(pid=os.getpid(), created=counters(os.getpid())["created"], task_sha256=task["sha256"]))
    a.run(args.source, args.deps, args.output, task["plan"])
    a.persist(args.output / "resources.json", dict(guard=guard, counters=counters(os.getpid())))


def batch(args, a, plan):
    from tools.research_capacity_scale.runtime import safe, store, catalog, save, disk_bytes
    from tools.research_capacity_scale.resources import counters, lower_priority
    from research_wp_r0.aql_factory_e_research_results_store_v1 import migrate_store_v2
    lower_priority()
    root = safe(args.output)
    for protected in (args.source, args.stage, args.deps):
        protected = safe(protected)
        need(root != protected and root not in protected.parents and protected not in root.parents, "OUTPUT_SCOPE")
    need(1 <= args.workers <= BUDGET["max_workers"], "WORKER_COUNT")
    if root.exists():
        need((root / "plan.json").exists() and read(root / "plan.json") == plan, "RUN_OWNERSHIP")
    root.mkdir(parents=True, exist_ok=True)
    a.persist(root / "plan.json", plan)
    lock = root / "runner.lock"
    if lock.exists():
        old = read(lock)
        proc = counters(old["pid"])
        need(proc is None or proc["created"] != old["created"], "CONCURRENT_RUNNER")
        lock.unlink()
    save(lock, dict(pid=os.getpid(), created=counters(os.getpid())["created"]))
    try:
        a.persist(root / "selection.json", {"count":args.count})
        path = root / "batch.sqlite"
        if not path.exists():
            need(not any(root.glob("sma3-*")), "MISSING_BATCH_CHECKPOINT")
            migrate_store_v2(path)
        docs = catalog(path) if path.exists() and (root / "initialized.json").exists() else {}
        store(path, dict(schema="aql.bridge.checkpoint.v1", experiment_id="PLAN", plan_sha256=plan["sha256"]))
        a.persist(root / "initialized.json", {"plan_sha256": plan["sha256"]})
        need(not docs or docs.get("PLAN", {}).get("plan_sha256") == plan["sha256"], "CHECKPOINT_PARENT")
        started = time.monotonic()
        need(0 < args.deadline_s <= BUDGET["batch_wall_s"], "DEADLINE_BOUND")
        deadline = started + args.deadline_s
        selected = plan["tasks"][:args.count]
        for task in selected:
            lease_path = root / (task["id"] + ".lease.json")
            if lease_path.exists():
                lease = read(lease_path)
                need(lease["task_sha256"] == task["sha256"], "WORKER_LEASE_PARENT")
                end = time.monotonic() + 3
                while True:
                    proc = counters(lease["pid"])
                    if proc is None or proc["created"] != lease["created"]:
                        break
                    need(time.monotonic() < end, "PREVIOUS_WORKER_STILL_RUNNING")
                    time.sleep(.04)

        def dispatch(task):
            folder = root / task["id"]
            command = [sys.executable, "-B", "-m", "tools.actual_research_batch_bridge.bridge",
                       "--stage", str(args.stage), "--deps", str(args.deps), "--source", str(args.source),
                       "--output", str(folder), "--plan", str(root / "plan.json"),
                       "--worker", task["id"], "--parent", str(os.getpid())]
            with (root / (task["id"] + ".log")).open("ab") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log)
                status = None
                peak = dict(cpu_s=0, peak_rss=0, io_bytes=0)
                try:
                    while process.poll() is None:
                        stat = counters(process.pid)
                        if stat:
                            for key in peak:
                                peak[key] = max(peak[key], stat[key])
                        if (root / "cancel").exists():
                            status = "CANCELLED"
                        elif time.monotonic() >= deadline:
                            status = "TIMEOUT"
                        elif disk_bytes(root) > BUDGET["local_bytes"] or peak["io_bytes"] > BUDGET["worker_io_bytes"]:
                            status = "REJECTED"
                        if status:
                            process.kill()
                            break
                        time.sleep(.04)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                status = status or {0:"SUCCEEDED",124:"TIMEOUT",125:"CANCELLED"}.get(process.returncode,"FAILED")
            return status, peak

        metrics = {}
        outcomes = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = {}
            for task in selected:
                identity = task["id"]
                terminal = docs.get("OUTCOME-" + identity)
                folder = root / identity
                if terminal:
                    need(terminal["task_sha256"] == task["sha256"], "TERMINAL_PARENT")
                    if terminal["status"] == "SUCCEEDED":
                        need(terminal["evidence"] == readback(a, task, folder), "FORGED_RECEIPT")
                    outcomes[identity] = terminal
                    continue
                claims = sum(key.startswith("CLAIM-" + identity + "-") for key in docs)
                if (folder / "resources.json").exists():
                    pending[identity] = None
                elif claims >= BUDGET["max_claims"]:
                    pending[identity] = "FAILED"
                elif (root / "cancel").exists():
                    pending[identity] = "CANCELLED"
                else:
                    store(path, dict(schema="aql.bridge.claim.v1", experiment_id=f"CLAIM-{identity}-{claims+1}",
                                     task_sha256=task["sha256"], ordinal=claims+1))
                    pending[identity] = pool.submit(dispatch, task)
            for task in selected:
                identity = task["id"]
                if identity in outcomes:
                    continue
                entry = pending[identity]
                status, sample = ("SUCCEEDED", {}) if entry is None else (entry,{}) if isinstance(entry,str) else entry.result()
                metrics[identity] = sample
                evidence = None
                if status == "SUCCEEDED":
                    folder = root / identity
                    resources = read(folder / "resources.json")
                    need(resources["guard"]["memory_kernel_cap"] and resources["guard"]["cpu_kernel_cap"], "WORKER_GUARD")
                    metrics[identity] = {**sample, "worker":resources}
                    evidence = readback(a, task, folder)
                if args.crash == "before-commit":
                    os._exit(72)
                body = dict(schema="aql.bridge.outcome.v1", experiment_id="OUTCOME-" + identity,
                            task_sha256=task["sha256"], status=status, evidence=evidence)
                outcomes[identity], _ = store(path, body)
                if args.crash == "before-ack":
                    os._exit(73)
        validate(a, plan, args.stage, args.source)
        result = dict(schema="aql.actual-research-batch-bridge.result.v1", plan_sha256=plan["sha256"],
                      source_class=plan["source_class"], science=plan["science"], holdout=plan["holdout"],
                      actual_fills=None, trading_authority="NONE", orders_created=0,
                      outcomes=[outcomes[t["id"]] for t in selected])
        a.persist(root / "result.json", {**result, "sha256":a.sha(result)})
        a.checkpoint(root / "metrics.json", dict(workers=args.workers, wall_s=time.monotonic()-started,
                     local_bytes=disk_bytes(root), tasks=metrics,
                     claims=sum(key.startswith("CLAIM-") for key in catalog(path))))
        if args.crash == "after-ack":
            os._exit(75)
    finally:
        lock.unlink()


def main():
    p = argparse.ArgumentParser()
    for name in ("stage","deps","source","output"):
        p.add_argument("--"+name,type=lambda value:Path(value).resolve(),required=True)
    p.add_argument("--plan",type=Path)
    p.add_argument("--freeze",action="store_true")
    p.add_argument("--fixture",action="store_true")
    p.add_argument("--standalone",choices=["sma3-8","sma3-12"])
    p.add_argument("--worker")
    p.add_argument("--parent",type=int)
    p.add_argument("--workers",type=int,default=1)
    p.add_argument("--count",type=int,choices=[1,2],default=2)
    p.add_argument("--deadline-s",type=float,default=BUDGET["batch_wall_s"])
    p.add_argument("--crash",choices=["before-commit","before-ack","after-ack"])
    args=p.parse_args()
    a, baseline = activate(args.stage,args.deps)
    if args.freeze:
        a.persist(args.output,plans(a,baseline,args.stage,args.source,args.fixture))
        return
    plan=read(args.plan)
    validate(a,plan,args.stage,args.source)
    if args.worker:
        worker(args,a,plan)
    elif args.standalone:
        task=next(t for t in plan["tasks"] if t["id"]==args.standalone)
        a.run(args.source,args.deps,args.output,task["plan"])
        a.persist(args.output/"bridge-readback.json",readback(a,task,args.output))
    else:
        batch(args,a,plan)


if __name__ == "__main__":
    main()
