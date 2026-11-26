"""Reproduce the completed TEST_ONLY package without re-running development tests."""
import argparse
from .common import Dependencies,read,raw_sha
from .run import FIXTURES,execute


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',required=True,action='append',metavar='COMPONENT=PATH')
    p.add_argument('--output',required=True)
    args=p.parse_args();roots=dict(x.split('=',1) for x in args.checkout)
    deps=Dependencies(FIXTURES/'dependencies.json',(FIXTURES/'dependencies.sha256').read_text().strip(),roots)
    report,key=execute(deps,args.output)
    print('RESULT_SHA256='+report.sha256)
    print('RESULT_OBJECT_SHA256='+key)
    print('PAPER_LIVE=NOT_ACTIVATED')


if __name__=='__main__':main()
