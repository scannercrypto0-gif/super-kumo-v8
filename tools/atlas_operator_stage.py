"""Stage the exact Capacity runtime used by the saved-only operator report."""
import argparse
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

CAPACITY = "dd3e149afe73d9d04c9892ad35005b04fb675fff"
ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ("atlas_operator_report.py", "atlas_operator_readback.py",
           "atlas_strategy_operations.py")


def stage(output):
    output.mkdir()
    archive = subprocess.check_output(
        ["git", "-C", str(ROOT), "-c", "core.autocrlf=false", "archive", "--format=zip",
         CAPACITY, "src", "research_wp_r0", "tools", "migrations"]
    )
    with ZipFile(BytesIO(archive)) as bundle:
        bundle.extractall(output)
    for name in OVERLAY:
        shutil.copyfile(ROOT / "tools" / name, output / "tools" / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    stage(parser.parse_args().output)
