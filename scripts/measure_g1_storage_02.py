"""Disposable local measurement, no network or existing database access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from aql.archive.local import LocalArchive, ArchiveService
from aql.archive.backup import create_backup, restore_backup
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def sample(i):
    opened=(i//8)*60000
    return MarketBar(f"SYM{i%8}USDT","1m",opened,opened+59999,10.,11.,9.,10.,float(i+1),True,"synthetic-measurement",opened+60000).with_checksum()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows",type=int,default=512)
    args=parser.parse_args()
    if not 128<=args.rows<=4096:parser.error("rows must be128..4096")
    out={"schema":"aql.storage-measurement.v1","utc":datetime.now(timezone.utc).isoformat(),
         "python":sys.version.split()[0],"platform":platform.platform(),"rows":args.rows,
         "fixture":"synthetic8 symbols x1m; not live deployment, no compression implemented"}
    out["source_sha256"]={name:hashlib.sha256((Path(__file__).resolve().parents[1]/"src/aql/archive"/name).read_bytes()).hexdigest() for name in ("contracts.py","local.py","backup.py")}
    with tempfile.TemporaryDirectory(prefix="aql-storage02-measure-") as directory:
        root=Path(directory)
        journal=DurableJournal(str(root/"journal.sqlite"))
        latencies=[]
        for i in range(args.rows):
            start=time.perf_counter();journal.commit(sample(i));latencies.append((time.perf_counter()-start)*1000)
        archive=LocalArchive(journal.db_path,root/"archive",market="spot",build="measurement-dev",policy="phase1-v1",reserve_bytes=0)
        start=time.monotonic();batches=0
        while archive.drain_once():batches+=1
        out["archive_elapsed_s"]=time.monotonic()-start
        out["archive_batches"]=batches
        out["core_commit_ms"]={"median":statistics.median(latencies),"p95":sorted(latencies)[int(.95*len(latencies))-1]}
        files=list((archive.root/"segments").rglob("*"))
        payload=sum(p.stat().st_size for p in files if p.is_file() and p.name=="records.jsonl")
        manifests=sum(p.stat().st_size for p in files if p.is_file() and p.name=="manifest.json")
        catalog=(archive.root/"catalog.sqlite").stat().st_size
        out["bytes"]={"jsonl":payload,"manifests":manifests,"catalog":catalog,
                      "journal":Path(journal.db_path).stat().st_size}
        per=(payload+manifests+catalog)/args.rows
        out["archive_bytes_per_row_including_fixed_catalog"]=per
        out["archive_GB_30_90_365"]={str(symbols):{str(days):round(symbols*1440*days*per/1e9,4) for days in (30,90,365)} for symbols in (10,100,500)}
        start=time.monotonic();backup,evidence=create_backup(archive,root/"backup")
        out["backup_elapsed_s"]=time.monotonic()-start
        start=time.monotonic();restored=restore_backup(backup,root/"restored",expected_digest=evidence["inventory_hash"])
        out["restore_elapsed_s"]=time.monotonic()-start
        assert restored==evidence and evidence["records"]==args.rows
        out["backup_restore"]=evidence
        # Independent journal: block archive I/O, measure real journal fsync commits.
        iso=DurableJournal(str(root/"isolation.sqlite"));iso.commit(sample(0))
        entered,release=threading.Event(),threading.Event()
        def fault(stage):
            if stage=="before_write":entered.set();release.wait(10)
        blocked=LocalArchive(iso.db_path,root/"blocked",market="spot",build="measurement-dev",policy="phase1-v1",reserve_bytes=0,fault=fault)
        service=ArchiveService(blocked)
        try:
            service.request();assert entered.wait(3)
            times=[]
            for i in range(1,21):
                start=time.perf_counter();iso.commit(sample(i));times.append((time.perf_counter()-start)*1000)
            out["core_while_archive_blocked_ms"]={"count":20,"median":statistics.median(times),"p95":sorted(times)[18],"max":max(times)}
        finally:release.set();service.finish(3)
        out["limits"]="single synthetic Windows/Linux fixture; same-device copies; no power-loss/offsite/RPO certification; fixed small-sample catalog allocation may overstate asymptotic B/row"
    print(json.dumps(out,indent=2))


if __name__=="__main__":main()
