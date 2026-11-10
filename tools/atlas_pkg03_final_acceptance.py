"""One pinned disposable four-delivery acceptance candidate; no owner edits.

A successfully executed protocol can report BLOCKED. It cannot repair another
package, fabricate a research join, or turn CI success into release acceptance.
Git fetch is optional source retrieval, never market-data acquisition.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from atlas_pkg03_stage import digest, git

PINS = {
    "pkg01": "612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d",
    "pkg02": "ea4ffd5ce278d93588338122ab6ac1af8ec4da26",
    "pkg03": "3b31fcc697deeab5b9489f20e026ebede1f4cf85",
    "pkg04": "a79b26f300f0e4a35c37d231a9d8f3fc0d97d031",
}
BASES = {
    "pkg01": "99c27ea2c1a4d41aaae361141301a8a9ea3b33c3",
    "pkg02": "04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf",
    "pkg03": "182331b90efdcc31cf04476200fe09b45e16997c",
    "pkg04": "90af9794880cbeb00e7e974bfa906ff5e9666183",
}


def save(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")


def extract(repo, sha, dest):
    records = {}
    with tarfile.open(fileobj=io.BytesIO(git(repo, "archive", "--format=tar", sha))) as archive:
        for member in archive:
            relative = Path(member.name)
            if member.name.endswith((".py", ".json")):
                if (not member.isfile() or relative.is_absolute() or
                        ".." in relative.parts or ".git" in relative.parts):
                    raise ValueError("UNSAFE_PINNED_SOURCE")
                raw = archive.extractfile(member).read()
                target = dest / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                records[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    return records


def run(root, name, argv, cwd, *, extra_path=()):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in (cwd / "src", cwd, *extra_path))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-B", *argv], cwd=cwd,
                            env=env, capture_output=True, text=True)
    (root / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    return result


def execute(repo, output, *, fetch=False):
    repo, root = Path(repo).resolve(), Path(output).resolve()
    if root.exists():
        raise ValueError("FINAL_CANDIDATE_MUST_BE_NEW")
    root.mkdir(parents=True)
    manifest = {}
    for lane, sha in PINS.items():
        if fetch:
            subprocess.run(["git", "-C", str(repo), "fetch", "--no-tags", "origin", sha], check=True)
        if git(repo, "rev-parse", sha + "^{commit}").decode().strip() != sha:
            raise ValueError("DELIVERED_PIN_DRIFT")
        paths = git(repo, "diff", "--name-only", BASES[lane], sha).decode().splitlines()
        manifest[lane] = dict(head=sha, base=BASES[lane], changed_paths=paths,
                              source_files=extract(repo, sha, root / lane))
    # Explicit ownership check: all four delivered deltas must be disjoint.
    owners = {}
    for lane, item in manifest.items():
        for path in item["changed_paths"]:
            if path in owners:
                raise ValueError("CROSS_LANE_CHANGED_PATH_COLLISION")
            owners[path] = lane
    source_manifest = dict(schema="aql.integration.four-package-source-candidate.v1",
                           lanes=manifest, composite_sha256=digest(manifest),
                           merges_performed=False, original_producers_modified=False)
    save(root / "candidate-manifest.json", source_manifest)
    commands = []
    tasks = (
        ("core", "pkg01", ["-m", "tools.core_prospective_readiness_smoke", "--output", str(root / "core.json")]),
        ("factory", "pkg02", ["-m", "tools.atlas_factory_pkg02_execution_smoke", "--output-dir", str(root / "factory")]),
        ("operational", "pkg03", ["tools/atlas_pkg03_smoke.py", "--repo", str(repo), "--output", str(root / "operational")]),
    )
    for name, lane, args in tasks:
        result = run(root, name, args, root / lane)
        commands.append(dict(name=name, lane=lane, command=["python", "-B", *[
            x.replace(str(root), "$CANDIDATE").replace(str(repo), "$REPO") for x in args]],
                             returncode=result.returncode))
        if result.returncode:
            raise RuntimeError("FINAL_PRODUCER_FAILED:" + name)
    core = json.loads((root / "core.json").read_text())
    factory = json.loads((root / "factory/report.json").read_text())
    negative = json.loads((root / "factory/negative-rejections.json").read_text())
    operational = json.loads((root / "operational/delivery.json").read_text())
    assert core["real_cohort_status"] == "BLOCKED_OWNER_AUTHORIZATION"
    assert factory["trading_authority"] == "NONE" and factory["actual_fills"] is None
    assert factory["orders_created"] == 0 and factory["winner"] is None
    assert factory["holdout"] == "SEALED_UNOPENED"
    assert sum(factory["denominators"]["attempt_state_counts"].values()) == factory["denominators"]["total_attempted"]
    assert len(factory["outcomes"]) == factory["denominators"]["total_variant_rows"]
    assert operational["result"]["duplicate_fills"] == operational["result"]["skipped_commands"] == 0
    assert [p["returncode"] for p in operational["processes"]] == [0, 73, 0]
    # Export actual recovered native G3 state; never reconstruct fills or alter
    # current native G2 horizon statuses to fit the consumer's older fixture.
    overlay = root / "operational/overlay"
    export = run(root, "native-state-export", ["-c",
        "import json,pathlib,sys;from aql.paper_sim.engine import PaperSimulator;"
        "p=pathlib.Path(sys.argv[1]);before=p.read_bytes();"
        "s=PaperSimulator(p);assert p.read_bytes()==before;"
        "pathlib.Path(sys.argv[2]).write_text(json.dumps(list(s.states.values()),sort_keys=True))",
        str(root / "operational/run/simulation.jsonl"), str(root / "native-results.json")],
        overlay)
    assert export.returncode == 0
    inputs = root / "gateway-inputs"
    inputs.mkdir()
    source = json.loads((root / "operational/run/g2-read.json").read_text())
    results = json.loads((root / "native-results.json").read_text())
    assert len(results) == 1 and len(results[0]["fills"]) == 2
    for name, doc in (("source.json", source), ("results.json", results),
                      ("factory.json", factory), ("prospective.json", core)):
        save(inputs / name, doc)
    # Same canonical policy as PKG04, pinned independently in the parent.
    gateway_sha = lambda obj: hashlib.sha256(json.dumps(obj, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    gateway_manifest = dict(schema="aql.research-evidence-gateway.inputs.v1",
        files={f.name: gateway_sha(json.loads(f.read_text())) for f in sorted(inputs.glob("*.json"))},
        run=source["run"], as_of_ms=source["as_of_ms"], expected_decisions=len(source["rows"]),
        expected_signal_ids=sorted(r["decision"]["opportunity_id"] for r in source["rows"]
                                   if r["decision"]["state"] == "ENTRY_SIGNAL"),
        expected_result_signal_ids=sorted(r["signal"]["signal_id"] for r in results),
        engine_sha256=results[0]["engine_sha256"], pinned_heads=PINS)
    save(inputs / "manifest.json", gateway_manifest)
    anchor = gateway_sha(gateway_manifest)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    consumer_runs = []
    for index in (1, 2):
        result = run(root, "gateway-attempt-" + str(index), ["-m", "tools.research_evidence_gateway.gateway",
            "--inputs", str(inputs), "--manifest-sha256", anchor,
            "--output", str(root / ("gateway-result-" + str(index) + ".json"))], root / "pkg04")
        consumer_runs.append(dict(returncode=result.returncode, response=json.loads(result.stdout)))
        assert not (root / ("gateway-result-" + str(index) + ".json")).exists()
    assert consumer_runs[0] == consumer_runs[1]
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    assert consumer_runs[0] == dict(returncode=2, response={"status": "REJECTED", "code": "UNSUPPORTED_MATURE_EVIDENCE_CONTRACT"})
    # Verify immutable extracted source bytes after producer and consumer runs.
    for lane, item in manifest.items():
        for name, expected in item["source_files"].items():
            assert hashlib.sha256((root / lane / name).read_bytes()).hexdigest() == expected
    body = dict(schema="aql.integration.four-package-final-acceptance.v1",
        status="BLOCKED_EXACT_PKG04_EVIDENCE_CONSUMER_SEAM",
        release_acceptance="NOT_GRANTED", pins=PINS, bases=BASES,
        composite_sha256=source_manifest["composite_sha256"], commands=commands,
        core_report_sha256=core["report_sha256"], factory_report_sha256=factory["sha256"],
        factory_rows=len(factory["outcomes"]), factory_negative_rejections=negative["rejected_count"],
        factory_modeled_fills_promoted_to_real=False,
        operational_delivery_sha256=operational["sha256"],
        operational_overlay_sha256=operational["combined_overlay_sha256"],
        gateway_manifest_sha256=anchor, gateway_runs=consumer_runs,
        gateway_input_bytes_unchanged=True, pinned_source_bytes_unchanged=True,
        discoverer_factory_join="NOT_AVAILABLE_IN_PKG04_NATIVE_CONSUMER",
        scope=dict(original_data_run=False, observer_reset=False, external_market_data=False,
                   paid_resources=False, merge=False, trading_authority="NONE", G0="NOT_APPROVED"),
        one_owner_handoff=dict(owner="PKG04 consumer owner via Integration #271",
            reproducible_failure="UNSUPPORTED_MATURE_EVIDENCE_CONTRACT on current native PKG03 export",
            minimum_fix="Extend only PKG04 native evidence consumer for mature/missing horizon parents and persisted research lineage; keep UNKNOWN and modeled-only boundaries. Research proposal/attempt/trial parent bundle must be supplied by Discoverer/Factory; never invent the join.",
            affected_regression_only="Rerun this persisted producer-to-consumer seam and PKG04 focused negatives; no accepted G4 or original rerun"))
    report = {**body, "sha256": digest(body)}
    save(root / "final-acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    report = execute(args.repo, args.output, fetch=args.fetch)
    print(json.dumps({k: report[k] for k in ("status", "sha256", "composite_sha256")}, sort_keys=True))
