"""Forward-only OWNER identity v2; never grants historical rights or source admission.

Owner enrollment is an explicit LOCAL ceremony, not part of this module.
Verification reuses the v1 HMAC scope+cost validator but binds fresh identity
metadata, owner key fingerprint, nonce, approval time and revocation registry.
No key generation, owner signing, or original dataset reads in this verifier.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path

from tools.atlas_h2_owner_research_authority_v1 import (
    AuthorityBlocked, _digest, _need, inspect_owner_assertion,
)

IDENTITY_SCHEMA = "aql.integration.h2.owner-identity.v2"
ENVELOPE_SCHEMA = "aql.integration.h2.owner-personal-signed-identity.v2"


def _timestamp(value):
    _need(type(value) is str and value.endswith("Z"),
          "OWNER_IDENTITY_TIMESTAMP_INVALID")
    try:
        return datetime.fromisoformat(value[:-1]+"+00:00")
    except ValueError:
        raise AuthorityBlocked("OWNER_IDENTITY_TIMESTAMP_INVALID") from None


def _identity_check(identity, key_file, registry):
    _need(type(identity) is dict
          and set(identity) == {
              "schema", "key_id", "created_at_utc", "activation",
              "custody", "rights_class",
          }
          and identity["schema"] == IDENTITY_SCHEMA
          and identity["activation"] == "FORWARD_ONLY"
          and identity["custody"] == "OWNER_LOCAL"
          and identity["rights_class"] == "OWNER_PERSONAL_NOT_EXTERNAL",
          "OWNER_IDENTITY_SCHEMA_OR_AUTHORITY")
    key_path=Path(key_file)
    _need(key_path.is_file() and not key_path.is_symlink()
          and 32 <= key_path.stat().st_size <= 4096,
          "OWNER_IDENTITY_PRIVATE_KEY_ABSENT")
    key=key_path.read_bytes()
    key_id=hashlib.sha256(b"ATLAS-H2-OWNER-IDENTITY-V2\0"+key).hexdigest()
    _need(type(identity["key_id"]) is str and
          hmac.compare_digest(identity["key_id"],key_id),
          "OWNER_IDENTITY_KEY_MISMATCH")
    created=_timestamp(identity["created_at_utc"])
    _need(created <= datetime.now(timezone.utc)
          and created.year >= 2026,
          "OWNER_IDENTITY_NOT_FORWARD_CREATED")
    _need(type(registry) is dict
          and set(registry) == {"schema","revoked_key_ids"}
          and registry["schema"] == "aql.integration.h2.owner-revocations.v2"
          and type(registry["revoked_key_ids"]) is list
          and all(type(i) is str and len(i)==64
                  for i in registry["revoked_key_ids"])
          and key_id not in registry["revoked_key_ids"],
          "OWNER_IDENTITY_REVOKED_OR_REGISTRY_MISSING")
    return key_id


def inspect_forward_owner_assertion(envelope, *, owner_key_file,
                                    revocation_registry):
    """Verify an owner-created NEW assertion; never create or backdate it."""
    _need(type(envelope) is dict and set(envelope) == {
        "schema", "identity", "assertion", "signed_at_utc",
    } and envelope["schema"] == ENVELOPE_SCHEMA,
          "OWNER_V2_ENVELOPE_SCHEMA")
    identity=envelope["identity"]
    key_id=_identity_check(identity, owner_key_file, revocation_registry)
    signed=_timestamp(envelope["signed_at_utc"])
    created=_timestamp(identity["created_at_utc"])
    _need(signed>=created and signed<=datetime.now(timezone.utc),
          "OWNER_V2_RETROACTIVE_OR_FUTURE_ASSERTION")
    assertion=envelope["assertion"]
    result=inspect_owner_assertion(
        assertion, trusted_owner_verifier_key=owner_key_file)
    _need(result["original_h2_execution_permitted"] is False,
          "OWNER_IDENTITY_MUST_NOT_GRANT_AUTHORITY")
    return {**result,
            "identity_schema": IDENTITY_SCHEMA,
            "envelope_schema": ENVELOPE_SCHEMA,
            "key_id":key_id,
            "created_at_utc":identity["created_at_utc"],
            "signed_at_utc":envelope["signed_at_utc"],
            "rights_class":"OWNER_PERSONAL_NOT_EXTERNAL",
            "identity_binding_sha256":_digest({
                "identity":identity,
                "signed_at_utc":envelope["signed_at_utc"],
            })}


def identity_metadata_from_key(key, created_at_utc):
    """Pure helper for owner-local ceremony; never writes or signs."""
    return {
        "schema":IDENTITY_SCHEMA,
        "key_id":hashlib.sha256(
            b"ATLAS-H2-OWNER-IDENTITY-V2\0"+key).hexdigest(),
        "created_at_utc":created_at_utc,
        "activation":"FORWARD_ONLY",
        "custody":"OWNER_LOCAL",
        "rights_class":"OWNER_PERSONAL_NOT_EXTERNAL",
    }
