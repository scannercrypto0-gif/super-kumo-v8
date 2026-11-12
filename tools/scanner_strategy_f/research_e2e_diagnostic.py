"""Scanner F3 local RESEARCH_E2E_DIAGNOSTIC — NOT signed historical F5.

Read the existing immutable Core #253 warehouse and replay its original-bar
SHA, then reuse existing Factory indicator kernels/StrategyDefinition AST.
There is NO independent source rights, PIT, policy signature, Secretary ACK,
strategy SELECTED, Factory Consumer ACK, Paper or trading authority here.

WARNING: caller-provided Core receipt alone is not trusted provenance. This
diagnostic is separately authorized by PM provisional B and private custody
remains explicitly operator-reported, NOT independently authenticated.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from hashlib import sha256
import inspect
import math
from pathlib import Path

from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_factory_historical_rule_projection import _vectors,_expression
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from tools.strategy_service_offline.common import Frozen,require
from tools.scanner_strategy_f.retrospective_policy import verify_retrospective_policy_draft

SCHEMA="aql.scanner-f.research-e2e-local-diagnostic.v1"
ATTEMPT="aql.scanner-f.research-e2e-local-diagnostic-attempt.v1"
STEP=900_000
ADMITTED=tuple(f"2024-{i:02d}" for i in range(1,13) if i not in (2,8))
RETAINED=("2024-02","2024-08")
SAFE_COHORT_PHASES=frozenset((
    "COHORT_POLICY_VERIFY","COHORT_SCOPE_VERIFY","COHORT_AST_RECONSTRUCT",
    "COHORT_CODE_FINGERPRINT","COHORT_CORE253_REPLAY",
    "COHORT_MONTH_GRID_VERIFY","COHORT_FACTORY_KERNEL",
    "COHORT_ATTEMPT_RECEIPTS","COHORT_RETAINED_UNKNOWN",
    "COHORT_FINAL_RECEIPT",
))

def _phase(callback, name):
    require(name in SAFE_COHORT_PHASES,"F_DIAGNOSTIC_INVALID_PHASE")
    if callback is not None:
        callback(name)



def _month_ms(month):
    year,number=map(int,month.split("-"))
    begin=int(datetime(year,number,1,tzinfo=timezone.utc).timestamp()*1000)
    finish=begin+monthrange(year,number)[1]*86_400_000
    return begin,finish


def _code_sha():
    # SHA of the Python code controlling the diagnostic's actual evaluator
    # and the reused canonical kernel, not a caller-supplied code string.
    here=Path(__file__).read_bytes()
    import research_wp_r0.aql_factory_historical_rule_projection as kernel
    real=Path(inspect.getfile(kernel)).read_bytes()
    return sha256(here+b"\n--existing-ast-kernel--\n"+real).hexdigest()


def _eval_strategy(definition,bars):
    """Confirmed-close AST only, no lookahead, no selection/profit scoring."""
    def indicator_input(value):
        # Core's monitor view preserves decimal text; indicator kernels use numbers.
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError as exc:
                raise ValueError("SCANNER_INDICATOR_INPUT") from exc
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("SCANNER_INDICATOR_INPUT")
        return value

    shaped=[
        {"open_ms":x["bar_open_ms"],"close_ms":x["bar_close_ms"],
         **{key:indicator_input(x[key]) for key in ("open","high","low","close","volume")},
         "known_at_ms":None,
         "quality":"FINAL"} for x in bars
    ]
    values=_vectors(definition,shaped)
    status="UNKNOWN"
    result=[]
    for i,row in enumerate(shaped):
        entry=_expression(definition.spec["entry"],i,values)
        exit_=_expression(definition.spec["exit"],i,values)
        state=("UNKNOWN" if entry is None or exit_ is None
               else "ENTRY_SIGNAL" if entry is True
               else "EXIT_SIGNAL" if exit_ is True
               else "NO_SIGNAL")
        result.append([row["close_ms"],state])
    return result


def diagnostic_original_cohort(
    *, warehouse_root,month_queries,policy_draft,proposal,
    approval_request,work_specs,phase_callback=None,
):
    """Complete 2 × 12 strategy/month census from read-only original Core DB.

    month_queries is an operator-owned map with exactly 10 existing original
    immutable #253 query receipt objects. The local operator must independently
    pin/inspect these against Core F2; SHA-only inputs do NOT prove issuer rights.
    No new ZIP acquisition, RAW/warehouse write or synthetic OHLCV is performed.
    """
    require(phase_callback is None or callable(phase_callback),
            "F_DIAGNOSTIC_INVALID_PHASE_CALLBACK")
    _phase(phase_callback,"COHORT_POLICY_VERIFY")
    frozen=verify_retrospective_policy_draft(
        policy_draft,proposal,approval_request,work_specs)
    p=frozen.data
    # Every failure has a single fixed, privacy-safe reason. WindowsPath is a
    # concrete subclass of Path on the actual Windows owner operator; exact
    # type() comparison to Path wrongly rejects it after Core validation.
    _phase(phase_callback,"COHORT_SCOPE_VERIFY")
    require(p["target_months"]==[f"2024-{i:02d}" for i in range(1,13)],
            "F_DIAGNOSTIC_SCOPE_TARGET_MONTHS")
    require(type(p["strategy_identity"]) is list
            and len(p["strategy_identity"])==2,
            "F_DIAGNOSTIC_SCOPE_TWO_STRATEGIES")
    require(type(month_queries) is dict
            and set(month_queries)==set(ADMITTED),
            "F_DIAGNOSTIC_SCOPE_TEN_MONTH_QUERIES")
    require(type(warehouse_root) is str or isinstance(warehouse_root,Path),
            "F_DIAGNOSTIC_SCOPE_WAREHOUSE_PATH")
    identities={(x["strategy_id"],x["strategy_version"]):x
                for x in p["strategy_identity"]}
    _phase(phase_callback,"COHORT_AST_RECONSTRUCT")
    specs={}
    for raw in work_specs:
        s=Frozen.restore(raw).data
        key=(s["strategy_id"],s["strategy_version"])
        require(key in identities and key not in specs
                and s["definition"]["digest"]==identities[key]["definition_digest"]
                and s["dna"]["digest"]==identities[key]["dna_digest"]
                and s["config_digest"]==identities[key]["work235_config_digest"],
                "F_DIAGNOSTIC_FROZEN_STRATEGY_PARENT")
        definition=StrategyDefinition.from_dict(
            s["definition"],registry=IndicatorRegistryV2())
        require(definition.digest==identities[key]["definition_digest"],
                "F_DIAGNOSTIC_ORIGINAL_DEFINITION_DRIFT")
        specs[key]=definition
    require(len(specs)==2,"F_DIAGNOSTIC_TWO_FROZEN_STRATEGIES")
    _phase(phase_callback,"COHORT_CODE_FINGERPRINT")
    code_sha=_code_sha()
    trials=[]
    total_bars=0
    queried={}
    for month in ADMITTED:
        q=month_queries[month]
        require(type(q) is dict
                and q.get("schema")=="aql.core.local-history-query.v1"
                and type(q.get("source_bytes_sha256")) is str
                and len(q["source_bytes_sha256"])==64
                and q.get("historical_pit")=="NOT_ATTESTED"
                and q.get("coverage")=="COMPLETE"
                and type(q.get("query_sha256")) is str
                and len(q["query_sha256"])==64,
                "F_DIAGNOSTIC_CORE_QUERY_SCOPE")
        start,end=_month_ms(month)
        require(q.get("start_ms")==start
                and q.get("end_exclusive_ms")==end
                and q.get("decision_cutoff_ms")>=end
                and q.get("available_bar_count")==monthrange(2024,int(month[-2:]))[1]*96
                and q.get("source_availability")=="RETROSPECTIVE_NON_PIT",
                "F_DIAGNOSTIC_MONTH_GRID_OR_CUTOFF")
        _phase(phase_callback,"COHORT_CORE253_REPLAY")
        actual=query_local(warehouse_root,q["dataset_id"],q["version"],
            start,end,q["decision_cutoff_ms"],
            required_source_sha256=q["source_bytes_sha256"],
            require_complete=True,sqlite_immutable=True)
        require(actual==q,"F_DIAGNOSTIC_REAL_CORE253_READBACK_MISMATCH")
        _phase(phase_callback,"COHORT_MONTH_GRID_VERIFY")
        bars=q["bars"]
        require(type(bars) is list and
                len(bars)==monthrange(2024,int(month[-2:]))[1]*96
                and all(
                    type(x["bar_open_ms"]) is int
                    and x["bar_open_ms"]==start+i*STEP
                    and x["bar_close_ms"]==x["bar_open_ms"]+STEP-1
                    and x["bar_close_ms"]<q["decision_cutoff_ms"]
                    and x["historical_known_at_ms"] is None
                    for i,x in enumerate(bars)),
                "F_DIAGNOSTIC_NO_MISSING_OR_FUTURE_BAR")
        total_bars+=len(bars)
        queried[month]=q["query_sha256"]
        for raw in p["strategy_identity"]:
            key=(raw["strategy_id"],raw["strategy_version"])
            _phase(phase_callback,"COHORT_FACTORY_KERNEL")
            signals=_eval_strategy(specs[key],bars)
            counts={v:sum(item[1]==v for item in signals) for v in
                    ("ENTRY_SIGNAL","EXIT_SIGNAL","NO_SIGNAL","UNKNOWN")}
            require(sum(counts.values())==len(bars),
                    "F_DIAGNOSTIC_INDICATOR_CENSUS")
            _phase(phase_callback,"COHORT_ATTEMPT_RECEIPTS")
            trials.append(Frozen.build({
                "schema":ATTEMPT,
                "month":month,"strategy_id":key[0],
                "strategy_version":key[1],
                "definition_digest":raw["definition_digest"],
                "dna_digest":raw["dna_digest"],
                "work235_config_digest":raw["work235_config_digest"],
                "native15m_config_digest":raw["scanner_native15m_config_digest"],
                "original_core253_query_sha256":q["query_sha256"],
                "original_source_sha256":q["source_bytes_sha256"],
                "evaluator_code_sha256":code_sha,
                "closed_bar_cutoff_ms":q["decision_cutoff_ms"],
                "last_closed_bar_open_ms":bars[-1]["bar_open_ms"],
                "signal_counts":counts,
                "signal_trace_sha256":Frozen.build(signals).sha256,
                "status":"DIAGNOSTIC_EVALUATED_NOT_SELECTED",
                "authority":"LOCAL_DIAGNOSTIC_ONLY",
                "historical_pit":"NOT_ATTESTED",
                "strategy_approval_sha256":None,
                "trading_authority":"NONE",
            }).receipt())
    require(total_bars==29376 and len(trials)==20,
            "F_DIAGNOSTIC_TOTAL_10_MONTH_BAR_CENSUS")
    _phase(phase_callback,"COHORT_RETAINED_UNKNOWN")
    for month in RETAINED:
        for x in p["strategy_identity"]:
            trials.append(Frozen.build({
                "schema":ATTEMPT,"month":month,
                "strategy_id":x["strategy_id"],
                "strategy_version":x["strategy_version"],
                "definition_digest":x["definition_digest"],
                "dna_digest":x["dna_digest"],
                "work235_config_digest":x["work235_config_digest"],
                "native15m_config_digest":x["scanner_native15m_config_digest"],
                "original_core253_query_sha256":None,
                "original_source_sha256":None,
                "evaluator_code_sha256":code_sha,
                "closed_bar_cutoff_ms":None,
                "last_closed_bar_open_ms":None,
                "signal_counts":None,
                "signal_trace_sha256":None,
                "status":"UNKNOWN_RETAINED_NOT_READBACK",
                "authority":"LOCAL_DIAGNOSTIC_ONLY",
                "historical_pit":"NOT_ATTESTED",
                "strategy_approval_sha256":None,
                "trading_authority":"NONE",
            }).receipt())
    require(len(trials)==24,"F_DIAGNOSTIC_ALL_ATTEMPTS_REQUIRED")
    _phase(phase_callback,"COHORT_FINAL_RECEIPT")
    return Frozen.build({
        "schema":SCHEMA,
        "execution_lane":"RESEARCH_E2E_DIAGNOSTIC",
        "trust_class":"LOCAL_OPERATOR_ONLY_NOT_INDEPENDENT",
        "policy_draft_sha256":frozen.sha256,
        "evaluator_code_sha256":code_sha,
        "source":"EXISTING_CORE_253_READONLY_REPLAY",
        "source_months":list(ADMITTED),
        "source_query_shas":queried,
        "native15m_month_bars":total_bars,
        "strategies":2,
        "total_attempts":24,
        "diagnostic_evaluated_attempts":20,
        "unknown_feb_aug_attempts":4,
        "attempts":trials,
        "signed_f5_approval":"NOT_GRANTED",
        "independent_policy_verified":False,
        "independent_source_verified":False,
        "independent_evaluator_verified":False,
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "selected":0,
        "secretary_state":"NOT_ENQUEUED",
        "factory_lab":"NOT_EVALUATED",
        "historical_pit":"NOT_ATTESTED",
        "holdout":"SEALED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
        "decision":"DIAGNOSTIC_ONLY_NOT_F5",
    }).receipt()
