"""Join new owner contracts onto retained receipts, never rerun accepted reports."""
from pathlib import Path
import subprocess
import sys
from tools.strategy_service_offline.common import Frozen,RunJournal,read,decode,raw_sha,require
from tools.original_history_batch.batch import owner_bytes,owner_digest,generation,plan

FIXTURES=Path(__file__).parent/'fixtures'
PREVIOUS_RESULT='8a444744165c533613bd1090249a035f881f647f727a56a1f88e2d9e0eab9962'
CORE_HEAD='7a2631325e70e70e5df25abc5f507cab53f4399e'
FACTORY_HEAD='bf48e77193e69f4e857e0a461b0895ab26af31a8'
BATCH_PLAN={'schema':'aql.work.scientific-validity-plan.v1','previous_work_head':'b44d9c317481388a235d6e0914e98345b1c211ec',
 'previous_result_object_sha256':PREVIOUS_RESULT,'core_head':CORE_HEAD,'factory_head':FACTORY_HEAD,
 'mode':'ASSESS_EXISTING_RECEIPTS_ONLY','chronology_sidecars':None,'universe_sidecars':None,
 'authentic_base_shadow_preregistration':None,'higher_cost_scenario_bps':'50',
 'cost_sensitivity_returns_recomputed':False,'historical_preregistration':False,
 'holdout':'SEALED_UNOPENED','authority':'NONE'}
BATCH_SHA=Frozen.build(BATCH_PLAN).sha256


def call(deps,name,body):
    raw=owner_bytes(body);require(len(raw)<=8*1024*1024,'PORT_INPUT_LIMIT')
    r=subprocess.run([sys.executable,'-I',str(Path(__file__).with_name('worker.py')),name,deps.roots[name]],
        input=raw,capture_output=True,timeout=30)
    if r.returncode:
        lines=r.stderr.decode(errors='replace').splitlines()
        raise ValueError('OWNER_REFUSED:'+name+':'+(lines[-1][:160] if lines else 'ERROR'))
    return decode(r.stdout)


def sealed(value,key):
    require(value[key]==owner_digest({k:v for k,v in value.items() if k!=key}),'OWNER_SEAL_DRIFT')


def compare_plan(native,assessment):
    a=native['admission'];q=native['prices'];sealed(a,'manifest_record_sha256');sealed(q,'price_query_sha256')
    sealed(assessment,'assessment_sha256')
    require(assessment['admission_sha256']==a['manifest_record_sha256'] and
        assessment['price_query_sha256']==q['price_query_sha256'] and
        assessment['dataset_id']==a['dataset_id']==q['dataset_id'] and
        assessment['version']==a['version']==q['version'] and
        assessment['source_bytes_sha256']==a['source_bytes_sha256']==q['source_bytes_sha256'] and
        assessment['manifest_integrity_sha256']==a['manifest_integrity_sha256']==q['manifest_integrity_sha256'] and
        assessment['decision_cutoff_ms']==a['decision_cutoff_ms']==q['decision_cutoff_ms'],'CORE_PARENT_JOIN')
    require(assessment['chronology']['evidence_state']=='CHRONOLOGY_EVIDENCE_NOT_AVAILABLE' and
        assessment['universe']['evidence_state']=='UNIVERSE_EVIDENCE_NOT_AVAILABLE' and
        assessment['universe']['reported_opportunity_count'] is None and
        assessment['independent_opportunity_denominator'] is None and
        assessment['historical_pit']=='NOT_ATTESTED' and assessment['factory_scientific_input']=='BLOCKED',
        'MISSING_WITNESS_OR_FALSE_AUTHORITY')
    g=generation();p=plan();costs=p['costs']
    return {'schema':'aql.factory.opportunity-comparison-plan.v1','holdout':'SEALED_UNOPENED',
        'execution_authority':'NONE','candidate_origin':p['candidate_origin'].replace('_REUSED_UNCHANGED',''),
        'historical_pit':'NOT_ATTESTED','historical_preregistration':False,
        # Frozen before THIS metadata-only assessment, not before old data or
        # old returns. No actual paired comparison or preregistered arm policy.
        'comparison_plan_frozen_before_evaluation':True,'comparison_scope':'DEVELOPMENT_ONLY',
        'comparison_freeze_meaning':'CURRENT_METADATA_ASSESSMENT_ONLY_NOT_OLD_RETURN_PREREGISTRATION',
        'development_end_ms':p['research_window']['train_end_exclusive_ms'],
        'holdout_start_ms':p['research_window']['holdout_start_ms'],'embargo_ms':p['research_window']['embargo_ms'],
        'source_pins':{'archive_sha256':a['source_bytes_sha256'],'member_sha256':a['native_csv_member_sha256'],
            'checksum_sha256':a['native_checksum_file_sha256'],'core_price_query_sha256':q['price_query_sha256']},
        'candidate_generation_sha256':g.sha256,'precalculation_plan_sha256':p and
            '0f2b6f32c768a616dafc7ca32b21cf0f7a2c4d98cdf1c68e9bfa367f1ce723ab',
        'trials':[{'attempt_id':x['attempt_id'],'family_id':Frozen.restore(x['candidate']).data['family_id'],
                   'state':'PROPOSED'} for x in g.data['attempts']],
        'selection_multiplicity':{'attempts_examined':53,'families_examined':7,
            'selection_policy':'FROZEN_NO_OUTCOME_RETUNING','adjustment_status':'NOT_ESTIMATED'},
        'modeled_costs_bps':{k:costs[k+'_bps'] for k in ('fee_entry','fee_exit','spread_entry','spread_exit','slippage_entry','slippage_exit')}
            | {'funding':costs['funding_bps_per_bar']},
        'cost_scenarios_bps':[{'name':'BASE_ASSUMPTION','total_round_trip_bps':'30'},
            {'name':'HIGHER_COST','total_round_trip_bps':BATCH_PLAN['higher_cost_scenario_bps']}],
        'universe_inventory':None,'core_assessment_sha256':assessment['assessment_sha256'],
        'work_assessment_plan_sha256':BATCH_SHA,'authentic_base_shadow_plan':None}


def verify_selection(packet,expected):
    require(owner_bytes(packet)==owner_bytes(expected),'FROZEN_SELECTION_OR_PLAN_DRIFT')


def verify_factory(r,p):
    sealed(r,'report_sha256')
    require(r['input_sha256']==owner_digest(p) and r['source_pins']==p['source_pins'],'FACTORY_INPUT_JOIN')
    require(r['trial_attempts']==53 and r['unique_families']==7 and r['historical_preregistration']=='NOT_ESTABLISHED'
        and r['multiplicity_adjustment']=='NOT_ESTIMATED','FALSE_SELECTION_CERTIFICATION')
    require(all(r[x] is None for x in ('universe_denominator','universe_status_counts','paired_arm_slots',
        'independent_market_opportunity_denominator','base_shadow_comparison')),'MISSING_DENOMINATOR_PROMOTED')
    require(r['modeled_returns_recomputed'] is False and r['scientific_result']=='INSUFFICIENT_EVIDENCE'
        and r['historical_pit']=='NOT_ATTESTED' and r['trading_authority']=='NONE','FALSE_SCIENTIFIC_PASS')


def integrate_one(deps,native):
    a=call(deps,'core',native|{'chronology':None,'universe':None})
    packet=compare_plan(native,a);verify_selection(packet,compare_plan(native,a))
    r=call(deps,'factory',{'plan':packet});verify_factory(r,packet)
    return {'core_assessment':a,'factory_input':packet,'factory_report':r}


def retained_inputs(directory):
    root=Path(directory);raw=read(root/'summary.json');require(raw_sha(raw)==PREVIOUS_RESULT,'PREVIOUS_RESULT_PIN')
    summary=Frozen.restore(decode(raw)).data
    require(len(summary['cohorts'])==2 and summary['generation_sha256']==generation().sha256,'PREVIOUS_COHORT_OR_GENERATION')
    inputs=[]
    for c in summary['cohorts']:
        key=c['private_source_receipt_object_sha256'];body=read(root/'receipts/objects'/(key+'.json'))
        require(raw_sha(body)==key,'RETAINED_CORE_OBJECT_PIN');wrapper=decode(body)
        native=decode(wrapper['owner_json'].encode());require(owner_digest(native)==wrapper['owner_json_sha256'],'RETAINED_OWNER_JSON_PIN')
        require(native['admission']['manifest_record_sha256']==c['core_admission_record_sha256'] and
                native['prices']['price_query_sha256']==c['core_price_query_sha256'],'RETAINED_PARENT_PIN')
        inputs.append(native)
    return inputs


def execute(deps,inputs,output,*,evidence_class):
    require(evidence_class in ('TEST_ONLY','RETAINED_AUDIT248_ACCEPTED_RECEIPTS'),'EVIDENCE_CLASS')
    journal=RunJournal(output,deps);journal.put('claim',BATCH_SHA,{'plan':BATCH_PLAN,'sha256':BATCH_SHA})
    cohorts=[integrate_one(deps,n) for n in inputs]
    result=Frozen.build({'schema':'aql.work.scientific-validity-integration.v1','evidence_class':evidence_class,
        'plan_sha256':BATCH_SHA,'previous_result_object_sha256':PREVIOUS_RESULT,'cohorts':cohorts,
        'status':'BLOCKED_MISSING_INDEPENDENT_EVIDENCE','scientific_result':'INSUFFICIENT_EVIDENCE',
        'authentic_pit':'NOT_ATTESTED','authentic_base_shadow_plan':None,'independent_opportunity_denominator':None,
        'base_shadow_comparison':None,'old_factory_reports_rerun':0,'returns_recomputed':False,
        'multiple_testing_adjustment':'NOT_ESTIMATED','holdout':'SEALED_UNOPENED','trading_authority':'NONE'})
    key=journal.store.put(result.receipt());return result,key
