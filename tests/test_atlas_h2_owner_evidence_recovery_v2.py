"""Owner evidence assembler v2: disposable MOCKED original parents only.

No owner key enrollment, no true publisher calls, no E: source or original H2.
The source integrity branches exercise the real signer and exact four-file
inert packet; Core245/253 and publisher are explicitly synthetic fixtures.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.atlas_h2_owner_evidence_recovery_v2 import (
    prepare_owner_private_evidence, RecoveryBlocked,
)
from tools.atlas_h2_owner_identity_v2 import identity_metadata_from_key
from tools.atlas_h2_owner_personal_batch_v1 import (
    _load_intake, scope_commitment,
)
from tools.atlas_h2_owner_identity_v2 import inspect_forward_owner_assertion


class OwnerRecoverySafeSynthetic(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.private=self.root/"private"
        self.private.mkdir()
        self.warehouse=self.private/"warehouse"
        self.warehouse.mkdir()
        self.vault=self.private/"vault"
        self.vault.mkdir()
        self.evidence=self.root/"evidence"
        self.evidence.mkdir()
        self.output=self.root/"output"
        self.output.mkdir()
        self.source=self.private/"historical"/"BTCUSDT-15m-2024-03.zip"
        self.source.parent.mkdir()
        self.source.write_bytes(b"ONLY-SYNTHETIC-TEST-ARCHIVE-NOT-REAL")
        self.source_sha=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.identity_dir=self.root/"identity"
        self.identity_dir.mkdir()
        self.key=b"SYNTHETIC-MOCK-NO-OWNER-KEY-32-BYTES-00000"
        (self.identity_dir/"owner-signing.key").write_bytes(self.key)
        created=(datetime.now(timezone.utc)-timedelta(minutes=2)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        self.identity=identity_metadata_from_key(self.key,created)
        (self.identity_dir/"owner-identity.json").write_text(
            json.dumps(self.identity))
        (self.identity_dir/"owner-revocations.json").write_text(
            json.dumps({"schema":"aql.integration.h2.owner-revocations.v2",
                        "revoked_key_ids":[]}))
        self.native={"schema":"aql.core.historical-price-custody-query.v1",
                     "price_query_sha256":"c"*64}
        self.local={"schema":"aql.core.local-history-query.v1",
                    "query_sha256":"d"*64}
        from research_wp_r0.strategy_definition import digest
        spec={"strategy_id":"h_manual_distinct_test","scope":"RESEARCH_ONLY"}
        self.ast={"definition":spec,"digest":digest(spec)}

    def _pub(self,*args,**kwargs):
        return {
            "bar_count":2976,"first_open_ms":1709251200000,
            "end_exclusive_ms":1711929600000,
            "zip_bytes_sha256":self.source_sha,
        }

    def _do(self,*,confirm=True,publisher=None):
        with patch(
            "tools.atlas_h2_owner_evidence_recovery_v2.verify_public_month",
            side_effect=lambda *a, **kw: (publisher or self._pub)()
        ), patch(
            "tools.atlas_h2_owner_evidence_recovery_v2._bounded_warehouse",
            return_value=self.warehouse
        ), patch(
            "tools.atlas_h2_owner_evidence_recovery_v2.fingerprint",
            return_value="f"*64
        ), patch(
            "tools.atlas_h2_owner_evidence_recovery_v2.verified_local_sqlite_snapshot",
            return_value=self.root/"disposable-fake-snapshot"
        ), patch(
            "tools.atlas_h2_owner_evidence_recovery_v2._real_core_dual",
            return_value=(
                self.native,self.local,
                "BINANCE-SPOT-BTCUSDT-15M-2024-03",1,"b"*64)
        ), patch(
            "tools.atlas_h2_owner_evidence_recovery_v2._manual_ast",
            return_value=(self.ast,"e"*64,"f"*64)
        ):
            return prepare_owner_private_evidence(
                source_zip=self.source,private_root=self.private,
                output_root=self.output,evidence_dir=self.evidence,
                identity_dir=self.identity_dir,confirm_sign=confirm,
                public_fetcher=publisher or self._pub)

    def test_genuine_shaped_synthetic_mock_proofs_generate_four_not_h2(self):
        result=self._do()
        self.assertEqual(result["status"],
                         "FOUR_AUTHENTIC_OWNER_LOCAL_ARTIFACTS_PREPARED_NOT_RUN")
        self.assertFalse(result["original_h2_executed"])
        self.assertEqual(set(p.name for p in self.evidence.iterdir()),{
            "technical-intake.json","owner-personal-assertion.json",
            "core245-native-receipt.json","manual-third-ast.json"})
        tech,envelope,root=_load_intake(self.evidence)
        registry=json.loads(
            (self.identity_dir/"owner-revocations.json").read_text())
        verified=inspect_forward_owner_assertion(
            envelope,owner_key_file=self.identity_dir/"owner-signing.key",
            revocation_registry=registry)
        self.assertEqual(envelope["schema"],
                         "aql.integration.h2.owner-personal-signed-identity.v2")
        self.assertEqual(envelope["assertion"]["scope"]["owner_authorization_ref"],
                         scope_commitment(
                            tech,self.output,
                            identity_binding=verified["identity_binding_sha256"]))
        self.assertEqual(verified["independent_license_review"],"NOT_ATTESTED")
        self.assertFalse(verified["original_h2_execution_permitted"])
        with self.assertRaisesRegex(
            RecoveryBlocked,"ORIGINAL_OR_PRIVATE_OUTPUT_PATH_UNSAFE"
        ): self._do()

    def test_no_owner_opt_in_blocks_without_evidence(self):
        with self.assertRaisesRegex(
            RecoveryBlocked,"OWNER_EXPLICIT_CONTEMPORANEOUS_SIGN_REQUIRED"
        ): self._do(confirm=False)
        self.assertEqual(list(self.evidence.iterdir()),[])

    def test_official_publisher_digest_drift_never_writes_evidence(self):
        def mismatch(*args,**kwargs):
            result=self._pub()
            result["zip_bytes_sha256"]="a"*64
            return result
        with self.assertRaisesRegex(
            RecoveryBlocked,"OWNER_ARCHIVE_NOT_IDENTICAL_TO_PUBLISHER"
        ): self._do(publisher=mismatch)
        self.assertEqual(list(self.evidence.iterdir()),[])

    def test_no_authentic_original_bridge_parent_returns_single_stop(self):
        with patch(
            "tools.atlas_h2_owner_evidence_recovery_v2.verify_public_month",
            side_effect=lambda *a,**kw: self._pub()
        ), patch(
            "tools.atlas_h2_owner_evidence_recovery_v2._bounded_warehouse",
            side_effect=RecoveryBlocked(
                "MISSING_OR_AMBIGUOUS_ORIGINAL_WAREHOUSE_SQLITE")
        ):
            with self.assertRaisesRegex(
                RecoveryBlocked,"MISSING_OR_AMBIGUOUS_ORIGINAL_WAREHOUSE_SQLITE"
            ):
                prepare_owner_private_evidence(
                    source_zip=self.source,private_root=self.private,
                    output_root=self.output,evidence_dir=self.evidence,
                    identity_dir=self.identity_dir,confirm_sign=True,
                    public_fetcher=self._pub)
        self.assertEqual(list(self.evidence.iterdir()),[])

    def test_revoked_new_owner_key_denied_before_evidence(self):
        (self.identity_dir/"owner-revocations.json").write_text(
            json.dumps({"schema":"aql.integration.h2.owner-revocations.v2",
                        "revoked_key_ids":[self.identity["key_id"]]}))
        with self.assertRaisesRegex(
            RecoveryBlocked,"OWNER_NEW_KEY_IDENTITY_OR_REVOCATION_INVALID"
        ): self._do()
        self.assertEqual(list(self.evidence.iterdir()),[])


if __name__=="__main__": unittest.main()
