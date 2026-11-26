"""Offline CLI. Checkout provisioning is an explicit external prerequisite."""
import argparse
import json
from .harness import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True)
    p.add_argument('--expected-sha256', required=True)
    p.add_argument('--checkout', action='append', default=[], metavar='COMPONENT=PATH')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    roots = dict(item.split('=', 1) for item in args.checkout)
    key, summary = run(args.manifest, args.expected_sha256, roots, args.output)
    print(json.dumps({'summary_sha256': key, 'census': summary['census'],
                      'verdict': summary['verdict']}, sort_keys=True))


if __name__ == '__main__':
    main()
