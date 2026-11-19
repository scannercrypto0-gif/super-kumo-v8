"""Read-only warehouse capacity and path preflight; no directory creation or download.

This preflight is intentionally separate from host provisioning and daily scheduler.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

DEFAULT_ROOT = Path("E:/ATLAS/DataWarehouse")
CAP_BYTES = 150_000_000_000
RESERVE_BYTES = 50_000_000_000


def plan_warehouse(root=DEFAULT_ROOT, *, cap_bytes=CAP_BYTES, reserve_bytes=RESERVE_BYTES):
    root = Path(root).absolute()
    if type(cap_bytes) is not int or type(reserve_bytes) is not int or cap_bytes <= 0 or reserve_bytes < 0:
        raise ValueError("WAREHOUSE_CAP_INVALID")
    if os.name == "nt" and (root.drive.upper() != "E:" or not root.is_absolute()):
        raise ValueError("WAREHOUSE_ROOT_MUST_BE_E")
    # Never traverse an existing symlink/reparse point in the selected root ancestry.
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise ValueError("WAREHOUSE_SYMLINK_DENIED")
    anchor = next((parent for parent in (root, *root.parents) if parent.exists()), None)
    if anchor is None or not anchor.is_dir():
        raise ValueError("WAREHOUSE_ANCHOR_MISSING")
    stats = os.statvfs(anchor) if hasattr(os, "statvfs") else None
    if stats is None:
        import shutil
        free = shutil.disk_usage(anchor).free
    else:
        free = stats.f_bavail * stats.f_frsize
    budget = min(cap_bytes, max(0, free - reserve_bytes))
    return {
        "schema": "aql.research.warehouse-plan.v1",
        "status": "CAPACITY_PREFLIGHT_PASS" if budget > 0 else "WAIT_INSUFFICIENT_FREE_SPACE",
        "root": str(root), "anchor": str(anchor), "free_bytes": free,
        "cap_bytes": cap_bytes, "reserve_bytes": reserve_bytes,
        "new_data_budget_bytes": budget,
        "layout": ["raw", "catalog", "bars", "receipts", "quarantine"],
        "host_mutations": 0, "downloads": 0, "scheduler_changes": 0,
        "source_class": "RETROSPECTIVE_NON_PIT",
        "scientific_pit_oos": "NOT_ATTESTED",
        "trading_authority": "NONE",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = p.parse_args()
    print(json.dumps(plan_warehouse(args.root), sort_keys=True))


if __name__ == "__main__":
    main()
