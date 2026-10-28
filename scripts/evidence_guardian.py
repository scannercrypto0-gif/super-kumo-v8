"""Local preflight ONLY. Continuous and once-only delivery remain on HOLD."""
import argparse
import json
import sys
sys.dont_write_bytecode = True
from aql.guardian_launch import LaunchError, preflight


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--contract')
    p.add_argument('--expected-contract-sha256')
    # Recognize legacy invocations to fail with HOLD before any queue mutation.
    p.add_argument('--outbox')
    p.add_argument('--remote')
    p.add_argument('--once', action='store_true')
    args = p.parse_args(argv)
    if (not args.preflight or not args.contract or not args.expected_contract_sha256
            or args.outbox or args.remote or args.once):
        print(json.dumps(dict(status='CONTINUOUS_ENABLEMENT_HOLD')))
        return 2
    try:
        print(json.dumps(preflight(args.contract, args.expected_contract_sha256)))
        return 0
    except LaunchError as exc:
        print(json.dumps(dict(status='PREFLIGHT_REJECTED', code=str(exc),
                              continuous_enablement='HOLD')))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
