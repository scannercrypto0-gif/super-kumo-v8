"""Stage immutable role heads in disposable GitHub Actions checkout, no merges.

Git archive overlays ONLY research code and the two existing Factory tests.
Run this script only in ephemeral synthetic CI; never in owner's staged worktree.
"""
import io
from pathlib import Path
import subprocess
import tarfile

PINS={
 "work235":"6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
 "scanner":"3c82448702c9ae35783716e4e2c3b640010db97c",
 "factory":"04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf",
 "core":"99c27ea2c1a4d41aaae361141301a8a9ea3b33c3",
}
ALLOWED={
 "work235":("research_wp_r0/","tools/strategy_service_offline/"),
 "scanner":("research_wp_r0/","tools/scanner_strategy_f/"),
 "factory":("research_wp_r0/","tests/test_aql_factory_h_generic_signal_adapter_v1.py",
            "tests/test_aql_factory_lab_generic_wiring_v1.py"),
 "core":("research_wp_r0/aql_core_h_research_secretary_v1.py",),
}

def main():
    root=Path.cwd()
    for role,sha in PINS.items():
        subprocess.run(["git","fetch","--no-tags","--depth=1","origin",sha],
                       check=True,stdout=subprocess.DEVNULL)
        actual=subprocess.run(["git","rev-parse",sha+"^{commit}"],
                              capture_output=True,text=True,check=True).stdout.strip()
        if actual!=sha:
            raise RuntimeError("ROLE_PIN_MISMATCH:"+role)
        archive=subprocess.run(["git","archive","--format=tar",sha],
                               capture_output=True,check=True).stdout
        copied=0
        with tarfile.open(fileobj=io.BytesIO(archive),mode="r:") as tf:
            for member in tf:
                name=member.name.replace("\\","/")
                if not any(name.startswith(p) for p in ALLOWED[role]):
                    continue
                if not name.endswith((".py",".json")):
                    continue
                parts=Path(name).parts
                if (member.issym() or member.islnk() or not member.isfile()
                    or name.startswith("/") or ".." in parts):
                    raise RuntimeError("UNSAFE_ROLE_ARCHIVE:"+role)
                dest=root.joinpath(*parts)
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(tf.extractfile(member).read())
                copied+=1
        if not copied:
            raise RuntimeError("ROLE_EMPTY:"+role)
        print("F_LAB_3_ROLE_PIN",role,sha,"files",copied)
    for path in (
       "research_wp_r0/aql_factory_lab_experiment_index_v1.py",
       "research_wp_r0/aql_factory_lab_generic_paired_v1.py",
       "research_wp_r0/aql_core_h_research_secretary_v1.py",
       "tools/scanner_strategy_f/research_strategy_plugin.py",
       "tests/test_aql_factory_h_generic_signal_adapter_v1.py",
       "tests/test_aql_factory_lab_generic_wiring_v1.py"):
        if not (root/path).is_file():
            raise RuntimeError("MISSING_PINNED_API:"+path)
    print("F_LAB_3_STAGING_OK")

if __name__=="__main__":
    main()
