"""Create a create-only local manifest pin for one sealed watchdog snapshot."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import atlas_ops_watchdog as watchdog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path,
                        help="One existing sealed atlas.operator.health-snapshot.v1 JSON file.")
    parser.add_argument("--output", required=True, type=Path, help="New manifest path; existing files are never replaced.")
    args = parser.parse_args()
    snapshot, raw_sha = watchdog.read_json(args.snapshot)
    watchdog.sealed_hash(snapshot, "sha256", "SNAPSHOT_SEAL_INVALID")
    watchdog.require(snapshot.get("schema") == "atlas.operator.health-snapshot.v1"
                     and snapshot.get("source_paths_exposed") is False
                     and snapshot.get("raw_market_payload_included") is False
                     and snapshot.get("network_calls") == 0
                     and snapshot.get("source_mutations") == 0
                     and snapshot.get("trading_authority") == "NONE", "SNAPSHOT_CONTRACT")
    target = args.output.absolute()
    watchdog.require(".." not in args.output.parts, "OUTPUT_PATH_TRAVERSAL")
    for item in (target, *target.parents):
        if item.exists() or item.is_symlink():
            st = item.lstat()
            watchdog.require(not item.is_symlink() and not getattr(st, "st_file_attributes", 0) & 1024,
                             "OUTPUT_PATH_LINK_DENIED")
    manifest_body = {"schema": "atlas.mcp.source-manifest.v1",
                     "snapshot_path": str(args.snapshot.absolute()),
                     "snapshot_file_sha256": raw_sha}
    manifest = {**manifest_body, "manifest_sha256": watchdog.digest(watchdog.canonical(manifest_body))}
    raw = watchdog.canonical(manifest)
    target.parent.mkdir(parents=False, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    print(watchdog.digest(raw))


if __name__ == "__main__":
    main()

