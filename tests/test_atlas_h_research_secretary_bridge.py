"""Package H bridge: cross-owner negative contracts; no original data."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from tools.atlas_h_research_secretary_bridge import (
    HBridgeError, deliver_research_review_wait,
)
from research_wp_r0.aql_factory_e_research_results_store_v1 import digest


def seal(body, field="sha256"):
    return {**body, field: digest(body)}


def fixture():
    packet=seal({
        "schema":"aql.factory.f.f2-recovery-research-input.v2",
        "experiment_id":"DIAG-H-BRIDGE-1","config_sha256":"a"*64,
        "code_sha256":"b"*64,"strategy_definitions":{},
        "operator_policy":{},"trading_authority":"NONE",
    })
    factory=seal({
        "schema":"aql.factory.f.f2-recovery-research-report.v2",
        "experiment_id":packet["experiment_id"],"input_sha256":packet["sha256"],
        "experiment_sha256":"c"*64,"result_sha256":"d"*64,
        "lab_sha256":"e"*64,"trading_authority":"NONE",
    },"receipt_sha256")
    ledger=seal({
        "strategy_digest":"f"*64,"policy_sha256":"1"*64,
        "trading_authority":"NONE",
    })
    lab=seal({
        "ledger_sha256":ledger["sha256"],
        "strategy_digest":ledger["strategy_digest"],
        "policy_sha256":ledger["policy_sha256"],
        "uncertainty":{"economic_claim":"NOT_ATTESTED"},
        "trading_authority":"NONE",
    })
    proposal=seal({
        "experiment_sha256":factory["experiment_sha256"],
        "result_sha256":factory["result_sha256"],
        "lab_sha256":lab["sha256"],
        "policy_sha256":lab["policy_sha256"],
        "strategy_definition_sha256":lab["strategy_digest"],
        "code_sha256":packet["code_sha256"],
        "config_sha256":packet["config_sha256"],
        "state":"RESEARCH_RESULT_READY_FOR_REVIEW_NOT_ACK",
        "source_ack_sha256":None,"strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,"trading_authority":"NONE",
    })
    package=seal({
        "schema":"aql.factory.h.research-package.v1",
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "factory_experiment_sha256":factory["experiment_sha256"],
        "factory_result_sha256":factory["result_sha256"],
        "scientific_lab":lab,"trade_event_ledger":ledger,
        "secretary_research_receipt":proposal,
        "holdout":"SEALED_UNOPENED","trading_authority":"NONE",
    })
    result=seal({
        "schema":"aql.factory.h.research-package-result.v1",
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "package_sha256":package["sha256"],
        "scientific_lab_sha256":lab["sha256"],
        "trade_ledger_sha256":ledger["sha256"],
        "secretary_receipt_sha256":proposal["sha256"],
        "paper":"NOT_ACTIVATED","f5":"BLOCKED_EXTERNAL_INPUT",
        "trading_authority":"NONE",
    },"receipt_sha256")
    return packet,factory,package,result


class HBridgeTests(unittest.TestCase):
    def invoke(self, parts):
        p,f,h,r=parts
        route={
            "state":"WAIT_RESEARCH_REVIEW",
            "receipt_sha256":"9"*64,
            "lab_evaluation_sha256":h["scientific_lab"]["sha256"],
            "strategy_approval_sha256":None,"source_ack_sha256":None,
            "factory_consumer_ack_sha256":None,"trading_authority":"NONE",
        }
        with patch("tools.atlas_h_research_secretary_bridge.route_research_result",
                   return_value=route) as writer, patch(
                "tools.atlas_h_research_secretary_bridge.read_research_result_route",
                return_value=route):
            result=deliver_research_review_wait(
                secretary_root="unused-synthetic",packet=p,factory_report=f,
                factory_h_package=h,factory_h_result=r)
        return result,writer

    def test_research_wait_success_without_approval(self):
        result,writer=self.invoke(fixture())
        self.assertEqual(result["status"],"WAIT_RESEARCH_REVIEW")
        self.assertEqual(result["trading_authority"],"NONE")
        self.assertEqual(result["economic_status"],"ECONOMIC_NOT_ATTESTED")
        self.assertEqual(writer.call_count,1)

    def test_tampered_lab_seal_refused_before_write(self):
        p,f,h,r=fixture()
        h["scientific_lab"]["uncertainty"]["economic_claim"]="ATTESTED"
        with self.assertRaisesRegex(HBridgeError,"PARENT_SEAL"):
            self.invoke((p,f,h,r))

    def test_forged_approval_refused_before_write(self):
        p,f,h,r=fixture()
        h["secretary_research_receipt"]["strategy_approval_sha256"]="a"*64
        h["secretary_research_receipt"]=seal({
            k:v for k,v in h["secretary_research_receipt"].items()
            if k!="sha256"})
        h=seal({k:v for k,v in h.items() if k!="sha256"})
        r=seal({**{k:v for k,v in r.items() if k!="receipt_sha256"},
                "package_sha256":h["sha256"]},"receipt_sha256")
        with self.assertRaisesRegex(HBridgeError,"AUTHORITY_OR_ECONOMIC_PROMOTION"):
            self.invoke((p,f,h,r))

    def test_result_parent_swap_refused(self):
        p,f,h,r=fixture()
        r=seal({**{k:v for k,v in r.items() if k!="receipt_sha256"},
                "scientific_lab_sha256":"0"*64},"receipt_sha256")
        with self.assertRaisesRegex(HBridgeError,"CROSS_PARENT_DRIFT"):
            self.invoke((p,f,h,r))


if __name__=="__main__":
    unittest.main()
