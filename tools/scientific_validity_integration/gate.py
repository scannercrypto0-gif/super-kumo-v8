import argparse
from pathlib import Path
import unittest
from tools.strategy_service_offline.common import Dependencies,canonical
from .integration import FIXTURES,execute,retained_inputs
from .fixture import fixture


def dependencies(roots):
    return Dependencies(FIXTURES/'dependencies.json',(FIXTURES/'dependencies.sha256').read_text().strip(),roots)


def main():
    p=argparse.ArgumentParser(description='Work #251 new metadata-only evidence contracts, no accepted research rerun')
    p.add_argument('--checkout',action='append',required=True);p.add_argument('--output',required=True)
    p.add_argument('--retained-receipts');a=p.parse_args();roots=dict(x.split('=',1) for x in a.checkout)
    deps=dependencies(roots)
    if a.retained_receipts:
        result,key=execute(deps,retained_inputs(a.retained_receipts),a.output,evidence_class='RETAINED_AUDIT248_ACCEPTED_RECEIPTS')
    else:
        from .test_integration import ValidityGate
        ValidityGate.roots=roots
        tests=unittest.defaultTestLoader.loadTestsFromTestCase(ValidityGate)
        outcome=unittest.TextTestRunner(verbosity=2).run(tests)
        if not outcome.wasSuccessful():raise SystemExit(1)
        result,key=execute(deps,[fixture()],a.output,evidence_class='TEST_ONLY')
    (Path(a.output)/'result.json').write_bytes(canonical(result.receipt()))
    print('RESULT_SHA256='+result.sha256);print('RESULT_OBJECT_SHA256='+key)
    print('SCIENTIFIC_RESULT=INSUFFICIENT_EVIDENCE; OLD_REPORT_RERUNS=0; RETURNS_RECOMPUTED=FALSE')


if __name__=='__main__':main()
