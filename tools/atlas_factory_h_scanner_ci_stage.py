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


if __name__=="__main__":
    main()
