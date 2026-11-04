"""Explicit TEST_ONLY replay or retained-original integrity inspection, no scoring."""
import argparse
from .run import FIXTURES,execute_test_only,inspect_originals
from tools.strategy_service_offline.common import Dependencies


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',action='append',required=True,metavar='COMPONENT=PATH')
    p.add_argument('--output',required=True)
    p.add_argument('--mode',choices=('test-only','inspect-retained-originals'),required=True)
    p.add_argument('--retained-package')
    p.add_argument('--package-sha256')
    a=p.parse_args()
    deps=Dependencies(FIXTURES/'dependencies.json',(FIXTURES/'dependencies.sha256').read_text().strip(),
                       dict(x.split('=',1) for x in a.checkout))
    if a.mode=='test-only':report,key=execute_test_only(deps,a.output)
    else:
        if a.retained_package and not a.package_sha256:p.error('--package-sha256 required for an existing package')
        report,key=inspect_originals(deps,a.retained_package,a.package_sha256,a.output)
    print('RESULT_SHA256='+report.sha256)
    print('RESULT_OBJECT_SHA256='+key)
    print('SCIENTIFIC_RESULT=INSUFFICIENT_EVIDENCE; AUTHENTIC_E2E=NOT_CONNECTED')


if __name__=='__main__':main()
