"""Independently signed policy authority: true Ed25519, no Scanner trust root."""
from __future__ import annotations
import copy
import json
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_e.historical_research_policy import propose_historical_research_policy
from tools.scanner_strategy_e.historical_policy_approval_request import prepare_historical_policy_approval_request
from tools.scanner_strategy_f.retrospective_policy import create_retrospective_policy_draft
from tools.scanner_strategy_f.policy_activation_request import make_historical_activation_request
from tools.scanner_strategy_f.independent_policy_verification import (
    SCHEMA, _canonical, verify_external_policy_approval
)

class ExternalPolicyApproval(unittest.TestCase):
    def setUp(self):
        self.specs=json.loads((FIXTURES/"strategies.json").read_text())
        self.proposal=propose_historical_research_policy(self.specs)
        self.request=prepare_historical_policy_approval_request(self.proposal,self.specs)
        self.draft=create_retrospective_policy_draft(
            self.proposal,self.request,self.specs)
        self.activation=make_historical_activation_request(
            self.draft,self.proposal,self.request,self.specs)
        self.private=Ed25519PrivateKey.generate()  # TEST ONLY / no signing key committed
        pub=self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        self.keyring={"external-policy-k1":{
            "public_key_hex":pub.hex(),
            "approver_identity":"separate-governance-owner",
            "authority":"INDEPENDENT_STRATEGY_POLICY_OWNER",
            "enabled":True,
        }}
        self.at="2026-11-05T13:00:00Z"
        scope=self.activation["payload"]["scope"]
        self.approval={
            "schema":SCHEMA,
            "decision":"APPROVE_RESEARCH_ONLY_RETROSPECTIVE_NON_PIT",
            "activation_request_sha256":self.activation["sha256"],
            **scope,
            "approver_identity":"separate-governance-owner",
            "approval_time_utc":"2026-11-05T12:00:00Z",
            "expires_at_utc":"2026-12-05T12:00:00Z",
            "trusted_record_reference":"governance://owner/approved-policy/1",
            "signature_scheme":"Ed25519","key_id":"external-policy-k1",
        }
        self.approval["signature"]=self.private.sign(
            _canonical(self.approval)).hex()

    def verify(self,approval=None,keyring=None,observed_at_utc=None,
               draft=None):
        return verify_external_policy_approval(
            self.approval if approval is None else approval,
            self.activation,
            self.draft if draft is None else draft,
            self.proposal,self.request,self.specs,
            trusted_keyring=self.keyring if keyring is None else keyring,
            observed_at_utc=self.at if observed_at_utc is None else observed_at_utc,
        )

    def test_valid_external_signature_still_no_source_or_secretary_authority(self):
        verified=Frozen.restore(self.verify()).data
        self.assertEqual(verified["research_scope"],"RETROSPECTIVE_NON_PIT")
        self.assertEqual(verified["source_gate"],"STILL_SEPARATELY_REQUIRED")
        self.assertFalse(verified["core_source_verified"])
        self.assertEqual(verified["secretary_state"],"NOT_ENQUEUED")
        self.assertIsNone(verified["source_ack_sha256"])
        self.assertIsNone(verified["factory_consumer_ack_sha256"])
        self.assertEqual(verified["trading_authority"],"NONE")
        self.assertEqual(self.verify(),self.verify())

    def test_missing_wrong_disabled_and_wrong_authority_key_reject(self):
        for keyring in (
            {}, {"external-policy-k1":{**self.keyring["external-policy-k1"],
                                       "enabled":False}},
            {"external-policy-k1":{**self.keyring["external-policy-k1"],
                                       "authority":"SCANNER_SELF"}},
            {"external-policy-k1":{**self.keyring["external-policy-k1"],
                                       "approver_identity":"other-owner"}},
        ):
            with self.subTest(keyring=keyring),self.assertRaises(ValueError):
                self.verify(keyring=keyring)
        wrong=Ed25519PrivateKey.generate()
        raw=wrong.public_key().public_bytes(serialization.Encoding.Raw,
                                            serialization.PublicFormat.Raw)
        changed=copy.deepcopy(self.keyring)
        changed["external-policy-k1"]["public_key_hex"]=raw.hex()
        with self.assertRaises(ValueError):
            self.verify(keyring=changed)

    def test_resealed_scope_widening_and_forged_signature_reject(self):
        for name,value in (
            ("decision","APPROVE_LIVE"),
            ("approved_months",["2024-01"]),
            ("approved_symbol","ETHUSDT"),
            ("approved_timeframe","1m"),
            ("policy_draft_sha256","f"*64),
            ("activation_request_sha256","e"*64),
            ("strategy_identity_digest","d"*64),
            ("cutoff_rule","INCLUDE_FUTURE"),
            ("historical_pit","ATTESTED"),
            ("trading_authority","LIVE"),
            ("signature","f"*128),
        ):
            with self.subTest(name=name):
                bad=copy.deepcopy(self.approval)
                bad[name]=value
                with self.assertRaises(ValueError):
                    self.verify(approval=bad)
        changed=copy.deepcopy(self.approval)
        changed["trusted_record_reference"]="governance://fake/external/99"
        with self.assertRaises(ValueError):
            self.verify(approval=changed)

    def test_replay_expiry_future_approval_and_untrusted_user_time_reject(self):
        for now in ("2026-11-05T11:59:59Z",
                    "2026-12-05T12:00:00Z",
                    "2027-01-01T00:00:00Z"):
            with self.subTest(now=now),self.assertRaises(ValueError):
                self.verify(observed_at_utc=now)
        # Time MUST be supplied by the invoking trusted runner, not the
        # approval issuer itself; no hidden time provider or signature bypass.
        with self.assertRaises(ValueError):
            self.verify(observed_at_utc="2026-11-05T13:00:00+03:00")
        with self.assertRaises(ValueError):
            self.verify(observed_at_utc="NOT_TIME")

if __name__=="__main__":
    unittest.main()
