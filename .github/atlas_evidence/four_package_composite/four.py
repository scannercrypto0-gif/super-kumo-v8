"""Disposable four-package acceptance. No writes to source checkouts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from atlas_pkg03_final_acceptance import extract, run, save
from atlas_pkg03_stage import git, digest

MAIN = "90af9794880cbeb00e7e974bfa906ff5e9666183"
PINS = {
    "core": ("99c27ea2c1a4d41aaae361141301a8a9ea3b33c3", "612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d"),
    "factory": ("04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf", "ea4ffd5ce278d93588338122ab6ac1af8ec4da26"),
    "operational": ("182331b90efdcc31cf04476200fe09b45e16997c", "c01f526e762a014e5ed84ca3cf695b9d77502ab3"),
    "gateway": (MAIN, "ccd906ac6d770e1364889623cd79bb215f7b5c63"),
}


def manifest(repo):
    lanes, owners, index_rows = {}, set(), []
    for lane, (base, head) in PINS.items():
        paths = git(repo, "diff", "--name-only", "-z", base, head).decode().strip("\0").split("\0")
        assert paths and owners.isdisjoint(paths)
        owners.update(paths)
        blobs = {}
        for path in paths:
            entry = git(repo, "ls-tree", "-z", head, "--", path)
            assert entry and entry.count(b"\0") == 1, ("deleted or ambiguous path", path)
            mode, kind, sha = entry.split(b"\t")[0].decode().split()
            assert kind == "blob"
            blobs[path] = sha
            index_rows.append(f"{mode} {sha}\t{path}\0".encode())
        lanes[lane] = {"base": base, "head": head, "changed_blobs": blobs}
    with tempfile.TemporaryDirectory() as scratch:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        cmd = ["git", "-C", str(repo)]
        subprocess.run(cmd + ["read-tree", MAIN], env=env, check=True)
        subprocess.run(cmd + ["update-index", "-z", "--index-info"], input=b"".join(index_rows),
                       env=env, check=True)
        tree = subprocess.check_output(cmd + ["write-tree"], env=env, text=True).strip()
    doc = {"main": MAIN, "delta_tree": tree, "lanes": lanes}
    return {**doc, "sha256": digest(doc)}


def execute(repo, root):
    root.mkdir()
    pins = manifest(repo)
    save(root / "candidate-manifest.json", pins)
    sources = {lane: extract(repo, head, root / lane) for lane, (_, head) in PINS.items()}
    for lane, argv in (
        ("core", ["-m", "tools.core_prospective_readiness_smoke", "--output", str(root / "core.json")]),
        ("factory", ["-m", "tools.atlas_factory_pkg02_execution_smoke", "--output-dir", str(root / "factory-output")]),
    ):
        proc = run(root, lane, argv, root / lane)
        if proc.returncode:
            raise RuntimeError(f"COMPOSITE_{lane}_FAILED: {proc.stderr}")
    load = lambda file: json.loads(Path(file).read_text(encoding="utf-8"))
    core = load(root / "core.json")
    factory = load(root / "factory-output/report.json")
    assert core["status"] == "PASS_SYNTHETIC_SAFETY_AND_RESTART_REPLAY"
    assert core["real_cohort_status"] == "BLOCKED_OWNER_AUTHORIZATION"
    assert factory["trading_authority"] == "NONE" and factory["actual_fills"] is None
    assert factory["orders_created"] == 0 and factory["winner"] is None
    assert factory["holdout"] == "SEALED_UNOPENED"
    assert len(factory["outcomes"]) == factory["denominators"]["total_variant_rows"]
    assert sum(factory["denominators"]["attempt_state_counts"].values()) == factory["denominators"]["total_attempted"]
    # The current gateway acceptance already verifies actual pinned #293,
    # persisted G4 lineage, two fresh gateway processes and eight negatives.
    # Change only its disposable driver copy to feed the fresh #290/#291
    # receipts, not its gateway or native producer code.
    original = root / "gateway/tools/research_evidence_gateway/acceptance.py"
    driver = original.read_text(encoding="utf-8")
    old = """    (inputs/'factory.json').write_bytes(raw)
    files={n:sha(json.loads((inputs/n).read_text())) for n in ('source.json','results.json','factory.json')}"""
    new = """    fresh_factory=(root.parent/'factory-output/report.json').read_bytes()
    assert sha(json.loads(fresh_factory))==sha(json.loads(raw)), 'FRESH_FACTORY_PARITY'
    (inputs/'factory.json').write_bytes(fresh_factory)
    shutil.copyfile(root.parent/'core.json',inputs/'prospective.json')
    files={n:sha(json.loads((inputs/n).read_text())) for n in ('source.json','results.json','factory.json','prospective.json')}"""
    assert driver.count(old) == 1
    driver = driver.replace(old, new)
    old = "pinned_heads=dict(integration=INTEGRATION,pkg02=FACTORY02,g4_existing=COMMIT,**delivery['pins'])"
    new = ("pinned_heads=dict(integration=INTEGRATION,pkg02=FACTORY02,g4_existing=COMMIT,"
           f"pkg01='{PINS['core'][1]}',pkg04='{PINS['gateway'][1]}',**delivery['pins'])")
    assert driver.count(old) == 1
    old_fixture = "fixture=Path(__file__).parent/'fixtures/native-current'"
    assert driver.count(old_fixture) == 1
    driver = driver.replace(old_fixture,
        "fixture=Path.cwd()/'tools/research_evidence_gateway/fixtures/native-current'")
    old_cwd = "str(root/('read-model-'+str(number)+'.json'))],repo)"
    assert driver.count(old_cwd) == 1
    driver = driver.replace(old_cwd, old_cwd.replace("],repo)", "],Path.cwd())"))
    path = root / "corrected-driver.py"
    path.write_text(driver.replace(old, new), encoding="utf-8")
    result = run(root, "gateway-and-native", [str(path), "--repo", str(repo), "--output",
                                             str(root / "joined")], root / "gateway")
    if result.returncode:
        raise RuntimeError("COMPOSITE_GATEWAY_FAILED: " + result.stderr)
    acceptance = load(root / "joined/acceptance-receipt.json")
    assert acceptance["mature_g2_consumer_seam"] == "MATURE_G2_CONSUMER_SEAM_PASS"
    assert acceptance["research_join"] == "RESEARCH_JOIN_PASS"
    assert acceptance["actual_fills"] is None and acceptance["trading_authority"] == "NONE"
    assert acceptance["input_bytes_unchanged"] and acceptance["durable_producer_bytes_unchanged"]
    assert len(acceptance["negative_rejections"]) == 8
    for lane, files in sources.items():
        for filename, expected in files.items():
            assert hashlib.sha256((root / lane / filename).read_bytes()).hexdigest() == expected
    report = {"status": "INTEGRATED_RESEARCH_ENGINEERING_READY",
              "candidate": pins["sha256"], "delta_tree": pins["delta_tree"],
              "core_report": core["report_sha256"], "factory_report": factory["sha256"],
              "factory_negatives": load(root / "factory-output/negative-rejections.json"),
              "acceptance": acceptance, "pinned_source_bytes_unchanged": True,
              "real_pit_oos": "BLOCKED", "real_g2_24_72": "UNVERIFIED"}
    save(root / "final.json", {**report, "sha256": digest(report)})
    print(digest(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    execute(options.repo.resolve(), options.output.resolve())
