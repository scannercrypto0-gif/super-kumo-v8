"""Advisory same-config Ruff baseline comparison; never modifies project sources."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=check)


def findings(root, config):
    result = run(sys.executable, "-m", "ruff", "check", "--config", str(config),
                 "--output-format", "json", "src", "tests", cwd=root, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Ruff execution failed: {result.stderr}")
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ruff output was not JSON: {result.stderr}") from exc
    counts = Counter()
    for record in records:
        relative = Path(record["filename"]).relative_to(root).as_posix()
        counts[(relative, record["code"])] += 1
    return counts


def main():
    repo = Path.cwd().resolve()
    base = run("git", "merge-base", "HEAD", "origin/main").stdout.strip()
    config = repo / "ruff.toml"
    with tempfile.TemporaryDirectory(prefix="atlas-ruff-base-") as temp:
        checkout = Path(temp) / "base"
        run("git", "worktree", "add", "--detach", str(checkout), base)
        try:
            old = findings(checkout, config)
            new = findings(repo, config)
        finally:
            run("git", "worktree", "remove", "--force", str(checkout))
    increases = {k: new[k] - old[k] for k in new if new[k] > old[k]}
    decreases = {k: old[k] - new[k] for k in old if old[k] > new[k]}
    print(f"Common-base commit: {base}")
    print(f"Ruff baseline findings: {sum(old.values())}")
    print(f"Ruff PR-head findings: {sum(new.values())}")
    print(f"Increased per-file/rule counts (not proven newly introduced defects): {sum(increases.values())}")
    print(f"Decreased per-file/rule counts: {sum(decreases.values())}")
    for (path, rule), count in sorted(increases.items()):
        print(f"  +{count} {rule} {path}")
    print("Advisory comparison only; changed line locations and pre-existing violations need review.")


if __name__ == "__main__":
    main()
