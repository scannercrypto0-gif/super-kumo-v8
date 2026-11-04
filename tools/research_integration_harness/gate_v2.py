"""One consolidated current Core/Factory/Scanner/Discoverer TEST_ONLY seam gate."""
import argparse
from pathlib import Path
import unittest
from .harness import ReceiptStore
from .seams_v2 import run_v2
from .test_seams_v2 import FIXTURES, SeamIntegrationGate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout',action='append',required=True,metavar='COMPONENT=PATH')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    roots=dict(x.split('=',1) for x in args.checkout)
    SeamIntegrationGate.roots=roots
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SeamIntegrationGate)
    names=[test.id() for test in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    expected=(FIXTURES/'manifest.sha256').read_text().strip()
    key,summary=run_v2(FIXTURES/'manifest.json',expected,roots,Path(args.output)/'receipts')
    gate=ReceiptStore(Path(args.output)/'gate').put({
        'schema':'aql.work.research-boundary-gate.v2','evidence_class':'TEST_ONLY',
        'tests':names,'passed':result.testsRun,'summary_sha256':key,
        'fixture_manifest_raw_sha256':expected,'result':'TEST_ONLY_CONTRACT_BOUNDARY_GATE',
        'authentic_paths':'NOT_CONNECTED','independent_audit':'PENDING'})
    print('MANIFEST_SHA256='+expected)
    print('SUMMARY_SHA256='+key)
    print('GATE_SHA256='+gate)
    print('COUNTS='+str({k:summary[k] for k in ('factory_pairs','factory_arm_slots','discoverer_attempts','discoverer_eligible')}))
    print('AUTHENTIC_PATHS=NOT_CONNECTED; SCANNER_P0_QUARANTINE=UNKNOWN_DEFERRED')


if __name__=='__main__':main()
