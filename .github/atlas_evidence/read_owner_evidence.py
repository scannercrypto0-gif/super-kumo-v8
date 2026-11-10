"""Read only from the already running PR #286 observer. No network or restart."""
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from time import time_ns

from aql.journal.durable_journal import DurableJournal
from aql.observation.prospective import ProspectiveObserver
from aql.storage.operational_store import OperationalStore
from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research
from tools.atlas_prospective_observe import FIXTURE, read_only_g1

def stamp(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds")

def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    if root.drive.upper() == "E:" or not (root / "atlas-prospective-v1").is_file():
        raise SystemExit("Existing isolated PR #286 state required")
    journal_file = root / "journal.sqlite"
    store = read_only_g1(OperationalStore, root / "market.sqlite")
    journal = read_only_g1(DurableJournal, journal_file)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
    observer = ProspectiveObserver(root / "g2.sqlite", journal, store, fixture,
                                   synthetic=False, read_only=True)
    cutoff = time_ns() // 1_000_000
    g2 = observer.verified_read(as_of_ms=cutoff)
    factory = read_prospective_research(observer, as_of_ms=cutoff)
    if g2["sha256"] != factory["g2_sha256"]:
        raise SystemExit("Inconsistent concurrent read. Retry this read-only command.")
    with closing(sqlite3.connect(journal_file.as_uri()+"?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        receipts = db.execute("""
            SELECT j.stable_key, j.bar_open, r.commit_return_observed_at_ms
            FROM journal_entries j JOIN g1_commit_receipts r
              ON r.identity = j.stable_key AND r.kind = 'BAR'
            WHERE j.symbol = 'BTCUSDT' AND j.interval = '15m' AND j.is_final = 1
              AND r.commit_return_observed_at_ms <= ?
            ORDER BY j.bar_open
        """, (cutoff,)).fetchall()
    print(json.dumps({"as_of_utc": stamp(cutoff), "receipts": receipts,
                      "eligible_horizons": [
                          {"origin_utc": stamp(row["decision"]["cutoff_ms"]),
                           "due_utc": stamp(h["due_ms"]), "duration_ms": h["horizon_ms"],
                           "state": h["state"]}
                          for row in g2["rows"] if row["source_valid"]
                          for h in row["horizons"]],
                      "g2": g2, "factory": factory}, sort_keys=True))

if __name__ == "__main__":
    main()
