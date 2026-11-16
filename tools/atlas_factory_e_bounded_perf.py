"""Factory E deterministic bounded multi-strategy × multi-symbol CPU/memory smoke.

This benchmarks metadata registration and immutability, NOT market simulation,
strategy profitability, source PIT or operational scaling. The workload is a
publicly described deterministic generated research fixture. No trading.
"""
import argparse
import json
import tempfile
import time
import tracemalloc
from hashlib import sha256
from pathlib import Path

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment,register_experiment,read_experiment,audit_store_layout,
)

def stable(label):
    return sha256(label.encode("utf-8")).hexdigest()

def execute(*, strategies=12,symbols=8,per_pair=4,
            max_seconds=12.0,max_peak_mib=96.0):
    if not (type(strategies) is type(symbols) is type(per_pair) is int
            and 1<=strategies<=32 and 1<=symbols<=32 and 1<=per_pair<=10
            and 0<max_seconds<=120 and 0<max_peak_mib<=512):
        raise ValueError("invalid bounded performance workload")
    n=strategies*symbols
    tracemalloc.start()
    start=time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        database=Path(directory)/"factory-e-perf.sqlite"
        for i in range(strategies):
            for j in range(symbols):
                identity=f"strategy-{i:02d}:symbol-{j:02d}"
                attempts=[dict(
                    attempt_id=f"{identity}:candidate-{k}",
                    candidate_id=f"{identity}:trial-{k}",
                    state=("SELECTED","REJECTED","UNKNOWN","QUARANTINED")[k%4],
                    source_receipt_sha256=stable(identity+":candidate-source"))
                          for k in range(per_pair)]
                rec=build_experiment(
                    experiment_id=f"PERF-E-{i:02d}-{j:02d}",lane="SCANNER",
                    source_status="SYNTHETIC_ENGINEERING_PASS",
                    source_sha256=stable(identity+":synthetic-source"),
                    source_query_245_sha256=stable(identity+":native-query"),
                    source_query_253_sha256=stable(identity+":local-query"),
                    strategy_definition_sha256=stable(f"strategy-{i:02d}:definition"),
                    config_sha256=stable(identity+":config"),
                    code_sha256=stable("factory-e-performance-benchmark-v1"),
                    environment_sha256=stable("public-offline-bounded-fixture"),
                    parent_receipt_sha256=stable(identity+":parent"),
                    attempts=attempts)
                register_experiment(database,rec)
                if read_experiment(database,rec["experiment_id"])!=rec:
                    raise AssertionError("PERF_E_DURABLE_READBACK_DRIFT")
        layout=audit_store_layout(database)
        if layout["experiment_count"]!=n:
            raise AssertionError("PERF_E_DENOMINATOR_DRIFT")
        if sum(per_pair for _ in layout["all_document_shas"])!=n*per_pair:
            raise AssertionError("PERF_E_ATTEMPTS_CENSUS_DRIFT")
        canonical=sha256(json.dumps(
            layout["all_document_shas"],sort_keys=True,
            separators=(",",":")).encode()).hexdigest()
    elapsed=time.perf_counter()-start
    _,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mib=peak/1048576
    result=dict(
        schema="aql.factory.e.bounded-store-performance.v1",
        fixture="DETERMINISTIC_GENERATED_METADATA_NOT_MARKET_HISTORY",
        strategy_count=strategies,symbol_count=symbols,
        per_pair_attempts=per_pair,experiment_count=n,
        attempts_count=n*per_pair,elapsed_seconds=round(elapsed,4),
        peak_traced_python_mib=round(peak_mib,4),
        max_seconds=max_seconds,max_peak_mib=max_peak_mib,
        document_set_sha256=canonical,
        broker_network="NOT_USED",historical_pit="NOT_ATTESTED",
        trading_authority="NONE",orders_created=0,actual_fills=None,
        threshold_pass=elapsed<=max_seconds and peak_mib<=max_peak_mib)
    if not result["threshold_pass"]:
        raise AssertionError("PERF_E_BOUNDED_RESOURCE_THRESHOLD_EXCEEDED "+json.dumps(result))
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--strategies",type=int,default=12)
    parser.add_argument("--symbols",type=int,default=8)
    parser.add_argument("--per-pair",type=int,default=4)
    parser.add_argument("--max-seconds",type=float,default=12.0)
    parser.add_argument("--max-peak-mib",type=float,default=96.0)
    parser.add_argument("--output",default="e-factory-performance.json")
    cfg=parser.parse_args()
    out=execute(strategies=cfg.strategies,symbols=cfg.symbols,
                per_pair=cfg.per_pair,max_seconds=cfg.max_seconds,
                max_peak_mib=cfg.max_peak_mib)
    Path(cfg.output).write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("ATLAS_FACTORY_E_PERFORMANCE="+json.dumps(out,sort_keys=True,separators=(",",":")))
