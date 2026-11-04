"""ONE consolidated focused TEST_ONLY critical-boundary verification."""
import argparse
from pathlib import Path
import unittest
from tools.strategy_service_offline.common import Frozen,RunJournal,canonical,raw_sha
from .__main__ import dependencies
from .batch import execute,PLAN_SHA
from .test_batch import BatchGate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkout',action='append',required=True)
    p.add_argument('--output',required=True);a=p.parse_args();roots=dict(x.split('=',1) for x in a.checkout)
    BatchGate.roots=roots;suite=unittest.defaultTestLoader.loadTestsFromTestCase(BatchGate)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    deps=dependencies(roots)
    # One full 53-candidate integration on a native synthetic ZIP, fresh receipt
    # stores twice; comparison is required integration verification, not tuning.
    first,key=execute(deps,None,Path(a.output)/'first',mode='test-only')
    second,key2=execute(deps,None,Path(a.output)/'second',mode='test-only')
    if first.payload!=second.payload or key!=key2:raise ValueError('DETERMINISM_FAILURE')
    gate=Frozen.build({'schema':'aql.work.original-history-batch-gate.v1','evidence_class':'TEST_ONLY',
        'tests_passed':result.testsRun,'plan_sha256':PLAN_SHA,'result_sha256':first.sha256,
        'result_object_sha256':key,'same_inputs_twice':'CANONICAL_BYTES_IDENTICAL',
        'scientific_result':'INSUFFICIENT_EVIDENCE','private_originals_in_ci':False})
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    (root/'gate.json').write_bytes(canonical(gate.receipt()))
    (root/'summary.json').write_bytes(canonical(first.receipt()))
    print('RESULT_SHA256='+first.sha256);print('RESULT_OBJECT_SHA256='+key);print('GATE_SHA256='+gate.sha256)
    print('TEST_ONLY; PRIVATE_ORIGINALS_NOT_IN_CI; SCIENTIFIC_RESULT=INSUFFICIENT_EVIDENCE')


if __name__=='__main__':main()
