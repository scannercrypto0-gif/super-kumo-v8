"""Single consolidated integration verification and deterministic fixture delivery."""
import argparse
from pathlib import Path
import unittest
from .test_gate import IntegrationGate, FIXTURES
from .harness import ReceiptStore, run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout',action='append',required=True,metavar='COMPONENT=PATH')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    roots=dict(x.split('=',1) for x in args.checkout)
    IntegrationGate.roots=roots
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationGate)
    names=[test.id() for test in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    expected=(FIXTURES/'manifest.sha256').read_text().strip()
    key,summary=run(FIXTURES/'manifest.json',expected,roots,Path(args.output)/'receipts')
    store=ReceiptStore(Path(args.output)/'gate')
    gate_sha=store.put({'schema':'aql.work.offline-integration-gate.v1','evidence_class':'TEST_ONLY',
                        'tests':names,'passed':result.testsRun,'summary_sha256':key,
                        'fixture_manifest_raw_sha256':expected,'census':summary['census']})
    print('SUMMARY_SHA256='+key)
    print('GATE_SHA256='+gate_sha)
    print('VERDICT=TEST_ONLY_CONTRACT_GATE; AUTHENTIC_E2E_NOT_CONNECTED')


if __name__=='__main__':main()
