"""CI-only extraction of two immutable upstream modules into a disposable dir.

No checkout/cherry-pick/merge or changes to upstream-owned implementation files.
Tests hash-check both modules before importing. Fetching is separate from tests.
"""
from pathlib import Path
import subprocess
import sys

SHA="d072544427d6b08473c88b2e36d5857cfd8581dc"


if __name__=="__main__":
    dest=Path(sys.argv[1]);dest.mkdir(parents=True,exist_ok=True)
    subprocess.run(["git","fetch","--no-tags","origin",SHA],check=True)
    for name in ("prospective.py","durable_bridge_v1.py"):
        data=subprocess.check_output(["git","show",f"{SHA}:src/aql/observation/{name}"])
        (dest/name).write_bytes(data)
