"""Run only as a separate process; safe to stop while Core captures."""
import argparse
import json
import time
from aql.evidence_outbox import EvidenceOutbox
from aql.evidence_guardian import RcloneDriveSender

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--outbox', required=True, help='Core outbox directory; read/write for ACK')
    p.add_argument('--remote', required=True, help='configured rclone Google Drive remote, e.g. atlas:')
    p.add_argument('--once', action='store_true')
    args = p.parse_args()
    q = EvidenceOutbox(args.outbox)
    sender = RcloneDriveSender(args.remote)
    while True:
        print(json.dumps(q.deliver(sender)), flush=True)
        if args.once:
            break
        time.sleep(15)
