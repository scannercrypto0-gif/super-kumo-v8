"""Separate Windows 1 process: no network/time service wait in Core capture."""
import argparse
import json
import time
from pathlib import Path
from aql.utc_sampler import collect
from aql.observer_runtime import atomic_json

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--directory', required=True)
    p.add_argument('--once', action='store_true')
    args = p.parse_args()
    root = Path(args.directory)
    while True:
        try:
            session = json.loads((root/'runtime-session.json').read_text())['observer_session']
            result = collect(session)
        except Exception as exc:
            result = dict(status='UNKNOWN', reason=type(exc).__name__)
        atomic_json(root/'utc-sample.json', result)
        print(json.dumps(dict(status='SAMPLE_RECORDED', detail=result.get('reason'))), flush=True)
        if args.once:
            break
        time.sleep(20)
