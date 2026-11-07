"""Fail-closed Core F5 authority verifier tests; never sign or approve."""
import unittest
from research_wp_r0.aql_core_f5_secretary_authority_v1 import (
    SOURCE_ROLE, STRATEGY_ROLE, SOURCE_SCHEMA, STRATEGY_SCHEMA,
    pending_authority, verify_source_ack, verify_strategy_approval, canonical,
)


class TestCoreF5AuthorityNoSyntheticApproval(unittest.TestCase):
    def test_current_default_is_wait(self):
        self.assertEqual(pending_authority(), {
            "source_ack_sha256":None, "strategy_approval_sha256":None,
            "factory_consumer_ack_sha256":None, "secretary_state":"NOT_ENQUEUED",
            "historical_pit":"NOT_ATTESTED", "trading_authority":"NONE",
        })

    def test_unwitnessed_source_fails_before_any_positive(self):
        with self.assertRaisesRegex(ValueError, "EXTERNAL_SOURCE_WITNESS_MISSING"):
            verify_source_ack({},trusted_registry={},
                trusted_now_utc="2026-11-07T05:00:00Z",f2_report={},
                source_zip_sha256="a"*64,warehouse_receipt_sha256="b"*64,
                native245_sha256="c"*64,local253_sha256="d"*64,
                month="2024-01")

    def test_missing_original_f2_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError,"ACTUAL_F2_REPORT_REQUIRED"):
            verify_source_ack({},trusted_registry={},
                trusted_now_utc="2026-11-07T05:00:00Z",f2_report={},
                source_zip_sha256="a"*64,warehouse_receipt_sha256="b"*64,
                native245_sha256="c"*64,local253_sha256="d"*64,
                month="2024-01",independently_witnessed_source=True)

    def test_unverified_nomination_cannot_be_promoted(self):
        with self.assertRaisesRegex(ValueError,"AUTHENTIC_EVALUATOR_NOMINATION_REQUIRED"):
            verify_strategy_approval({},source_receipt={},
                source_ack_sha256="a"*64,strategy_nomination_sha256="b"*64,
                independent_policy_sha256="c"*64,evaluator_receipt_sha256="d"*64,
                strategy_definition_sha256="e"*64,trusted_registry={},
                trusted_now_utc="2026-11-07T05:00:00Z")

    def test_fake_source_ack_and_same_role_cannot_make_approval(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_ACK_NOT_VERIFIED"):
            verify_strategy_approval(
                {"schema":STRATEGY_SCHEMA,
                 "issuer_role":STRATEGY_ROLE,"source_ack_sha256":"a"*64},
                source_receipt={"schema":SOURCE_SCHEMA,"issuer_role":SOURCE_ROLE},
                source_ack_sha256="a"*64,
                strategy_nomination_sha256="b"*64,
                independent_policy_sha256="c"*64,
                evaluator_receipt_sha256="d"*64,
                strategy_definition_sha256="e"*64,
                trusted_registry={},trusted_now_utc="2026-11-07T05:00:00Z",
                authenticated_nomination=True,
            )

    def test_research_authority_cannot_be_operational(self):
        # Neither F2 nor a policy proposal can authorize trading.
        state=pending_authority()
        self.assertEqual(state["trading_authority"],"NONE")
        self.assertEqual(state["historical_pit"],"NOT_ATTESTED")


if __name__=="__main__":
    unittest.main()
