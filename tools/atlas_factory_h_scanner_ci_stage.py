"""CI-only ephemeral Scanner #277 overlay. Never modify tracked Factory files.

Reads one exact Git SHA, copies only currently absent Python/fixture files into
the disposable GitHub runner checkout. This is NOT a git merge and touches no
owner-local E: data, authenticated credentials, raw Warehouse or live source.
"""
from __future__ import annotations
import io
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

SCANNER_SHA="3c82448702c9ae35783716e4e2c3b640010db97c"
CORE_SHA="59510d302e7bb97a63e3d9603b9fb9f81f8f378a"
WORK235_SHA="6acbcc7fc243b132f58170df4c6469bbf7f4eff8"
WORK235_BLOB="c27eb5aa70a6d671791ba1e55e9b078a272b611f"
ALLOWED_ROOTS={"tools","research_wp_r0","src","tests"}
ALLOWED_FIXTURE="tools/strategy_service_offline/fixtures/strategies.json"


def main():
    subprocess.run(["git","fetch","--no-tags","--depth=1","origin",SCANNER_SHA],
                   check=True)
    subprocess.run(["git","cat-file","-e",SCANNER_SHA+"^{commit}"],check=True)
    data=subprocess.check_output(["git","archive","--format=tar",SCANNER_SHA])
    written=[]
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:") as archive:
        for item in archive:
            path=PurePosixPath(item.name)
            if (not item.isfile() or not path.parts
                or path.parts[0] not in ALLOWED_ROOTS
                or any(p in (".","..") for p in path.parts)
                or not (str(path).endswith(".py") or
                        str(path)==ALLOWED_FIXTURE)):
                continue
            target=Path(str(path))
            if target.exists():
                continue
            content=archive.extractfile(item)
            if content is None:
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(content.read())
            written.append(str(path))
    # Scanner H consumes the existing Core #253 immutable query verifier.
    # These Core modules live in a separate unmerged Draft branch; stage ONLY
    # missing modules, preserving Factory and Scanner exact file identities.
    subprocess.run(["git","fetch","--no-tags","--depth=1","origin",CORE_SHA],
                   check=True)
    core_data=subprocess.check_output(
        ["git","archive","--format=tar",CORE_SHA])
    core_written=0
    with tarfile.open(fileobj=io.BytesIO(core_data),mode="r:") as archive:
        for item in archive:
            path=PurePosixPath(item.name)
            if (not item.isfile() or not path.parts or
                path.parts[0] not in ALLOWED_ROOTS or
                any(p in (".","..") for p in path.parts) or
                not str(path).endswith(".py")):
                continue
            target=Path(str(path))
            if target.exists():
                continue
            handle=archive.extractfile(item)
            if handle is None:
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(handle.read())
            core_written+=1
    print("STAGED_CORE_EXACT_SHA:",CORE_SHA,flush=True)
    print("STAGED_MISSING_CORE_DEPENDENCIES:",core_written,flush=True)
    work=Path(ALLOWED_FIXTURE)
    if not work.is_file():
        subprocess.run(["git","fetch","--no-tags","--depth=1",
                        "origin",WORK235_SHA],check=True)
        # The historical frozen strategy service is a distinct Work235
        # commit; neither Scanner nor Core draft branches vendor its code.
        frozen_tar=subprocess.check_output(
            ["git","archive","--format=tar",WORK235_SHA])
        frozen_count=0
        with tarfile.open(fileobj=io.BytesIO(frozen_tar),mode="r:") as archive:
            for item in archive:
                path=PurePosixPath(item.name)
                if (not item.isfile() or not path.parts or
                    path.parts[0] not in ALLOWED_ROOTS or
                    any(p in (".","..") for p in path.parts) or
                    not str(path).endswith(".py")):
                    continue
                target=Path(str(path))
                if target.exists():
                    continue
                handle=archive.extractfile(item)
                if handle is None:
                    continue
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(handle.read())
                frozen_count+=1
        print("STAGED_FROZEN_WORK235_PYTHON:",frozen_count,flush=True)
        found=subprocess.check_output([
            "git","rev-parse",WORK235_SHA+":"+ALLOWED_FIXTURE],
            text=True).strip()
        if found!=WORK235_BLOB:
            raise RuntimeError("Frozen Work235 original blob mismatch")
        work.parent.mkdir(parents=True,exist_ok=True)
        work.write_bytes(subprocess.check_output([
            "git","show",WORK235_SHA+":"+ALLOWED_FIXTURE]))
    required={
        "tools/scanner_strategy_f/research_strategy_plugin.py",
        "tools/scanner_strategy_f/test_research_strategy_plugin.py",
        "tools/scanner_strategy_f/research_e2e_diagnostic.py",
        "tools/strategy_service_offline/fixtures/strategies.json",
    }
    print("STAGED_MISSING_RESEARCH_DEPENDENCIES:",len(written),flush=True)
    print("PINNED_REQUIRED_EXISTS:",{x:Path(x).is_file() for x in sorted(required)},flush=True)
    if not all(Path(x).is_file() for x in required):
        raise RuntimeError("Scanner pinned staged contract incomplete")
    print("STAGED_SCANNER_EXACT_SHA:",SCANNER_SHA)
    print("STAGED_MISSING_RESEARCH_DEPENDENCIES:",len(written))
    print("WORK235_EXACT_ORIGINAL_BLOB:",WORK235_BLOB,flush=True)


if __name__=="__main__":
    main()
