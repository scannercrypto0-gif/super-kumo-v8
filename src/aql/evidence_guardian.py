"""Optional separate-process backup verifier. No issuer/custody authority."""
import hashlib
import json
import subprocess
import tempfile
import re
from pathlib import Path
from aql.binance_observer import verify_bundle
from aql.evidence_outbox import encode
from aql.guardian_receipt import VAULT_ID


class GuardianError(Exception):
    """Fixed non-secret diagnostic; no subprocess output or argv retained."""
    CODES = {'REMOTE_TIMEOUT_UNKNOWN', 'REMOTE_DIRECTORY_MISSING', 'REMOTE_TRANSIENT',
             'REMOTE_COMMAND_FAILED_REVIEW_REQUIRED', 'SENDER_PERMISSION_DENIED',
             'SENDER_IO_FAILED', 'INVALID_BUNDLE_OR_READBACK',
             'OUTBOX_DIGEST_MISMATCH', 'REMOTE_CONTENT_CONFLICT'}
    def __init__(self, code, retryable=False):
        if code not in self.CODES:
            code, retryable = 'REMOTE_COMMAND_FAILED_REVIEW_REQUIRED', False
        self.code, self.retryable = code, retryable
        super().__init__(code)

class RcloneDriveSender:
    """Use an operator-configured rclone Google Drive remote, rooted by ID.

    Credentials remain in the owner's rclone config. Every acknowledgement
    requires downloading bytes through rclone, not trusting upload metadata.
    Retries use content-addressed names; immutable refuses overwrite conflicts.
    """
    def __init__(self, remote, *, timeout=45, runner=subprocess.run):
        if not isinstance(remote, str) or not re.fullmatch(r'[A-Za-z0-9_-]+:', remote):
            raise ValueError('expected configured rclone remote name ending in colon')
        self.remote, self.timeout, self.runner = remote, timeout, runner

    def command(self, args, *, data=None):
        return self.runner(['rclone', *args, '--drive-root-folder-id', VAULT_ID],
            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=self.timeout, check=True).stdout

    def __call__(self, bundle, sha):
        try:
            return self._send(bundle, sha)
        except GuardianError:
            raise
        except subprocess.TimeoutExpired:
            raise GuardianError('REMOTE_TIMEOUT_UNKNOWN', True) from None
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 3:
                raise GuardianError('REMOTE_DIRECTORY_MISSING') from None
            if exc.returncode in (5, 8, 9, 10):
                raise GuardianError('REMOTE_TRANSIENT', True) from None
            raise GuardianError('REMOTE_COMMAND_FAILED_REVIEW_REQUIRED') from None
        except PermissionError:
            raise GuardianError('SENDER_PERMISSION_DENIED') from None
        except OSError:
            raise GuardianError('SENDER_IO_FAILED', True) from None
        except (ValueError, KeyError, TypeError):
            raise GuardianError('INVALID_BUNDLE_OR_READBACK') from None

    def _send(self, bundle, sha):
        blob = encode(bundle)
        if hashlib.sha256(blob).hexdigest() != sha:
            raise GuardianError('OUTBOX_DIGEST_MISMATCH')
        verify_bundle(bundle, bundle['ledger_head'])
        target = self.remote + sha + '.json'
        # Check an existing copy first: recovery after upload-before-local-ack exit.
        try:
            downloaded = self.command(['cat', target])
        except subprocess.CalledProcessError as exc:
            # Missing directory (3) is not permission to attempt an upload.
            if exc.returncode != 4:
                raise
            with tempfile.TemporaryDirectory() as directory:
                local = Path(directory)/'bundle.json'
                local.write_bytes(blob)
                self.command(['copyto', str(local), target, '--immutable'])
            downloaded = self.command(['cat', target])
        if hashlib.sha256(downloaded).hexdigest() != sha:
            raise GuardianError('REMOTE_CONTENT_CONFLICT')
        verify_bundle(json.loads(downloaded), bundle['ledger_head'])
        return dict(version=1, sha256=sha, remote_id=target, vault_id=VAULT_ID,
                    download_sha256=hashlib.sha256(downloaded).hexdigest(),
                    status='BACKUP_READBACK_VERIFIED',
                    independent_custody=False, issuer_attestation=False)
