"""Stage exact read-only Core modules in a disposable checkout."""
import argparse
from pathlib import Path
import subprocess

CORE = "612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d"
FACTORY = "ea4ffd5ce278d93588338122ab6ac1af8ec4da26"
ROOT = Path(__file__).resolve().parents[2]
OVERLAY = Path(__file__).resolve().parent / ".native"
CORE_PATHS = (
    "research_wp_r0/aql_archive_custody_bridge_v1.py",
    "research_wp_r0/aql_core_prospective_readiness_v1.py",
)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def stage(fetch=False):
    if fetch:
        for commit in (CORE, FACTORY):
            git("fetch", "--no-tags", "origin", commit)
    for name in CORE_PATHS:
        raw = git("show", f"{CORE}:{name}")
        target = OVERLAY / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != raw:
                raise ValueError(f"CORE_SOURCE_DRIFT: {name}")
        else:
            with target.open("xb") as out:
                out.write(raw)


def verify():
    for name in CORE_PATHS:
        if (OVERLAY / name).read_bytes() != git("show", f"{CORE}:{name}"):
            raise ValueError(f"CORE_SOURCE_DRIFT: {name}")
    for name in (
        "research_wp_r0/aql_factory_h_execution_comparison_v1.py",
        "research_wp_r0/aql_factory_h_scientific_lab_v1.py",
        "research_wp_r0/aql_factory_historical_rule_projection.py",
        "src/aql/journal/durable_journal.py",
    ):
        if (ROOT / name).read_bytes().replace(b"\r\n", b"\n") != git("show", f"{FACTORY}:{name}").replace(b"\r\n", b"\n"):
            raise ValueError(f"NATIVE_SOURCE_DRIFT: {name}")


def activate():
    verify()
    import research_wp_r0
    research_wp_r0.__path__.append(str(OVERLAY / "research_wp_r0"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    stage(parser.parse_args().fetch)
    verify()
