"""Synthetic-only forward owner v2 identity and independently MACed costs tests."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest

from tools.atlas_h2_owner_identity_v2 import (
    ENVELOPE_SCHEMA, IDENTITY_SCHEMA, identity_metadata_from_key,
    inspect_forward_owner_assertion,
)
from tools.atlas_h2_owner_research_authority_v1 import AuthorityBlocked
from test_atlas_h2_owner_research_authority_v1 import (
    OwnerPersonalResearchAuthority,
)


def utc(delta=0):
    return (datetime.now(timezone.utc)+timedelta(seconds=delta)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class ForwardOnlyOwnerV2(unittest.TestCase):
    def setUp(self):
        self.fx=OwnerPersonalResearchAuthority(
            methodName="test_synthetic_both_mac_verified_but_no_license_or_original_run")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.created=utc(-30)
        self.signed=utc(-10)
        self.identity=identity_metadata_from_key(self.fx.secret,self.created)
        self.registry={"schema":"aql.integration.h2.owner-revocations.v2",
                       "revoked_key_ids":[]}

    def envelope(self):
        return {"schema":ENVELOPE_SCHEMA,"identity":self.identity,
                "signed_at_utc":self.signed,
                "assertion":self.fx.packet()}

    def inspect(self,envelope=None,registry=None,key=None):
        return inspect_forward_owner_assertion(
            self.envelope() if envelope is None else envelope,
            owner_key_file=self.fx.key if key is None else key,
            revocation_registry=self.registry if registry is None else registry)

    def test_new_identity_is_only_personal_not_external_or_original(self):
        report=self.inspect()
        self.assertEqual(report["identity_schema"],IDENTITY_SCHEMA)
        self.assertEqual(report["key_id"],self.identity["key_id"])
        self.assertEqual(report["rights_class"],"OWNER_PERSONAL_NOT_EXTERNAL")
        self.assertEqual(report["independent_license_review"],"NOT_ATTESTED")
        self.assertFalse(report["original_h2_execution_permitted"])
        self.assertFalse(report["actual_source_receipts_verified"])

    def test_identity_created_after_assertion_is_denied(self):
        doc=self.envelope()
        doc["signed_at_utc"]=utc(-120)
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_V2_RETROACTIVE_OR_FUTURE_ASSERTION"
        ): self.inspect(doc)

    def test_future_dated_identity_cannot_backdate_proof(self):
        doc=self.envelope()
        doc["identity"]["created_at_utc"]=utc(10000)
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_IDENTITY_NOT_FORWARD_CREATED"
        ): self.inspect(doc)

    def test_revoked_key_fails_before_source(self):
        reg=dict(self.registry)
        reg["revoked_key_ids"]=[self.identity["key_id"]]
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_IDENTITY_REVOKED_OR_REGISTRY_MISSING"
        ): self.inspect(registry=reg)

    def test_no_registry_fails_closed(self):
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_IDENTITY_REVOKED_OR_REGISTRY_MISSING"
        ): self.inspect(registry={})

    def test_key_switch_fails_with_no_fallback_to_legacy(self):
        other=self.fx.root/"other-owner.key"
        other.write_bytes(b"another synthetic not owner source key 00000000000")
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_IDENTITY_KEY_MISMATCH"
        ): self.inspect(key=other)

    def test_false_independent_license_class_not_accepted(self):
        doc=self.envelope()
        doc["identity"]["rights_class"]="INDEPENDENTLY_REVIEWED_LICENSE"
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_IDENTITY_SCHEMA_OR_AUTHORITY"
        ): self.inspect(doc)

    def test_scope_tampering_denied_by_actual_owner_hmac(self):
        doc=self.envelope()
        doc["assertion"]["scope"]["source_bytes_sha256"]="0"*64
        with self.assertRaisesRegex(
            AuthorityBlocked,"OWNER_SCOPE_MAC_INVALID"
        ): self.inspect(doc)


if __name__=="__main__": unittest.main()
