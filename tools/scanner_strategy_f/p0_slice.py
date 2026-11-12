"""Scanner P0 fixture runtime over the native Core253 and Scanner H contracts."""
from collections import Counter
import hashlib
from pathlib import Path
from types import SimpleNamespace

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_factory_historical_rule_projection import _vectors
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_f import research_strategy_plugin as native

STEP = native.STEP
ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "research_wp_r0/indicator_library_v2.py"


def seal(body):
    return {**body,"sha256":digest(body)}


def verify(doc, pin):
    require(doc["sha256"] == pin == digest({k:v for k,v in doc.items() if k!="sha256"}),"P0_PIN")


def clock(value):
    require(type(value) is int and 0<=value<2**53,"P0_CLOCK")
    return value


def freeze(*, origin, slots, symbols, source_pins, plugin_pins, warmup, catchup, max_rows, max_bytes, lag_ms):
    clock(origin)
    require(origin % STEP == 0 and origin >= warmup*STEP and
            all(type(v) is int and v>0 for v in (slots,warmup,catchup,max_rows,max_bytes,lag_ms)),
            "P0_SCHEDULE")
    require(1<=catchup<=slots and warmup<=4096 and bool(symbols) and bool(plugin_pins)
            and len(set(symbols))==len(symbols) and len(set(plugin_pins))==len(plugin_pins)
            and all(type(s) is str and s.isalnum() and len(s)<=24 for s in symbols)
            and all(native._hex(pin) for pin in plugin_pins)
            and set(source_pins)==set(symbols) and all(native._hex(pin) for pin in source_pins.values())
            and len(set(source_pins.values()))==len(symbols)
            and slots*len(symbols)*len(plugin_pins)<=max_rows,"P0_CAPACITY")
    return seal(dict(schema="aql.scanner.p0.schedule.v1",origin=origin,slots=slots,interval="15m",
                     symbols=sorted(symbols),sources=source_pins,plugins=sorted(plugin_pins),warmup=warmup,catchup=catchup,
                     max_rows=max_rows,max_bytes=max_bytes,lag_ms=lag_ms,
                     scope="TEST_ONLY",authority="NONE"))


def source_query(source, expected, symbol, start, end, cutoff, *, warehouse, reader=native.query_local):
    verify(source,expected)
    require(set(source)=={"schema","scope","symbol","interval","dataset_id","version","source_bytes_sha256",
                         "manifest_sha256","rights","valid_from","expires","max_age_ms","sha256"}
            and source["schema"]=="aql.scanner.p0.core-pin.v1" and source["scope"]=="TEST_ONLY"
            and source["symbol"]==symbol and source["interval"]=="15m"
            and source["rights"]=="FIXTURE_RESEARCH_ONLY"
            and clock(source["valid_from"]) <= cutoff < clock(source["expires"])
            and type(source["max_age_ms"]) is int and source["max_age_ms"]>=0
            and type(source["version"]) is int and source["version"]>=1
            and end<=cutoff and cutoff-end<=source["max_age_ms"],"CORE_RIGHTS_OR_STALE")
    query = reader(warehouse,source["dataset_id"],source["version"],start,end,cutoff,
                   required_source_sha256=source["source_bytes_sha256"],require_complete=False,sqlite_immutable=True)
    require(query["source_bytes_sha256"]==source["source_bytes_sha256"]
            and query["manifest_integrity_sha256"]==source["manifest_sha256"]
            and query["dataset_id"]==source["dataset_id"] and query["version"]==source["version"]
            and (query["start_ms"],query["end_exclusive_ms"],query["decision_cutoff_ms"])==(start,end,cutoff),
            "CORE_SOURCE_BINDING")
    native._validate_query(query)
    require(all(b["observation_lower_bound_ms"]<=cutoff for b in query["bars"]),"CORE_FUTURE_AVAILABILITY")
    return query


def decision(plan, plugin, symbol, slot, now, source_pin, query, *, warehouse=None):
    instance = Frozen.restore(plugin)
    require(instance.sha256 in plan["plugins"] and symbol in plan["symbols"]
            and plan["sources"][symbol]==source_pin,"P0_FROZEN_STRATEGY")
    clock(now)
    cutoff = slot+STEP
    require(now>=cutoff and (slot-plan["origin"])%STEP==0 and
            0<=(slot-plan["origin"])//STEP<plan["slots"],"P0_SLOT")
    identity = digest([plan["sha256"],symbol,instance.sha256,slot])
    batch, status, reason = None,"UNKNOWN","SOURCE_UNAVAILABLE"
    if query is not None:
        require(query["decision_cutoff_ms"]==cutoff and query["end_exclusive_ms"]==cutoff,
                "P0_LOOKAHEAD")
        batch = native.evaluate_strategy_plugin(plugin,query,warehouse_root=warehouse,
                                                policy=native.research_signal_policy())
        body = native.verify_factory_signal_batch(batch).data
        last = body["events"][-1]
        status = last["signal_state"] if body["coverage"]=="COMPLETE" else "UNKNOWN"
        reason = "SOURCE_GAP" if body["coverage"]!="COMPLETE" else None
    return seal(dict(schema="aql.scanner.p0.decision.v1",id=identity,plan_sha256=plan["sha256"],
                     symbol=symbol,plugin_sha256=instance.sha256,strategy_version=instance.data["strategy_version"],
                     slot=slot,cutoff=cutoff,source_sha256=source_pin,state=status,reason=reason,
                     timing="LATE_RESEARCH_ONLY" if now-cutoff>plan["lag_ms"] else "FIXTURE_ON_TIME",
                     known_at=None,authority="NONE",
                     source_query_sha256=query["query_sha256"] if query else None,
                     native_batch_sha256=batch["sha256"] if batch else None)),batch


def monitor(request, expected, *, decision_doc, query):
    """Lab request scope is separate from the frozen decision receipt."""
    verify(request,expected)
    require(set(request)=={"schema","symbol","plugin_sha256","indicator","parameters","version","sha256"}
            and request["schema"]=="aql.scanner.p0.monitor-request.v1"
            and request["symbol"]==decision_doc["symbol"]
            and request["plugin_sha256"]==decision_doc["plugin_sha256"],"P0_MONITOR_SCOPE")
    indicator, value, warmup, reason = request["indicator"],None,None,"SOURCE_UNKNOWN"
    try:
        kernel = IndicatorRegistryV2().get(indicator,**request["parameters"])
        warmup = getattr(kernel,"min_warmup_bars",None)
        require(str(kernel.version)==request["version"],"P0_INDICATOR_VERSION")
        if query is not None:
            require(query["decision_cutoff_ms"]==decision_doc["cutoff"]
                    and query["query_sha256"]==decision_doc["source_query_sha256"],"P0_MONITOR_CUTOFF")
            native._validate_query(query)
            if query["coverage"]=="COMPLETE":
                ref = dict(name="monitor",indicator_id=indicator,parameters=request["parameters"])
                shaped = [dict(open_ms=b["bar_open_ms"],close_ms=b["bar_close_ms"],
                               **{k:b[k] for k in ("open","high","low","close","volume")}) for b in query["bars"]]
                result = _vectors(SimpleNamespace(spec={"indicators":[ref]}),shaped)["monitor"]
                value = result.get(len(shaped)-1)
                if value is not None and any(v is None for v in value.values()):
                    value = None
                reason = None if value is not None else "WARMUP"
    except (ValueError,TypeError,KeyError):
        reason = "INVALID_MONITOR_OR_SOURCE"
    return seal(dict(schema="aql.scanner.p0.lab-monitor.v1",mode="MONITOR_ONLY",request_sha256=expected,
                     decision_sha256=decision_doc["sha256"],symbol=decision_doc["symbol"],
                     plugin_sha256=decision_doc["plugin_sha256"],strategy_version=decision_doc["strategy_version"],
                     indicator=indicator,parameters=request["parameters"],version=request["version"],
                     library_sha256=hashlib.sha256(LIBRARY.read_bytes().replace(b"\r\n",b"\n")).hexdigest(),
                     cutoff=decision_doc["cutoff"],source_query_sha256=query["query_sha256"] if query else None,
                     known_at=None,timing=decision_doc["timing"],warmup_bars=warmup,
                     availability="AVAILABLE" if value is not None else "UNKNOWN",
                     reason=reason,value=value,authority="NONE"))


def census(rows, expected):
    require(len(rows)==expected and len({r["id"] for r in rows})==expected,"P0_DENOMINATOR")
    return dict(Counter(row["state"] for row in rows))
