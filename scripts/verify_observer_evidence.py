"""Read-only bundle validation; use the previously retained SHA, not a new guess."""
import argparse
import hashlib
import json
from pathlib import Path
from aql.binance_observer import verify_bundle
if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('file');p.add_argument('--sha256',required=True)
    args=p.parse_args();raw=Path(args.file).read_bytes()
    actual=hashlib.sha256(raw).hexdigest()
    if actual!=args.sha256: raise SystemExit('SHA256 MISMATCH')
    bundle=json.loads(raw);versions=verify_bundle(bundle,bundle['ledger_head'])
    print(json.dumps(dict(sha256=actual,ledger_head=bundle['ledger_head'],versions=len(versions),
        verified='BYTES_AND_INTERNAL_BINDINGS_ONLY',real_pit_accepted=False,independent_custody=False)))
