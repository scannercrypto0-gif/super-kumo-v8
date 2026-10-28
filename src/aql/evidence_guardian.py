"""Optional separate-process backup verifier. No issuer/custody authority."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from aql.binance_observer import verify_bundle
from aql.evidence_outbox import encode

VAULT_ID = '1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q'

class RcloneDriveSender:
    """Use an operator-configured rclone Google Drive remote, rooted by ID.

    Credentials remain in the owner's rclone config. Every acknowledgement
    requires downloading bytes through rclone, not trusting upload metadata.
    Retries use content-addressed names; immutable refuses overwrite conflicts.
    """
    def __init__(self, remote, *, timeout=45, runner=subprocess.run):
        if not remote.endswith(':') or '/' in remote or '\\' in remote or remote.startswith('-'):
            raise ValueError('expected configured rclone remote name ending in colon')
        self.remote, self.timeout, self.runner = remote, timeout, runner

    def command(self, args, *, data=None):
        return self.runner(['rclone', *args, '--drive-root-folder-id', VAULT_ID],
            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=self.timeout, check=True).stdout

    def __call__(self, bundle, sha):
        blob = encode(bundle)
        if hashlib.sha256(blob).hexdigest() != sha:
            raise ValueError('outbox digest mismatch')
        verify_bundle(bundle, bundle['ledger_head'])
        target = self.remote + sha + '.json'
        # Check an existing copy first: recovery after upload-before-local-ack exit.
        try:
            downloaded = self.command(['cat', target])
        except subprocess.CalledProcessError as exc:
            if exc.returncode not in (3, 4):
                raise
            with tempfile.TemporaryDirectory() as directory:
                local = Path(directory)/'bundle.json'
                local.write_bytes(blob)
                self.command(['copyto', str(local), target, '--immutable'])
            downloaded = self.command(['cat', target])
        if hashlib.sha256(downloaded).hexdigest() != sha:
            raise ValueError('Drive readback digest mismatch; no acknowledgement')
        verify_bundle(json.loads(downloaded), bundle['ledger_head'])
        return dict(sha256=sha, remote_id=target, vault_id=VAULT_ID,
                    download_sha256=hashlib.sha256(downloaded).hexdigest(),
                    status='BACKUP_READBACK_VERIFIED',
                    independent_custody=False, issuer_attestation=False)
