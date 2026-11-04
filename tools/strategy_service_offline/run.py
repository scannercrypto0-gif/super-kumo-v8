"""Executable isolated package: TEST_ONLY screening + decision handoff + independent research."""
from pathlib import Path
from .common import Dependencies, Frozen, RunJournal, decode, digest, read, raw_sha, require, confined, BoundaryError
from .screening import StrategyScreeningSpec, scan
from .routing import route, TestOnlyStrategySink
from .research import independent_research

FIXTURES=Path(__file__).parent/'fixtures'


def inputs(root=FIXTURES):
    root=Path(root)
    raw=read(root/'inputs.json')
    require(raw_sha(raw)==(root/'inputs.sha256').read_text().strip(),'TEST_INPUT_LOCK_DRIFT')
    lock=decode(raw)
    require(lock['evidence_class']=='TEST_ONLY','PRIVATE_INPUT_NOT_AUTHORIZED')
    for path,expected in lock['files'].items():
        require(raw_sha(read(confined(root,path)))==expected,'TEST_INPUT_BYTES_DRIFT')
    return {p:decode(read(root/p)) for p in lock['files'] if p.endswith('.json')}


def execute(deps, output, *, fixture_root=FIXTURES):
    f=inputs(fixture_root)
    specs=[StrategyScreeningSpec.restore_spec(x) for x in f['strategies.json']]
    source=read(Path(fixture_root)/'source.json');manifest=f['source-manifest.json']
    try:
        scan_result=scan(specs,source,manifest,f['universe.json'],cutoff_ms=manifest['cutoff_ms'],symbol_budget=3,deps=deps)
    except BoundaryError as exc:
        scan_result=Frozen.build({'schema':'aql.strategy-aware-scan-refusal.v1','nominations':[],
            'status':'CONTRACT_BLOCKED','error_code':str(exc),'denominator':'UNKNOWN_CONFLICTING_INPUT',
            'paper_activation':'NOT_AUTHORIZED','authentic_route':'NOT_CONNECTED'})
    journal=RunJournal(Path(output)/'routing',deps)
    receipts=[];unconnected=[]
    for s in specs:
        # Fixture decisions belong to these explicit strategy test consumers.
        decision='ACCEPT' if s.data['strategy_id']=='test_momentum' else 'WAIT'
        sink=TestOnlyStrategySink(s,RunJournal(Path(output)/('sink-'+s.data['strategy_id']),deps),
                                 lambda n,d=decision:d,decision_policy_id='test_policy_'+decision.lower()+'_v1')
        for n in scan_result.data['nominations']:
            if n['payload']['strategy_id']==s.data['strategy_id'] and n['payload']['status']=='SELECTED':
                receipts.append(route(n,s,journal,test_sink=sink).receipt())
                unconnected.append(route(n,s,RunJournal(Path(output)/'unconnected',deps)).receipt())
    research=independent_research(f['research-plan.json'],RunJournal(Path(output)/'research',deps),deps,
                                  factory_fixture=f['factory-test-input.json'])
    report=Frozen.build({'schema':'aql.work.strategy-service.package-result.v1','evidence_class':'TEST_ONLY',
        'scan':scan_result.receipt(),'strategy_test_decisions':receipts,'unconnected_paper_decisions':unconnected,
        'research':research.receipt(),'component_shas':{n:s['commit_sha'] for n,s in deps.lock['components'].items()},
        'real_integrations':{'strategy_definition_registry':'CONNECTED_VERIFIED_RESEARCH_CONTRACT_ONLY',
            'indicator_math':'CONNECTED_VERIFIED_TEST_ONLY_KERNELS',
            'approved_paper_strategy_registry':'NOT_CONNECTED','paper_consumer':'PAPER_CONSUMER_NOT_CONNECTED',
            'authentic_source_verifier':'NOT_CONNECTED','independent_discoverer_templates':'CONNECTED_VERIFIED_TEST_ONLY',
            'factory_descriptive_fixture_port':'CONNECTED_VERIFIED_TEST_ONLY',
            'authentic_factory_strategy_evaluation':'NOT_CONNECTED'},
        'scanner_origin_research_feedback':'OPTIONAL_QUARANTINED_NOT_REQUIRED',
        'paper_execution':'NOT_ACTIVATED','live_execution':'NOT_ACTIVATED','g0':'NOT_APPROVED',
        'independent_audit':'PENDING','verdict':'TEST_ONLY_IMPLEMENTED_NOT_PAPER_READY'})
    store=RunJournal(Path(output)/'package',deps).store
    object_sha=store.put(report.receipt())
    return report,object_sha
