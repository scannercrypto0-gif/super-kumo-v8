"""F3 owner-private original-query operator bundle fail-closed tests.

All input SHA and keys in this module are TEST FIXTURES; do not claim that
real owner-private E: data was accessed or policy signer was authorized.
"""
from __future__ import annotations
import copy
import unittest

from tools.strategy_service_offline.common import Frozen
from tools.scanner_strategy_f.policy_activation_request import (
    make_historical_activation_request,
)
from tools.scanner_strategy_f.private_operator_bundle import (
    prepare_original_evaluator_operator_bundle,
    verify_original_evaluator_operator_bundle,
    verify_real_evaluator_operator_envelope,
)
from tools.scanner_strategy_f.test_independent_evaluator_nomination import (
    F3ExternalEvaluatorNomination,
)


class F3OperatorInputBundle(F3ExternalEvaluatorNomination):
    def setup_bundle(self):
        activation=make_historical_activation_request(
            self.policy,self.e,self.er,self.specs)
        decision_payload=copy.deepcopy(self.decision["payload"])
        decision_payload["source_zip_sha256"]=self.record["original_source_sha256"]
        full_decision=Frozen.build(decision_payload).receipt()
        kwargs=dict(
            source_bound_census=self.census,
            strategy_decision=full_decision,
            activation_request=activation,
            policy_draft=self.policy,
            original_e_proposal=self.e,
            original_e_request=self.er,
            work_specs=self.specs,
        )
        return kwargs

    def test_deterministic_exact_owner_bundle(self):
        kw=self.setup_bundle()
        b=prepare_original_evaluator_operator_bundle(**kw)
        self.assertEqual(b,prepare_original_evaluator_operator_bundle(**kw))
        d=verify_original_evaluator_operator_bundle(b,**kw).data
        self.assertEqual(d["strategy_id"],"test_momentum")
        self.assertEqual(d["symbol"],"BTCUSDT")
        self.assertEqual(d["attempt_count"],24)
        self.assertEqual(d["admitted_attempts"],20)
        self.assertEqual(d["feb_aug_unknown_attempts"],4)
        self.assertIs(d["selected"],False)
        self.assertIsNone(d["core_source_ack_sha256"])
        self.assertIsNone(d["core_secretary_strategy_approval_sha256"])
        self.assertIsNone(d["factory_consumer_ack_sha256"])
        self.assertEqual(d["source_issuer"],"CORE_SOURCE_CUSTODIAN")
        self.assertEqual(d["policy_issuer"],"INDEPENDENT_STRATEGY_POLICY_OWNER")
        self.assertEqual(d["evaluator_issuer"],"INDEPENDENT_EVALUATOR")
        self.assertEqual(d["trading_authority"],"NONE")

    def test_resigned_authority_and_strategy_drift_rejected(self):
        kw=self.setup_bundle()
        b=prepare_original_evaluator_operator_bundle(**kw)
        for key,value in (
            ("selected",True),
            ("strategy_id","test_reversion"),
            ("month","2024-02"),
            ("core_source_ack_sha256","f"*64),
            ("core_secretary_strategy_approval_sha256","e"*64),
            ("factory_consumer_ack_sha256","d"*64),
            ("trusted_external_registry","ALREADY_TRUSTED"),
            ("evaluator_code_execution_proof","VERIFIED"),
            ("research_scope","PIT"),
            ("trading_authority","LIVE"),
        ):
            with self.subTest(key=key),self.assertRaises(ValueError):
                forged=copy.deepcopy(b["payload"])
                forged[key]=value
                verify_original_evaluator_operator_bundle(
                    Frozen.build(forged).receipt(),**kw)

    def test_fake_evidence_envelope_cannot_claim_external_private_run(self):
        kw=self.setup_bundle()
        b=prepare_original_evaluator_operator_bundle(**kw)
        fake={
            "schema":"aql.scanner-f.original-private-evaluation-evidence.v1",
            "bundle_sha256":b["sha256"],
            "source_bound_census_sha256":self.census["sha256"],
            "strategy_decision_sha256":self.decision["sha256"],
            "policy_approval_verified_sha256":"1"*64,
            "evaluator_verified_sha256":"2"*64,
            "nomination_sha256":"3"*64,
            "independent_source_witness_sha256":"4"*64,
            "original_query_execution_witness_sha256":"5"*64,
            "evaluator_execution_witness_sha256":"6"*64,
            "result_class":"NOMINATED_RESEARCH_ONLY",
            "historical_pit":"NOT_ATTESTED",
            "trading_authority":"NONE",
            "source_ack_sha256":None,
            "strategy_approval_sha256":None,
            "factory_consumer_ack_sha256":None,
        }
        args=dict(
            envelope=fake,bundle=b,
            source_bound_census=self.census,
            strategy_decision=self.decision,
            activation_request=kw["activation_request"],
            policy_draft=self.policy,
            original_e_proposal=self.e,original_e_request=self.er,
            work_specs=self.specs,
            signed_policy_approval=self.approval,
            trusted_policy_keyring=self.keys,
            signed_evaluator_receipt=self.receipt,
            trusted_evaluator_keyring=self.evaluator_keys,
            observed_at_utc="2026-11-07T09:00:00Z",
        )
        with self.assertRaises(ValueError):
            verify_real_evaluator_operator_envelope(**args)
        args["envelope"]=copy.deepcopy(fake)
        args["envelope"]["policy_approval_verified_sha256"]="f"*64
        with self.assertRaises(ValueError):
            verify_real_evaluator_operator_envelope(**args)

    def test_unknown_retained_source_not_validated_as_selected(self):
        kw=self.setup_bundle()
        b=prepare_original_evaluator_operator_bundle(**kw)
        x=copy.deepcopy(kw["strategy_decision"]["payload"])
        x["month"]="2024-02"
        kw["strategy_decision"]=Frozen.build(x).receipt()
        with self.assertRaises(ValueError):
            prepare_original_evaluator_operator_bundle(**kw)


if __name__=="__main__":
    unittest.main()
