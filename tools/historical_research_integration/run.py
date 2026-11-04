from pathlib import Path
from tools.strategy_service_offline.common import Dependencies,Frozen,RunJournal,decode,read,raw_sha,require,canonical
from .adapters import integrate
from .inventory import inspect_retained_package,probe_original_core_format

FIXTURES=Path(__file__).parent/'fixtures'


def locked_inputs():
    raw=read(FIXTURES/'inputs.json')
    require(raw_sha(raw)==(FIXTURES/'inputs.sha256').read_text().strip(),'INPUT_MANIFEST_SHA')
    lock=decode(raw)
    for name,expected in lock['files'].items():require(raw_sha(read(FIXTURES/name))==expected,'INPUT_BYTES_CHANGED')
    return {name:decode(read(FIXTURES/name)) for name in lock['files'] if name.endswith('.json')}


def execute_test_only(deps,output):
    f=locked_inputs()
    return integrate(deps,f['core-source.json'],f['plan.json'],output)


def inspect_originals(deps,package,expected_sha,output):
    inventory=inspect_retained_package(package,expected_sha)
    probes=probe_original_core_format(deps,package,inventory.receipt()) if inventory.data['source_available'] else []
    report=Frozen.build({'schema':'aql.work.original-history-access-result.v1','inventory':inventory.receipt(),
            'core_admission_attempts':probes,'actual_strategy_evaluation':'NOT_PERFORMED',
            'raw_data_published':False,'scientific_result':'INSUFFICIENT_EVIDENCE','authentic_e2e':'NOT_CONNECTED'})
    key=RunJournal(output,deps).store.put(report.receipt())
    return report,key
