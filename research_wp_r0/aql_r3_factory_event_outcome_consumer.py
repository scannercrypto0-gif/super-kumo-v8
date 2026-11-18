"""R3 Factory non-trading C2/F1/F3 read-only projection.
No original G2 event is synthesized from Core's R3 closed-prefix evaluator.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from collections import Counter

ARMS=("BASE","SHADOW")
HOURS=(4,24,72)
C2_FIELDS=("trial_id","opportunity_id","producer_event_id","envelope_sha256")
PINS=("source_id","source_version","source_bytes_sha256","correction_generation",
      "strategy_id","strategy_version","feature_snapshot_sha256","regime_snapshot_sha256")
SCHEDULE_FIELDS=set(("c2_identity","pair_id","experiment_plan_sha256","decision_cutoff_ms",
                     "scheduled_at_ms","availability_mode"))|set(PINS)
HASH=re.compile(r"[a-f0-9]{64}\Z")
STATES=("MISSING_CAPTURE","UNVERIFIED","QUARANTINED","RECORDED")
RESEARCH_SCHEMA="aql.r3-breakout-closed-prefix-evaluation.v1"
HOST_SCHEMA="aql.f1-prospective-host-handoff.v1"

def need(ok,reason):
    if not ok: raise ValueError("R3_"+reason)

def _pairs(rows):
    out={}
    for k,v in rows:
        need(k not in out,"DUPLICATE_JSON_KEY")
        out[k]=v
    return out

def read_json(raw):
    try:
        return json.loads(raw,object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError("R3_NONFINITE_JSON")))
    except (TypeError,UnicodeError,json.JSONDecodeError) as e:
        raise ValueError("R3_INVALID_JSON") from e

def jcs(value):
    """Core JCS subset (safe ints, strings, booleans, null, lists and objects)."""
    def check(v):
        if v is None or type(v) in (bool,str):
            need(type(v) is not str or not any(0xD800<=ord(c)<=0xDFFF for c in v),"SURROGATE")
        elif type(v) is int:
            need(abs(v)<=2**53-1,"INTEGER_RANGE")
        elif type(v) is list:
            for a in v: check(a)
        elif type(v) is dict:
            for k,a in v.items():
                need(type(k) is str,"OBJECT_KEY")
                check(k);check(a)
        else: raise ValueError("R3_NON_JCS_VALUE")
    check(value)
    def enc(v):
        if isinstance(v,dict):
            return "{"+",".join(enc(k)+":"+enc(v[k]) for k in sorted(v,key=lambda k:k.encode("utf-16-be")))+"}"
        if isinstance(v,list): return "["+",".join(enc(x) for x in v)+"]"
        if isinstance(v,str): return json.dumps(v,ensure_ascii=False,separators=(",",":"))
        if v is None:return "null"
        if v is True:return "true"
        if v is False:return "false"
        return str(v)
    return enc(value).encode("utf-8")

def digest(value):return hashlib.sha256(jcs(value)).hexdigest()
def ishash(v):return type(v) is str and HASH.fullmatch(v) is not None
def text(v):return type(v) is str and bool(v)
def timestamp(v):return type(v) is int and 0<=v<=2**53-1

def schedules(rows,pin=None):
    need(type(rows) is list,"SCHEDULE_LIST")
    if pin is not None:need(ishash(pin) and digest(rows)==pin,"SCHEDULE_SHA_DRIFT")
    result={};seen=set();previous=None
    for row in rows:
        need(type(row) is dict and set(row)==SCHEDULE_FIELDS,"SCHEDULE_FIELDS")
        c=row["c2_identity"]
        need(type(c) is dict and set(c)==set(C2_FIELDS),"C2_FIELDS")
        need(all(text(c[k]) for k in C2_FIELDS[:-1]) and ishash(c["envelope_sha256"]),"C2_IDENTITY")
        need(row["availability_mode"]=="PROSPECTIVE_CAPTURE","RETROSPECTIVE_SCHEDULE")
        need(ishash(row["experiment_plan_sha256"]) and
             row["pair_id"]==digest({"experiment_plan_sha256":row["experiment_plan_sha256"],
                                      "c2_identity":c}),"PAIR_SHA_DRIFT")
        for k in PINS:
            need(ishash(row[k]) if k.endswith("sha256") else text(row[k]),"SCHEDULE_PIN")
        cutoff=row["decision_cutoff_ms"];scheduled=row["scheduled_at_ms"]
        need(timestamp(cutoff) and cutoff>0 and cutoff%900000==0 and
             timestamp(scheduled) and scheduled<=cutoff,"SCHEDULE_CLOCK")
        unique=tuple(c[k] for k in C2_FIELDS)
        need(row["pair_id"] not in result and unique not in seen,"DUPLICATE_SCHEDULE")
        key=(scheduled,cutoff,row["pair_id"])
        need(previous is None or key>previous,"SCHEDULE_ORDER")
        previous=key;seen.add(unique);result[row["pair_id"]]=row
    return result

def research(doc):
    need(type(doc) is dict and doc.get("schema_version")==RESEARCH_SCHEMA,"RESEARCH_SCHEMA")
    need(doc.get("original_g2_event_status")=="NOT_CONNECTED" and
         doc.get("pre_f3_capture_status")=="NOT_CONNECTED" and
         doc.get("f3_monitor_status")=="NOT_CONNECTED" and
         doc.get("proof_status")=="BLOCKED_EXTERNAL_EVIDENCE" and
         doc.get("execution")=="DISABLED" and doc.get("direction") is None and
         doc.get("breakout_signal_state") in ("NO_SIGNAL","ARMED"),
         "RESEARCH_NOT_ORIGINAL_EVENT")
    need(ishash(doc.get("prefix_sha256")) and text(doc.get("source_id")) and
         text(doc.get("strategy_id")) and timestamp(doc.get("decision_cutoff_ms")),
         "RESEARCH_PINS")
    need(not any(k in doc for k in ("pair_id","original_f1_record","arm_statuses")),
         "RESEARCH_FORGED_EVENT")
    return {"schema_version":RESEARCH_SCHEMA,"counted_as_opportunity":False,
            "original_g2_event_status":"NOT_CONNECTED","prefix_sha256":doc["prefix_sha256"]}

def host_slots(events,plans,verify_handoff):
    out={};seen=set()
    for e in events:
        need(type(e) is dict and e.get("schema_version")==HOST_SCHEMA,"NOT_CORE_HOST_HANDOFF")
        pair=e.get("pair_id")
        need(pair in plans and pair not in seen,"DUPLICATE_OR_ORPHAN_HANDOFF")
        seen.add(pair);plan=plans[pair]
        need(e.get("c2_identity")==plan["c2_identity"] and
             e.get("experiment_plan_sha256")==plan["experiment_plan_sha256"],"HANDOFF_IDENTITY")
        need(e.get("handoff_sha256")==digest({k:v for k,v in e.items()
                                              if k!="handoff_sha256"}),"HANDOFF_SHA_DRIFT")
        need(e.get("proof_scope")=="RESEARCH_ONLY_HOST_VERIFIER_NOT_TRUST_ROOT",
             "HANDOFF_AUTHORITY_FORGED")
        slots=e.get("slots")
        need(type(slots) is list and len(slots)==2 and
             {s.get("arm") for s in slots if type(s) is dict}==set(ARMS),"TWO_ARM_HANDOFF")
        verified=callable(verify_handoff) and verify_handoff(e) is True
        for s in slots:
            need(s.get("pair_id")==pair and s.get("capture_status") in STATES,"INVALID_ARM_SLOT")
            status=s["capture_status"]
            if status=="RECORDED" and not verified:status="UNVERIFIED"
            if status=="RECORDED":need(ishash(s.get("f1_record_sha256")),"F1_SHA_MISSING")
            out[pair,s["arm"]]=status
    return out,len(seen)

def monitor_states(windows,plans,asof,verify_monitor):
    out={}
    for w in windows:
        need(type(w) is dict,"MONITOR_FORMAT")
        pair=w.get("pair_id");h=w.get("horizon_hours")
        need(pair in plans and type(h) is int and h in HOURS,"ORPHAN_OR_BAD_HORIZON")
        need((pair,h) not in out,"DUPLICATE_MONITOR")
        plan=plans[pair];cutoff=plan["decision_cutoff_ms"];due=cutoff+h*3600000
        need(w.get("decision_cutoff_ms")==cutoff and w.get("window_start_ms")==cutoff
             and w.get("window_end_exclusive_ms")==due,"MONITOR_CUTOFF")
        need(all(w.get(k)==plan[k] for k in PINS),"MONITOR_PIN_DRIFT")
        need(timestamp(w.get("available_at_ms")) and due<=w["available_at_ms"]<=asof
             and asof>=due,"MONITOR_EARLY_OR_FUTURE")
        need(ishash(w.get("source_artifact_sha256")) and text(w.get("evidence_ref")),
             "MONITOR_PROOF_MISSING")
        coverage=w.get("coverage_status")
        need(coverage in ("COMPLETE","CENSORED","UNKNOWN"),"MONITOR_STATUS")
        observed=w.get("observed_bars")
        need(type(observed) is int and 0<=observed<=h*4 and
             w.get("expected_bars")==h*4,"MONITOR_GRID")
        end=w.get("source_end_exclusive_ms")
        if coverage=="COMPLETE":
            need(observed==h*4 and timestamp(end) and end>=due,"FALSE_COMPLETE")
        elif coverage=="CENSORED":
            need(observed<h*4 and timestamp(end) and cutoff<=end<due,"FALSE_CENSORED")
        else:
            need(w.get("missing_reason") in ("GAP","CORRUPTION","SOURCE_UNAVAILABLE"),
                 "UNKNOWN_REASON")
        out[pair,h]=(coverage if callable(verify_monitor) and verify_monitor(w) is True
                     else "UNKNOWN")
    return out

def project_r3(schedule,handoffs=(),monitor_windows=(),research_evaluations=(),*,
               asof_ms,expected_schedule_sha256=None,verify_handoff=None,verify_monitor=None):
    need(timestamp(asof_ms),"ASOF")
    plans=schedules(schedule,expected_schedule_sha256)
    probes=[research(x) for x in research_evaluations]
    slots,received=host_slots(handoffs,plans,verify_handoff)
    windows=monitor_states(monitor_windows,plans,asof_ms,verify_monitor)
    ledger=[];outcomes=[]
    for pair,plan in plans.items():
        cutoff=plan["decision_cutoff_ms"];arms=[]
        for arm in ARMS:
            capture=slots.get((pair,arm),"MISSING_CAPTURE")
            arms.append({"arm":arm,"capture_status":capture})
            for h in HOURS:
                due=cutoff+h*3600000
                status=("PENDING" if asof_ms<due else
                        "NOT_CONNECTED" if not callable(verify_monitor) else
                        windows.get((pair,h),"UNKNOWN"))
                outcomes.append({"pair_id":pair,
                                 "opportunity_id":plan["c2_identity"]["opportunity_id"],
                                 "arm":arm,"horizon_hours":h,"window_end_exclusive_ms":due,
                                 "capture_status":capture,"monitor_status":status,
                                 "measurement_class":"MARKET_ONLY_NOT_EVALUATED",
                                 "directional_mfe_mae":None,"tp_sl":None,
                                 "fills_pnl":None,"paired_uplift":None})
        ledger.append({"pair_id":pair,"c2_identity":plan["c2_identity"],
                       "decision_cutoff_ms":cutoff,"scheduled_at_ms":plan["scheduled_at_ms"],
                       "pins":{k:plan[k] for k in PINS},"arms":arms})
    need(len(outcomes)==6*len(plans),"DENOMINATOR_LOSS")
    report={"schema_version":"aql.r3-factory-nontrading-event-outcome.v1",
            "scope":"SOFTWARE_PROJECTION_ONLY_NO_ORIGINAL_G2_RUNTIME_AUTHORITY",
            "scheduled_denominator_status":"SUPPLIED_UNVERIFIED" if plans else "NOT_SUPPLIED",
            "scheduled_opportunities":len(plans),"arm_slots":2*len(plans),
            "horizon_rows":6*len(plans),"core_host_handoffs":received,
            "original_g2_event_status":"BLOCKED_ON_REAL_G2_EVENT",
            "f3_monitor_status":("VERIFIER_PROVIDED_UNAUDITED" if callable(verify_monitor)
                                  else "NOT_CONNECTED"),
            "coverage_counts":dict(sorted(Counter(x["monitor_status"] for x in outcomes).items())),
            "core_research_evaluations_not_counted":probes,
            "opportunity_ledger":ledger,"outcomes":outcomes,
            "directional_evaluation_status":"NOT_EVALUABLE",
            "independent_issuer_clock_custody_freeze":"BLOCKED_EXTERNAL_EVIDENCE",
            "g0_merge_paper_shadow_live_authorized":False}
    report["report_sha256"]=digest(report)
    return report

def main():
    p=argparse.ArgumentParser()
    for k in ("schedule","handoffs","monitor","core-research"):p.add_argument("--"+k,type=Path,required=k=="schedule")
    p.add_argument("--asof-ms",type=int,required=True)
    p.add_argument("--schedule-sha256")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    read=lambda path:read_json(path.read_bytes()) if path else []
    result=project_r3(read(a.schedule),read(a.handoffs),read(a.monitor),read(a.core_research),
                      asof_ms=a.asof_ms,expected_schedule_sha256=a.schedule_sha256)
    data=jcs(result)+b"\n";a.out.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(a.out,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        need(os.write(fd,data)==len(data),"SHORT_WRITE");os.fsync(fd)
    finally:os.close(fd)
    need(a.out.read_bytes()==data,"READBACK")
    print("sha256="+hashlib.sha256(data).hexdigest())

if __name__=="__main__":main()
