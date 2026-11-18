"""Opt-in isolated PIT mutation probe: source tree remains untouched."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    root = Path.cwd().resolve()
    source = root / "src" / "aql" / "archive" / "contracts.py"
    original = source.read_text(encoding="utf-8")
    needle = 'raise ValueError("Future/inconsistent feature evidence")'
    if original.count(needle) != 1:
        raise SystemExit("FAIL: expected exactly one PIT validation branch")
    with tempfile.TemporaryDirectory(prefix="atlas-pit-mutation-") as directory:
        copy = Path(directory) / "src"
        shutil.copytree(root / "src", copy)
        mutant = copy / "aql" / "archive" / "contracts.py"
        mutant.write_text(original.replace(needle, "pass", 1), encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(copy)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_tooling_properties.py",
             "-q", "-x", "-k", "test_pit_context_rejects_future_available_feature"],
            cwd=root, env=env, capture_output=True, text=True, timeout=90,
        )
        output = result.stdout + "\n" + result.stderr
        print(output[-5000:])
        if result.returncode == 0:
            raise SystemExit("FAIL: PIT property did not detect disabled validation")
        if "DID NOT RAISE" not in output:
            raise SystemExit("FAIL: mutant run failed for an unrelated reason")
        print("PASS: PIT property killed isolated validation-bypass mutant")


if __name__ == "__main__":
    main()
