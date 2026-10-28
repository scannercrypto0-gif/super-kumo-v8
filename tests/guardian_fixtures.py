"""Synthetic receipt only; never proof of a cloud operation."""
from aql.guardian_receipt import VAULT_ID


def receipt(key, **overrides):
    value = dict(sha256=key, remote_id='atlas_vault:' + key + '.json',
                 vault_id=VAULT_ID, download_sha256=key,
                 status='BACKUP_READBACK_VERIFIED',
                 independent_custody=False, issuer_attestation=False)
    value.update(overrides)
    return value
