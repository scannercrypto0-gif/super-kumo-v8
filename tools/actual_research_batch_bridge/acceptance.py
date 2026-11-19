"""Delta-only integration acceptance using an explicitly simulated archive."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import sqlite3

from tools.actual_research_batch_bridge.bridge import read


def seal(value):
    payload = {k:v for k,v in value.items() if k != "sha256"}
    raw = json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    return {**payload, "sha256":hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", type=Path)
    parser.add_argument("deps", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir()
    source = root / "source"
    plan_path = root / "plan.json"
    base = [sys.executable, "-B", "-m", "tools.actual_research_batch_bridge.bridge",
            "--stage", str(args.stage.resolve()), "--deps", str(args.deps.resolve()),
            "--source", str(source)]
    evidence = {}

    def run(label, output, options=(), code=0, error=None, plan=plan_path):
        cmd = base + ["--output", str(output), "--plan", str(plan), *options]
        child = subprocess.run(cmd, capture_output=True, text=True, timeout=130)
        assert child.returncode == code, (label, child.returncode, child.stdout, child.stderr)
        if error:
            assert error in child.stderr, (label, child.stderr)
        evidence[label] = child.returncode

    run("freeze", plan_path, ["--freeze", "--fixture"])
    plan = read(plan_path)
    for candidate in ("sma3-8", "sma3-12"):
        run("standalone-" + candidate, root / ("standalone-" + candidate), ["--standalone", candidate])
    run("single", root / "single", ["--count", "1"])
    one = read(root / "single/result.json")
    assert one["outcomes"][0]["evidence"] == read(root / "standalone-sma3-8/bridge-readback.json")
    for workers in (1, 2):
        run(f"workers-{workers}", root / f"workers-{workers}", ["--workers", str(workers)])
    reference = (root / "workers-1/result.json").read_bytes()
    assert reference == (root / "workers-2/result.json").read_bytes()
    result = json.loads(reference)
    assert result["source_class"] == "SIMULATED_ADAPTER_TEST"
    for task, outcome in zip(plan["tasks"], result["outcomes"]):
        assert outcome["status"] == "SUCCEEDED"
        assert outcome["evidence"] == read(root / f"standalone-{task['id']}/bridge-readback.json")
    for stage, code in (("before-commit",72), ("before-ack",73), ("after-ack",75)):
        target = root / stage
        run(stage, target, ["--count","1","--crash",stage], code)
        run(stage + "-restart", target, ["--count","1"])
        assert read(target / "result.json") == one
        assert read(target / "metrics.json")["claims"] == 1
    stopped = root / "cancelled"
    stopped.mkdir()
    (stopped / "plan.json").write_bytes(plan_path.read_bytes())
    (stopped / "cancel").touch()
    run("cancel", stopped)
    assert {row["status"] for row in read(stopped / "result.json")["outcomes"]} == {"CANCELLED"}
    run("deadline", root / "deadline", ["--deadline-s", ".001"])
    assert {row["status"] for row in read(root / "deadline/result.json")["outcomes"]} == {"TIMEOUT"}
    run("source-output", source / "blocked", code=1, error="OUTPUT_SCOPE")
    assert not (source / "blocked").exists()
    for key, value in (("pit","ATTESTED"), ("actual_fills",1), ("ack","FAKE"), ("trading_authority","LIVE")):
        forged = {**plan,key:value}
        file = root / (key + ".json")
        file.write_text(json.dumps(seal(forged)))
        run("reject-"+key, root / "rejected", code=1, error="EVIDENCE_BOUNDARY", plan=file)
    file = next(source.glob("*.CHECKSUM"))
    original = file.read_bytes()
    try:
        file.write_bytes(original + b" ")
        run("swapped-checksum", root / "rejected", code=1, error="SOURCE_CUSTODY")
    finally:
        file.write_bytes(original)
    target = root / "single"
    report = target / "sma3-8/result.json"
    original = report.read_bytes()
    try:
        report.write_text("{}")
        run("forged-native-report", target, ["--count","1"], code=1)
    finally:
        report.write_bytes(original)
    native = target / "sma3-8/factory.sqlite"
    native_bytes = native.read_bytes()
    for label, error in (("duplicate-cost","DOUBLE_COST"), ("late-outcome","HOLDOUT_LOOKAHEAD")):
        try:
            con = sqlite3.connect(native)
            try:
                table = "factory_h_research_results_v1"
                document = json.loads(con.execute(f"select document from {table}").fetchone()[0])
                row = next(r for r in document["outcomes"] if r["status"] == "MODEL_ONLY")
                if label == "duplicate-cost":
                    row["total_cost_bps"] = "999"
                else:
                    row["legs"][0]["accounting_asof_ms"] = plan["tasks"][0]["plan"]["end_exclusive_ms"]
                document = seal(document)
                con.execute(f"update {table} set document=?,canonical_sha256=?",
                            (json.dumps(document),document["sha256"]))
                con.commit()
            finally:
                con.close()
            report.write_text(json.dumps(seal({**json.loads(original),"result_store_sha256":document["sha256"]})))
            run(label,target,["--count","1"],code=1,error=error)
        finally:
            native.write_bytes(native_bytes)
            report.write_bytes(original)
    checkpoint = target / "batch.sqlite"
    original = checkpoint.read_bytes()
    try:
        checkpoint.write_bytes(b"corrupt")
        run("corrupt-checkpoint", target, ["--count","1"], code=1, error="not a database")
    finally:
        checkpoint.write_bytes(original)
    run("restored-checkpoint", target, ["--count","1"])
    assert read(target / "result.json") == one
    assert {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in source.iterdir()} == plan["source_files"]
    receipt = dict(status="PASS_ADAPTER_ENGINEERING_ONLY", canonical_sha256=result["sha256"],
                   outcomes=result["outcomes"], cases=evidence)
    (root / "acceptance.json").write_text(json.dumps(receipt,sort_keys=True,indent=2))
    print(json.dumps({"status":receipt["status"],"canonical_sha256":receipt["canonical_sha256"],"cases":len(evidence)}))


if __name__ == "__main__":
    main()
