"""Finite opt-in CLI; no network, pruning or ingestion callback wiring."""
import argparse
import json
from .local import LocalArchive
from .backup import create_backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("journal", "root", "market", "build", "policy"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--batches", type=int, default=1)
    parser.add_argument("--reserve-bytes", type=int, default=10_000_000_000)
    parser.add_argument("--backup-to")
    args = parser.parse_args()
    if not 1 <= args.batches <= 100: parser.error("batches must be1..100")
    archive = LocalArchive(args.journal, args.root, market=args.market, build=args.build,
                           policy=args.policy, reserve_bytes=args.reserve_bytes)
    count = 0
    for _ in range(args.batches):
        n = archive.drain_once(); count += n
        if not n: break
    result = {"archived_this_run": count}
    if args.backup_to:
        path, evidence = create_backup(archive, args.backup_to)
        result["backup"] = {"path": str(path), **evidence}
    result["health"] = archive.health()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
