"""Guardian readback receipts: local integrity, never independent custody."""
import re

VAULT_ID = '1WeOdQ4COL89w4uqX-BnGGM4_xFYZHB9q'
REMOTE = 'atlas_vault:'


def validate_receipt(receipt, key):
    """Accept original unversioned Guardian receipts and explicit v1 unchanged.

    Arbitrary sender ACKs are not readback evidence. No migration/rewrite.
    Protected local ACLs remain necessary; this is not issuer authentication.
    """
    if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
        raise ValueError('INVALID_OBJECT_ID')
    if not isinstance(receipt, dict):
        raise ValueError('INVALID_RECEIPT')
    if 'version' in receipt and (type(receipt['version']) is not int or receipt['version'] != 1):
        raise ValueError('UNSUPPORTED_RECEIPT_VERSION')
    target = receipt.get('remote_id')
    # Legacy Guardian accepted other bare configured remotes, e.g. atlas:.
    if (not isinstance(target, str) or not re.fullmatch(
            r'[A-Za-z0-9_-]+:' + re.escape(key) + r'\.json', target)
            or receipt.get('sha256') != key
            or receipt.get('download_sha256') != key
            or receipt.get('vault_id') != VAULT_ID
            or receipt.get('status') != 'BACKUP_READBACK_VERIFIED'
            or receipt.get('independent_custody') is not False
            or receipt.get('issuer_attestation') is not False):
        raise ValueError('INVALID_READBACK_RECEIPT')
    return receipt
