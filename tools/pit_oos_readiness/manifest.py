"""Bind rehearsal evidence to the exact checkout and file bytes."""
import argparse
from hashlib import sha256
from pathlib import Path

from tools.pit_oos_readiness.dependencies import CORE, FACTORY, git
from tools.pit_oos_readiness.readiness import canonical, immutable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    root = parser.parse_args().root
    files = {path.name: sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.iterdir()) if path.is_file() and path.name != "manifest.json"}
    immutable(root / "manifest.json", canonical(dict(
        schema="aql.pit-oos.evidence-manifest.v1",
        source_head=git("rev-parse", "HEAD").decode().strip(),
        source_tree=git("rev-parse", "HEAD^{tree}").decode().strip(),
        core=CORE, factory=FACTORY, files=files)))


if __name__ == "__main__":
    main()
