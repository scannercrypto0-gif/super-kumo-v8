"""One consolidated exact-pin Core/Discoverer/Factory TEST_ONLY regression gate."""
import argparse
from pathlib import Path
import unittest
from tools.strategy_service_offline.common import Dependencies,Frozen,RunJournal,read,raw_sha
from .run import FIXTURES,execute_test_only
from .test_gate import HistoricalGate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',required=True,action='append',metavar='COMPONENT=PATH')
    p.add_argument('--output',required=True)
    args=p.parse_args();roots=dict(x.split('=',1) for x in args.checkout)
    HistoricalGate.roots=roots
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(HistoricalGate);names=[t.id() for t in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    deps=Dependencies(FIXTURES/'dependencies.json',(FIXTURES/'dependencies.sha256').read_text().strip(),roots)
    report,key=execute_test_only(deps,args.output)
    gate=Frozen.build({'schema':'aql.work.history-integration.gate.v1','evidence_class':'TEST_ONLY',
            'passed':result.testsRun,'tests':names,'input_manifest_sha256':raw_sha(read(FIXTURES/'inputs.json')),
            'result_sha256':report.sha256,'result_object_sha256':key,'scientific_result':'INSUFFICIENT_EVIDENCE',
            'authentic_e2e':'NOT_CONNECTED','independent_audit':'PENDING'})
    RunJournal(Path(args.output)/'gate',deps).store.put(gate.receipt())
    print('RESULT_SHA256='+report.sha256)
    print('RESULT_OBJECT_SHA256='+key)
    print('GATE_SHA256='+gate.sha256)
    print('CENSUS='+str({k:report.data[k] for k in ('trial_count','candidate_count','native_factory_attempt_slots')}))
    print('SCIENTIFIC_RESULT=INSUFFICIENT_EVIDENCE; AUTHENTIC_E2E=NOT_CONNECTED')


if __name__=='__main__':main()
