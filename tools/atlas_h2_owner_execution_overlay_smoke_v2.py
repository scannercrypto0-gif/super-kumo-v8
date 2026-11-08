"""Exercise actual Windows execution/readiness PowerShell embedded staging; no E: or H2."""
from __future__ import annotations
import pathlib
import re
import subprocess
import sys
import tempfile

ROLE_PINS=(
 "43a3bf3196649c46aed54872f958c323e4ae4913",
 "99c27ea2c1a4d41aaae361141301a8a9ea3b33c3",
 "af3720b6be921444cb83d52f3e975a9c85475ec6",
 "04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf",
 "6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
)
PERSONAL="82c39963bea8f0a19b67efcfb4c0744dfb8f2d8e"
READINESS="885904a5e1df06bee1e32152a43f0fda4d0a4188"
IMPORT_TEST=r"""
import importlib,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
for mod in (
    'tools.atlas_h2_owner_local_one_shot_v1',
    'tools.atlas_h2_owner_personal_batch_v1',
    'tools.scanner_strategy_f.research_strategy_plugin',
    'research_wp_r0.aql_core_backbone_local_v1',
    'research_wp_r0.aql_factory_h_generic_signal_adapter_v1',
    'research_wp_r0.aql_factory_lab_experiment_index_v1',
    'research_wp_r0.aql_core_h_research_secretary_v1',
    'tools.atlas_h_generic_secretary_bridge',
):
    loaded=importlib.import_module(mod)
    if not Path(loaded.__file__).resolve().is_relative_to(root):
        raise AssertionError('UNCHECKED_EXTERNAL_IMPORT:'+mod)
print('EXECUTION_OVERLAY_IMPORTS_PASS_NO_SOURCE',flush=True)
"""


def check(repo):
    repo=pathlib.Path(repo)
    with tempfile.TemporaryDirectory(prefix="aql-h2-execution-code-only-") as root:
        base=pathlib.Path(root)
        clone=base/"repo"
        clone.mkdir()
        subprocess.run(["git","-C",str(clone),"init","-q"],check=True)
        subprocess.run(["git","-C",str(clone),"remote","add","origin",
                        "https://github.com/scannercrypto0-gif/super-kumo-v8.git"],
                       check=True)
        for sha in (*ROLE_PINS,PERSONAL,READINESS):
            subprocess.run(["git","-C",str(clone),"fetch","-q","--no-tags",
                            "origin",sha],check=True)
        for filename,tag,args in (
            ("tools/atlas_h2_windows_batch.ps1","stagePersonal",
             (str(clone),None,PERSONAL)),
            ("tools/atlas_h2_owner_readiness_bundle_v2.ps1","stageScript",
             (str(clone),None,PERSONAL,READINESS)),
        ):
            source=(repo/filename).read_text("utf-8")
            match=re.search(
                r"\$"+tag+r"\s*=\s*@'\r?\n(.*?)\r?\n'@",
                source,re.DOTALL)
            if not match:
                raise AssertionError("EXACT_WINDOWS_STAGER_NOT_FOUND:"+tag)
            stage=base/(tag+"-isolated")
            stage.mkdir()
            # The Windows execution script's bootstrap has already staged
            # operator & policies, as verified by its pinned bootstrap tests.
            arguments=list(args)
            arguments[1]=str(stage)
            subprocess.run(
                [sys.executable,"-I","-c",match.group(1),*arguments],
                check=True)
            subprocess.run(
                [sys.executable,"-I","-c",IMPORT_TEST,str(stage)],
                check=True)
            if tag=="stageScript":
                subprocess.run([sys.executable,"-I","-c",
                    "import sys;sys.path.insert(0,sys.argv[1]);"
                    "from tools.atlas_h2_owner_readiness_v2 import "
                    "verify_signed_parent,validate_owner_readiness;"
                    "print('READINESS_MODULE_IMPORTS_PASS_NO_ORIGINAL')",
                    str(stage)],check=True)


if __name__=="__main__":
    check(sys.argv[1] if len(sys.argv)>1 else ".")
