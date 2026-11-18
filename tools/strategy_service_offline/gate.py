"""ONE consolidated TEST_ONLY strategy-service and independent research gate."""
import argparse
from pathlib import Path
import unittest
from .common import Dependencies, Frozen, RunJournal, read, raw_sha
from .test_gate import PackageGate
from .run import FIXTURES,execute


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',required=True,action='append',metavar='COMPONENT=PATH')
    p.add_argument('--output',required=True)
    args=p.parse_args();roots=dict(x.split('=',1) for x in args.checkout)
    PackageGate.roots=roots
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PackageGate)
    names=[t.id() for t in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    deps=Dependencies(FIXTURES/'dependencies.json',(FIXTURES/'dependencies.sha256').read_text().strip(),roots)
    report,object_key=execute(deps,args.output)
    gate=Frozen.build({'schema':'aql.work.strategy-service.gate.v1','evidence_class':'TEST_ONLY',
        'tests':names,'passed':result.testsRun,'input_manifest_sha256':raw_sha(read(FIXTURES/'inputs.json')),
        'result_sha256':report.sha256,'result_object_sha256':object_key,
        'verdict':'TEST_ONLY_IMPLEMENTED_NOT_PAPER_READY','independent_audit':'PENDING'})
    RunJournal(Path(args.output)/'gate',deps).store.put(gate.receipt())
    print('RESULT_SHA256='+report.sha256)
    print('RESULT_OBJECT_SHA256='+object_key)
    print('GATE_SHA256='+gate.sha256)
    print('AUTHENTIC_PAPER_REGISTRY=NOT_CONNECTED; PAPER_CONSUMER=PAPER_CONSUMER_NOT_CONNECTED')
    print('PRIVATE_RUN=NOT_PERFORMED; PAPER_LIVE=NOT_ACTIVATED; G0=NOT_APPROVED')


if __name__=='__main__':main()
