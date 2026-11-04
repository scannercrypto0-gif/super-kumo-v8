import argparse
from pathlib import Path
from tools.strategy_service_offline.common import Dependencies,canonical,read
from .batch import FIXTURES,execute


def dependencies(roots):
    return Dependencies(FIXTURES/'dependencies.json',(FIXTURES/'dependencies.sha256').read_text().strip(),roots)


def main():
    p=argparse.ArgumentParser(description='Work #247: explicit TEST_ONLY or retained-original RETROSPECTIVE projection, never PIT acceptance')
    p.add_argument('--checkout',required=True,action='append',metavar='COMPONENT=PATH')
    p.add_argument('--output',required=True)
    p.add_argument('--mode',required=True,choices=['test-only','retrospective-originals'])
    p.add_argument('--package')
    a=p.parse_args();roots=dict(x.split('=',1) for x in a.checkout)
    if a.mode=='retrospective-originals' and not a.package:p.error('--package is required for retained original mode')
    deps=dependencies(roots);r,key=execute(deps,a.package,a.output,mode=a.mode)
    path=Path(a.output)/'summary.json';path.write_bytes(canonical(r.receipt()))
    print('RESULT_SHA256='+r.sha256);print('RESULT_OBJECT_SHA256='+key)
    print('STATUS='+r.data['status']);print('SCIENTIFIC_RESULT=INSUFFICIENT_EVIDENCE')


if __name__=='__main__':main()
