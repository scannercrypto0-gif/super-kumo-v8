"""Bounded actual-retained-market adapter; no acquisition, source writes or orders.

Reuses pinned DiscovererLedger, StrategyDefinition/indicator/rule kernels,
Factory immutable experiment/package store and PKG02 Decimal exit/cost kernels.
The synthetic-only high-level PKG02 packet API is never called or relabeled.
Its lower-level modeled execution assumptions remain explicitly hypothetical.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def need(ok,code):
    if not ok:raise ValueError(code)


def persist(path,value):
    raw=canonical(value)+b'\n'
    if path.exists():
        need(path.read_bytes()==raw,'IMMUTABLE_OUTPUT_CONFLICT');return
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


def checkpoint(path,value):
    # Only caller-owned new run state, never upstream. Atomic complete JSON.
    temp=path.with_suffix('.tmp')
    with temp.open('wb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def load_archives(source,plan):
    bars=[];proof=[]
    for item in plan['archives']:
        p=source/item['name'];need(not p.is_symlink(),'LINKED_ARCHIVE')
        raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        need(digest==item['sha256'],'SOURCE_SHA_SWAP')
        checksum=(source/(item['name']+'.CHECKSUM')).read_text().split()
        need(checksum==[digest,item['name']],'CHECKSUM_PARENT')
        z=zipfile.ZipFile(io.BytesIO(raw));expected=item['name'][:-4]+'.csv'
        need(z.namelist()==[expected] and z.getinfo(expected).file_size<8_000_000,'ZIP_MEMBER')
        rows=list(csv.reader(io.StringIO(z.read(expected).decode('utf-8'))))
        need(len(rows)==item['rows'],'ARCHIVE_POPULATION')
        for r in rows:
            need(len(r)==12,'NATIVE_KLINE_FIELDS')
            b=dict(open_ms=int(r[0]),close_ms=int(r[6]),open=float(r[1]),high=float(r[2]),
                   low=float(r[3]),close=float(r[4]),volume=float(r[5]))
            need(b['open_ms']%900000==0 and b['close_ms']==b['open_ms']+899999,'PROVISIONAL_OR_GRID')
            need(0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'] and b['volume']>=0,'OHLC')
            # canonical rejects NaN/Infinity before accepting a source row.
            b['source_row_sha256']=sha(b);bars.append(b)
        proof.append(dict(name=item['name'],sha256=digest,rows=len(rows),checksum='MATCH_RETAINED_NOT_EXTERNAL_WITNESS'))
    need(len(bars)==plan['expected_bars']<=8192,'JOINED_SOURCE_POPULATION')
    need([b['open_ms'] for b in bars]==list(range(plan['first_open_ms'],plan['end_exclusive_ms'],900000)),
         'MISSING_DUPLICATE_REORDERED_SOURCE')
    return bars,proof


def configure(deps,plan):
    roots=[deps/'factory',deps/'scanner',deps/'discoverer',deps/'work235',deps/'scanner_b']
    for item in plan['dependency_files']:
        p=deps/item['path']
        need(hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],'DEPENDENCY_SOURCE_SWAP')
    # Exact archive snapshots in caller-owned dirs; no upstream copying/modifying.
    sys.path[:0]=[str(p) for p in roots]+[str(Path(__file__).resolve().parents[2])]
    import research_wp_r0
    research_wp_r0.__path__.append(str(deps/'core/research_wp_r0'))
    research_wp_r0.__path__.append(str(deps/'work235/research_wp_r0'))


def run(source,deps,output,plan,*,crash=False):
    need(plan['schema']=='aql.first-cycle.market-plan.v1' and plan['trading_authority']=='NONE','PLAN_AUTHORITY')
    need(plan['source_class'] in ('RETAINED_ACTUAL_MARKET_RETROSPECTIVE_NON_PIT','SIMULATED_ADAPTER_TEST') and
         plan['real_pit']=='NOT_ATTESTED' and plan['holdout']=='SEALED_UNOPENED','FALSE_PIT_OOS')
    need(plan['freeze_purpose']=='BEFORE_THIS_CYCLE_OUTCOME_READ_NOT_CONTEMPORANEOUS_2024','FALSE_FREEZE')
    need(plan['first_open_ms']<plan['train_end_ms']<plan['validation_end_ms'] and
         plan['validation_end_ms']+259200000<=plan['holdout_start_ms']<plan['end_exclusive_ms'],'SPLIT_LOOKAHEAD')
    need(plan['candidate_budget']==1 and plan['winner'] is None and
         plan['null']['method']=='FIXED_PERIODIC_PREDECLARED_INDEPENDENT_OF_RULE_AND_OUTCOMES','ADAPTIVE_SELECTION')
    need(plan.get('actual_fills') is None and plan.get('ack') is None and plan.get('claimed_pnl') is None,'FALSE_FILL_PNL_ACK')
    configure(deps,plan)
    from research_wp_r0.strategy_definition import StrategyDefinition
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
    from research_wp_r0.aql_factory_historical_rule_projection import _vectors,_expression,_costs
    from research_wp_r0.aql_factory_h_execution_comparison_v1 import _path,_summarize
    from research_wp_r0.aql_factory_e_research_results_store_v1 import build_experiment,register_experiment,read_experiment,migrate_store_v2
    from research_wp_r0.aql_factory_h_research_package_v1 import _store_package
    from tools.strategy_discoverer_offline.ledger import DiscovererLedger,AttemptState
    from tools.strategy_discoverer_offline.contracts import DiscoveryCandidatePackageV1
    from research_wp_r0.frozen_research_plan import commit_research_plan,verify_research_plan
    from tools.scanner_strategy_f.research_e2e_diagnostic import _eval_strategy
    need(source.resolve()!=output.resolve() and source.resolve() not in output.resolve().parents and
         output.resolve() not in source.resolve().parents,'SOURCE_OUTPUT_COLLISION')
    need(not output.exists() or (output/'market-plan.json').is_file(),'UNRELATED_OUTPUT_DIRECTORY')
    output.mkdir(parents=True,exist_ok=True)
    persist(output/'market-plan.json',plan)
    bars,source_proof=load_archives(source,plan)
    definition=StrategyDefinition.from_dict(plan['strategy'],registry=IndicatorRegistryV2())
    evalbars=[b for b in bars if b['open_ms']<plan['validation_end_ms']]
    need(evalbars and len(evalbars)<len(bars),'SEALED_HOLDOUT_REQUIRED')
    raw,plan_sha=commit_research_plan('FIRST_CYCLE_294',[('sma3_8',definition.digest)],protocol_digest=sha(plan),
        dataset_digest=sha(source_proof),split_digest=sha(plan['splits']),baseline_digest=sha(plan['null']),
        metrics=['gross','net','unknown','nonfill','drawdown'],selection_rule={'rule':'NO_WINNER_ALL_VARIANTS'},cost_model=plan['costs'])
    verify_research_plan(raw,plan_sha)
    persist(output/'native-plan.json',json.loads(raw))
    ledger_path=output/'discoverer-ledger.json'
    ledger=DiscovererLedger.from_dict_list(json.loads(ledger_path.read_text())) if ledger_path.exists() else DiscovererLedger()
    need(not (output/'factory.sqlite').exists() or bool(ledger.entries()),'CORRUPT_OR_MISSING_LEDGER')
    if not ledger.entries():
        ledger.register('attempt294','sma3_8','FIRST_CYCLE',definition.digest,plan_sha,sha(source_proof),'ONE_PREDECLARED_HYPOTHESIS')
        ledger.transition('attempt294',AttemptState.PENDING,'REGISTERED_BEFORE_EVALUATION')
        checkpoint(ledger_path,ledger.to_dict_list())
    need(ledger.verify_chain(),'DISCOVERER_CHAIN')
    package=DiscoveryCandidatePackageV1.build(schema_version='aql.discoverer.candidate.v1',candidate_id='sma3_8',
        family_id='FIRST_CYCLE',family_version='1',strategy_definition_digest=definition.digest,strategy_spec=definition.to_dict(),
        nomination_evidence_digest=sha(source_proof),source_manifest_sha256=sha(source_proof),
        rule_grammar_version='aql.strategy-definition.grammar.v1',search_plan_digest=plan_sha,
        counterhypothesis_id='fixed_periodic_null',attempt_ledger_head=ledger.entries()[1].entry_digest,status='PROPOSED_RESEARCH_ONLY')
    persist(output/'candidate.json',package.to_dict())
    values=_vectors(definition,evalbars)
    native_signals=_eval_strategy(definition,[{**b,'bar_open_ms':b['open_ms'],'bar_close_ms':b['close_ms']} for b in evalbars])
    # Actual prefix replay: indicator values at a past slot must not use later bars.
    prefix=evalbars[:64];prefix_values=_vectors(definition,prefix)
    need(all(prefix_values[k]=={i:v for i,v in values[k].items() if i<64} for k in values),'FEATURE_LOOKAHEAD')
    decisions=[];entries=[];null_entries=[];counts=Counter()
    for i,b in enumerate(bars):
        state='SEALED_HOLDOUT' if b['open_ms']>=plan['holdout_start_ms'] else 'EMBARGO'
        features=None
        if b['open_ms']<plan['validation_end_ms']:
            result=_expression(definition.spec['entry'],i,values)
            state=native_signals[i][1]
            need((state=='ENTRY_SIGNAL')==(result is True),'SCANNER_KERNEL_DISAGREEMENT')
            features=sha({name:vector.get(i) for name,vector in values.items()})
            if i+1<len(evalbars):
                entry=dict(entry_id='entry'+str(i),attempt_id='attempt294',entry_ms=evalbars[i+1]['open_ms'],
                    partition=('TRAIN' if b['open_ms']<plan['train_end_ms'] else 'VALIDATION'),
                    entry_price=str(evalbars[i+1]['open']),maker_state='UNKNOWN',maker_fill_fraction=None,
                    bars=[{**x,**{k:str(x[k]) for k in ('open','high','low','close')}}
                          for x in evalbars[i+1:min(i+1+plan['holding_bars'],len(evalbars))]])
                if state=='ENTRY_SIGNAL':entries.append(entry)
                if i%plan['null']['period']==plan['null']['offset']:
                    null_entries.append({**entry,'entry_id':'null'+str(i)})
        counts[state]+=1
        decisions.append(dict(source_row_sha256=b['source_row_sha256'],open_ms=b['open_ms'],state=state,
            features_sha256=features,decision_cutoff_ms=b['close_ms']+1,known_at_ms=None,
            availability='RETROSPECTIVE_NON_PIT',strategy_sha256=definition.digest))
    need(sum(counts.values())==len(bars),'CENSUS_CONSERVATION')
    outcomes=[];summaries={}
    with localcontext() as context:
        context.prec=40
        for cohort,population in (('CANDIDATE',entries),('PAIRED_NULL',null_entries)):
            for scenario,cost in plan['costs'].items():
                fees=_costs({'market':'SPOT','costs':cost})
                for policy in ('A','B','C'):
                    subset=[{**_path(e,scenario,fees,policy,Decimal(plan['risk']),
                                [Decimal(v) for v in plan['target_rs']],[Decimal(v) for v in plan['allocation']],
                                'STOP_MARKET'),'cohort':cohort,'partition':e['partition'],'market_source_class':plan['source_class']} for e in population]
                    # Cost-once and fraction conservation independent readback.
                    for row in subset:
                        if row['status']=='MODEL_ONLY':
                            fraction=sum(Decimal(x['fraction_of_initial_notional']) for x in row['legs'])
                            need(fraction==1 and Decimal(row['gross_return'])-Decimal(row['net_return'])==Decimal(row['total_cost_bps'])/10000,
                                 'CASH_OR_DOUBLE_COST')
                    def summary(rows):
                        base=_summarize(rows) if rows else dict(attempted_entry_count=0,
                            comparison_status='NO_ENTRIES_NO_PERFORMANCE_CLAIM',gross_return_sum=None,net_return_sum=None)
                        known=[r for r in rows if r['status']=='MODEL_ONLY']
                        # A labeled diagnostic, never a favorable-subset aggregate verdict.
                        return {**base,'known_subset_only_count':len(known),
                            'known_subset_gross_diagnostic_sum':str(sum((Decimal(r['gross_return']) for r in known),Decimal(0))),
                            'known_subset_net_diagnostic_sum':str(sum((Decimal(r['net_return']) for r in known),Decimal(0))),
                            'known_subset_warning':'EXCLUDES_UNKNOWN_NOT_A_FULL_POPULATION_RETURN_OR_ALPHA'}
                    outcomes.extend(subset);summaries[cohort+':'+scenario+':'+policy]=summary(subset)
                    for part in ('TRAIN','VALIDATION'):
                        summaries[part+':'+cohort+':'+scenario+':'+policy]=summary([r for r in subset if r['partition']==part])
    expected=(len(entries)+len(null_entries))*9
    need(len(outcomes)==expected,'VARIANT_POPULATION')
    experiment=build_experiment(experiment_id='FIRST-CYCLE-294',lane='SCANNER',
        source_status='RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT',source_sha256=sha(source_proof),
        source_query_245_sha256=sha({'query':'native_zip_grid','source':source_proof}),
        source_query_253_sha256=sha({'query':'causal_eval_prefix','count':len(evalbars),'source':source_proof}),
        strategy_definition_sha256=definition.digest,config_sha256=sha(plan['strategy']),code_sha256=sha(plan['dependency_files']),
        environment_sha256=sha({'runtime':'Python>=3.11','decimal_precision':40}),parent_receipt_sha256=package.package_digest,
        attempts=[dict(attempt_id='attempt294',candidate_id='sma3_8',state='NOT_VERIFIED',source_receipt_sha256=package.package_digest)],
        evidence_class='RETROSPECTIVE_NON_PIT')
    store=output/'factory.sqlite';register_experiment(store,experiment);migrate_store_v2(store)
    need(read_experiment(store,'FIRST-CYCLE-294')==experiment,'FACTORY_READBACK')
    package_body=dict(schema='aql.first-cycle.actual-market-evaluation.v1',experiment_id='FIRST-CYCLE-294',
        source_sha256=sha(source_proof),native_plan_sha256=plan_sha,candidate_package_sha256=package.package_digest,
        factory_experiment_sha256=experiment['sha256'],decision_census_sha256=sha(decisions),outcomes=outcomes,
        source_class=plan['source_class'],actual_fills=None,trading_authority='NONE')
    result_sha,_=_store_package(store,package_body)
    if crash:os._exit(73) # committed native Factory result, before caller ACK/ledger completion
    if ledger.summary()['by_state']['COMPLETE']==0:
        ledger.transition('attempt294',AttemptState.COMPLETE,'ALL_PREDECLARED_MODEL_VARIANTS_RETAINED')
        checkpoint(ledger_path,ledger.to_dict_list())
    need(DiscovererLedger.from_dict_list(json.loads(ledger_path.read_text())).verify_chain(),'LEDGER_RESTART')
    need(load_archives(source,plan)[1]==source_proof,'SOURCE_CHANGED_AFTER_EXECUTION')
    body=dict(schema='aql.first-cycle.actual-market-result.v1',status=('PASS_FIRST_RESEARCH_ENGINEERING_CYCLE' if
        plan['source_class']=='RETAINED_ACTUAL_MARKET_RETROSPECTIVE_NON_PIT' else 'PASS_ADAPTER_SIMULATION_ONLY'),
        science='REAL_PIT_OOS_BLOCKED',source_class=plan['source_class'],source=source_proof,plan_sha256=sha(plan),
        native_plan_sha256=plan_sha,candidate_package_sha256=package.package_digest,factory_experiment_sha256=experiment['sha256'],
        result_store_sha256=result_sha,discoverer=ledger.summary(),populations=dict(source_bars=len(bars),
        scanner_slots=len(decisions),scanner_census=dict(counts),discoverer_attempts=1,factory_trials=1,
        policy_scenario_cells=18,candidate_entries=len(entries),null_entries=len(null_entries),cost_rows=expected),
        decision_census_sha256=sha(decisions),outcome_status_counts=dict(Counter(r['status'] for r in outcomes)),
        scanner_evaluator='tools.scanner_strategy_f.research_e2e_diagnostic._eval_strategy',
        comparisons=summaries,holdout='SEALED_UNOPENED',winner=None,actual_fills=None,trading_authority='NONE',
        limits=['Retrospective availability unknown, no real PIT/OOS','OHLC passive fills UNKNOWN; no queue or partial-fill evidence',
                'Execution assumptions remain synthetic/hypothetical on actual prices; no venue fills',
                'Independent per-entry returns, overlapping entries; not a portfolio or allocation',
                'One candidate, no multiplicity adjustment needed beyond retaining all eighteen cells; no selection',
                'No continuous stop/trailing optimization; C is next-bar breakeven','No causal regime generalization or alpha claim'],
        rights=dict(reference=plan['terms_reference'],scope='OWNER_AUTHORIZED_NONCOMMERCIAL_LOCAL_RESEARCH_NO_RAW_REDISTRIBUTION',
                    acquisition_time_rights='NOT_INDEPENDENTLY_ATTESTED'),source_bytes_unchanged=True)
    result={**body,'sha256':sha(body)}
    persist(output/'result.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--deps',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plan',type=Path,default=Path(__file__).with_name('market-plan.json'))
    p.add_argument('--crash-after-commit',action='store_true');args=p.parse_args()
    try:
        plan=json.loads(args.plan.read_text());anchor=args.plan.with_suffix('.sha256').read_text().strip()
        need(sha(plan)==anchor,'PLAN_TRUST_ANCHOR')
        report=run(args.source,args.deps,args.output,plan,crash=args.crash_after_commit)
        print(json.dumps({'status':report['status'],'sha256':report['sha256'],'populations':report['populations']}))
    except (ValueError,KeyError,TypeError,OSError,zipfile.BadZipFile) as e:
        print(json.dumps({'status':'FAIL_MATERIAL_GATE','code':type(e).__name__,'reason':str(e) if type(e) is ValueError else 'INVALID_INPUT'}))
        raise SystemExit(2) from None


if __name__=='__main__':main()
