"""Stage exact Git blobs in disposable directories."""
import argparse
import io
from pathlib import Path
import subprocess
import sys
import tarfile

PINS = {
    "a": "eb49308d61ffdfc24ed5032df2cb541f37c48bfe",
    "b": "dd3e149afe73d9d04c9892ad35005b04fb675fff",
}


def stage(output, fetch):
    output.mkdir()
    for role, namespace in (("a", "first_research_cycle"), ("b", "research_capacity_scale")):
        pin = PINS[role]
        if fetch:
            subprocess.run(["git", "fetch", "--no-tags", "origin", pin], check=True)
        raw = subprocess.check_output([
            "git", "-c", "core.autocrlf=false", "archive", pin, f"tools/{namespace}"
        ])
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for item in archive.getmembers():
                if item.isfile():
                    path = output / role / item.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.extractfile(item).read())
    if fetch:
        subprocess.run([
            sys.executable, "-B", str(output / "a/tools/first_research_cycle/stage_dependencies.py"),
            "--fetch", "--output", str(output / "deps")
        ], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    stage(args.output.resolve(), args.fetch)
