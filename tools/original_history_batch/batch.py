"""Work #247 custody/plan/rule-projection joins; scientific acceptance stays blocked."""
from collections import Counter
from decimal import Decimal
from io import BytesIO,StringIO
import csv
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
from tools.strategy_service_offline.common import (
    Frozen,RunJournal,canonical,decode,digest,read,raw_sha,require,BoundaryError,
)
from tools.historical_research_integration.inventory import inspect_retained_package,ALLOWED
from tools.historical_research_integration.adapters import GenerationOnlyPort,STATE_MAP
from tools.strategy_service_offline.research import independent_research
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

FIXTURES=Path(__file__).parent/'fixtures'
PLAN_SHA='0f2b6f32c768a616dafc7ca32b21cf0f7a2c4d98cdf1c68e9bfa367f1ce723ab'


def plan():
    raw=read(FIXTURES/'plan.json');require(raw_sha(raw)==PLAN_SHA,'FROZEN_PLAN_DRIFT')
    return decode(raw)


def generation():
    g=Frozen.restore(decode(read(FIXTURES/'generation.json')))
    require(g.sha256==plan()['generation_sha256'],'FROZEN_GENERATION_DRIFT')
    require(len(g.data['attempts'])==g.data['attempt_count']==53 and g.data['unique_definitions']==53,
            'FROZEN_53_CENSUS')
    ids=set();definitions=set();families=set()
    for a in g.data['attempts']:
        require(a['attempt_id'] not in ids,'DUPLICATE_ATTEMPT');ids.add(a['attempt_id'])
        c=Frozen.restore(a['candidate']).data
        sd=StrategyDefinition.from_dict(c['definition'],registry=IndicatorRegistryV2())
        require(c['attempt_id']==a['attempt_id'] and c['plan_sha256']==g.data['plan_sha256']
                and a['state']=='SUBMITTED_NOT_EVALUATED','CANDIDATE_PLAN_JOIN')
        require(sd.digest not in definitions,'DUPLICATE_CANDIDATE');definitions.add(sd.digest)
        families.add(c['family_id'])
    require(families=={'F00'+str(i) for i in range(1,8)},'SEVEN_FAMILY_CENSUS')
    return g


def owner_bytes(value):
    # Core/Factory seal JSON preserves 1.0; StrategyDefinition canonicalizes
    # it to 1. Keep these distinct contracts instead of rewriting owner seals.
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def owner_digest(value):return raw_sha(owner_bytes(value))


def owner_call(deps,name,body):
    raw=owner_bytes(body);require(len(raw)<=8*1024*1024,'PORT_INPUT_LIMIT')
    r=subprocess.run([sys.executable,'-I',str(Path(__file__).with_name('worker.py')),name,deps.roots['factory' if name=='factory-core' else name]],
        input=raw,capture_output=True,timeout=180)
    if r.returncode:
        lines=r.stderr.decode(errors='replace').splitlines()
        raise BoundaryError('OWNER_PORT_REFUSED:'+name+':'+(lines[-1][:180] if lines else 'ERROR'))
    return decode(r.stdout)


def original_inputs(package):
    p=plan();inventory=inspect_retained_package(package,p['source_package_sha256'])
    if not inventory.data['source_available']:return inventory,[]
    # Reopen and rehash at use; old #242 inventory blockers describe its old pins,
    # not current native Core capability. Carry only its factual archive records.
    raw=read(Path(package));require(raw_sha(raw)==p['source_package_sha256'],'SOURCE_CHANGED_AT_USE')
    sources=[]
    with ZipFile(BytesIO(raw)) as z:
        for record in inventory.data['archives']:
            name=record['name'];require(name in ALLOWED,'UNDECLARED_SOURCE')
            data=z.read('ATLAS_P2A_DEV/raw/'+name);cs=z.read('ATLAS_P2A_DEV/raw/'+name+'.CHECKSUM')
            pin={'schema':'aql.core.external-original-byte-pin.v1','source_kind':'BINANCE_KLINES_ZIP',
                'original_object_id':name,'original_sha256':record['archive_sha256'],
                'provenance_reference':'WORK_239_RETAINED_P2A_INTAKE','captured_at_ms':None,
                'claimed_available_at_ms':None,'expected_inventory_sha256':None,'vault_object_metadata':None,
                'universe_manifest_sha256':None,'universe_member_count':None,'test_only':False,
                'archive_name':name,'csv_member_name':name[:-4]+'.csv',
                'csv_member_sha256':record['member_sha256'],'checksum_file_sha256':record['checksum_file_sha256']}
            spec={'dataset_id':record['dataset_id'],'version':1,'symbol':'BTCUSDT','interval':'15m',
                'exchange':'BINANCE','market':'SPOT','source_label':'retained-binance-native-zip',
                'start_ms':record['start_ms'],'end_exclusive_ms':record['end_exclusive_ms'],
                'as_of_ms':record['end_exclusive_ms'],'parent_source_sha256':None,'correction_reason':None,
                'test_only':False}
            sources.append({'source_hex':data.hex(),'checksum_hex':cs.hex(),'pin':pin,'spec':spec,
                            'cutoff_ms':record['end_exclusive_ms']})
    return inventory,sources


def verify_core(call,source):
    a=call['admission'];q=call['prices'];s=source['spec'];pin=source['pin']
    require(a['manifest_record_sha256']==owner_digest({k:v for k,v in a.items() if k!='manifest_record_sha256'}),
            'CORE_ADMISSION_SEAL')
    require(q.get('price_query_sha256')==owner_digest({k:v for k,v in q.items() if k!='price_query_sha256'}),
            'PRICE_QUERY_SEAL')
    require(a['source_bytes_sha256']==q['source_bytes_sha256']==pin['original_sha256']==raw_sha(bytes.fromhex(source['source_hex'])),
            'ORIGINAL_SOURCE_JOIN')
    require(a['native_csv_member_sha256']==pin['csv_member_sha256'] and
            a['native_checksum_file_sha256']==pin['checksum_file_sha256']==raw_sha(bytes.fromhex(source['checksum_hex'])),
            'MEMBER_CHECKSUM_JOIN')
    require(a['manifest_integrity_sha256']==q['manifest_integrity_sha256'] and
            a['dataset_id']==q['dataset_id']==s['dataset_id'] and a['version']==q['version']==s['version'] and
            a['decision_cutoff_ms']==q['decision_cutoff_ms']==source['cutoff_ms'],'CORE_IDENTITY_JOIN')
    require(a['confirmed_pit']=='NOT_ATTESTED' and a['authenticated_source']=='NOT_ATTESTED' and
            q['scientific_pit']=='NOT_ATTESTED' and q['source_availability']=='RETROSPECTIVE_NON_PIT',
            'FALSE_PIT_OR_SOURCE_AUTHORITY')
    require(q['status']=='OK' and q['coverage']==a['coverage']=='COMPLETE' and not q['missing_bar_opens'] and
            q['available_bar_count']==q['required_bar_count']==len(q['bars']),'INCOMPLETE_CORE_GRID')
    expected=(s['end_exclusive_ms']-s['start_ms'])//900000
    require(expected==len(q['bars']),'COHORT_DENOMINATOR')
    with ZipFile(BytesIO(bytes.fromhex(source['source_hex']))) as z:
        member=z.read(pin['csv_member_name']);require(raw_sha(member)==pin['csv_member_sha256'],'NATIVE_MEMBER_SHA')
        native=list(csv.reader(StringIO(member.decode())))
    require(len(native)==expected,'NATIVE_CENSUS')
    base=a['query']['result']['bars']
    require(len(base)==expected,'BASE_QUERY_CENSUS')
    for i,(b,row,meta) in enumerate(zip(q['bars'],native,base)):
        start=s['start_ms']+i*900000
        require(b['bar_open_ms']==int(row[0])==start and b['bar_close_ms']==int(row[6])==start+899999
                and b['bar_close_ms']<source['cutoff_ms'],'COHORT_GRID_OR_LOOKAHEAD')
        require(all(b[k]==float(row[j]) for k,j in [('open',1),('high',2),('low',3),('close',4),('volume',5)]),
                'PRICE_PROJECTION_DRIFT')
        require(b['checksum']==meta['checksum'] and b['historical_known_at_ms'] is None and
                b['availability_kind']=='RETROSPECTIVE' and b['observation_lower_bound_ms']==start+900000,
                'PRICE_OR_AVAILABILITY_LINEAGE')
    return q


def factory_packet(call,source,attempt,g):
    q=verify_core(call,source);a=call['admission'];p=plan();c=Frozen.restore(attempt['candidate']).data
    sd=StrategyDefinition.from_dict(c['definition'],registry=IndicatorRegistryV2())
    rows=[]
    for b in q['bars']:
        row={'open_ms':b['bar_open_ms'],'close_ms':b['bar_close_ms'],
             **{k:b[k] for k in ('open','high','low','close','volume')},'known_at_ms':None,'quality':'FINAL'}
        row['bar_sha256']=owner_digest(row);rows.append(row)
    return {'schema':'aql.factory.historical-rule-projection.v1',
        'source_kind':'TEST_ONLY' if source['pin']['test_only'] else 'ORIGINAL_UNVERIFIED',
        'availability':'SYNTHETIC_TEST' if source['pin']['test_only'] else 'RETROSPECTIVE_NON_PIT',
        'market':'SPOT','direction':'LONG','holdout':'SEALED_UNOPENED','execution_authority':'NONE',
        'dataset_id':a['dataset_id'],'dataset_version':a['version'],
        'source_bytes_sha256':a['source_bytes_sha256'],'source_manifest_sha256':a['manifest_integrity_sha256'],
        'plan_digest':g.data['plan_sha256'],'strategy':sd.to_dict(),'selected_attempt_id':attempt['attempt_id'],
        'trial_budget':53,'trials':[{'attempt_id':x['attempt_id'],
            'candidate_digest':Frozen.restore(x['candidate']).data['definition']['digest'],
            'plan_digest':g.data['plan_sha256'],'state':STATE_MAP[x['state']],'duplicate_of':x['duplicate_of']}
            for x in g.data['attempts']],
        # ONE explicitly scoped symbol/window. NOT the global market universe.
        # No independent Scanner opportunity ledger is connected; empty adapter
        # slots are recorded separately from UNKNOWN global opportunity counts.
        'universe':{'full':1,'eligible':1,'ineligible':0,'unscanned':0,'rejected':0,
                    'unknown':1,'nominated':0,'source_coverage':'NOT_INDEPENDENTLY_ATTESTED'},
        'opportunity_count':0,'opportunities':[],'bars':rows,'width_ms':900000,
        'research_window':p['research_window'],'costs':p['costs'],
        'work_batch_plan_sha256':PLAN_SHA,'core_price_query_sha256':q['price_query_sha256'],
        'core_admission_record_sha256':a['manifest_record_sha256']}


def native_factory_call(deps,native,packet):
    # The finalized Factory-owned native adapter performs normalization and
    # custody binding itself. Work supplies its frozen plan, no duplicate engine.
    keys=('dataset_id','dataset_version','source_bytes_sha256','plan_digest','trial_budget','trials',
          'selected_attempt_id','strategy','universe','opportunity_count','opportunities',
          'research_window','width_ms','costs','holdout','execution_authority','market','direction')
    work_plan={k:packet[k] for k in keys}
    work_plan.update(schema='aql.factory.historical-rule-work-plan.v1',
        manifest_integrity_sha256=packet['source_manifest_sha256'],
        correction_parent_source_sha256=native['admission']['correction_parent_source_sha256'],
        decision_cutoff_ms=native['admission']['decision_cutoff_ms'])
    port=owner_call(deps,'factory-core',{'admission':native['admission'],'prices':native['prices'],'plan':work_plan})
    require(port['artifact_sha256']==owner_digest({k:v for k,v in port.items() if k!='artifact_sha256'}),'FACTORY_PORT_SEAL')
    require(port['research_plan_sha256']==owner_digest(work_plan) and
        port['core_admission_sha256']==native['admission']['manifest_record_sha256'] and
        port['core_price_query_sha256']==native['prices']['price_query_sha256'] and
        port['core_native_csv_member_sha256']==native['admission']['native_csv_member_sha256'] and
        port['core_original_checksum_file_sha256']==native['admission']['native_checksum_file_sha256'] and
        port['core_bar_checksum_list_sha256']==owner_digest([b['checksum'] for b in native['prices']['bars']]),
        'FACTORY_NATIVE_PORT_LINEAGE')
    require(port['historical_pit']=='NOT_ATTESTED' and port['scientific_result']=='INSUFFICIENT_EVIDENCE',
            'FALSE_FACTORY_PORT_ACCEPTANCE')
    # This is the exact documented packet emitted by the owner adapter, which
    # contains no Work extension keys. Its normalized prices are cross-checked
    # independently against the pinned original CSV above.
    normalized={k:v for k,v in packet.items() if k not in
        ('work_batch_plan_sha256','core_price_query_sha256','core_admission_record_sha256')}
    validate_factory(port['factory_report'],normalized)
    return port


def validate_factory(report,packet):
    require(report['artifact_sha256']==owner_digest({k:v for k,v in report.items() if k!='artifact_sha256'}),'FACTORY_SEAL')
    for r,k in [('input_sha256',None),('source_bytes_sha256','source_bytes_sha256'),
                ('source_manifest_sha256','source_manifest_sha256'),('strategy_digest',None),
                ('selected_attempt_id','selected_attempt_id'),('dataset_id','dataset_id'),('dataset_version','dataset_version'),
                ('plan_digest','plan_digest')]:
        expected=owner_digest(packet) if r=='input_sha256' else packet['strategy']['digest'] if r=='strategy_digest' else packet[k]
        require(report[r]==expected,'FACTORY_IDENTITY_DRIFT:'+r)
    require(report['scientific_result']=='INSUFFICIENT_EVIDENCE' and report['historical_pit_verified'] is False
            and report['source_original_bytes_verified'] is False and report['trading_authority']=='NONE',
            'FALSE_SCIENTIFIC_ACCEPTANCE')
    require(report['bar_count']==len(packet['bars']) and report['decision_slots']==len(packet['bars'])-1
            and sum(report['decision_counts'].values())==report['decision_slots'],'DECISION_DENOMINATOR')
    require(report['trial_budget']==53 and sum(report['trial_state_counts'].values())==53,'FACTORY_TRIAL_CENSUS')
    require(report['opportunity_count']==report['arm_slots']==0 and report['costs']==plan()['costs'],'FALSE_ARM_OR_COST_DRIFT')
    price={b['open_ms']:b['open'] for b in packet['bars']};unknown=0
    for t in report['modeled_outcomes']:
        if t['status']!='MODEL_ONLY':
            require(t['modeled_net_return'] is None,'UNKNOWN_NON_NULL');unknown+=1;continue
        entry=Decimal(str(price[t['entry_open_ms']]));exit_=Decimal(str(price[t['exit_open_ms']]))
        gross=exit_/entry-1
        require(Decimal(t['modeled_entry_open'])==entry and Decimal(t['modeled_exit_open'])==exit_ and
                Decimal(t['modeled_gross_return'])==gross and Decimal(t['total_cost_bps'])==30 and
                Decimal(t['modeled_net_return'])==gross-Decimal('0.003'),'MODELED_COST_ARITHMETIC')
    require(unknown==report['unknown_outcomes'],'UNKNOWN_DENOMINATOR')


def summarize(report,attempt):
    c=Frozen.restore(attempt['candidate']).data;trades=report['modeled_outcomes']
    scored=[t for t in trades if t['status']=='MODEL_ONLY'];counts=Counter(t['status'] for t in trades)
    return {'attempt_id':attempt['attempt_id'],'family_id':c['family_id'],'strategy_digest':report['strategy_digest'],
        'factory_receipt_sha256':report['artifact_sha256'],'decision_slots':report['decision_slots'],
        'decision_counts':report['decision_counts'],'modeled_outcome_states':dict(sorted(counts.items())),
        'scored_model_only_count':len(scored),'null_outcomes':report['unknown_outcomes'],
        'sum_independent_modeled_net_returns':str(sum((Decimal(t['modeled_net_return']) for t in scored),Decimal(0))),
        'return_sum_meaning':'DESCRIPTIVE_SUM_ONLY_NOT_FUNDED_EQUITY_OR_STATISTICAL_ACCEPTANCE',
        'scientific_result':report['scientific_result'],'base_shadow_comparison':None}


def execute(deps,package,output,*,mode):
    require(mode in ('test-only','retrospective-originals'),'EXPLICIT_MODE_REQUIRED')
    p=plan();g=generation();journal=RunJournal(Path(output)/'receipts',deps)
    journal.put('claim',PLAN_SHA,{'plan':p,'plan_sha256':PLAN_SHA,'generation_sha256':g.sha256})
    if mode=='retrospective-originals':
        inventory,sources=original_inputs(package)
        if not sources:
            result=Frozen.build({'schema':'aql.work.original-history-batch-result.v1','status':'SOURCE_NOT_AVAILABLE',
                'scientific_result':'INSUFFICIENT_EVIDENCE','source_package_sha256':None,'cohorts':[]})
            return result,journal.store.put(result.receipt())
    else:
        from .test_fixture import source_fixture
        sources=[source_fixture()];inventory=None
    cohorts=[]
    for source in sources:
        require(source['pin']['test_only']==(mode=='test-only'),'SOURCE_CLASS_DRIFT')
        native=owner_call(deps,'core',source);q=verify_core(native,source)
        source_key=journal.store.put({'owner_json':owner_bytes(native).decode(),'owner_json_sha256':owner_digest(native)});outcomes=[]
        for attempt in g.data['attempts']:
            packet=factory_packet(native,source,attempt,g)
            port=native_factory_call(deps,native,packet);r=port['factory_report']
            key=journal.store.put(port)
            outcomes.append({**summarize(r,attempt),'receipt_object_sha256':key,
                             'work_factory_input_sha256':r['input_sha256'],'factory_native_port_sha256':port['artifact_sha256']})
        cohorts.append({'dataset_id':source['spec']['dataset_id'],'version':source['spec']['version'],
            'original_archive_sha256':source['pin']['original_sha256'],'native_member_sha256':source['pin']['csv_member_sha256'],
            'checksum_file_sha256':source['pin']['checksum_file_sha256'],'core_admission_record_sha256':native['admission']['manifest_record_sha256'],
            'core_packet_sha256':native['admission']['packet_sha256'],'core_custody_receipt_sha256':native['admission']['custody_receipt_sha256'],
            'core_manifest_integrity_sha256':native['admission']['manifest_integrity_sha256'],
            'core_price_query_sha256':q['price_query_sha256'],'private_source_receipt_object_sha256':source_key,
            'coverage':q['coverage'],'bar_count':len(q['bars']),'historical_known_at_count':0,
            'missing_opens':q['missing_bar_opens'],'candidate_attempt_count':53,
            'outcomes':outcomes,'global_market_universe':None,'independent_opportunity_count':None,
            'base_arm_count':None,'shadow_arm_count':None,'adapter_unconnected_opportunity_slots':0})
    result=Frozen.build({'schema':'aql.work.original-history-batch-result.v1',
        'status':'TEST_ONLY_INTEGRATED' if mode=='test-only' else 'RETAINED_ORIGINAL_RETROSPECTIVE_PROJECTION_COMPLETED',
        'evidence_class':'TEST_ONLY' if mode=='test-only' else 'RETROSPECTIVE_ONLY_UNVERIFIED',
        'work_batch_plan_sha256':PLAN_SHA,'generation_sha256':g.sha256,
        'candidate_origin':p['candidate_origin'],'trial_count':53,'cohorts':cohorts,
        'source_package_sha256':None if inventory is None else inventory.data['package_sha256'],
        'source_byte_integrity':'TEST_ONLY' if inventory is None else 'MATCHES_PREVIOUS_RETAINED_BYTE_PINS',
        'independent_vendor_provenance':'NOT_ATTESTED','historical_pit':'NOT_ATTESTED',
        'correction_history':'UNKNOWN_NOT_ATTESTED','global_market_universe':None,
        'independent_base_shadow_opportunities':None,'costs':p['costs'],
        'scientific_result':'INSUFFICIENT_EVIDENCE','authentic_scientific_e2e':'BLOCKED',
        'holdout':'SEALED_UNOPENED','execution_authority':'NONE','independent_audit':'PENDING'})
    journal.put('result',PLAN_SHA,result.receipt())
    return result,journal.store.put(result.receipt())
