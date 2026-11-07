"""Offline/verifier-only Core F5 signatures: no real approvals or private data."""
import unittest
from copy import deepcopy

from research_wp_r0.aql_core_f5_secretary_authority_v1 import (
    SOURCE_ROLE, STRATEGY_ROLE, SOURCE_SCHEMA, STRATEGY_SCHEMA,
    CUSTODIAN_ROLE, FACTORY_ROLE_SCHEMA, canonical, digest,
    _signed, _verify_external_role_attestation, _require_distinct_signers,
    pending_authority, verify_source_ack, verify_strategy_approval,
    verify_scanner_nomination,
)


class TestCoreF5AuthorityNoSyntheticApproval(unittest.TestCase):
    def test_current_default_is_wait(self):
        self.assertEqual(pending_authority(), {
            "source_ack_sha256": None, "strategy_approval_sha256": None,
            "factory_consumer_ack_sha256": None, "secretary_state": "NOT_ENQUEUED",
            "historical_pit": "NOT_ATTESTED", "trading_authority": "NONE",
        })

    def test_source_ack_requires_original_report_not_a_flag(self):
        with self.assertRaisesRegex(ValueError, "ACTUAL_F2_REPORT_REQUIRED"):
            verify_source_ack(
                {}, custodian_attestation=None, authorization_document=None,
                trusted_registry={}, trusted_role_registry={},
                trusted_now_utc="2026-11-07T05:00:00Z", f2_report={},
                source_zip_sha256="a"*64, warehouse_receipt_sha256="b"*64,
                native245_sha256="c"*64, local253_sha256="d"*64,
                month="2024-01")

    def test_strategy_approval_requires_actual_source_proof(self):
        with self.assertRaisesRegex(ValueError, "ACTUAL_F2_REPORT_REQUIRED"):
            verify_strategy_approval(
                {}, source_receipt={}, source_attestation=None,
                authorization_document=None, f2_report={},
                scanner_nomination={}, source_zip_sha256="a"*64, warehouse_receipt_sha256="b"*64,
                native245_sha256="c"*64, local253_sha256="d"*64,
                month="2024-01", strategy_nomination_sha256="e"*64,
                independent_policy_sha256="f"*64,
                evaluator_receipt_sha256="0"*64,
                strategy_definition_sha256="1"*64,
                policy_attestation=None, evaluator_attestation=None,
                trusted_registry={}, trusted_role_registry={},
                trusted_now_utc="2026-11-07T05:00:00Z")

    def test_missing_trust_root_and_wrong_external_witness_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROLE_FIELDS"):
            _verify_external_role_attestation(
                None, role=CUSTODIAN_ROLE, subject_sha256="a"*64,
                trusted_role_registry={}, trusted_now_utc="2026-11-07T05:00:00Z")
        with self.assertRaisesRegex(ValueError, "SIGNER_ROLE_ALIAS"):
            _require_distinct_signers([("same", "abc"), ("same", "def")])


    def test_scanner_nomination_never_promotes_by_sha_alone(self):
        body = {
            "schema":"aql.scanner-f.original-research-nomination.v1",
            "decision":"NOMINATED_RESEARCH_ONLY","selected":False,
            "secretary_status":"NOT_ENQUEUED","factory_lab":"NOT_EVALUATED",
            "paper":"NOT_ACTIVATED","holdout":"SEALED",
            "historical_pit":"NOT_ATTESTED",
            "research_class":"RETROSPECTIVE_NON_PIT","trading_authority":"NONE",
            "core_source_ack_sha256":None,
            "core_secretary_strategy_approval_sha256":None,
            "factory_consumer_ack_sha256":None,
            "core_f2_report_sha256":"daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40",
            "verified_policy_approval_sha256":"a"*64,
            "signed_evaluator_receipt_sha256":"b"*64,
            "strategy_definition_digest":"c"*64,
            "month":"2024-01","symbol":"BTCUSDT","timeframe":"15m",
            "market":"BINANCE:SPOT:USDT",
            "warehouse_receipt_sha256":"d"*64,
            "core245_native_query_sha256":"e"*64,
            "core253_local_query_sha256":"f"*64,
            "strategy_decision_sha256":"1"*64,
            "source_bound_census_sha256":"2"*64,
            "verified_independent_evaluator_sha256":"3"*64,
            "dna_digest":"4"*64,"native15m_config_digest":"5"*64,
            "dual_query_map_sha256":"6"*64,
            "strategy_id":"test_momentum","strategy_version":"v1",
            "cutoff_ms":1738368000000,
            "last_evaluated_open_ms":1735688700000,
        }
        receipt={"payload":body,"sha256":digest(body)}
        args={
            "nomination_sha256":receipt["sha256"],
            "independent_policy_sha256":"a"*64,
            "evaluator_receipt_sha256":"b"*64,
            "strategy_definition_sha256":"c"*64,
            "expected_f2_report_sha256":body["core_f2_report_sha256"],
            "month":"2024-01","warehouse_receipt_sha256":"d"*64,
            "native245_sha256":"e"*64,"local253_sha256":"f"*64,
        }
        self.assertEqual(verify_scanner_nomination(receipt,**args),body)
        # This seal is a contract fixture only. It is not external policy/evaluator
        # authority, a strategy approval, or a real original-bar run.
        for field,value in (("selected",True),("month","2024-02"),
                            ("core253_local_query_sha256","a"*64),
                            ("secretary_status","ENQUEUED")):
            forged={**body,field:value}
            new_receipt={"payload":forged,"sha256":digest(forged)}
            with self.subTest(field=field),self.assertRaisesRegex(
                    ValueError,"SCANNER_NOMINATION"):
                verify_scanner_nomination(
                    new_receipt,**{**args,"nomination_sha256":new_receipt["sha256"]})


@unittest.skipUnless(__import__("importlib").util.find_spec("cryptography") is not None,
                     "cryptography required for ephemeral signature verifier tests")
class TestCoreF5Ed25519VerifierOnly(unittest.TestCase):
    """All keys generated inside tests and never used as genuine owner evidence."""

    @staticmethod
    def _key():
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        sk = Ed25519PrivateKey.generate()
        public = sk.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        return sk, public.hex()

    def _external_witness(self, *, sk, subject, role, kid, approver):
        signed = {
            "schema": FACTORY_ROLE_SCHEMA, "role": role,
            "key_id": kid, "approver_id": approver,
            "subject_sha256": subject,
            "issued_at_utc": "2026-11-07T04:00:00Z",
            "expires_at_utc": "2026-11-07T06:00:00Z",
        }
        signed["signature_hex"] = sk.sign(canonical(signed)).hex()
        return signed

    def test_ephemeral_external_custodian_signature_verified_and_tamper_rejected(self):
        private, public = self._key()
        src_digest = "a"*64
        att = self._external_witness(sk=private, subject=src_digest,
                                     role=CUSTODIAN_ROLE,
                                     kid="test-only-source-key",approver="test-only-custodian")
        registry = {CUSTODIAN_ROLE: {
            "key_id": "test-only-source-key",
            "approver_id": "test-only-custodian",
            "public_key_hex": public, "enabled": True,
        }}
        self.assertEqual(_verify_external_role_attestation(
            att, role=CUSTODIAN_ROLE, subject_sha256=src_digest,
            trusted_role_registry=registry,
            trusted_now_utc="2026-11-07T05:00:00Z"), digest(att))
        fake = deepcopy(att)
        fake["subject_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROLE_SUBJECT_DRIFT"):
            _verify_external_role_attestation(
                fake, role=CUSTODIAN_ROLE,subject_sha256=src_digest,
                trusted_role_registry=registry,
                trusted_now_utc="2026-11-07T05:00:00Z")
        expired = deepcopy(att)
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROLE_EXPIRED_OR_FUTURE"):
            _verify_external_role_attestation(
                expired, role=CUSTODIAN_ROLE, subject_sha256=src_digest,
                trusted_role_registry=registry,
                trusted_now_utc="2026-11-07T07:00:00Z")
        forged = deepcopy(att)
        forged["approver_id"] = "test-only-fake"
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROLE_REGISTRY_DRIFT"):
            _verify_external_role_attestation(
                forged, role=CUSTODIAN_ROLE,subject_sha256=src_digest,
                trusted_role_registry=registry,
                trusted_now_utc="2026-11-07T05:00:00Z")
        invalid_signature = deepcopy(att)
        invalid_signature["signature_hex"] = "0"*128
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROLE_BAD_SIGNATURE"):
            _verify_external_role_attestation(
                invalid_signature,role=CUSTODIAN_ROLE,subject_sha256=src_digest,
                trusted_role_registry=registry,
                trusted_now_utc="2026-11-07T05:00:00Z")
        disabled = deepcopy(registry)
        disabled[CUSTODIAN_ROLE]["enabled"] = False
        with self.assertRaisesRegex(ValueError, "EXTERNAL_ROLE_REGISTRY_DRIFT"):
            _verify_external_role_attestation(
                att,role=CUSTODIAN_ROLE,subject_sha256=src_digest,
                trusted_role_registry=disabled,
                trusted_now_utc="2026-11-07T05:00:00Z")

    def test_ephemeral_core_source_ack_crypto_only_not_an_original_positive(self):
        sk, pub = self._key()
        body = {
            "schema": SOURCE_SCHEMA, "issuer_role": SOURCE_ROLE,
            "approver_identity": "test-only-core-source",
            "key_id": "test-only-core-source-id",
            "not_before_utc": "2026-11-07T04:00:00Z",
            "expires_at_utc": "2026-11-07T06:00:00Z",
            "signature_scheme": "Ed25519",
            "research_scope": "RETROSPECTIVE_NON_PIT",
            "historical_pit": "NOT_ATTESTED", "trading_authority": "NONE",
            "source_ack_sha256": None,
            "payload_sha256": "a"*64,
        }
        receipt = {**body, "signature": sk.sign(canonical(body)).hex()}
        registry = {"test-only-core-source-id": {
            "public_key_hex":pub, "approver_identity":"test-only-core-source",
            "authority":SOURCE_ROLE, "enabled":True}}
        self.assertEqual(_signed(SOURCE_ROLE, receipt,trusted_registry=registry,
                                 trusted_now_utc="2026-11-07T05:00:00Z"), digest(receipt))
        mutated=deepcopy(receipt)
        mutated["payload_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"SIGNATURE_INVALID"):
            _signed(SOURCE_ROLE, mutated, trusted_registry=registry,
                    trusted_now_utc="2026-11-07T05:00:00Z")
        badrole=deepcopy(registry)
        badrole["test-only-core-source-id"]["authority"]=STRATEGY_ROLE
        with self.assertRaisesRegex(ValueError,"SIGNER_ROLE_UNTRUSTED"):
            _signed(SOURCE_ROLE, receipt,trusted_registry=badrole,
                    trusted_now_utc="2026-11-07T05:00:00Z")


if __name__=="__main__":
    unittest.main()
