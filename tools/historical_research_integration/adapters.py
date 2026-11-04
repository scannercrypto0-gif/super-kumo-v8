"""Original-byte/custody/candidate/attempt joins. Current authentic route is closed."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import subprocess
import sys
from tools.strategy_service_offline.common import (
    Dependencies,Frozen,RunJournal,canonical,decode,digest,raw_sha,require,BoundaryError,read,
)
from tools.strategy_service_offline.research import independent_research
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2


class Ports:
    def __init__(self,deps):self.deps=deps;self.store_type=deps.store_type

    def call(self,name,body):
        raw=canonical(body);require(len(raw)<=8*1024*1024,'PORT_INPUT_LIMIT')
        r=subprocess.run([sys.executable,'-I',str(Path(__file__).with_name('worker.py')),name,
                          self.deps.roots[name]],input=raw,capture_output=True,timeout=30)
        if r.returncode:
            lines=r.stderr.decode(errors='replace').splitlines()
            raise BoundaryError('PINNED_PORT_REFUSED:'+name+':'+(lines[-1][:180] if lines else 'ERROR'))
        return decode(r.stdout)


def source_call(ports,source):
    result=ports.call('core',{'sources':[source]})['results'][0]
    if result['status']=='REFUSED':
        return Frozen.build({'schema':'aql.work.historical-source-boundary.v1',
             'status':'CORE_ADMISSION_REFUSED','core_error':result['code'],
             'source_available':source['source_hex'] is not None,'scientific_run':'BLOCKED',
             'authentic_connection':'NOT_CONNECTED','receipt':None})
    receipt=result['receipt']
    require(receipt['schema']=='aql.core.historical-original-admission.v1','CORE_CONTRACT')
    if receipt['status']=='SOURCE_NOT_AVAILABLE':
        require(receipt['source_bytes_sha256'] is None and receipt['query'] is None,'NO_SOURCE_FABRICATION')
        return Frozen.build({'schema':'aql.work.historical-source-boundary.v1','status':'SOURCE_NOT_AVAILABLE',
             'source_available':False,'scientific_run':'BLOCKED','authentic_connection':'NOT_CONNECTED','receipt':receipt})
    payload={k:v for k,v in receipt.items() if k!='manifest_record_sha256'}
    require(receipt['manifest_record_sha256']==digest(payload),'CORE_RECORD_TAMPER')
    original=bytes.fromhex(source['source_hex'])
    require(raw_sha(original)==source['pin']['original_sha256']==receipt['source_bytes_sha256'],'ORIGINAL_SOURCE_JOIN')
    spec=source['spec'];q=receipt['query'];r=q['result']
    require(receipt['dataset_id']==r['dataset_id']==spec['dataset_id'] and
            receipt['version']==r['version']==spec['version'],'DATASET_VERSION_JOIN')
    require(receipt['manifest_integrity_sha256']==r['manifest_integrity_sha256'] and
            receipt['source_bytes_sha256']==r['source_bytes_sha256'],'CORE_QUERY_PARENT')
    require(receipt['correction_parent_source_sha256']==spec['parent_source_sha256'] and
            receipt['correction_reason']==spec['correction_reason'],'CORRECTION_JOIN')
    require(receipt['decision_cutoff_ms']==r['decision_cutoff_ms']==source['cutoff_ms'],'CUTOFF_JOIN')
    require(r['available_bar_count']+len(r['missing_bar_opens'])==r['required_bar_count'],'SOURCE_DENOMINATOR')
    require(all(b['availability_kind']=='RETROSPECTIVE' and
                b['bar_close']<source['cutoff_ms'] and b['observation_cutoff_ms']<=source['cutoff_ms']
                for b in r['bars']),'LOOKAHEAD_OR_AVAILABILITY_UPGRADE')
    # Current exact Core contract NEVER attests independent source/PIT/universe.
    # A changed self-asserted flag is not a newly reviewed verifier interface.
    require(receipt['authenticated_source']=='NOT_ATTESTED' and receipt['confirmed_pit']=='NOT_ATTESTED'
            and receipt['complete_market_universe']=='NOT_ATTESTED'
            and receipt['factory_scientific_input']=='BLOCKED','FORGED_SCIENTIFIC_AUTHORITY')
    return Frozen.build({'schema':'aql.work.historical-source-boundary.v1','status':receipt['status'],
         'source_available':True,'receipt':receipt,'scientific_run':'BLOCKED',
         'authentic_connection':'NOT_CONNECTED','independent_provenance':'NOT_ATTESTED'})


class GenerationOnlyPort:
    """Reuse #235 independent generator, deferring Factory until census is final.

    No fake Factory result: explicit generation-only deferral is retained, then
    the real #241 admission API is invoked below on the finalized attempt census.
    """
    def __init__(self,deps):self.deps=deps
    def call(self,name,action,body):
        if name=='factory' and action=='research_handoff':
            return {'strategy_definition_digest':body['candidate']['definition']['digest'],
                    'status':'GENERATION_ONLY_FACTORY_NOT_CALLED','evaluation':'NOT_PERFORMED'}
        return self.deps.call(name,action,body)


STATE_MAP={'SUBMITTED_NOT_EVALUATED':'PROPOSED','INVALID':'INVALID','FAILED':'FAILED',
           'DUPLICATE':'DUPLICATE','BUDGET_EXHAUSTED':'BUDGET_EXHAUSTED',
           'FACTORY_HANDOFF_BLOCKED':'UNKNOWN'}


def join_factory_packets(generation,source_boundary,*,holdout='SEALED_UNOPENED'):
    require(holdout=='SEALED_UNOPENED','SEALED_HOLDOUT_ACCESS_DENIED')
    g=Frozen.restore(generation).data;s=Frozen.restore(source_boundary).data
    require(g['scanner_required'] is False and g['source_kind']=='INDEPENDENT_TEST_ONLY_RESEARCH_SEED',
            'DISCOVERY_SOURCE_OR_ROLE')
    attempts=g['attempts'];require(len(attempts)==g['attempt_count'],'TRIAL_DENOMINATOR')
    seen=set();byid={};groups={};unrouted=[]
    for a in attempts:
        require(a['attempt_id'] not in seen,'DUPLICATE_ATTEMPT_ID');seen.add(a['attempt_id']);byid[a['attempt_id']]=a
        require(a['state'] in STATE_MAP,'ATTEMPT_STATE')
        if a['state']=='DUPLICATE':
            require(a['duplicate_of'] in byid and a['duplicate_of']!=a['attempt_id'],'DUPLICATE_PARENT')
        if a['candidate'] is not None:
            candidate=Frozen.restore(a['candidate']).data
            sd=StrategyDefinition.from_dict(candidate['definition'],registry=IndicatorRegistryV2())
            require(candidate['attempt_id']==a['attempt_id'] and candidate['plan_sha256']==g['plan_sha256'],
                    'CANDIDATE_ATTEMPT_PLAN')
            groups.setdefault(sd.digest,{'definition':sd,'attempts':[]})['attempts'].append(a)
        elif a['state']=='DUPLICATE':
            parent=byid[a['duplicate_of']]
            require(parent['candidate'] is not None,'DUPLICATE_UNRESOLVED_PARENT')
            key=Frozen.restore(parent['candidate']).data['definition']['digest']
            require(key in groups,'DUPLICATE_GROUP');groups[key]['attempts'].append(a)
        else:unrouted.append({'attempt_id':a['attempt_id'],'state':a['state'],'reason':'NO_VALID_DEFINITION'})
    require(sum(len(x['attempts']) for x in groups.values())+len(unrouted)==len(attempts),'CANDIDATE_DENOMINATOR')
    require(g['status_counts']==dict(sorted(Counter(a['state'] for a in attempts).items())),'TRIAL_STATUS_CENSUS')
    if s['receipt'] is None or s['status'] in ('SOURCE_NOT_AVAILABLE','CORE_ADMISSION_REFUSED'):
        return [],unrouted,'NO_ADMISSIBLE_CORE_RECORD'
    core=s['receipt']
    require(core['manifest_record_sha256']==digest({k:v for k,v in core.items() if k!='manifest_record_sha256'}),
            'CORE_RECORD_TAMPER')
    require(core['authenticated_source']=='NOT_ATTESTED' and core['confirmed_pit']=='NOT_ATTESTED'
            and core['factory_scientific_input']=='BLOCKED','FORGED_SCIENTIFIC_AUTHORITY')
    query=core['query']['result']
    require(query['source_bytes_sha256']==core['source_bytes_sha256'] and
            query['manifest_integrity_sha256']==core['manifest_integrity_sha256'] and
            query['dataset_id']==core['dataset_id'] and query['version']==core['version'] and
            query['decision_cutoff_ms']==core['decision_cutoff_ms'],'CORE_QUERY_PARENT')
    require(core['coverage']=='COMPLETE' and not core['missing_bar_opens'],'INCOMPLETE_PRICE_SOURCE_GRID')
    require(core['query']['result']['required_bar_count']==core['query']['result']['available_bar_count'],
            'INCOMPLETE_PRICE_SOURCE_GRID')
    packets=[]
    for key,group in sorted(groups.items()):
        definition=group['definition'];rows=[]
        for a in group['attempts']:
            rows.append({'attempt_id':a['attempt_id'],'strategy_id':definition.spec['strategy_id'],
               'strategy_version':definition.spec['strategy_version'],'plan_digest':g['plan_sha256'],
               'decision_cutoff_ms':core['decision_cutoff_ms'],'feature_available_ms':None,
               'state':STATE_MAP[a['state']],'duplicate_of':a['duplicate_of'],'result':None,'holdout_access':False})
        packets.append({'schema':'aql.factory.authentic-research-admission.v1',
            'execution_authority':'NONE','paper_live':False,'holdout':holdout,
            'source_kind':'TEST_ONLY' if core['status']=='TEST_ONLY_INTEGRITY_VERIFIED' else 'ORIGINAL_UNVERIFIED',
            'source_bytes_sha256':core['source_bytes_sha256'],'source_manifest_sha256':core['manifest_integrity_sha256'],
            'dataset_version_sha256':digest({'dataset_id':core['dataset_id'],'version':core['version'],
                                          'manifest_sha256':core['manifest_integrity_sha256'],
                                          'correction_parent':core['correction_parent_source_sha256']}),
            'dataset_id':core['dataset_id'],'strategy_id':definition.spec['strategy_id'],
            'strategy_version':definition.spec['strategy_version'],'strategy_definition_digest':key,
            'plan_digest':g['plan_sha256'],'decision_cutoff_ms':core['decision_cutoff_ms'],
            'availability':'SYNTHETIC_TEST' if core['status']=='TEST_ONLY_INTEGRITY_VERIFIED' else 'RETROSPECTIVE_NON_PIT',
            'expected_attempts':len(rows),'attempts':rows,'global_trial_census_sha256':digest(attempts),
            'global_trial_count':len(attempts),'candidate_definition':definition.to_dict(),
            'price_grid':'NOT_PROVIDED_BY_CORE_QUERY','rule_trigger_port':'NOT_CONNECTED',
            'market_universe_denominator':None,'base_shadow_opportunity_denominator':None})
    return packets,unrouted,'FINALIZED_CENSUS_BOUND'


def integrate(deps,source,plan,output):
    ports=Ports(deps);boundary=source_call(ports,source)
    # This complete independent proposal path is TEST_ONLY. Actual original
    # sources are never scored through this branch or relabelled as fixtures.
    require(plan['evidence_class']=='TEST_ONLY','ORIGINAL_EVALUATION_PERMISSION_AND_PROOF_REQUIRED')
    require(source['source_hex'] is None or source['pin']['test_only'] is True,'ORIGINAL_SOURCE_NOT_TEST_INPUT')
    generated=independent_research(plan,RunJournal(Path(output)/'attempts',deps),GenerationOnlyPort(deps),
                                   factory_fixture=None)
    packets,unrouted,join_status=join_factory_packets(generated.receipt(),boundary.receipt())
    calls=[]
    for packet in packets:
        response=ports.call('factory',{'packet':packet});receipt=response['receipt']
        require(receipt['source_bytes_sha256']==packet['source_bytes_sha256'] and
                receipt['source_manifest_sha256']==packet['source_manifest_sha256'] and
                receipt['attempt_count']==packet['expected_attempts'],'FACTORY_RECEIPT_BINDING')
        require(receipt['strategy_rule_trigger_evaluation']=='NOT_PERFORMED'
                and receipt['scientific_result']=='INSUFFICIENT_EVIDENCE'
                and receipt['source_original_bytes_verified'] is False and receipt['pit_verified'] is False,
                'FALSE_AUTHENTIC_OR_SCIENTIFIC_PASS')
        calls.append(response)
    result=Frozen.build({'schema':'aql.work.original-history-integration.v1','evidence_class':'TEST_ONLY',
         'source':boundary.receipt(),'generation':generated.receipt(),'factory_calls':calls,
         'unrouted_attempts':unrouted,'join_status':join_status,
         'trial_count':generated.data['attempt_count'],'candidate_count':generated.data['unique_definitions'],
         'native_factory_attempt_slots':sum(c['receipt']['attempt_count'] for c in calls),
         'market_universe_count':None,'opportunity_count':None,'base_arm_count':None,'shadow_arm_count':None,
         'observation_count':None,'scientific_result':'INSUFFICIENT_EVIDENCE','authentic_e2e':'NOT_CONNECTED',
         'price_grid':'NOT_CONNECTED_METADATA_QUERY_ONLY','strategy_rule_trigger_port':'NOT_CONNECTED',
         'modeled_costs':'NOT_APPLIED_NO_EVALUATION','multiple_testing':'FROZEN_ATTEMPT_CENSUS_NO_INFERENCE',
         'holdout':'SEALED_UNOPENED','paper_live':'NOT_ACTIVATED','g0':'NOT_APPROVED'})
    store=RunJournal(Path(output)/'result',deps).store
    key=store.put(result.receipt())
    return result,key
