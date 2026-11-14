"""Bind the offline evidence to the exact Git checkout."""
import argparse
from pathlib import Path
import subprocess
from tools.binance_live_feed.feed import canonical, hash_bytes
from tools.binance_live_feed.interface import HISTORICAL_HEAD


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    root = parser.parse_args().root
    files = {p.relative_to(root).as_posix(): hash_bytes(p.read_bytes())
             for p in root.rglob("*") if p.is_file() and p.name != "manifest.json"}
    def git(ref):
        return subprocess.check_output(["git","rev-parse",ref],text=True).strip()
    with (root/"manifest.json").open("xb") as out:
        out.write(canonical(dict(head=git("HEAD"),tree=git("HEAD^{tree}"),historical_head=HISTORICAL_HEAD,files=files)))
