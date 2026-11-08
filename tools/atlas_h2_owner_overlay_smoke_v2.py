"""CI smoke of EXACT owner PowerShell source overlay, without original source or key.

Stage the Python text between $prepare=@' ... '@ from the actual owner bundle,
then import the same research modules under python -I in a fresh isolated child.
No touching E:, no private files, no persistent Git checkout, no H2 execution.
"""
from __future__ import annotations
import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

PINS = (
    "43a3bf3196649c46aed54872f958c323e4ae4913",
    "99c27ea2c1a4d41aaae361141301a8a9ea3b33c3",
    "af3720b6be921444cb83d52f3e975a9c85475ec6",
    "04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf",
    "6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
)
IMPORTS = (
    "tools.atlas_h2_owner_evidence_recovery_v2",
    "tools.atlas_h2_owner_personal_batch_v1",
    "research_wp_r0.aql_archive_custody_bridge_v1",
    "research_wp_r0.aql_native_price_custody_query_v1",
    "research_wp_r0.aql_core_backbone_local_v1",
    "research_wp_r0.aql_core_research_query_seam_v1",
    "research_wp_r0.aql_factory_h_generic_signal_adapter_v1",
    "tools.strategy_service_offline.run",
    "tools.scanner_strategy_f.frozen_diagnostic_contracts",
)


def run(repo, code_commit):
    repo = pathlib.Path(repo).resolve()
    bundle = (repo/"tools"/"atlas_h2_owner_recovery_bundle_v2.ps1").read_text("utf-8")
    match = re.search(r"\$prepare=@'\r?\n(.*?)\r?\n'@", bundle, re.DOTALL)
    if not match:
        raise RuntimeError("BUNDLE_INLINE_STAGE_CODE_MISSING")
    with tempfile.TemporaryDirectory(prefix="aql-r2-overlay-probe-") as dirname:
        folder=pathlib.Path(dirname)
        local=folder/"repo"
        local.mkdir()
        subprocess.run(["git","-C",str(local),"init","-q"],check=True)
        subprocess.run([
            "git","-C",str(local),"remote","add","origin",
            "https://github.com/scannercrypto0-gif/super-kumo-v8.git"
        ],check=True)
        for pin in (code_commit,*PINS):
            subprocess.run(["git","-C",str(local),"fetch","--quiet",
                            "--no-tags","origin",pin],check=True)
        stage=folder/"overlay"
        stage.mkdir()
        subprocess.run([
            sys.executable,"-I","-c",match.group(1),
            str(local),str(stage),code_commit
        ],check=True)
        child = """
import importlib, sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
for name in sys.argv[2:]:
    try:
        module=importlib.import_module(name)
    except ModuleNotFoundError as exc:
        print("MISSING_PINNED_MODULE:"+str(exc.name),flush=True)
        raise
    path=Path(module.__file__).resolve()
    if not path.is_relative_to(Path(sys.argv[1]).resolve()):
        raise AssertionError("IMPORT_ESCAPED_PINNED_OVERLAY:"+name+":"+str(path))
    print("STAGED_PINNED_MODULE_OK:"+name,flush=True)
# Scanner StrategyDefinition and actual frozen 2 Work235 fixtures are an
# owner-independent, no-market-data, deterministic manual AST preflight.
recovery=importlib.import_module("tools.atlas_h2_owner_evidence_recovery_v2")
definition, config_sha, evaluator_sha = recovery._manual_ast()
assert definition["definition"]["strategy_id"] == "h_manual_distinct_test"
assert len(config_sha) == len(evaluator_sha) == 64
print("STAGED_MANUAL_AST_REAL_PINNED_FIXTURE_OK",flush=True)
"""
        subprocess.run([sys.executable,"-I","-c",child,str(stage),*IMPORTS],
                       check=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",default=".")
    ap.add_argument("--code-commit",required=True)
    args=ap.parse_args()
    run(args.repo,args.code_commit)


if __name__=="__main__":
    main()
