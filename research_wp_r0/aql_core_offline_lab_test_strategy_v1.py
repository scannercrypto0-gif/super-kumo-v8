"""Core #253: one immutable same-original-source TEST_ONLY strategy decision grid.

No new numerical indicator kernel or backtester. Reuses StrategyDefinition and
IndicatorRegistryV2._values (the existing tested indicator numerical kernel);
consumes only independently readback-verified Core query_local results. This is
retrospective engineering, not historical PIT or real/paper trade authority.
"""
from __future__ import annotations

from types import SimpleNamespace

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import query_local, require
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import StrategyDefinition

SCHEMA = "aql.core.offline-lab-test-strategy.v1"
STATES = ("ENTRY_TRIGGERED","EXIT_TRIGGERED","NO_SIGNAL","UNKNOWN")
WIDTH = 900_000


def _eval(node, i, values):
    op=node["op"]
    if op=="constant":
        return node["value"]
    if op=="indicator":
        idx=i-node["lag"]
        return values[node["name"]].get(idx,{}).get(node["field"])
    if op in ("gt","ge","lt","le","eq"):
        a=_eval(node["left"],i,values)
        b=_eval(node["right"],i,values)
        if a is None or b is None:
            return None
        return {"gt":lambda:a>b,"ge":lambda:a>=b,"lt":lambda:a<b,
                "le":lambda:a<=b,"eq":lambda:a==b}[op]()
    if op in ("all","any"):
        xs=[_eval(v,i,values) for v in node["args"]]
        if op=="all":
            return False if False in xs else None if None in xs else True
        return True if True in xs else None if None in xs else False
    if op=="not":
        x=_eval(node["arg"],i,values)
        return None if x is None else not x
    raise ValueError("CORE_253_UNSUPPORTED_RULE")


def calculate_one_original_test_strategy(
    root, warehouse_receipt, *, start_ms, end_exclusive_ms,
    cutoff_ms, definition=None,
):
    """Calculate one research-only candidate, sealed for Factory #254.

    The caller must supply a genuine Core warehouse receipt produced from
    source bytes in this runner; source and bar checksums are rechecked by
    query_local against immutable original Bridge bytes, not accepted as a
    detached user-provided array. This API never models fills or opens holdout.
    """
    w=warehouse_receipt
    require(type(w) is dict and w.get("schema")=="aql.core.local-history-warehouse.v1",
            "CORE_LAB_WAREHOUSE_REQUIRED")
    sealed={k:v for k,v in w.items() if k!="receipt_sha256"}
    require(w.get("receipt_sha256")==digest(sealed)
            and w.get("status")=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
            and w.get("vault",{}).get("vault")=="EXISTING_PINNED_RAW_VAULT"
            and w.get("interval")=="15m" and w.get("symbol")=="BTCUSDT"
            and w.get("market")=="SPOT" and w.get("exchange")=="BINANCE"
            and w.get("coverage")=="COMPLETE"
            and w.get("availability")=="RETROSPECTIVE_NON_PIT"
            and w.get("historical_known_at")=="NOT_ATTESTED",
            "CORE_LAB_SOURCE_SCOPE_OR_VAULT")
    require(type(start_ms) is int and type(end_exclusive_ms) is int
            and type(cutoff_ms) is int and
            start_ms==w["start_ms"] and end_exclusive_ms==w["end_exclusive_ms"]
            and cutoff_ms==w["decision_cutoff_ms"]
            and start_ms%WIDTH==0 and end_exclusive_ms%WIDTH==0,
            "CORE_LAB_WINDOW_OR_CUTOFF_DRIFT")
    q=query_local(root,w["dataset_id"],w["version"],start_ms,
                  end_exclusive_ms,cutoff_ms,
                  required_source_sha256=w["source_zip_sha256"],
                  require_complete=True)
    bars=q["bars"]
    require(2<=len(bars)<=4096 and q["coverage"]=="COMPLETE"
            and q["available_bar_count"]==w["bar_count"]
            and q["source_bytes_sha256"]==w["source_zip_sha256"]
            and q["manifest_integrity_sha256"]==w["manifest_integrity_sha256"]
            and q["missing_bar_opens"]==[]
            and all(b["historical_known_at_ms"] is None for b in bars),
            "CORE_LAB_QUERY_DRIFT_OR_PIT")
    registry=IndicatorRegistryV2()
    if definition is None:
        definition=default_test_strategy()
    strategy=StrategyDefinition.from_dict(definition,registry=registry)
    spec=strategy.spec
    require(spec["scope"]=="RESEARCH_ONLY"
            and spec["strategy_id"]=="OFFLINE_LAB_TEST_STRATEGY"
            and spec["timing"]["decision"]=="CONFIRMED_CLOSE"
            and spec["timing"]["entry_execution"]=="NEXT_ELIGIBLE_OPEN",
            "CORE_LAB_UNAPPROVED_TEST_DEFINITION")
    # One full 15m source grid. The existing indicator kernel is called only
    # with source-locked, contiguous closed OHLCV, never future features.
    values={}
    native=[SimpleNamespace(open=b["open"],high=b["high"],low=b["low"],
                            close=b["close"],volume=b["volume"]) for b in bars]
    for ref in spec["indicators"]:
        indicator=registry.get(ref["indicator_id"],**ref["parameters"])
        require(indicator.version==ref["version"] and
                hasattr(indicator,"_values"),
                "CORE_LAB_NUMERICAL_KERNEL_NOT_SUPPORTED")
        try:
            vectors=indicator._values(native)
        except (ValueError,ZeroDivisionError,OverflowError) as exc:
            raise ValueError("CORE_LAB_INDICATOR_NUMERICAL_FAILURE") from exc
        values[ref["name"]]={
            i:dict(zip(indicator.output_fields,outputs))
            for i,outputs in vectors
        }
    rows=[]
    for i,bar in enumerate(bars[:-1]):
        # bar i closes strictly before the next eligible open; never
        # inspect next-bar prices for the signal.
        require(bar["bar_close_ms"]<bars[i+1]["bar_open_ms"]
                and bars[i+1]["bar_open_ms"]==bar["bar_open_ms"]+WIDTH,
                "CORE_LAB_NEXT_OPEN_NOT_CONTIGUOUS")
        entry=_eval(spec["entry"],i,values)
        exit_=_eval(spec["exit"],i,values)
        ready=entry is not None and exit_ is not None
        state=("UNKNOWN" if not ready else
               "ENTRY_TRIGGERED" if entry else
               "EXIT_TRIGGERED" if exit_ else "NO_SIGNAL")
        rows.append({"bar_open_ms":bar["bar_open_ms"],
                     "state":state,"indicator_ready":ready})
    counts={name:sum(x["state"]==name for x in rows) for name in STATES}
    attempt=digest({"dataset_id":w["dataset_id"],
                    "source_sha256":w["source_zip_sha256"],
                    "strategy_digest":strategy.digest,
                    "cutoff_ms":cutoff_ms,
                    "research_lane":"OFFLINE_LAB_TEST_STRATEGY"})
    body={
        "schema":SCHEMA,"research_lane":"OFFLINE_LAB_TEST_STRATEGY",
        "evidence_class":"RETROSPECTIVE_NON_PIT","test_only":True,
        "operational_scanner_status":"UNKNOWN",
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "scientific_result":"INSUFFICIENT_EVIDENCE",
        "trading_authority":"NONE","real_paper_activation":"DISABLED",
        "holdout":"SEALED_UNOPENED",
        "dataset_id":w["dataset_id"],"version":w["version"],
        "source_zip_sha256":w["source_zip_sha256"],
        "manifest_integrity_sha256":w["manifest_integrity_sha256"],
        "warehouse_receipt_sha256":w["receipt_sha256"],
        "core_price_query_sha256":q["query_sha256"],
        "core_253_query_sha256":q["query_sha256"],
        "decision_cutoff_ms":cutoff_ms,
        "strategy_definition":strategy.to_dict(),
        "strategy_digest":strategy.digest,
        "strategy_id":spec["strategy_id"],
        "strategy_version":spec["strategy_version"],
        "bar_count":len(bars),"width_ms":WIDTH,
        "source_first_bar_open_ms":bars[0]["bar_open_ms"],
        "decisions":rows,"decision_slots":len(rows),
        "decision_counts":counts,
        "attempt_id":attempt,"attempt_denominator":1,
        "independent_market_opportunity_denominator":None,
        "base_shadow_results":None,
    }
    return {**body,"evaluation_sha256":digest(body)}


def default_test_strategy():
    """A deterministic ROC test definition, not a selected/profitable strategy."""
    spec={
        "schema_version":"1","strategy_id":"OFFLINE_LAB_TEST_STRATEGY",
        "strategy_version":"v1","scope":"RESEARCH_ONLY",
        "indicators":[{
            "name":"roc","indicator_id":"ROC_v2","version":"2",
            "parameters":{"period":5},
            "constraints":{"period":{"type":"int","min":2,"max":1000}},
        }],
        "entry":{"op":"gt",
                 "left":{"op":"indicator","name":"roc","field":"roc","lag":0},
                 "right":{"op":"constant","value":1.0}},
        "exit":{"op":"lt",
                "left":{"op":"indicator","name":"roc","field":"roc","lag":0},
                "right":{"op":"constant","value":-1.0}},
        "timing":{"decision":"CONFIRMED_CLOSE",
                  "entry_execution":"NEXT_ELIGIBLE_OPEN",
                  "ambiguity":"REJECT"},
        "risk":{"unit":"ENTRY_NOTIONAL","max_exposure":0.01,
                "max_leverage":1,"stop_fraction":0.5,
                "target_fraction":0.9,"entry_ttl_bars":3,
                "holding_bars":3},
    }
    return StrategyDefinition(spec,registry=IndicatorRegistryV2()).to_dict()
