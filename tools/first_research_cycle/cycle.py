"""First-cycle fail-closed input assessment and native research-plan commitment.

This gate never treats a structural input check as an executed research cycle.
Existing synthetic-only evaluators remain unmodified and are never relabeled.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from aql.models.bar import MarketBar
from research_wp_r0.frozen_research_plan import commit_research_plan, verify_research_plan


class Stop(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Stop(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items):
    result={}
    for key,value in items:
        need(key not in result,'DUPLICATE_JSON_KEY')
        result[key]=value
    return result


def read(path):
    path=Path(path).absolute()
    for parent in (path,*path.parents):
        need(not parent.is_symlink() and not (parent.exists() and getattr(parent.lstat(),'st_file_attributes',0)&0x400),'LINKED_INPUT')
    raw=path.read_bytes()
    need(len(raw)<=8_000_000,'INPUT_BOUND')
    try:
        return json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda _: (_ for _ in ()).throw(Stop('NONFINITE_JSON')))
    except (UnicodeError,json.JSONDecodeError):
        raise Stop('CORRUPT_JSON') from None


def validate_design(design):
    need(design['schema']=='aql.first-cycle.design.v1','DESIGN_VERSION')
    need(design['candidate_budget']==1 and design['max_bars']==8192 and design['seed']==294,'FROZEN_BUDGET')
    need(design['selection']=='NO_WINNER_NO_POST_HOLDOUT_TUNING' and design['embargo_ms']>=259200000,'LEAKY_DESIGN')
    need(design['holdout']=='SEALED_UNOPENED' and design['trading_authority']=='NONE','AUTHORITY')
    need(design['baseline']=='INDEPENDENT_PREDECLARED_NULL' and design['exit_policies']==['A','B','C'],'DESIGN_SCOPE')
    need(design['source_binding']=='PENDING_AUTHORIZED_NEW_ACTUAL_BUNDLE','UNPROVEN_SOURCE_BINDING')


def inspect_actual(root,anchor,design):
    """Read an explicitly supplied disposable export, never a running DB.

    Native MarketBar serialization/checksum is reused. Dossier is only a minimal
    consumer envelope, not a source-rights registry or external attestation.
    """
    root=Path(root)
    dossier=read(root/'source.json')
    need(sha(dossier)==anchor,'SOURCE_TRUST_ANCHOR')
    need(dossier['schema']=='aql.first-cycle.source-export.v1','SOURCE_VERSION')
    need(dossier['evidence_class']=='ACTUAL_MARKET','SYNTHETIC_SUBSTITUTION')
    accepted_reuse=design.get('accepted_period_reuse')=='OWNER_AUTHORIZED_NEW_HISTORICAL_CYCLE_NO_OLD_SUITE_RERUN'
    need(dossier['cohort'] not in ('MARCH_2024','APRIL_2024') or accepted_reuse,'ACCEPTED_COHORT_WITHOUT_OWNER_OVERRIDE')
    need(dossier['trading_authority']=='NONE' and dossier['actual_fills'] is None and dossier['ack'] is None,'FORBIDDEN_AUTHORITY')
    need(dossier['historical_pit']=='NOT_ATTESTED' and dossier['real_oos']=='NOT_ATTESTED','UNSUPPORTED_SCIENCE_PROMOTION')
    need(dossier['rights']['authorized_research_use'] is True and bool(dossier['rights']['reference']), 'MISSING_USE_RIGHTS')
    terms=(root/'terms.txt')
    # Apply the same path safety guard before reading non-JSON terms bytes.
    for p in (terms,*terms.absolute().parents):
        need(not p.is_symlink() and not (p.exists() and getattr(p.lstat(),'st_file_attributes',0)&0x400),'LINKED_INPUT')
    need(hashlib.sha256(terms.read_bytes()).hexdigest()==dossier['rights']['terms_sha256'],'RIGHTS_BYTES')
    rows=read(root/'bars.json')
    need(sha(rows)==dossier['bars_sha256'] and type(rows) is list and 0<len(rows)<=design['max_bars'],'BARS_IDENTITY_OR_BOUND')
    need(dossier['interval']=='15m' and dossier['step_ms']==900000 and dossier['market']=='SPOT','COHORT_SCOPE')
    first,last=dossier['first_open_ms'],dossier['last_open_ms']
    need(type(first) is int and type(last) is int and 0<=first<=last and (last-first)%900000==0,'COHORT_RANGE')
    need(not (first<1714521600000 and last>=1709251200000) or accepted_reuse,'ACCEPTED_MARCH_APRIL_NO_RERUN')
    count=(last-first)//900000+1
    need(0<count<=design['max_bars'] and dossier['expected_bars']==count==len(rows),'MISSING_POPULATION')
    expected=range(first,last+1,900000)
    need(dossier['plan_frozen_before_evaluation'] is True and
         dossier['prefreeze_ms']<dossier['evaluation_read_at_ms'],'PLAN_AFTER_EVALUATION')
    retrospective=dossier['first_outcome_available_ms']<=dossier['prefreeze_ms']
    need(dossier['train_end_ms']<dossier['validation_end_ms'] and
         dossier['validation_end_ms']+design['embargo_ms']<=dossier['holdout_start_ms']<dossier['holdout_end_ms'],'SPLIT_LEAKAGE')
    for row,opened in zip(rows,expected):
        bar=MarketBar.from_dict(row)
        need(bar.symbol==dossier['symbol'] and bar.interval=='15m' and bar.source==dossier['source_label'],'SOURCE_SWAP')
        need(type(bar.bar_open) is int and bar.bar_open==opened and opened%900000==0 and
             bar.bar_close==opened+899999 and bar.is_final is True,'GRID_DUPLICATE_OR_PROVISIONAL')
        need(type(bar.ingested_at) is int and bar.bar_close<bar.ingested_at<=dossier['as_of_ms'],'FUTURE_SOURCE')
        need(bar.checksum==bar.compute_checksum(),'BAR_TAMPER')
        need(all(type(v) in (int,float) and math.isfinite(v) for v in (bar.open,bar.high,bar.low,bar.close,bar.volume)) and
             0<bar.low<=min(bar.open,bar.close)<=max(bar.open,bar.close)<=bar.high and bar.volume>=0,'BAD_PRICE')
    raw,plan_sha=commit_research_plan('FIRST_CYCLE_294',[(design['candidate_id'],design['strategy_sha256'])],
        protocol_digest=sha(design),dataset_digest=sha(dossier),split_digest=sha({k:dossier[k] for k in
        ('train_end_ms','validation_end_ms','holdout_start_ms','holdout_end_ms')}),
        baseline_digest=design['baseline_sha256'],metrics=design['metrics'],
        selection_rule={'rule':design['selection']},cost_model={'source':design['cost_contract'],'authority':'ASSUMPTIONS_ONLY'})
    verify_research_plan(raw,plan_sha)
    return dict(status='STRUCTURAL_CHECK_ONLY_NOT_AUTHENTICATED',bars=len(rows),source_sha256=sha(dossier),
        native_research_plan_sha256=plan_sha,rights_grade='OWNER_SUPPLIED_REFERENCE_NOT_LEGAL_CERTIFICATION',
        prefreeze_after_historical_data=retrospective,first_known_at='NOT_ATTESTED',custody='NOT_INDEPENDENTLY_ATTESTED')


def assess(design,*,source=None,anchor=None):
    validate_design(design)
    expected=Path(__file__).with_name('design.sha256').read_text().strip()
    need(sha(design)==expected,'FROZEN_DESIGN_PIN')
    detail=None
    if source is not None:
        need(anchor is not None,'RETAINED_SOURCE_DIGEST_REQUIRED')
        detail=inspect_actual(source,anchor,design)
    missing='AUTHORIZED_NEW_ACTUAL_MARKET_BUNDLE' if detail is None else 'ACTUAL_MARKET_RUNTIME_ADAPTER_NOT_YET_PROVED'
    gates={
        'F0':dict(status='PARTIAL_DESIGN_FROZEN_SOURCE_BINDING_PENDING',proof=sha(design)),
        'F1':dict(status='BLOCKED_INPUT' if detail is None else 'STRUCTURE_ONLY',proof=detail),
        'F2':dict(status='NOT_RUN',reason='NO_ACTUAL_COHORT_BOUND_ATTEMPT_LEDGER'),
        'F3':dict(status='NOT_RUN',reason='PINNED_EXECUTION_MODEL_IS_SYNTHETIC_ONLY'),
        'F4':dict(status='NOT_RUN',reason='NO_ACTUAL_PAIRED_RESULTS'),
        'F5':dict(status='BLOCKED',reason=missing)}
    body=dict(schema='aql.first-cycle.readiness.v1',status='BLOCKED_EXACT_DATA_RUNTIME_DEPENDENCY',
        blocker=missing,design_sha256=sha(design),gates=gates,source=detail,
        real_science_status='REAL_PIT_OOS_BLOCKED',actual_market_cycle_executed=False,
        populations=dict(scanner_slots=None,discoverer_attempts=None,factory_trials=None,h_variants=None,cost_model_rows=None),
        gross_net_exit_comparison='NOT_RUN_ON_ACTUAL_MARKET',trading_authority='NONE',actual_fills=None,
        accepted_work_rerun=False,package2_files_changed=False)
    return dict(body,sha256=sha(body))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--design',type=Path,default=Path(__file__).with_name('design.json'))
    p.add_argument('--source',type=Path)
    p.add_argument('--source-sha256')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        need(not args.output.exists() and not args.output.is_symlink(),'OUTPUT_EXISTS')
        if args.source is not None:
            need(args.source.resolve() not in args.output.resolve().parents,'OUTPUT_IN_SOURCE')
        report=assess(read(args.design),source=args.source,anchor=args.source_sha256)
        with args.output.open('xb') as stream:
            stream.write(canonical(report)+b'\n');stream.flush()
        print(json.dumps({'status':report['status'],'sha256':report['sha256']}))
    except (Stop,KeyError,TypeError,ValueError,OSError) as error:
        print(json.dumps({'status':'FAIL_MATERIAL_GATE','code':str(error) if isinstance(error,Stop) else 'INVALID_OR_MISSING_INPUT'}))
        raise SystemExit(2) from None


if __name__=='__main__':main()
